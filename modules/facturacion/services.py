"""
Capa de servicio para el módulo de Facturación Electrónica.

Centraliza toda la lógica de negocio: cálculo de IVA, creación de
comprobantes, integración con ARCA, registro en caja y consultas de
reportes (Libro IVA ventas).

Todas las funciones reciben/devuelven objetos del modelo SQLAlchemy o
tipos primitivos; nunca objetos de Flask (request, session, etc.).
"""

import logging
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from extensions import db
from models import (
    ClienteFacturacion,
    Factura,
    FacturaDetalle,
    MovimientoCaja,
)
from modules.facturacion.afip_client import (
    AfipClient,
    AfipError,
    tipo_doc_receptor,
    validar_cuit,
    ALICUOTA_IVA_DEFECTO,
    ID_IVA_DEFECTO,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────

# Tipos de comprobante que llevan IVA discriminado (Factura A / NC A)
TIPOS_CON_IVA = {1, 3}


# ──────────────────────────────────────────────────────────────
# Clientes de facturación
# ──────────────────────────────────────────────────────────────

def crear_cliente(
    nombre,
    condicion_iva,
    cuit=None,
    direccion=None,
    email=None,
    cliente_id=None,
):
    """Crea un registro de cliente para facturación.

    Args:
        nombre: Razón social o nombre del receptor.
        condicion_iva: 'CF', 'RI', 'M' o 'EX'.
        cuit: CUIT del receptor (requerido para RI, M, EX).
        direccion: Domicilio fiscal.
        email: E-mail de contacto.
        cliente_id: FK al modelo Cliente existente (opcional).

    Returns:
        ClienteFacturacion recién creado y persistido.

    Raises:
        ValueError: si el CUIT es inválido o falta para condiciones
                    que lo requieren.
    """
    if condicion_iva in ('RI', 'M', 'EX') and not cuit:
        raise ValueError(
            f'Se requiere CUIT para la condición de IVA "{condicion_iva}".'
        )
    if cuit and not validar_cuit(cuit):
        raise ValueError(f'El CUIT "{cuit}" no es válido.')

    cliente = ClienteFacturacion(
        nombre=nombre.strip(),
        condicion_iva=condicion_iva,
        cuit=cuit.replace('-', '').strip() if cuit else None,
        direccion=direccion.strip() if direccion else None,
        email=email.strip() if email else None,
        cliente_id=cliente_id,
    )
    db.session.add(cliente)
    db.session.commit()
    logger.info('Cliente facturación creado: %s', cliente.nombre)
    return cliente


def actualizar_cliente(
    cliente,
    nombre,
    condicion_iva,
    cuit=None,
    direccion=None,
    email=None,
):
    """Actualiza los datos fiscales de un cliente existente."""
    if condicion_iva in ('RI', 'M', 'EX') and not cuit:
        raise ValueError(
            f'Se requiere CUIT para la condición de IVA "{condicion_iva}".'
        )
    if cuit and not validar_cuit(cuit):
        raise ValueError(f'El CUIT "{cuit}" no es válido.')

    cliente.nombre = nombre.strip()
    cliente.condicion_iva = condicion_iva
    cliente.cuit = cuit.replace('-', '').strip() if cuit else None
    cliente.direccion = direccion.strip() if direccion else None
    cliente.email = email.strip() if email else None
    db.session.commit()
    return cliente


# ──────────────────────────────────────────────────────────────
# Cálculo de IVA
# ──────────────────────────────────────────────────────────────

def calcular_iva(subtotal, tipo_cbte):
    """Calcula IVA e importe total según tipo de comprobante.

    Para Factura B y C el precio ya incluye IVA (precio final);
    para Factura A el precio es neto y se agrega el 21 %.

    Args:
        subtotal: Suma de (cantidad × precio_unitario) de todos los ítems.
        tipo_cbte: Código AFIP del tipo de comprobante.

    Returns:
        (imp_neto, imp_iva, imp_total) como float con 2 decimales.
    """
    sub = Decimal(str(subtotal))

    if tipo_cbte in TIPOS_CON_IVA:
        # Factura A: precio neto + IVA 21 %
        alicuota = Decimal(str(ALICUOTA_IVA_DEFECTO)) / 100
        imp_iva = (sub * alicuota).quantize(Decimal('0.01'), ROUND_HALF_UP)
        imp_total = (sub + imp_iva).quantize(Decimal('0.01'), ROUND_HALF_UP)
        return float(sub), float(imp_iva), float(imp_total)
    else:
        # Factura B / C: precio con IVA incluido → IVA = 0 para AFIP
        return float(sub), 0.0, float(sub)


# ──────────────────────────────────────────────────────────────
# Creación de facturas
# ──────────────────────────────────────────────────────────────

def crear_factura(
    cliente_id,
    tipo_cbte,
    punto_vta,
    fecha,
    concepto,
    items,
    forma_pago='efectivo',
    notas=None,
):
    """Crea un borrador de factura con sus ítems.

    La factura queda en estado 'borrador'; para emitirla se debe llamar
    a :func:`emitir_factura`.

    Args:
        cliente_id: ID del ClienteFacturacion.
        tipo_cbte: Código AFIP del tipo (1, 6, 11, etc.).
        punto_vta: Punto de venta (número entero).
        fecha: Fecha del comprobante.
        concepto: 1=Productos, 2=Servicios, 3=Mixto.
        items: Lista de dicts con descripcion, cantidad y precio_unitario.
        forma_pago: Forma de cobro.
        notas: Observaciones libres.

    Returns:
        Objeto Factura persistido.

    Raises:
        ValueError: si no hay ítems o el cliente no existe.
    """
    if not items:
        raise ValueError('La factura debe tener al menos un ítem.')

    cliente = ClienteFacturacion.query.get(cliente_id)
    if not cliente:
        raise ValueError(f'Cliente de facturación con ID {cliente_id} no encontrado.')

    # Calcular subtotal a partir de los ítems
    subtotal = sum(
        float(it['cantidad']) * float(it['precio_unitario']) for it in items
    )
    imp_neto, imp_iva, imp_total = calcular_iva(subtotal, tipo_cbte)

    factura = Factura(
        cliente_id=cliente_id,
        tipo_cbte=tipo_cbte,
        punto_vta=punto_vta,
        fecha=fecha,
        concepto=concepto,
        subtotal=imp_neto,
        iva=imp_iva,
        total=imp_total,
        estado='borrador',
        forma_pago=forma_pago,
        notas=notas,
    )
    db.session.add(factura)
    db.session.flush()

    for it in items:
        cant = float(it['cantidad'])
        pu = float(it['precio_unitario'])
        detalle = FacturaDetalle(
            factura_id=factura.id,
            descripcion=it['descripcion'].strip(),
            cantidad=cant,
            precio_unitario=pu,
            subtotal=round(cant * pu, 2),
        )
        db.session.add(detalle)

    db.session.commit()
    logger.info('Factura borrador creada: ID=%d tipo=%d', factura.id, tipo_cbte)
    return factura


# ──────────────────────────────────────────────────────────────
# Emisión ante ARCA
# ──────────────────────────────────────────────────────────────

def emitir_factura(factura_id):
    """Envía la factura a ARCA, obtiene el CAE y actualiza el registro.

    Registra el ingreso en la caja automáticamente tras la emisión exitosa.

    Args:
        factura_id: ID de la Factura a emitir (debe estar en 'borrador').

    Returns:
        Factura actualizada con CAE.

    Raises:
        ValueError: si la factura no existe o no está en borrador.
        AfipError: si ARCA rechaza el comprobante.
    """
    factura = Factura.query.get(factura_id)
    if not factura:
        raise ValueError(f'Factura ID {factura_id} no encontrada.')
    if factura.estado != 'borrador':
        raise ValueError(
            f'La factura ya está en estado "{factura.estado}". '
            'Solo se pueden emitir borradores.'
        )

    cliente = factura.cliente

    # Determinar siguiente número de comprobante
    afip = AfipClient()
    afip.conectar()
    ultimo = afip.ultimo_numero(factura.tipo_cbte, factura.punto_vta)
    siguiente = ultimo + 1

    # Determinar tipo de documento del receptor
    tipo_doc, nro_doc = tipo_doc_receptor(
        cliente.condicion_iva, cliente.cuit
    )

    # Solicitar CAE
    resultado = afip.solicitar_cae(
        tipo_cbte=factura.tipo_cbte,
        punto_vta=factura.punto_vta,
        numero=siguiente,
        fecha=factura.fecha.strftime('%Y%m%d'),
        concepto=factura.concepto,
        tipo_doc=tipo_doc,
        nro_doc=nro_doc,
        imp_neto=float(factura.subtotal),
        imp_iva=float(factura.iva),
        imp_total=float(factura.total),
        alicuota_iva_id=ID_IVA_DEFECTO,
        alicuota_iva_pct=ALICUOTA_IVA_DEFECTO,
    )

    # Convertir fecha de vencimiento del CAE (YYYYMMDD → date)
    vto_raw = resultado.get('vencimiento_cae', '')
    try:
        vto = datetime.strptime(vto_raw, '%Y%m%d').date()
    except (ValueError, TypeError):
        vto = None

    # Persistir resultado
    factura.numero = resultado['numero']
    factura.cae = resultado['cae']
    factura.vencimiento_cae = vto
    factura.estado = 'emitida'

    # Registrar en caja
    _registrar_ingreso_caja(factura)

    db.session.commit()
    logger.info(
        'Factura emitida: ID=%d N°=%s CAE=%s',
        factura.id, factura.numero_display, factura.cae,
    )
    return factura


def _registrar_ingreso_caja(factura):
    """Registra el total de la factura como ingreso en la caja."""
    tipo_display = factura.tipo_cbte_display
    concepto = (
        f'{tipo_display} {factura.numero_display} – '
        f'{factura.cliente.nombre}'
    )
    mov = MovimientoCaja(
        tipo='ingreso',
        cuenta='venta_productos',
        forma_pago=factura.forma_pago,
        concepto=concepto,
        monto=float(factura.total),
        referencia_tipo='factura',
        referencia_id=factura.id,
        fecha=datetime.utcnow(),
    )
    db.session.add(mov)


# ──────────────────────────────────────────────────────────────
# Anulación / nota de crédito
# ──────────────────────────────────────────────────────────────

def anular_factura(factura_id):
    """Marca la factura como anulada y elimina el movimiento de caja.

    Nota: ARCA no permite anular comprobantes electrónicos directamente.
    Para anular formalmente se debe emitir una Nota de Crédito con el
    mismo importe.  Este método solo cambia el estado interno del sistema.

    Args:
        factura_id: ID de la factura a anular.

    Returns:
        Factura actualizada.

    Raises:
        ValueError: si la factura no existe o ya está anulada.
    """
    factura = Factura.query.get(factura_id)
    if not factura:
        raise ValueError(f'Factura ID {factura_id} no encontrada.')
    if factura.estado == 'anulada':
        raise ValueError('La factura ya está anulada.')

    factura.estado = 'anulada'

    # Revertir movimiento de caja si existe
    MovimientoCaja.query.filter_by(
        referencia_tipo='factura', referencia_id=factura_id
    ).delete()

    db.session.commit()
    logger.info('Factura anulada: ID=%d', factura_id)
    return factura


# ──────────────────────────────────────────────────────────────
# Reportes
# ──────────────────────────────────────────────────────────────

def libro_iva_ventas(desde, hasta):
    """Devuelve las facturas emitidas en el período indicado.

    Args:
        desde: date de inicio del período.
        hasta: date de fin del período.

    Returns:
        Lista de Factura ordenadas por fecha.
    """
    return (
        Factura.query
        .filter(
            Factura.estado == 'emitida',
            Factura.fecha >= desde,
            Factura.fecha <= hasta,
        )
        .order_by(Factura.fecha.asc(), Factura.id.asc())
        .all()
    )
