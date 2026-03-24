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
    cuit = db.Column(db.String(20))
    # CF=Consumidor Final, RI=Responsable Inscripto, M=Monotributista, EX=Exento
    condicion_iva = db.Column(db.String(10), default='CF')
    notas = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    talleres = db.relationship('Taller', backref='cliente', lazy=True)
    ventas = db.relationship('Venta', backref='cliente', lazy=True)

    CONDICIONES_IVA = [
        ('CF', 'Consumidor Final'),
        ('RI', 'Responsable Inscripto'),
        ('M',  'Monotributista'),
        ('EX', 'Exento'),
    ]

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"


class Proveedor(db.Model):
    __tablename__ = 'proveedores'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(30))
    email = db.Column(db.String(120))
    direccion = db.Column(db.String(200))
    notas = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ingresos = db.relationship('IngresoMercaderia', backref='proveedor', lazy=True)

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
    ingreso_items = db.relationship('IngresoMercaderiaItem', backref='producto', lazy=True)

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
    def total_egreso_repuestos(self):
        # Egreso real por costo de compra de los repuestos utilizados en la orden.
        return sum((p.cantidad or 0) * ((p.producto.precio_compra or 0) if p.producto else 0) for p in self.productos_usados)

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
    # FACTURA / NOTA_VENTA
    tipo_comprobante = db.Column(db.String(20), default='NOTA_VENTA', nullable=False)
    punto_venta = db.Column(db.Integer, default=1)
    numero_comprobante = db.Column(db.Integer)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    subtotal = db.Column(db.Float, default=0.0)   # importe neto gravado
    iva_total = db.Column(db.Float, default=0.0)  # IVA total
    descuento = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    pagado = db.Column(db.Boolean, default=True)
    forma_pago = db.Column(db.String(50), default='efectivo')
    # AFIP fields (only for FACTURA)
    tipo_cbte_afip = db.Column(db.Integer)        # 1=FA, 6=FB, 11=FC
    cae = db.Column(db.String(20))
    fecha_vencimiento_cae = db.Column(db.Date)
    notas = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('VentaItem', backref='venta', lazy=True, cascade='all, delete-orphan')

    TIPOS_COMPROBANTE = [
        ('NOTA_VENTA', 'Nota de Venta'),
        ('FACTURA',    'Factura Electrónica'),
    ]

    @property
    def numero_display(self):
        pv = self.punto_venta or 1
        nro = self.numero_comprobante
        if nro:
            return f'{pv:04d}-{nro:08d}'
        return f'#{self.id}'

    @property
    def tipo_display(self):
        return dict(self.TIPOS_COMPROBANTE).get(self.tipo_comprobante, self.tipo_comprobante)


class VentaItem(db.Model):
    __tablename__ = 'venta_items'
    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # producto / servicio / libre
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    servicio_id = db.Column(db.Integer, db.ForeignKey('servicios.id'), nullable=True)
    codigo = db.Column(db.String(50))
    descripcion_libre = db.Column(db.String(300))  # free-text or product name snapshot
    unidad = db.Column(db.String(20), default='unidad')
    cantidad = db.Column(db.Float, default=1)
    precio_unitario = db.Column(db.Float, nullable=False)
    bonificacion = db.Column(db.Float, default=0.0)  # discount %
    alicuota_iva = db.Column(db.Float, default=21.0)  # IVA rate: 0, 10.5, 21, 27
    subtotal_neto = db.Column(db.Float, default=0.0)  # net amount before IVA
    subtotal = db.Column(db.Float, nullable=False)    # total with IVA

    @property
    def descripcion(self):
        if self.descripcion_libre:
            return self.descripcion_libre
        if self.tipo == 'producto' and self.producto:
            return self.producto.nombre
        if self.tipo == 'servicio' and self.servicio:
            return self.servicio.nombre
        return ''

    @property
    def iva_monto(self):
        return round((self.subtotal_neto or 0) * (self.alicuota_iva or 0) / 100, 2)


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


class IngresoMercaderia(db.Model):
    __tablename__ = 'ingresos_mercaderia'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)
    forma_pago = db.Column(db.String(50), default='efectivo')
    notas = db.Column(db.Text)
    total = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('IngresoMercaderiaItem', backref='ingreso', lazy=True, cascade='all, delete-orphan')


class IngresoMercaderiaItem(db.Model):
    __tablename__ = 'ingreso_mercaderia_items'
    id = db.Column(db.Integer, primary_key=True)
    ingreso_id = db.Column(db.Integer, db.ForeignKey('ingresos_mercaderia.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    nombre_producto = db.Column(db.String(150), nullable=False)
    cantidad = db.Column(db.Integer, default=1)
    precio_compra = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)


# ─────────────────────────────────────────────
# Módulo Facturación Electrónica (ARCA / AFIP)
# ─────────────────────────────────────────────

class ClienteFacturacion(db.Model):
    """Datos fiscales del cliente para facturación electrónica."""
    __tablename__ = 'clientes_facturacion'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    cuit = db.Column(db.String(20), nullable=True)
    direccion = db.Column(db.String(300), nullable=True)
    # CF=Consumidor Final, RI=Responsable Inscripto, M=Monotributista, EX=Exento
    condicion_iva = db.Column(db.String(10), default='CF')
    email = db.Column(db.String(200), nullable=True)
    # Vínculo opcional con el modelo de clientes ya existente
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)

    facturas = db.relationship('Factura', backref='cliente', lazy=True)

    # Códigos AFIP para tipo de documento
    CONDICIONES_IVA = [
        ('CF',  'Consumidor Final'),
        ('RI',  'Responsable Inscripto'),
        ('M',   'Monotributista'),
        ('EX',  'Exento'),
    ]

    def __repr__(self):
        return f'<ClienteFacturacion {self.nombre}>'


class Factura(db.Model):
    """Cabecera de comprobante electrónico emitido ante ARCA."""
    __tablename__ = 'facturas'

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(
        db.Integer, db.ForeignKey('clientes_facturacion.id'), nullable=False
    )
    # tipo_cbte: 1=Factura A, 6=Factura B, 11=Factura C, 3=N.Crédito A, 8=N.Crédito B, 13=N.Crédito C
    tipo_cbte = db.Column(db.Integer, nullable=False)
    punto_vta = db.Column(db.Integer, nullable=False, default=1)
    numero = db.Column(db.Integer, nullable=True)
    fecha = db.Column(db.Date, nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    iva = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(12, 2), default=0)
    # Campos devueltos por ARCA
    cae = db.Column(db.String(20), nullable=True)
    vencimiento_cae = db.Column(db.Date, nullable=True)
    # borrador | emitida | anulada
    estado = db.Column(db.String(20), default='borrador', nullable=False)
    concepto = db.Column(db.Integer, default=1)   # 1=Productos, 2=Servicios, 3=Mixto
    forma_pago = db.Column(db.String(50), default='efectivo')
    notas = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship(
        'FacturaDetalle', backref='factura', lazy=True, cascade='all, delete-orphan'
    )

    TIPOS_CBTE = [
        (1,  'Factura A'),
        (6,  'Factura B'),
        (11, 'Factura C'),
        (3,  'Nota de Crédito A'),
        (8,  'Nota de Crédito B'),
        (13, 'Nota de Crédito C'),
    ]

    @property
    def tipo_cbte_display(self):
        return dict(self.TIPOS_CBTE).get(self.tipo_cbte, str(self.tipo_cbte))

    @property
    def letra(self):
        """Devuelve la letra del comprobante (A, B o C)."""
        return {1: 'A', 6: 'B', 11: 'C', 3: 'A', 8: 'B', 13: 'C'}.get(
            self.tipo_cbte, ''
        )

    @property
    def numero_display(self):
        if self.numero:
            return f'{self.punto_vta:04d}-{self.numero:08d}'
        return '—'

    def __repr__(self):
        return f'<Factura {self.numero_display}>'


class FacturaDetalle(db.Model):
    """Línea de detalle de un comprobante electrónico."""
    __tablename__ = 'factura_detalle'

    id = db.Column(db.Integer, primary_key=True)
    factura_id = db.Column(
        db.Integer, db.ForeignKey('facturas.id'), nullable=False
    )
    descripcion = db.Column(db.String(500), nullable=False)
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)
    precio_unitario = db.Column(db.Numeric(12, 2), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)

    def __repr__(self):
        return f'<FacturaDetalle {self.descripcion[:30]}>'


# ─────────────────────────────────────────────
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
