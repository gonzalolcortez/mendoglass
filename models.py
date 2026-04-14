from extensions import db
from datetime import datetime
from flask_login import UserMixin
from sqlalchemy import case, func
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
    apellido = db.Column(db.String(150), nullable=False, default='')
    dni_cuit = db.Column(db.String(30))
    direccion = db.Column(db.String(200))
    celular = db.Column(db.String(30))
    actividades = db.Column(db.Text, default='')
    es_tercerizado = db.Column(db.Boolean, default=False)
    empresa_tercerizado = db.Column(db.String(150))
    activo = db.Column(db.Boolean, default=True)
    movimientos_cuenta_corriente = db.relationship(
        'TecnicoCuentaCorrienteMovimiento',
        backref='tecnico',
        lazy=True,
        cascade='all, delete-orphan',
    )

    ACTIVIDADES_PREDEFINIDAS = [
        ('tecnico', 'Técnico'),
        ('administrativo', 'Administrativo'),
        ('vendedor', 'Vendedor'),
    ]

    @property
    def nombre_completo(self):
        return ' '.join(part for part in [self.nombre, self.apellido] if part).strip()

    @property
    def nombre_display(self):
        nombre_base = self.nombre_completo or self.nombre
        if self.es_tercerizado and self.empresa_tercerizado:
            return f"{nombre_base} - {self.empresa_tercerizado}"
        return nombre_base

    @property
    def actividades_lista(self):
        return [item.strip() for item in (self.actividades or '').split(',') if item.strip()]

    @property
    def actividades_display(self):
        return ', '.join(self.actividades_lista)

    @property
    def actividades_personalizadas(self):
        predefinidas = {valor for valor, _ in self.ACTIVIDADES_PREDEFINIDAS}
        return [actividad for actividad in self.actividades_lista if actividad not in predefinidas]

    @property
    def saldo_cuenta_corriente(self):
        saldo = 0.0
        for mov in self.movimientos_cuenta_corriente:
            monto = float(mov.monto or 0.0)
            if mov.tipo == 'cargo':
                saldo += monto
            else:
                saldo -= monto
        return round(saldo, 2)


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
    created_at = db.Column(db.DateTime, default=datetime.now)

    talleres = db.relationship('Taller', backref='cliente', lazy=True)
    ventas = db.relationship('Venta', backref='cliente', lazy=True)
    movimientos_cuenta_corriente = db.relationship(
        'ClienteCuentaCorrienteMovimiento',
        backref='cliente',
        lazy=True,
        cascade='all, delete-orphan',
    )

    CONDICIONES_IVA = [
        ('CF', 'Consumidor Final'),
        ('RI', 'Responsable Inscripto'),
        ('M',  'Monotributista'),
        ('EX', 'Exento'),
    ]

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"

    @property
    def saldo_cuenta_corriente(self):
        saldo = 0.0
        for mov in self.movimientos_cuenta_corriente:
            monto = float(mov.monto or 0.0)
            if mov.tipo == 'cargo':
                saldo += monto
            else:
                saldo -= monto
        return round(saldo, 2)


class Proveedor(db.Model):
    __tablename__ = 'proveedores'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(30))
    email = db.Column(db.String(120))
    direccion = db.Column(db.String(200))
    notas = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

    ingresos = db.relationship('IngresoMercaderia', backref='proveedor', lazy=True)
    movimientos_cuenta_corriente = db.relationship(
        'ProveedorCuentaCorrienteMovimiento',
        backref='proveedor',
        lazy=True,
        cascade='all, delete-orphan',
    )

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"

    @property
    def saldo_cuenta_corriente(self):
        saldo = 0.0
        for mov in self.movimientos_cuenta_corriente:
            monto = float(mov.monto or 0.0)
            if mov.tipo == 'cargo':
                saldo += monto
            else:
                saldo -= monto
        return round(saldo, 2)


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
    alicuota_iva = db.Column(db.Float, default=21.0)  # IVA incluido en el precio: 0, 10.5 o 21
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
    alicuota_iva = db.Column(db.Float, default=21.0)  # IVA incluido en el precio: 0, 10.5 o 21
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
    fecha_ingreso = db.Column(db.DateTime, default=datetime.now)
    fecha_estimada_entrega = db.Column(db.DateTime)
    fecha_entrega = db.Column(db.DateTime)
    tecnico = db.Column(db.String(100))
    pagado = db.Column(db.Boolean, default=False)
    forma_pago = db.Column(db.String(50), default='efectivo')
    created_at = db.Column(db.DateTime, default=datetime.now)

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
    # FACTURA / NOTA_VENTA / NOTA_CREDITO
    tipo_comprobante = db.Column(db.String(20), default='NOTA_VENTA', nullable=False)
    punto_venta = db.Column(db.Integer, default=1)
    numero_comprobante = db.Column(db.Integer)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.now)
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
    created_at = db.Column(db.DateTime, default=datetime.now)

    items = db.relationship('VentaItem', backref='venta', lazy=True, cascade='all, delete-orphan')

    TIPOS_COMPROBANTE = [
        ('NOTA_VENTA', 'Nota de Venta'),
        ('NOTA_CREDITO', 'Nota de Crédito'),
        ('FACTURA',    'Factura Electrónica'),
    ]

    @property
    def numero_display(self):
        nro = self.numero_comprobante
        if nro is None:
            return f'#{self.id}'
        if self.tipo_comprobante in ('NOTA_VENTA', 'NOTA_CREDITO'):
            return f'{nro:04d}'
        pv = self.punto_venta or 1
        if nro is not None:
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
    fecha = db.Column(db.DateTime, default=datetime.now)
    notas = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)


class ClienteCuentaCorrienteMovimiento(db.Model):
    __tablename__ = 'clientes_cuenta_corriente'
    __table_args__ = (
        db.Index('ix_clientes_cc_cliente_fecha', 'cliente_id', 'fecha'),
    )

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    # cargo: aumenta deuda | abono: reduce deuda / genera saldo a favor
    tipo = db.Column(db.String(10), nullable=False)
    concepto = db.Column(db.String(200), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    cuenta = db.Column(db.String(50), default='otro')
    referencia_tipo = db.Column(db.String(20))
    referencia_id = db.Column(db.Integer)
    fecha = db.Column(db.DateTime, default=datetime.now)
    created_at = db.Column(db.DateTime, default=datetime.now)

    TIPOS = [
        ('cargo', 'Cargo'),
        ('abono', 'Abono'),
    ]

    @property
    def monto_con_signo(self):
        monto = float(self.monto or 0.0)
        return monto if self.tipo == 'cargo' else -monto


class ProveedorCuentaCorrienteMovimiento(db.Model):
    __tablename__ = 'proveedores_cuenta_corriente'
    __table_args__ = (
        db.Index('ix_proveedores_cc_proveedor_fecha', 'proveedor_id', 'fecha'),
    )

    id = db.Column(db.Integer, primary_key=True)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=False)
    # cargo: aumenta deuda con proveedor | abono: reduce deuda / saldo a favor
    tipo = db.Column(db.String(10), nullable=False)
    concepto = db.Column(db.String(200), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    cuenta = db.Column(db.String(50), default='otro')
    referencia_tipo = db.Column(db.String(30))
    referencia_id = db.Column(db.Integer)
    fecha = db.Column(db.DateTime, default=datetime.now)
    created_at = db.Column(db.DateTime, default=datetime.now)

    TIPOS = [
        ('cargo', 'Cargo'),
        ('abono', 'Abono'),
    ]


class TecnicoCuentaCorrienteMovimiento(db.Model):
    __tablename__ = 'tecnicos_cuenta_corriente'
    __table_args__ = (
        db.Index('ix_tecnicos_cc_tecnico_fecha', 'tecnico_id', 'fecha'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tecnico_id = db.Column(db.Integer, db.ForeignKey('tecnicos.id'), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)
    concepto = db.Column(db.String(200), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    cuenta = db.Column(db.String(50), default='tecnicos')
    forma_pago = db.Column(db.String(50), default='cuenta_corriente')
    referencia_tipo = db.Column(db.String(30))
    referencia_id = db.Column(db.Integer)
    fecha = db.Column(db.DateTime, default=datetime.now)
    created_at = db.Column(db.DateTime, default=datetime.now)

    TIPOS = [
        ('cargo', 'Cargo'),
        ('abono', 'Abono'),
    ]

    @property
    def monto_con_signo(self):
        monto = float(self.monto or 0.0)
        return monto if self.tipo == 'cargo' else -monto


class IngresoMercaderia(db.Model):
    __tablename__ = 'ingresos_mercaderia'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.now)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)
    forma_pago = db.Column(db.String(50), default='efectivo')
    notas = db.Column(db.Text)
    total = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.now)

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
    created_at = db.Column(db.DateTime, default=datetime.now)

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
    ('tecnicos', 'Personal y Adelantos'),
    ('impuestos', 'Impuestos'),
    ('alquiler', 'Alquiler'),
    ('compra_mercaderia', 'Compra de Mercadería'),
    ('compra_repuestos', 'Compra de Repuestos'),
    ('otro', 'Otro'),
]

ACTIVIDADES_PERSONAL = Tecnico.ACTIVIDADES_PREDEFINIDAS

# Formas de pago
FORMAS_PAGO = [
    ('efectivo', 'Efectivo'),
    ('mercado_pago', 'Mercado Pago'),
    ('tarjeta', 'Tarjetas'),
    ('banco', 'Banco'),
    ('cuenta_corriente', 'Cuentas Corrientes'),
]

FORMAS_PAGO_ALIAS = {
    'transferencia': 'banco',
    'transferencia_bancaria': 'banco',
}


def normalizar_forma_pago(forma_pago, default='efectivo'):
    valor = (forma_pago or '').strip().lower()
    if not valor:
        return default
    return FORMAS_PAGO_ALIAS.get(valor, valor)


_ORDEN_CUENTAS = [cuenta for cuenta, _ in CUENTAS_CAJA]
_REPARTO_TOLERANCIA = 0.004
_PALABRAS_REPUESTO = (
    'repuesto',
    'pantalla',
    'bateria',
    'batería',
    'display',
    'modulo',
    'módulo',
    'flex',
    'placa',
    'pin',
    'conector',
    'touch',
    'vidrio',
)


def _texto_normalizado(value):
    return ' '.join((value or '').strip().lower().split())


def categoria_es_repuesto(nombre_categoria=None, nombre_producto=None):
    texto = _texto_normalizado(nombre_categoria)
    if not texto:
        texto = _texto_normalizado(nombre_producto)
    return any(palabra in texto for palabra in _PALABRAS_REPUESTO)


def obtener_cuenta_producto(producto, tipo_movimiento='venta'):
    es_repuesto = categoria_es_repuesto(
        producto.categoria.nombre if getattr(producto, 'categoria', None) else None,
        getattr(producto, 'nombre', None),
    )
    if tipo_movimiento == 'compra':
        return 'compra_repuestos' if es_repuesto else 'compra_mercaderia'
    return 'venta_repuestos' if es_repuesto else 'venta_productos'


def acumular_total_por_cuenta(totales, cuenta, monto):
    monto_val = round(float(monto or 0.0), 2)
    if monto_val <= 0:
        return totales
    totales[cuenta] = round(float(totales.get(cuenta, 0.0)) + monto_val, 2)
    return totales


def normalizar_totales_por_cuenta(totales):
    return {
        cuenta: round(float(monto or 0.0), 2)
        for cuenta, monto in totales.items()
        if abs(float(monto or 0.0)) > _REPARTO_TOLERANCIA
    }


def obtener_saldos_por_cuenta_desde_movimientos(movimientos):
    saldos = {}
    for movimiento in sorted(movimientos, key=lambda item: (item.fecha or datetime.min, item.id or 0)):
        cuenta = (getattr(movimiento, 'cuenta', None) or 'otro').strip() or 'otro'
        monto = round(float(getattr(movimiento, 'monto', 0.0) or 0.0), 2)
        if getattr(movimiento, 'tipo', None) == 'cargo':
            saldos[cuenta] = round(float(saldos.get(cuenta, 0.0)) + monto, 2)
        else:
            saldos[cuenta] = round(float(saldos.get(cuenta, 0.0)) - monto, 2)
    return {
        cuenta: saldo
        for cuenta, saldo in saldos.items()
        if saldo > _REPARTO_TOLERANCIA
    }


def distribuir_monto_entre_cuentas(saldos_por_cuenta, monto):
    restante = round(float(monto or 0.0), 2)
    if restante <= 0:
        return {}

    asignaciones = {}
    for cuenta in _ORDEN_CUENTAS:
        saldo = round(float(saldos_por_cuenta.get(cuenta, 0.0) or 0.0), 2)
        if saldo <= _REPARTO_TOLERANCIA or restante <= _REPARTO_TOLERANCIA:
            continue
        aplicado = min(saldo, restante)
        if aplicado > _REPARTO_TOLERANCIA:
            asignaciones[cuenta] = round(aplicado, 2)
            restante = round(restante - aplicado, 2)

    for cuenta, saldo in saldos_por_cuenta.items():
        if cuenta in asignaciones or restante <= _REPARTO_TOLERANCIA:
            continue
        saldo_val = round(float(saldo or 0.0), 2)
        if saldo_val <= _REPARTO_TOLERANCIA:
            continue
        aplicado = min(saldo_val, restante)
        if aplicado > _REPARTO_TOLERANCIA:
            asignaciones[cuenta] = round(aplicado, 2)
            restante = round(restante - aplicado, 2)

    if restante > _REPARTO_TOLERANCIA:
        asignaciones['otro'] = round(float(asignaciones.get('otro', 0.0)) + restante, 2)

    return normalizar_totales_por_cuenta(asignaciones)


def obtener_totales_taller_por_cuenta(taller):
    totales = {}
    acumular_total_por_cuenta(totales, 'venta_repuestos', getattr(taller, 'total_productos', 0.0))
    acumular_total_por_cuenta(totales, 'servicio_tecnico', getattr(taller, 'total_servicios', 0.0))
    return normalizar_totales_por_cuenta(totales)


def obtener_totales_venta_por_cuenta(items):
    totales = {}
    for item in items:
        subtotal = round(abs(float(getattr(item, 'subtotal', 0.0) or 0.0)), 2)
        if subtotal <= _REPARTO_TOLERANCIA:
            continue
        item_tipo = getattr(item, 'tipo', '')
        if item_tipo == 'servicio':
            cuenta = 'servicio_tecnico'
        elif item_tipo == 'producto' and getattr(item, 'producto', None):
            cuenta = obtener_cuenta_producto(item.producto, 'venta')
        else:
            cuenta = 'otro'
        acumular_total_por_cuenta(totales, cuenta, subtotal)
    return normalizar_totales_por_cuenta(totales)


def obtener_totales_ingreso_por_cuenta(items):
    totales = {}
    for item in items:
        subtotal = round(abs(float(getattr(item, 'subtotal', 0.0) or 0.0)), 2)
        if subtotal <= _REPARTO_TOLERANCIA:
            continue
        producto = getattr(item, 'producto', None)
        cuenta = obtener_cuenta_producto(producto, 'compra') if producto else 'compra_mercaderia'
        acumular_total_por_cuenta(totales, cuenta, subtotal)
    return normalizar_totales_por_cuenta(totales)


def _saldo_agrupado_query(modelo, entidad_col, filtro_ids=None):
    saldo_expr = func.coalesce(
        func.sum(
            case(
                (modelo.tipo == 'cargo', modelo.monto),
                else_=-modelo.monto,
            )
        ),
        0.0,
    )
    query = db.session.query(entidad_col, saldo_expr.label('saldo')).group_by(entidad_col)
    if filtro_ids is not None:
        ids = [int(item_id) for item_id in filtro_ids if item_id is not None]
        if not ids:
            return []
        query = query.filter(entidad_col.in_(ids))
    return query.all()


def obtener_saldos_clientes(cliente_ids=None):
    rows = _saldo_agrupado_query(
        ClienteCuentaCorrienteMovimiento,
        ClienteCuentaCorrienteMovimiento.cliente_id,
        filtro_ids=cliente_ids,
    )
    return {cliente_id: round(float(saldo or 0.0), 2) for cliente_id, saldo in rows}


def obtener_saldos_proveedores(proveedor_ids=None):
    rows = _saldo_agrupado_query(
        ProveedorCuentaCorrienteMovimiento,
        ProveedorCuentaCorrienteMovimiento.proveedor_id,
        filtro_ids=proveedor_ids,
    )
    return {proveedor_id: round(float(saldo or 0.0), 2) for proveedor_id, saldo in rows}


def obtener_saldos_tecnicos(tecnico_ids=None):
    rows = _saldo_agrupado_query(
        TecnicoCuentaCorrienteMovimiento,
        TecnicoCuentaCorrienteMovimiento.tecnico_id,
        filtro_ids=tecnico_ids,
    )
    return {tecnico_id: round(float(saldo or 0.0), 2) for tecnico_id, saldo in rows}


def registrar_movimiento_cuenta_corriente(
    cliente_id,
    tipo,
    monto,
    concepto,
    cuenta='otro',
    referencia_tipo=None,
    referencia_id=None,
    fecha=None,
):
    if not cliente_id:
        return None
    if tipo not in ('cargo', 'abono'):
        raise ValueError('Tipo de movimiento de cuenta corriente inválido.')

    monto_val = round(float(monto or 0.0), 2)
    if monto_val <= 0:
        raise ValueError('El monto de cuenta corriente debe ser mayor que cero.')

    mov = ClienteCuentaCorrienteMovimiento(
        cliente_id=int(cliente_id),
        tipo=tipo,
        concepto=(concepto or '').strip() or 'Movimiento de cuenta corriente',
        monto=monto_val,
        cuenta=(cuenta or 'otro').strip() or 'otro',
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id,
        fecha=fecha or datetime.now(),
    )
    db.session.add(mov)
    return mov


def registrar_movimiento_cc_proveedor(
    proveedor_id,
    tipo,
    monto,
    concepto,
    cuenta='otro',
    referencia_tipo=None,
    referencia_id=None,
    fecha=None,
):
    if not proveedor_id:
        return None
    if tipo not in ('cargo', 'abono'):
        raise ValueError('Tipo de movimiento de cuenta corriente de proveedor inválido.')

    monto_val = round(float(monto or 0.0), 2)
    if monto_val <= 0:
        raise ValueError('El monto de cuenta corriente de proveedor debe ser mayor que cero.')

    mov = ProveedorCuentaCorrienteMovimiento(
        proveedor_id=int(proveedor_id),
        tipo=tipo,
        concepto=(concepto or '').strip() or 'Movimiento de cuenta corriente de proveedor',
        monto=monto_val,
        cuenta=(cuenta or 'otro').strip() or 'otro',
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id,
        fecha=fecha or datetime.now(),
    )
    db.session.add(mov)
    return mov


def registrar_movimiento_cc_tecnico(
    tecnico_id,
    tipo,
    monto,
    concepto,
    cuenta='tecnicos',
    forma_pago='cuenta_corriente',
    referencia_tipo=None,
    referencia_id=None,
    fecha=None,
):
    if not tecnico_id:
        return None
    if tipo not in ('cargo', 'abono'):
        raise ValueError('Tipo de movimiento de cuenta corriente de personal inválido.')

    monto_val = round(float(monto or 0.0), 2)
    if monto_val <= 0:
        raise ValueError('El monto de cuenta corriente de personal debe ser mayor que cero.')

    mov = TecnicoCuentaCorrienteMovimiento(
        tecnico_id=int(tecnico_id),
        tipo=tipo,
        concepto=(concepto or '').strip() or 'Movimiento de cuenta corriente de personal',
        monto=monto_val,
        cuenta=(cuenta or 'tecnicos').strip() or 'tecnicos',
        forma_pago=(forma_pago or 'cuenta_corriente').strip() or 'cuenta_corriente',
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id,
        fecha=fecha or datetime.now(),
    )
    db.session.add(mov)
    return mov


def sincronizar_movimientos_contables_automaticos():

    for venta in Venta.query.all():
        movimientos = MovimientoCaja.query.filter_by(
            referencia_tipo='venta',
            referencia_id=venta.id,
        ).order_by(MovimientoCaja.fecha.asc(), MovimientoCaja.id.asc()).all()
        totales = {} if venta.forma_pago == 'cuenta_corriente' else obtener_totales_venta_por_cuenta(venta.items)
        tipo_mov = 'egreso' if venta.tipo_comprobante == 'NOTA_CREDITO' else 'ingreso'
        existentes = normalizar_totales_por_cuenta({m.cuenta: float(m.monto or 0.0) for m in movimientos})
        if not totales:
            for movimiento in movimientos:
                db.session.delete(movimiento)
            continue
        if movimientos and existentes == totales and all(m.tipo == tipo_mov for m in movimientos):
            continue
        fecha = movimientos[0].fecha if movimientos else venta.fecha or venta.created_at or datetime.now()
        forma_pago = movimientos[0].forma_pago if movimientos else venta.forma_pago
        for movimiento in movimientos:
            db.session.delete(movimiento)
        for cuenta, monto in totales.items():
            concepto = f'{venta.tipo_display} {venta.numero_display}'
            if venta.cliente:
                concepto = f'{concepto} - {venta.cliente.nombre_completo}'
            db.session.add(MovimientoCaja(
                tipo=tipo_mov,
                cuenta=cuenta,
                forma_pago=forma_pago,
                concepto=concepto,
                monto=monto,
                referencia_tipo='venta',
                referencia_id=venta.id,
                fecha=fecha,
            ))

    for taller in Taller.query.all():
        movimientos = MovimientoCaja.query.filter_by(
            referencia_tipo='taller',
            referencia_id=taller.id,
        ).order_by(MovimientoCaja.fecha.asc(), MovimientoCaja.id.asc()).all()
        totales = {}
        if taller.pagado and (taller.forma_pago or 'efectivo') != 'cuenta_corriente':
            totales = obtener_totales_taller_por_cuenta(taller)
        existentes = normalizar_totales_por_cuenta({m.cuenta: float(m.monto or 0.0) for m in movimientos})
        if not totales:
            for movimiento in movimientos:
                db.session.delete(movimiento)
            continue
        if movimientos and existentes == totales and all(m.tipo == 'ingreso' for m in movimientos):
            continue
        fecha = movimientos[0].fecha if movimientos else taller.fecha_entrega or taller.fecha_ingreso or taller.created_at or datetime.now()
        forma_pago = movimientos[0].forma_pago if movimientos else taller.forma_pago
        nombre_cliente = taller.cliente.nombre_completo if taller.cliente else f'Cliente #{taller.cliente_id}'
        for movimiento in movimientos:
            db.session.delete(movimiento)
        for cuenta, monto in totales.items():
            db.session.add(MovimientoCaja(
                tipo='ingreso',
                cuenta=cuenta,
                forma_pago=forma_pago,
                concepto=f'Reparación #{taller.numero} - {nombre_cliente}',
                monto=monto,
                referencia_tipo='taller',
                referencia_id=taller.id,
                fecha=fecha,
            ))

    for ingreso in IngresoMercaderia.query.all():
        movimientos = MovimientoCaja.query.filter_by(
            referencia_tipo='ingreso_mercaderia',
            referencia_id=ingreso.id,
        ).order_by(MovimientoCaja.fecha.asc(), MovimientoCaja.id.asc()).all()
        totales = {}
        if (ingreso.forma_pago or 'efectivo') != 'cuenta_corriente':
            totales = obtener_totales_ingreso_por_cuenta(ingreso.items)
        existentes = normalizar_totales_por_cuenta({m.cuenta: float(m.monto or 0.0) for m in movimientos})
        if not totales:
            for movimiento in movimientos:
                db.session.delete(movimiento)
            continue
        if movimientos and existentes == totales and all(m.tipo == 'egreso' for m in movimientos):
            continue
        fecha = movimientos[0].fecha if movimientos else ingreso.fecha or ingreso.created_at or datetime.now()
        forma_pago = movimientos[0].forma_pago if movimientos else ingreso.forma_pago
        for movimiento in movimientos:
            db.session.delete(movimiento)
        for cuenta, monto in totales.items():
            db.session.add(MovimientoCaja(
                tipo='egreso',
                cuenta=cuenta,
                forma_pago=forma_pago,
                concepto=f'Ingreso de Mercadería #{ingreso.id}',
                monto=monto,
                referencia_tipo='ingreso_mercaderia',
                referencia_id=ingreso.id,
                fecha=fecha,
            ))

    db.session.commit()
