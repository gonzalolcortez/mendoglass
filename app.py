from flask import Flask, jsonify, g, request, has_request_context
from extensions import db, login_manager
import os
import time
from sqlalchemy import inspect, text, event
from sqlalchemy.exc import SQLAlchemyError


def _load_local_instance_env(app):
    """Load local-only environment vars from instance/local.env if present.

    This file is intended for developer machines and is ignored by git.
    Existing environment variables are never overridden.
    """
    local_env_path = os.path.join(app.instance_path, 'local.env')
    if not os.path.exists(local_env_path):
        return

    try:
        with open(local_env_path, 'r', encoding='utf-8') as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                if key:
                    os.environ.setdefault(key, value)
    except OSError as exc:
        app.logger.warning('Could not read local env file %s: %s', local_env_path, exc)


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


def _ensure_tecnicos_columns(app):
    """Ensure legacy DBs have the columns required by the current Personal model."""
    required_columns = {
        'apellido': "VARCHAR(150) NOT NULL DEFAULT ''",
        'dni_cuit': 'VARCHAR(30)',
        'direccion': 'VARCHAR(200)',
        'celular': 'VARCHAR(30)',
        'actividades': "TEXT DEFAULT ''",
    }

    inspector = inspect(db.engine)
    if not inspector.has_table('tecnicos'):
        return

    existing_columns = {c['name'] for c in inspector.get_columns('tecnicos')}
    missing_columns = [
        (name, ddl)
        for name, ddl in required_columns.items()
        if name not in existing_columns
    ]

    if not missing_columns:
        return

    with db.engine.begin() as conn:
        for column_name, column_ddl in missing_columns:
            conn.execute(text(f'ALTER TABLE tecnicos ADD COLUMN {column_name} {column_ddl}'))

    app.logger.warning(
        'Schema patched on startup: added missing tecnicos columns: %s',
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


def _ensure_productos_servicios_columns(app):
    """Ensure productos and servicios tables have alicuota_iva column."""
    required_by_table = {
        'productos': {
            'alicuota_iva': 'DOUBLE PRECISION NOT NULL DEFAULT 21',
        },
        'servicios': {
            'alicuota_iva': 'DOUBLE PRECISION NOT NULL DEFAULT 21',
        },
    }

    inspector = inspect(db.engine)
    for table_name, columns in required_by_table.items():
        if not inspector.has_table(table_name):
            continue

        existing_columns = {c['name'] for c in inspector.get_columns(table_name)}
        missing_columns = [
            (name, ddl)
            for name, ddl in columns.items()
            if name not in existing_columns
        ]
        if not missing_columns:
            continue

        with db.engine.begin() as conn:
            for column_name, column_ddl in missing_columns:
                conn.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_ddl}'))

        app.logger.warning(
            'Schema patched on startup: added missing %s columns: %s',
            table_name,
            ', '.join(name for name, _ in missing_columns),
        )


def _ensure_cuenta_corriente_indexes(app):
    """Ensure indexes exist for the heaviest current-account queries."""
    statements = [
        'CREATE INDEX IF NOT EXISTS ix_clientes_cc_cliente_fecha ON clientes_cuenta_corriente (cliente_id, fecha)',
        'CREATE INDEX IF NOT EXISTS ix_proveedores_cc_proveedor_fecha ON proveedores_cuenta_corriente (proveedor_id, fecha)',
        'CREATE INDEX IF NOT EXISTS ix_tecnicos_cc_tecnico_fecha ON tecnicos_cuenta_corriente (tecnico_id, fecha)',
    ]

    with db.engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))

    app.logger.info('Verified current-account indexes for customer and supplier movement tables.')


def _ensure_cuenta_corriente_columns(app):
    required_by_table = {
        'clientes_cuenta_corriente': {
            'cuenta': "VARCHAR(50) DEFAULT 'otro'",
        },
        'proveedores_cuenta_corriente': {
            'cuenta': "VARCHAR(50) DEFAULT 'otro'",
        },
    }

    inspector = inspect(db.engine)
    for table_name, columns in required_by_table.items():
        if not inspector.has_table(table_name):
            continue

        existing_columns = {c['name'] for c in inspector.get_columns(table_name)}
        missing_columns = [
            (name, ddl)
            for name, ddl in columns.items()
            if name not in existing_columns
        ]
        if not missing_columns:
            continue

        with db.engine.begin() as conn:
            for column_name, column_ddl in missing_columns:
                conn.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_ddl}'))

        app.logger.warning(
            'Schema patched on startup: added missing %s columns: %s',
            table_name,
            ', '.join(name for name, _ in missing_columns),
        )


def _install_request_metrics(app):
    """Install optional per-request performance metrics for profiling."""
    if not app.config.get('PERF_REQUEST_METRICS', False):
        return

    monitored_prefixes = ('/taller', '/stock', '/ventas', '/clientes', '/caja', '/contabilidad')

    @app.before_request
    def _perf_before_request():
        g.perf_start = time.perf_counter()
        g.perf_sql_queries = 0
        g.perf_sql_time_ms = 0.0

    @app.after_request
    def _perf_after_request(response):
        if not hasattr(g, 'perf_start'):
            return response

        elapsed_ms = (time.perf_counter() - g.perf_start) * 1000
        sql_queries = getattr(g, 'perf_sql_queries', 0)
        sql_time_ms = getattr(g, 'perf_sql_time_ms', 0.0)

        response.headers['X-Perf-Time-Ms'] = f'{elapsed_ms:.2f}'
        response.headers['X-Perf-Sql-Queries'] = str(sql_queries)
        response.headers['X-Perf-Sql-Time-Ms'] = f'{sql_time_ms:.2f}'

        if request.path == '/' or request.path.startswith(monitored_prefixes):
            app.logger.info(
                '[PERF] %s %s -> status=%s total_ms=%.2f sql_queries=%s sql_ms=%.2f',
                request.method,
                request.path,
                response.status_code,
                elapsed_ms,
                sql_queries,
                sql_time_ms,
            )
        return response

    if app.extensions.get('perf_sql_events_installed'):
        return

    @event.listens_for(db.engine, 'before_cursor_execute')
    def _perf_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        context._query_start_time = time.perf_counter()

    @event.listens_for(db.engine, 'after_cursor_execute')
    def _perf_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if has_request_context() and hasattr(g, 'perf_sql_queries'):
            g.perf_sql_queries += 1
            start = getattr(context, '_query_start_time', None)
            if start is not None:
                g.perf_sql_time_ms += (time.perf_counter() - start) * 1000

    app.extensions['perf_sql_events_installed'] = True

def create_app():
    app = Flask(__name__)
    _load_local_instance_env(app)
    _configure_timezone(app)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    database_url = os.environ.get('DATABASE_URL', 'sqlite:///sistema.db')
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['PERF_REQUEST_METRICS'] = os.environ.get('PERF_REQUEST_METRICS', 'false').lower() == 'true'

    db.init_app(app)
    login_manager.init_app(app)

    from models import Usuario, sincronizar_movimientos_contables_automaticos

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

    with app.app_context():
        try:
            _init_db_with_retry(app, retries=5, delay=3)
        except Exception as e:
            app.logger.error('Database init skipped during startup: %s', e)

        _install_request_metrics(app)

        try:
            _ensure_ventas_columns(app)
            _ensure_clientes_columns(app)
            _ensure_tecnicos_columns(app)
            _ensure_venta_items_columns(app)
            _ensure_cuenta_corriente_columns(app)
            _ensure_cuenta_corriente_indexes(app)
            _ensure_productos_servicios_columns(app)
            skip_sync = os.environ.get('SKIP_STARTUP_CONTABLE_SYNC', 'false').lower() == 'true'
            if skip_sync:
                app.logger.info('Skipping startup accounting sync (SKIP_STARTUP_CONTABLE_SYNC=true).')
            else:
                sincronizar_movimientos_contables_automaticos()
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
    if not Usuario.query.filter_by(username='Administrador').first():
        u = Usuario(username='Administrador', nombre='Administrador')
        u.set_password('010203')
        db.session.add(u)
    db.session.commit()


app = create_app()

if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    port = int(os.environ.get('PORT', 10000))
    app.run(debug=debug, host='0.0.0.0', port=port)