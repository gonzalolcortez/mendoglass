from flask import Flask
from extensions import db, login_manager
import os

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL', 'sqlite:///sistema.db'
    )
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
        db.create_all()
        _seed_default_user()

    return app


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
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=debug, host='0.0.0.0', port=port)
