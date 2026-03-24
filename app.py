from flask import Flask, jsonify
from extensions import db, login_manager
import os
import time
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError


def _configure_timezone(app):
    """Configure process timezone, defaulting to Argentina (-03:00)."""
    tz_name = os.environ.setdefault('TZ', 'America/Argentina/Buenos_Aires')
    app.config['APP_TIMEZONE'] = tz_name

    # tzset is available on Unix platforms (Render/Linux).
    try:
        time.tzset()
    except AttributeError:
        app.logger.warning('tzset is not available on this platform; TZ=%s', tz_name)
def _ensure_ventas_columns(app):
    """Ensure legacy DBs have the columns required by the current Venta model."""
    dialect = db.engine.dialect.name
    bool_true = 'TRUE' if dialect == 'postgresql' else '1'

    required_columns = {
        'tipo_comprobante': "VARCHAR(20) NOT NULL DEFAULT 'NOTA_VENTA'",
        'punto_venta': 'INTEGER NOT NULL DEFAULT 1',
        'numero_comprobante': 'INTEGER',
        'subtotal': 'DOUBLE PRECISION NOT NULL DEFAULT 0',
        'iva_total': 'DOUBLE PRECISION NOT NULL DEFAULT 0',
        'descuento': 'DOUBLE PRECISION NOT NULL DEFAULT 0',
        'total': 'DOUBLE PRECISION NOT NULL DEFAULT 0',
        'pagado': f'BOOLEAN NOT NULL DEFAULT {bool_true}',
        'forma_pago': "VARCHAR(50) DEFAULT 'efectivo'",
        'tipo_cbte_afip': 'INTEGER',
        'cae': 'VARCHAR(20)',
        'fecha_vencimiento_cae': 'DATE',
        'notas': 'TEXT',
        'created_at': 'TIMESTAMP',
    }

    inspector = inspect(db.engine)
    if not inspector.has_table('ventas'):
        return

    existing_columns = {c['name'] for c in inspector.get_columns('ventas')}
    missing_columns = [
        (name, ddl)
        for name, ddl in required_columns.items()
        if name not in existing_columns
    ]

    if not missing_columns:
        return

    with db.engine.begin() as conn:
        for column_name, column_ddl in missing_columns:
            conn.execute(text(f'ALTER TABLE ventas ADD COLUMN {column_name} {column_ddl}'))

    app.logger.warning(
        'Schema patched on startup: added missing ventas columns: %s',
        ', '.join(name for name, _ in missing_columns),
    )


def _ensure_clientes_columns(app):
    """Ensure legacy DBs have the columns required by the current Cliente model."""
    required_columns = {
        'cuit': 'VARCHAR(20)',
        'condicion_iva': "VARCHAR(10) DEFAULT 'CF'",
        'notas': 'TEXT',
        'created_at': 'TIMESTAMP',
    }

    inspector = inspect(db.engine)
    if not inspector.has_table('clientes'):
        return

    existing_columns = {c['name'] for c in inspector.get_columns('clientes')}
    missing_columns = [
        (name, ddl)
        for name, ddl in required_columns.items()
        if name not in existing_columns
    ]

    if not missing_columns:
        return

    with db.engine.begin() as conn:
        for column_name, column_ddl in missing_columns:
            conn.execute(text(f'ALTER TABLE clientes ADD COLUMN {column_name} {column_ddl}'))

    app.logger.warning(
        'Schema patched on startup: added missing clientes columns: %s',
        ', '.join(name for name, _ in missing_columns),
    )


def _ensure_venta_items_columns(app):
    """Ensure legacy DBs have the columns required by the current VentaItem model."""
    required_columns = {
        'tipo': "VARCHAR(10) NOT NULL DEFAULT 'producto'",
        'servicio_id': 'INTEGER',
        'codigo': 'VARCHAR(50)',
        'descripcion_libre': 'VARCHAR(300)',
        'unidad': "VARCHAR(20) NOT NULL DEFAULT 'unidad'",
        'bonificacion': 'DOUBLE PRECISION NOT NULL DEFAULT 0',
        'alicuota_iva': 'DOUBLE PRECISION NOT NULL DEFAULT 21',
        'subtotal_neto': 'DOUBLE PRECISION NOT NULL DEFAULT 0',
    }

    inspector = inspect(db.engine)
    if not inspector.has_table('venta_items'):
        return

    existing_columns = {c['name'] for c in inspector.get_columns('venta_items')}
    missing_columns = [
        (name, ddl)
        for name, ddl in required_columns.items()
        if name not in existing_columns
    ]

    if not missing_columns:
        return

    with db.engine.begin() as conn:
        for column_name, column_ddl in missing_columns:
            conn.execute(text(f'ALTER TABLE venta_items ADD COLUMN {column_name} {column_ddl}'))

    app.logger.warning(
        'Schema patched on startup: added missing venta_items columns: %s',
        ', '.join(name for name, _ in missing_columns),
    )

def create_app():
    app = Flask(__name__)
    _configure_timezone(app)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    database_url = os.environ.get('DATABASE_URL', 'sqlite:///sistema.db')
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    login_manager.init_app(app)

    from models import Usuario

    @login_manager.user_loader
    def load_user(user_id):
        return Usuario.query.get(int(user_id))

    from routes.auth import auth_bp
    from routes.clientes import clientes_bp
    from routes.productos import productos_bp
    from routes.stock import stock_bp
    from routes.taller import taller_bp
    from routes.caja import caja_bp
    from routes.contabilidad import contabilidad_bp
    from routes.ventas import ventas_bp
    from routes.dashboard import dashboard_bp
    from routes.tecnicos import tecnicos_bp
    from routes.whatsapp import whatsapp_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(clientes_bp, url_prefix='/clientes')
    app.register_blueprint(productos_bp, url_prefix='/productos')
    app.register_blueprint(stock_bp, url_prefix='/stock')
    app.register_blueprint(taller_bp, url_prefix='/taller')
    app.register_blueprint(caja_bp, url_prefix='/caja')
    app.register_blueprint(contabilidad_bp, url_prefix='/contabilidad')
    app.register_blueprint(ventas_bp, url_prefix='/ventas')
    app.register_blueprint(tecnicos_bp, url_prefix='/tecnicos')
    app.register_blueprint(whatsapp_bp)

    with app.app_context():
        try:
            _init_db_with_retry(app, retries=5, delay=3)
        except Exception as e:
            app.logger.error('Database init skipped during startup: %s', e)

        try:
            _ensure_ventas_columns(app)
            _ensure_clientes_columns(app)
            _ensure_venta_items_columns(app)
        except SQLAlchemyError as e:
            app.logger.error('Could not apply runtime schema patch: %s', e)

    @app.route('/health')
    def health():
        return jsonify({"status": "ok"}), 200
    return app


# 👇 dejamos esto para usar manualmente si querés inicializar la DB
def _init_db_with_retry(app, retries=5, delay=3):
    from sqlalchemy.exc import OperationalError, DatabaseError
    import time

    for attempt in range(1, retries + 1):
        try:
            db.create_all()
            _seed_default_user()
            return
        except (OperationalError, DatabaseError) as e:
            if attempt == retries:
                app.logger.error(f"Database initialization failed after {retries} attempts: {e}")
                raise
            app.logger.warning(f"Database not ready (attempt {attempt}/{retries}): {e}. Retrying in {delay}s...")
            time.sleep(delay)

def _seed_default_user():
    from models import Usuario
    if not Usuario.query.filter_by(username='Gonzalo').first():
        u = Usuario(username='Gonzalo', nombre='Gonzalo')
        u.set_password('1234')
        db.session.add(u)
    if not Usuario.query.filter_by(username='Administrador').first():
        u = Usuario(username='Administrador', nombre='Administrador')
        u.set_password('010203')
        db.session.add(u)
    if not Usuario.query.filter_by(username='Matias').first():
        u = Usuario(username='Matias', nombre='Matias')
        u.set_password('Joel')
        db.session.add(u)
    db.session.commit()


app = create_app()

if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    port = int(os.environ.get('PORT', 10000))
    app.run(debug=debug, host='0.0.0.0', port=port)