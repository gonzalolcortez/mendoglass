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


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _siguiente_numero(tipo_comprobante: str, punto_venta: int) -> int:
    """Returns the next sequential comprobante number for NOTA_VENTA."""
    ultimo = (
        Venta.query
        .filter_by(tipo_comprobante=tipo_comprobante, punto_venta=punto_venta)
        .filter(Venta.numero_comprobante.isnot(None))
        .order_by(Venta.numero_comprobante.desc())
        .first()
    )
    return (ultimo.numero_comprobante + 1) if ultimo else 1


def _tipo_cbte_afip(condicion_iva: str) -> int:
    """Determine AFIP tipo_cbte based on customer's condicion_iva."""
    if condicion_iva == 'RI':
        return 1   # Factura A
    elif condicion_iva in ('M', 'EX'):
        return 11  # Factura C
    else:
        return 6   # Factura B (Consumidor Final)


def _emitir_ante_afip(venta: Venta):
    """Sends the venta to ARCA/AFIP and stores CAE + numero. Raises on error."""
    from modules.facturacion.afip_client import (
        AfipClient, AfipError, tipo_doc_receptor,
        IVA_0, IVA_10_5, IVA_21, IVA_27,
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

    fecha_str = (venta.fecha or datetime.utcnow()).strftime('%Y%m%d')

    # Aggregate IVA by rate for multi-rate support
    ivas_agrupados: dict[float, dict] = {}
    for item in venta.items:
        alicuota = item.alicuota_iva or 0.0
        if alicuota not in ivas_agrupados:
            ivas_agrupados[alicuota] = {'base': 0.0, 'monto': 0.0,
                                         'iva_id': _AFIP_IVA_ID.get(alicuota, 5)}
        base = item.subtotal_neto or 0.0
        ivas_agrupados[alicuota]['base'] += base
        ivas_agrupados[alicuota]['monto'] += round(base * alicuota / 100, 2)

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
        alicuota_iva_id=list(ivas_agrupados.values())[0]['iva_id'] if ivas_agrupados else 5,
        alicuota_iva_pct=list(ivas_agrupados.keys())[0] if ivas_agrupados else 21.0,
    )

    venta.numero_comprobante = resultado['numero']
    venta.cae = resultado['cae']

    vto_raw = resultado.get('vencimiento_cae', '')
    try:
        venta.fecha_vencimiento_cae = datetime.strptime(vto_raw, '%Y%m%d').date()
    except (ValueError, TypeError):
        venta.fecha_vencimiento_cae = None

    db.session.commit()


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
        now=datetime.utcnow(),
    )


@ventas_bp.route('/guardar', methods=['POST'])
@login_required
def guardar():
    tipo_comprobante = request.form.get('tipo_comprobante', 'NOTA_VENTA')
    punto_venta = int(request.form.get('punto_venta', 1) or 1)
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
        fecha=datetime.utcnow(),
    )
    db.session.add(venta)
    db.session.flush()

    subtotal_neto = 0.0
    iva_total = 0.0

    for it in items_data:
        cant = it['cantidad']
        precio = it['precio']
        bonif = it['bonificacion']
        alicuota = it['alicuota']
        pid = it['producto_id']

        precio_bonif = precio * (1 - bonif / 100) if bonif else precio
        sub_neto = round(precio_bonif * cant, 2)
        iva_monto = round(sub_neto * alicuota / 100, 2)
        sub_total = round(sub_neto + iva_monto, 2)

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
        venta.numero_comprobante = _siguiente_numero('NOTA_VENTA', punto_venta)

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
        fecha=datetime.utcnow(),
    )
    db.session.add(mov)
    db.session.commit()

    # AFIP emission for FACTURA
    if tipo_comprobante == 'FACTURA':
        try:
            _emitir_ante_afip(venta)
            flash(
                f'Factura emitida exitosamente. '
                f'N° {venta.numero_display} | CAE: {venta.cae}',
                'success',
            )
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
        _emitir_ante_afip(venta)
        flash(f'Factura emitida. CAE: {venta.cae}', 'success')
    except Exception as exc:
        flash(f'Error al emitir: {exc}', 'danger')
    return redirect(url_for('ventas.detalle', id=id))


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
