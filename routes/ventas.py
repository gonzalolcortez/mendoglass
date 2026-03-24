import base64
import io
import json
import os

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from models import (
    db, Venta, VentaItem, Producto, Servicio, Cliente,
    MovimientoCaja, FORMAS_PAGO, Categoria,
)
from datetime import datetime, date

ventas_bp = Blueprint('ventas', __name__)

# IVA alícuotas disponibles (tasa%, id_afip)
ALICUOTAS_IVA = [
    (0.0,   'Exento / 0%'),
    (10.5,  '10.5%'),
    (21.0,  '21%'),
    (27.0,  '27%'),
]

# Condiciones de venta (forma de pago)
CONDICIONES_VENTA = FORMAS_PAGO

# Map alicuota → AFIP iva_id
_AFIP_IVA_ID = {0.0: 4, 10.5: 8, 21.0: 5, 27.0: 6}


_TIPO_CBTE_LETRA = {
    1: 'A',
    6: 'B',
    11: 'C',
}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _siguiente_numero(tipo_comprobante: str, punto_venta: int | None = None) -> int:
    """Returns the next sequential comprobante number."""
    query = Venta.query.filter_by(tipo_comprobante=tipo_comprobante)
    if tipo_comprobante != 'NOTA_VENTA':
        query = query.filter_by(punto_venta=punto_venta)

    ultimo = (
        query
        .filter(Venta.numero_comprobante.isnot(None))
        .order_by(Venta.numero_comprobante.desc())
        .first()
    )
    if ultimo:
        return ultimo.numero_comprobante + 1
    return 0 if tipo_comprobante == 'NOTA_VENTA' else 1


def _tipo_cbte_afip(condicion_iva: str) -> int:
    """Determine AFIP tipo_cbte based on customer's condicion_iva."""
    if condicion_iva == 'RI':
        return 1   # Factura A
    elif condicion_iva in ('M', 'EX'):
        return 11  # Factura C
    else:
        return 6   # Factura B (Consumidor Final)


def _env_first(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, '').strip()
        if value:
            return value
    return ''


def _datos_emisor_factura() -> dict:
    """Arma los datos del emisor para la plantilla imprimible de factura."""
    cuit_raw = _env_first('ARCA_CUIT', 'AFIP_CUIT')
    if not cuit_raw:
        try:
            from modules.facturacion.afip_client import (
                _autodescubrir_cert_key,
                _extraer_cuit_desde_certificado,
            )

            cert_path, _ = _autodescubrir_cert_key()
            if cert_path:
                cuit_raw = _extraer_cuit_desde_certificado(cert_path)
        except Exception:
            cuit_raw = ''

    cuit_digits = ''.join(ch for ch in cuit_raw if ch.isdigit())
    defaults = {}
    if cuit_digits == '30718185854':
        defaults = {
            'razon_social': 'URITIC S. A. S.',
            'direccion': 'San Juan 721, Ciudad, Mendoza',
            'condicion_iva': 'Responsable Inscripto',
            'ingresos_brutos': '0951886',
            'inicio_actividades': '01/07/2023',
            'telefono': '+54 9 261 723-4524',
            'email': 'info@uritic.com.ar',
        }

    cuit = cuit_digits if cuit_digits else 'No configurado'
    return {
        'razon_social': _env_first('FACTURA_EMISOR_RAZON_SOCIAL', 'ARCA_RAZON_SOCIAL', 'EMPRESA_NOMBRE') or defaults.get('razon_social') or 'Emisor no configurado',
        'direccion': _env_first('FACTURA_EMISOR_DIRECCION', 'EMPRESA_DIRECCION') or defaults.get('direccion') or 'Dirección no configurada',
        'condicion_iva': _env_first('FACTURA_EMISOR_CONDICION_IVA', 'EMPRESA_CONDICION_IVA') or defaults.get('condicion_iva') or 'Responsable Inscripto',
        'ingresos_brutos': _env_first('FACTURA_EMISOR_IIBB', 'EMPRESA_IIBB') or defaults.get('ingresos_brutos') or 'No informado',
        'inicio_actividades': _env_first('FACTURA_EMISOR_INICIO_ACTIVIDADES', 'EMPRESA_INICIO_ACTIVIDADES') or defaults.get('inicio_actividades') or 'No informado',
        'telefono': _env_first('FACTURA_EMISOR_TELEFONO', 'EMPRESA_TELEFONO') or defaults.get('telefono') or '',
        'email': _env_first('FACTURA_EMISOR_EMAIL', 'EMPRESA_EMAIL') or defaults.get('email') or '',
        'cuit': cuit,
    }


def _qr_afip_data(venta: Venta, emisor: dict) -> dict | None:
    """Construye URL e imagen base64 del QR AFIP para comprobantes con CAE."""
    if not venta.cae or not venta.numero_comprobante:
        return None

    try:
        import qrcode
        from modules.facturacion.afip_client import tipo_doc_receptor

        cuit_emisor = str(emisor.get('cuit', '')).replace('-', '').replace('.', '').strip()
        if not (cuit_emisor.isdigit() and len(cuit_emisor) == 11):
            return None

        condicion_iva = (venta.cliente.condicion_iva if venta.cliente else 'CF') or 'CF'
        cuit_cliente = venta.cliente.cuit if venta.cliente else None
        tipo_doc, nro_doc = tipo_doc_receptor(condicion_iva, cuit_cliente)

        payload = {
            'ver': 1,
            'fecha': (venta.fecha or datetime.now()).strftime('%Y-%m-%d'),
            'cuit': int(cuit_emisor),
            'ptoVta': int(venta.punto_venta or 1),
            'tipoCmp': int(venta.tipo_cbte_afip or 6),
            'nroCmp': int(venta.numero_comprobante),
            'importe': round(float(venta.total or 0.0), 2),
            'moneda': 'PES',
            'ctz': 1,
            'tipoDocRec': int(tipo_doc),
            'nroDocRec': int(str(nro_doc or '0')),
            'tipoCodAut': 'E',
            'codAut': int(str(venta.cae)),
        }

        payload_b64 = base64.b64encode(
            json.dumps(payload, separators=(',', ':')).encode('utf-8')
        ).decode('utf-8')
        qr_url = f'https://www.afip.gob.ar/fe/qr/?p={payload_b64}'

        qr_img = qrcode.make(qr_url)
        buffer = io.BytesIO()
        qr_img.save(buffer, format='PNG')
        qr_png_b64 = base64.b64encode(buffer.getvalue()).decode('ascii')

        return {
            'url': qr_url,
            'png_b64': qr_png_b64,
        }
    except Exception:
        return None


def _emitir_ante_afip(venta: Venta):
    """Sends the venta to ARCA/AFIP and stores CAE + numero. Raises on error."""
    from modules.facturacion.afip_client import (
        AfipClient, AfipError, tipo_doc_receptor,
    )

    cliente = venta.cliente
    condicion_iva = (cliente.condicion_iva if cliente else 'CF') or 'CF'
    cuit = cliente.cuit if cliente else None

    tipo_cbte = _tipo_cbte_afip(condicion_iva)
    venta.tipo_cbte_afip = tipo_cbte

    afip = AfipClient()
    afip.conectar()

    ultimo = afip.ultimo_numero(tipo_cbte, venta.punto_venta)
    siguiente = ultimo + 1

    tipo_doc, nro_doc = tipo_doc_receptor(condicion_iva, cuit)

    fecha_str = (venta.fecha or datetime.now()).strftime('%Y%m%d')

    # Aggregate IVA by rate for multi-rate support
    ivas_agrupados: dict[float, dict] = {}
    for item in venta.items:
        alicuota = item.alicuota_iva or 0.0
        if alicuota not in ivas_agrupados:
            ivas_agrupados[alicuota] = {
                'base_imp': 0.0,
                'importe': 0.0,
                'iva_id': _AFIP_IVA_ID.get(alicuota, 5),
            }
        base = item.subtotal_neto or 0.0
        ivas_agrupados[alicuota]['base_imp'] += base
        ivas_agrupados[alicuota]['importe'] += round(base * alicuota / 100, 2)

    # Build the list of IVA entries to pass to solicitar_cae
    ivas = [
        {
            'iva_id': datos['iva_id'],
            'base_imp': round(datos['base_imp'], 2),
            'importe': round(datos['importe'], 2),
        }
        for datos in ivas_agrupados.values()
        if datos['importe'] > 0
    ]

    imp_neto = venta.subtotal or 0.0
    imp_iva = venta.iva_total or 0.0
    imp_total = venta.total or 0.0

    resultado = afip.solicitar_cae(
        tipo_cbte=tipo_cbte,
        punto_vta=venta.punto_venta,
        numero=siguiente,
        fecha=fecha_str,
        concepto=1,  # Productos
        tipo_doc=tipo_doc,
        nro_doc=nro_doc,
        imp_neto=round(imp_neto, 2),
        imp_iva=round(imp_iva, 2),
        imp_total=round(imp_total, 2),
        ivas=ivas if ivas else None,
    )

    venta.numero_comprobante = resultado['numero']
    venta.cae = resultado['cae']

    vto_raw = resultado.get('vencimiento_cae', '')
    try:
        venta.fecha_vencimiento_cae = datetime.strptime(vto_raw, '%Y%m%d').date()
    except (ValueError, TypeError):
        venta.fecha_vencimiento_cae = None

    db.session.commit()
    return afip.mensaje_configuracion()


def _parse_items_from_form():
    """Extract and validate item arrays from the POST request."""
    codigos = request.form.getlist('item_codigo[]')
    descripciones = request.form.getlist('item_descripcion[]')
    cantidades = request.form.getlist('item_cantidad[]')
    unidades = request.form.getlist('item_unidad[]')
    precios = request.form.getlist('item_precio[]')
    bonificaciones = request.form.getlist('item_bonificacion[]')
    alicuotas = request.form.getlist('item_alicuota[]')
    producto_ids = request.form.getlist('item_producto_id[]')

    items = []
    for i, desc in enumerate(descripciones):
        if not desc.strip():
            continue
        items.append({
            'codigo': codigos[i] if i < len(codigos) else '',
            'descripcion': desc.strip(),
            'cantidad': float(cantidades[i] or 1) if i < len(cantidades) else 1.0,
            'unidad': unidades[i] if i < len(unidades) else 'unidad',
            'precio': float(precios[i] or 0) if i < len(precios) else 0.0,
            'bonificacion': float(bonificaciones[i] or 0) if i < len(bonificaciones) else 0.0,
            'alicuota': float(alicuotas[i] or 21) if i < len(alicuotas) else 21.0,
            'producto_id': producto_ids[i] if i < len(producto_ids) else '',
        })
    return items


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@ventas_bp.route('/')
@ventas_bp.route('/listado')
@login_required
def index():
    ventas = Venta.query.order_by(Venta.fecha.desc()).all()
    return render_template('ventas/index.html', ventas=ventas)


@ventas_bp.route('/nueva', methods=['GET'])
@login_required
def nueva():
    clientes = Cliente.query.order_by(Cliente.apellido).all()
    productos_obj = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
    servicios_obj = Servicio.query.filter_by(activo=True).order_by(Servicio.nombre).all()
    categorias = Categoria.query.order_by(Categoria.nombre).all()

    productos_json = [
        {
            'id': p.id,
            'nombre': p.nombre,
            'codigo_barras': p.codigo_barras or '',
            'precio_venta': p.precio_venta,
            'stock_actual': p.stock_actual,
            'categoria_id': p.categoria_id,
            'unidad': p.unidad or 'unidad',
        }
        for p in productos_obj
    ]
    servicios_json = [
        {'id': s.id, 'nombre': s.nombre, 'precio': s.precio}
        for s in servicios_obj
    ]

    return render_template(
        'ventas/form.html',
        clientes=clientes,
        productos=productos_json,
        servicios=servicios_json,
        formas_pago=CONDICIONES_VENTA,
        alicuotas=ALICUOTAS_IVA,
        categorias=categorias,
        tipos_comprobante=Venta.TIPOS_COMPROBANTE,
        now=datetime.now(),
    )


@ventas_bp.route('/guardar', methods=['POST'])
@login_required
def guardar():
    tipo_comprobante = request.form.get('tipo_comprobante', 'NOTA_VENTA')
    es_factura = tipo_comprobante == 'FACTURA'
    punto_venta = int(request.form.get('punto_venta', 1) or 1) if es_factura else None
    cliente_id = request.form.get('cliente_id') or None
    forma_pago = request.form.get('forma_pago', 'efectivo')
    notas = request.form.get('notas', '').strip()

    items_data = _parse_items_from_form()
    if not items_data:
        flash('Debe agregar al menos un producto o servicio.', 'danger')
        return redirect(url_for('ventas.nueva'))

    # Stock validation
    errores = []
    for it in items_data:
        pid = it['producto_id']
        if pid:
            prod = Producto.query.get(int(pid))
            if prod:
                cant_int = int(it['cantidad'])
                if prod.stock_actual < cant_int:
                    errores.append(
                        f'Stock insuficiente para "{prod.nombre}" '
                        f'(disponible: {prod.stock_actual}).'
                    )
    if errores:
        for e in errores:
            flash(e, 'danger')
        return redirect(url_for('ventas.nueva'))

    # Create venta
    venta = Venta(
        tipo_comprobante=tipo_comprobante,
        punto_venta=punto_venta,
        cliente_id=int(cliente_id) if cliente_id else None,
        forma_pago=forma_pago,
        notas=notas,
        fecha=datetime.now(),
    )
    db.session.add(venta)
    db.session.flush()

    subtotal_neto = 0.0
    iva_total = 0.0

    for it in items_data:
        cant = it['cantidad']
        precio = it['precio']
        bonif = it['bonificacion']
        alicuota = it['alicuota'] if es_factura else 0.0
        pid = it['producto_id']

        precio_bonif = precio * (1 - bonif / 100) if bonif else precio
        if es_factura:
            sub_neto = round(precio_bonif * cant, 2)
            iva_monto = round(sub_neto * alicuota / 100, 2)
            sub_total = round(sub_neto + iva_monto, 2)
        else:
            sub_total = round(precio_bonif * cant, 2)
            sub_neto = sub_total
            iva_monto = 0.0

        vi = VentaItem(
            venta_id=venta.id,
            tipo='producto' if pid else 'libre',
            producto_id=int(pid) if pid else None,
            codigo=it['codigo'],
            descripcion_libre=it['descripcion'],
            unidad=it['unidad'] or 'unidad',
            cantidad=cant,
            precio_unitario=precio,
            bonificacion=bonif,
            alicuota_iva=alicuota,
            subtotal_neto=sub_neto,
            subtotal=sub_total,
        )
        db.session.add(vi)

        # Discount stock
        if pid:
            prod = Producto.query.get(int(pid))
            if prod:
                prod.stock_actual -= int(cant)

        subtotal_neto += sub_neto
        iva_total += iva_monto

    total = round(subtotal_neto + iva_total, 2)
    venta.subtotal = round(subtotal_neto, 2)
    venta.iva_total = round(iva_total, 2)
    venta.total = total
    venta.pagado = True

    # Assign comprobante number for NOTA_VENTA now; FACTURA gets it from AFIP
    if tipo_comprobante == 'NOTA_VENTA':
        venta.numero_comprobante = _siguiente_numero('NOTA_VENTA')

    # Cash movement
    cliente_label = ''
    if cliente_id:
        c = Cliente.query.get(int(cliente_id))
        if c:
            cliente_label = f' – {c.nombre_completo}'
    tipo_label = dict(Venta.TIPOS_COMPROBANTE).get(tipo_comprobante, tipo_comprobante)

    mov = MovimientoCaja(
        tipo='ingreso',
        cuenta='venta_productos',
        forma_pago=forma_pago,
        concepto=f'{tipo_label}{cliente_label or " – Mostrador"}',
        monto=total,
        referencia_tipo='venta',
        referencia_id=venta.id,
        fecha=datetime.now(),
    )
    db.session.add(mov)
    db.session.commit()

    # AFIP emission for FACTURA
    if tipo_comprobante == 'FACTURA':
        try:
            mensaje_config = _emitir_ante_afip(venta)
            flash(
                f'Factura emitida exitosamente. '
                f'N° {venta.numero_display} | CAE: {venta.cae}',
                'success',
            )
            if mensaje_config:
                flash(mensaje_config, 'info')
        except Exception as exc:
            flash(
                f'Venta guardada pero la emisión ante ARCA falló: {exc}. '
                f'Puede reintentarse desde el detalle.',
                'warning',
            )
    else:
        flash(
            f'Nota de Venta {venta.numero_display} registrada por '
            f'${total:,.2f}. Stock actualizado.',
            'success',
        )

    return redirect(url_for('ventas.detalle', id=venta.id))


@ventas_bp.route('/<int:id>')
@login_required
def detalle(id):
    venta = Venta.query.get_or_404(id)

    # IVA breakdown per alicuota
    iva_breakdown: dict[float, dict] = {}
    for item in venta.items:
        alicuota = item.alicuota_iva or 0.0
        if alicuota not in iva_breakdown:
            iva_breakdown[alicuota] = {'neto': 0.0, 'iva': 0.0}
        iva_breakdown[alicuota]['neto'] += item.subtotal_neto or 0.0
        iva_breakdown[alicuota]['iva'] += item.iva_monto

    return render_template(
        'ventas/detalle.html',
        venta=venta,
        iva_breakdown=iva_breakdown,
    )


@ventas_bp.route('/<int:id>/emitir', methods=['POST'])
@login_required
def emitir(id):
    """Retry AFIP emission for a FACTURA that failed on first attempt."""
    venta = Venta.query.get_or_404(id)
    if venta.tipo_comprobante != 'FACTURA':
        flash('Solo las facturas pueden emitirse ante ARCA.', 'warning')
        return redirect(url_for('ventas.detalle', id=id))
    if venta.cae:
        flash('Esta factura ya tiene CAE asignado.', 'info')
        return redirect(url_for('ventas.detalle', id=id))
    try:
        mensaje_config = _emitir_ante_afip(venta)
        flash(f'Factura emitida. CAE: {venta.cae}', 'success')
        if mensaje_config:
            flash(mensaje_config, 'info')
    except Exception as exc:
        flash(f'Error al emitir: {exc}', 'danger')
    return redirect(url_for('ventas.detalle', id=id))


@ventas_bp.route('/<int:id>/imprimir')
@login_required
def imprimir(id):
    """Vista de impresión de factura electrónica."""
    venta = Venta.query.get_or_404(id)
    if venta.tipo_comprobante != 'FACTURA':
        flash('Solo se puede imprimir formato fiscal para comprobantes tipo FACTURA.', 'warning')
        return redirect(url_for('ventas.detalle', id=id))

    iva_breakdown: dict[float, dict] = {}
    for item in venta.items:
        alicuota = item.alicuota_iva or 0.0
        if alicuota not in iva_breakdown:
            iva_breakdown[alicuota] = {'neto': 0.0, 'iva': 0.0}
        iva_breakdown[alicuota]['neto'] += item.subtotal_neto or 0.0
        iva_breakdown[alicuota]['iva'] += item.iva_monto

    tipo_cbte = venta.tipo_cbte_afip or _tipo_cbte_afip((venta.cliente.condicion_iva if venta.cliente else 'CF') or 'CF')
    letra = _TIPO_CBTE_LETRA.get(tipo_cbte, 'B')
    emisor = _datos_emisor_factura()
    qr_afip = _qr_afip_data(venta, emisor)

    return render_template(
        'ventas/factura_print.html',
        venta=venta,
        iva_breakdown=iva_breakdown,
        emisor=emisor,
        letra=letra,
        qr_afip=qr_afip,
    )


@ventas_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar(id):
    venta = Venta.query.get_or_404(id)
    # Return stock
    for item in venta.items:
        if item.tipo == 'producto' and item.producto:
            item.producto.stock_actual += int(item.cantidad)
    MovimientoCaja.query.filter_by(referencia_tipo='venta', referencia_id=venta.id).delete()
    db.session.delete(venta)
    db.session.commit()
    flash('Venta eliminada y stock devuelto.', 'success')
    return redirect(url_for('ventas.index'))
