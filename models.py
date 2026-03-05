from extensions import db
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    nombre = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    activo = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.activo


class Tecnico(db.Model):
    __tablename__ = 'tecnicos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    es_tercerizado = db.Column(db.Boolean, default=False)
    empresa_tercerizado = db.Column(db.String(150))
    activo = db.Column(db.Boolean, default=True)

    @property
    def nombre_display(self):
        if self.es_tercerizado and self.empresa_tercerizado:
            return f"Técnico Tercerizado - {self.empresa_tercerizado}"
        return self.nombre


class Cliente(db.Model):
    __tablename__ = 'clientes'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(30))
    email = db.Column(db.String(120))
    direccion = db.Column(db.String(200))
    notas = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    talleres = db.relationship('Taller', backref='cliente', lazy=True)
    ventas = db.relationship('Venta', backref='cliente', lazy=True)

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"


class Categoria(db.Model):
    __tablename__ = 'categorias'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)

    productos = db.relationship('Producto', backref='categoria', lazy=True)


class Producto(db.Model):
    __tablename__ = 'productos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text)
    codigo_barras = db.Column(db.String(50))
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias.id'))
    precio_compra = db.Column(db.Float, default=0.0)
    precio_venta = db.Column(db.Float, nullable=False)
    stock_actual = db.Column(db.Integer, default=0)
    stock_minimo = db.Column(db.Integer, default=5)
    unidad = db.Column(db.String(20), default='unidad')
    activo = db.Column(db.Boolean, default=True)

    taller_productos = db.relationship('TallerProducto', backref='producto', lazy=True)
    venta_items = db.relationship('VentaItem', backref='producto', lazy=True)

    @property
    def stock_bajo(self):
        return self.stock_actual <= self.stock_minimo


class Servicio(db.Model):
    __tablename__ = 'servicios'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text)
    precio = db.Column(db.Float, nullable=False)
    activo = db.Column(db.Boolean, default=True)

    taller_servicios = db.relationship('TallerServicio', backref='servicio', lazy=True)
    venta_items = db.relationship('VentaItem', backref='servicio', lazy=True)


class Taller(db.Model):
    __tablename__ = 'taller'
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.Integer, unique=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    tipo_equipo = db.Column(db.String(100))
    marca = db.Column(db.String(100))
    modelo = db.Column(db.String(100))
    descripcion_problema = db.Column(db.Text, nullable=False)
    observaciones = db.Column(db.Text)
    estado = db.Column(db.String(30), default='recibido')
    costo_estimado = db.Column(db.Float, default=0.0)
    costo_reparacion = db.Column(db.Float, default=0.0)
    fecha_ingreso = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_estimada_entrega = db.Column(db.DateTime)
    fecha_entrega = db.Column(db.DateTime)
    tecnico = db.Column(db.String(100))
    pagado = db.Column(db.Boolean, default=False)
    forma_pago = db.Column(db.String(50), default='efectivo')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    productos_usados = db.relationship('TallerProducto', backref='taller', lazy=True, cascade='all, delete-orphan')
    servicios_usados = db.relationship('TallerServicio', backref='taller', lazy=True, cascade='all, delete-orphan')

    ESTADOS = [
        ('recibido', 'Recibido'),
        ('diagnostico', 'En Diagnóstico'),
        ('en_reparacion', 'En Reparación'),
        ('sin_solucion', 'Sin Solución'),
        ('listo', 'Listo'),
        ('entregado', 'Entregado'),
        ('cancelado', 'Cancelado'),
    ]

    @property
    def estado_display(self):
        return dict(self.ESTADOS).get(self.estado, self.estado)

    @property
    def total_productos(self):
        return sum(p.cantidad * p.precio_unitario for p in self.productos_usados)

    @property
    def total_servicios(self):
        return sum(s.precio for s in self.servicios_usados)

    @property
    def total_final(self):
        if self.costo_reparacion and self.costo_reparacion > 0:
            return self.costo_reparacion
        return self.total_productos + self.total_servicios


class TallerProducto(db.Model):
    __tablename__ = 'taller_productos'
    id = db.Column(db.Integer, primary_key=True)
    taller_id = db.Column(db.Integer, db.ForeignKey('taller.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    cantidad = db.Column(db.Integer, default=1)
    precio_unitario = db.Column(db.Float, nullable=False)


class TallerServicio(db.Model):
    __tablename__ = 'taller_servicios'
    id = db.Column(db.Integer, primary_key=True)
    taller_id = db.Column(db.Integer, db.ForeignKey('taller.id'), nullable=False)
    servicio_id = db.Column(db.Integer, db.ForeignKey('servicios.id'), nullable=False)
    precio = db.Column(db.Float, nullable=False)


class Venta(db.Model):
    __tablename__ = 'ventas'
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    subtotal = db.Column(db.Float, default=0.0)
    descuento = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    pagado = db.Column(db.Boolean, default=True)
    forma_pago = db.Column(db.String(50), default='efectivo')
    notas = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('VentaItem', backref='venta', lazy=True, cascade='all, delete-orphan')


class VentaItem(db.Model):
    __tablename__ = 'venta_items'
    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # producto / servicio
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    servicio_id = db.Column(db.Integer, db.ForeignKey('servicios.id'), nullable=True)
    cantidad = db.Column(db.Integer, default=1)
    precio_unitario = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)


class MovimientoCaja(db.Model):
    __tablename__ = 'movimientos_caja'
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(10), nullable=False)  # ingreso / egreso
    cuenta = db.Column(db.String(50), default='otro')
    forma_pago = db.Column(db.String(50), default='efectivo')
    concepto = db.Column(db.String(200), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    referencia_tipo = db.Column(db.String(20))  # taller / venta / ajuste / otro
    referencia_id = db.Column(db.Integer)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    notas = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# Cuentas disponibles para movimientos de caja
CUENTAS_CAJA = [
    ('venta_productos', 'Venta de Productos'),
    ('venta_repuestos', 'Venta de Repuestos'),
    ('servicio_tecnico', 'Servicio Técnico'),
    ('impuestos', 'Impuestos'),
    ('alquiler', 'Alquiler'),
    ('matias', 'Matias'),
    ('compra_mercaderia', 'Compra de Mercadería'),
    ('compra_repuestos', 'Compra de Repuestos'),
    ('otro', 'Otro'),
]

# Formas de pago
FORMAS_PAGO = [
    ('efectivo', 'Efectivo'),
    ('mercado_pago', 'Mercado Pago'),
    ('tarjeta', 'Tarjetas'),
    ('cuenta_corriente', 'Cuenta Corriente Gonzalo'),
]
