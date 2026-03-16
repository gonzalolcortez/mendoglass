"""
Blueprint de Facturación Electrónica.

Endpoints REST + vistas HTML para el módulo de facturación ARCA/AFIP.

Rutas:
    GET  /facturas                   – Lista de facturas
    GET  /facturas/nueva             – Formulario de nueva factura
    POST /facturas                   – Crear factura (borrador)
    GET  /facturas/<id>              – Detalle de una factura
    POST /facturas/<id>/emitir       – Enviar a ARCA y obtener CAE
    GET  /facturas/<id>/pdf          – Descargar PDF
    POST /facturas/<id>/anular       – Anular factura
    GET  /facturas/libro-iva         – Libro IVA ventas
    GET  /facturas/clientes          – Lista de clientes de facturación
    GET  /facturas/clientes/nuevo    – Formulario nuevo cliente
    POST /facturas/clientes          – Crear cliente
    GET  /facturas/clientes/<id>/editar  – Editar cliente
    POST /facturas/clientes/<id>     – Actualizar cliente
"""

import os
import logging
from datetime import date, datetime

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, send_file, jsonify,
)
from flask_login import login_required

from extensions import db
from models import ClienteFacturacion, Factura, FacturaDetalle, FORMAS_PAGO
from modules.facturacion.services import (
    crear_cliente,
    actualizar_cliente,
    crear_factura,
    emitir_factura,
    anular_factura,
    libro_iva_ventas,
)
from modules.facturacion.afip_client import AfipError
from modules.facturacion.pdf_generator import generar_pdf

logger = logging.getLogger(__name__)

facturacion_bp = Blueprint('facturacion', __name__)

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

TIPOS_CBTE = Factura.TIPOS_CBTE
CONDICIONES_IVA = ClienteFacturacion.CONDICIONES_IVA
CONCEPTOS = [
    (1, 'Productos'),
    (2, 'Servicios'),
    (3, 'Productos y Servicios'),
]


def _parse_date(value, default=None):
    """Parsea una cadena 'YYYY-MM-DD' a date."""
    if not value:
        return default
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return default


# ──────────────────────────────────────────────────────────────
# Facturas – listado
# ──────────────────────────────────────────────────────────────

@facturacion_bp.route('/')
@login_required
def index():
    """Lista todas las facturas ordenadas por fecha descendente."""
    facturas = (
        Factura.query
        .order_by(Factura.fecha.desc(), Factura.id.desc())
        .all()
    )
    return render_template(
        'facturacion/index.html',
        facturas=facturas,
        title='Facturas',
    )


# ──────────────────────────────────────────────────────────────
# Facturas – crear
# ──────────────────────────────────────────────────────────────

@facturacion_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
def nueva():
    """Formulario y procesamiento de nueva factura (borrador)."""
    clientes = ClienteFacturacion.query.order_by(ClienteFacturacion.nombre).all()

    if request.method == 'POST':
        cliente_id = request.form.get('cliente_id', type=int)
        tipo_cbte = request.form.get('tipo_cbte', type=int, default=6)
        punto_vta = request.form.get('punto_vta', type=int, default=1)
        fecha_str = request.form.get('fecha', '')
        concepto = request.form.get('concepto', type=int, default=1)
        forma_pago = request.form.get('forma_pago', 'efectivo')
        notas = request.form.get('notas', '').strip() or None

        # Ítems
        descripciones = request.form.getlist('item_descripcion[]')
        cantidades = request.form.getlist('item_cantidad[]')
        precios = request.form.getlist('item_precio[]')

        # Validaciones básicas
        errores = []
        if not cliente_id:
            errores.append('Debe seleccionar un cliente.')
        fecha = _parse_date(fecha_str, default=date.today())
        items = []
        for desc, cant, precio in zip(descripciones, cantidades, precios):
            desc = desc.strip()
            if not desc:
                continue
            try:
                items.append({
                    'descripcion': desc,
                    'cantidad': float(cant or 1),
                    'precio_unitario': float(precio or 0),
                })
            except (ValueError, TypeError):
                errores.append(f'Valor inválido en ítem "{desc}".')

        if not items:
            errores.append('Debe agregar al menos un ítem.')

        if errores:
            for e in errores:
                flash(e, 'danger')
            return render_template(
                'facturacion/form.html',
                clientes=clientes,
                tipos_cbte=TIPOS_CBTE,
                condiciones_iva=CONDICIONES_IVA,
                conceptos=CONCEPTOS,
                formas_pago=FORMAS_PAGO,
                today=date.today(),
                title='Nueva Factura',
            )

        try:
            factura = crear_factura(
                cliente_id=cliente_id,
                tipo_cbte=tipo_cbte,
                punto_vta=punto_vta,
                fecha=fecha,
                concepto=concepto,
                items=items,
                forma_pago=forma_pago,
                notas=notas,
            )
            flash(
                f'Factura borrador creada correctamente (ID {factura.id}). '
                'Emítela para obtener el CAE.',
                'success',
            )
            return redirect(url_for('facturacion.detalle', id=factura.id))
        except (ValueError, Exception) as exc:
            flash(str(exc), 'danger')

    return render_template(
        'facturacion/form.html',
        clientes=clientes,
        tipos_cbte=TIPOS_CBTE,
        condiciones_iva=CONDICIONES_IVA,
        conceptos=CONCEPTOS,
        formas_pago=FORMAS_PAGO,
        today=date.today(),
        title='Nueva Factura',
    )


# ──────────────────────────────────────────────────────────────
# Facturas – detalle
# ──────────────────────────────────────────────────────────────

@facturacion_bp.route('/<int:id>')
@login_required
def detalle(id):
    """Muestra el detalle de una factura."""
    factura = db.get_or_404(Factura, id)
    return render_template(
        'facturacion/detalle.html',
        factura=factura,
        title=f'Factura {factura.numero_display}',
    )


# ──────────────────────────────────────────────────────────────
# Facturas – emitir (POST /facturas/<id>/emitir)
# ──────────────────────────────────────────────────────────────

@facturacion_bp.route('/<int:id>/emitir', methods=['POST'])
@login_required
def emitir(id):
    """Envía la factura a ARCA y guarda el CAE."""
    try:
        factura = emitir_factura(id)
        flash(
            f'Factura emitida correctamente. CAE: {factura.cae}  '
            f'(vence {factura.vencimiento_cae.strftime("%d/%m/%Y") if factura.vencimiento_cae else "—"})',
            'success',
        )
    except (ValueError, AfipError) as exc:
        flash(f'Error al emitir la factura: {exc}', 'danger')
        logger.exception('Error emitiendo factura ID %d', id)
    except Exception as exc:
        flash(f'Error inesperado: {exc}', 'danger')
        logger.exception('Error inesperado emitiendo factura ID %d', id)
    return redirect(url_for('facturacion.detalle', id=id))


# ──────────────────────────────────────────────────────────────
# Facturas – PDF (GET /facturas/<id>/pdf)
# ──────────────────────────────────────────────────────────────

@facturacion_bp.route('/<int:id>/pdf')
@login_required
def pdf(id):
    """Descarga el PDF del comprobante electrónico."""
    factura = db.get_or_404(Factura, id)

    logo_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'static', 'img', 'logo.png',
    )
    if not os.path.exists(logo_path):
        logo_path = None

    try:
        buf = generar_pdf(
            factura,
            cuit_emisor=os.environ.get('AFIP_CUIT', ''),
            nombre_empresa=os.environ.get('EMPRESA_NOMBRE', 'Mi Empresa'),
            logo_path=logo_path,
        )
    except RuntimeError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('facturacion.detalle', id=id))

    filename = f'factura_{factura.numero_display.replace("-", "_")}.pdf'
    return send_file(
        buf,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename,
    )


# ──────────────────────────────────────────────────────────────
# Facturas – anular (POST /facturas/<id>/anular)
# ──────────────────────────────────────────────────────────────

@facturacion_bp.route('/<int:id>/anular', methods=['POST'])
@login_required
def anular(id):
    """Marca la factura como anulada en el sistema."""
    try:
        anular_factura(id)
        flash('Factura anulada en el sistema.', 'success')
    except ValueError as exc:
        flash(str(exc), 'danger')
    return redirect(url_for('facturacion.detalle', id=id))


# ──────────────────────────────────────────────────────────────
# Libro IVA ventas
# ──────────────────────────────────────────────────────────────

@facturacion_bp.route('/libro-iva')
@login_required
def libro_iva():
    """Muestra el libro IVA ventas para el período seleccionado."""
    desde_str = request.args.get('desde', '')
    hasta_str = request.args.get('hasta', '')

    hoy = date.today()
    desde = _parse_date(desde_str, default=date(hoy.year, hoy.month, 1))
    hasta = _parse_date(hasta_str, default=hoy)

    facturas = libro_iva_ventas(desde, hasta)

    total_neto = sum(float(f.subtotal) for f in facturas)
    total_iva = sum(float(f.iva) for f in facturas)
    total_total = sum(float(f.total) for f in facturas)

    return render_template(
        'facturacion/libro_iva.html',
        facturas=facturas,
        desde=desde,
        hasta=hasta,
        total_neto=total_neto,
        total_iva=total_iva,
        total_total=total_total,
        title='Libro IVA Ventas',
    )


# ──────────────────────────────────────────────────────────────
# Clientes de facturación
# ──────────────────────────────────────────────────────────────

@facturacion_bp.route('/clientes')
@login_required
def clientes():
    """Lista clientes de facturación."""
    clientes_list = (
        ClienteFacturacion.query
        .order_by(ClienteFacturacion.nombre)
        .all()
    )
    return render_template(
        'facturacion/clientes.html',
        clientes=clientes_list,
        condiciones_iva=dict(CONDICIONES_IVA),
        title='Clientes de Facturación',
    )


@facturacion_bp.route('/clientes/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_cliente():
    """Crea un nuevo cliente de facturación."""
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        condicion_iva = request.form.get('condicion_iva', 'CF')
        cuit = request.form.get('cuit', '').strip() or None
        direccion = request.form.get('direccion', '').strip() or None
        email = request.form.get('email', '').strip() or None

        if not nombre:
            flash('El nombre es obligatorio.', 'danger')
        else:
            try:
                cliente = crear_cliente(
                    nombre=nombre,
                    condicion_iva=condicion_iva,
                    cuit=cuit,
                    direccion=direccion,
                    email=email,
                )
                flash(f'Cliente "{cliente.nombre}" creado correctamente.', 'success')
                return redirect(url_for('facturacion.clientes'))
            except ValueError as exc:
                flash(str(exc), 'danger')

    return render_template(
        'facturacion/cliente_form.html',
        cliente=None,
        condiciones_iva=CONDICIONES_IVA,
        title='Nuevo Cliente',
    )


@facturacion_bp.route('/clientes/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_cliente(id):
    """Edita un cliente de facturación existente."""
    cliente = db.get_or_404(ClienteFacturacion, id)

    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        condicion_iva = request.form.get('condicion_iva', 'CF')
        cuit = request.form.get('cuit', '').strip() or None
        direccion = request.form.get('direccion', '').strip() or None
        email = request.form.get('email', '').strip() or None

        if not nombre:
            flash('El nombre es obligatorio.', 'danger')
        else:
            try:
                actualizar_cliente(
                    cliente=cliente,
                    nombre=nombre,
                    condicion_iva=condicion_iva,
                    cuit=cuit,
                    direccion=direccion,
                    email=email,
                )
                flash('Cliente actualizado correctamente.', 'success')
                return redirect(url_for('facturacion.clientes'))
            except ValueError as exc:
                flash(str(exc), 'danger')

    return render_template(
        'facturacion/cliente_form.html',
        cliente=cliente,
        condiciones_iva=CONDICIONES_IVA,
        title='Editar Cliente',
    )
