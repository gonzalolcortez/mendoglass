from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from models import (
    db,
    Cliente,
    Proveedor,
    Taller,
    Venta,
    IngresoMercaderia,
    MovimientoCaja,
    FORMAS_PAGO,
    ClienteCuentaCorrienteMovimiento,
    registrar_movimiento_cuenta_corriente,
    registrar_movimiento_cc_proveedor,
    ProveedorCuentaCorrienteMovimiento,
    Producto,
    obtener_saldos_clientes,
    obtener_saldos_proveedores,
    obtener_cuenta_producto,
    obtener_saldos_por_cuenta_desde_movimientos,
    distribuir_monto_entre_cuentas,
)
from sqlalchemy import func
from sqlalchemy.orm import selectinload

clientes_bp = Blueprint('clientes', __name__)


def _adjuntar_saldos_clientes(clientes):
    saldos = obtener_saldos_clientes([cliente.id for cliente in clientes]) if clientes else {}
    for cliente in clientes:
        cliente.saldo_cc = saldos.get(cliente.id, 0.0)


def _adjuntar_saldos_proveedores(proveedores):
    saldos = obtener_saldos_proveedores([proveedor.id for proveedor in proveedores]) if proveedores else {}
    for proveedor in proveedores:
        proveedor.saldo_cc = saldos.get(proveedor.id, 0.0)


def _calcular_saldo_desde_movimientos(movimientos):
    saldo = 0.0
    for movimiento in movimientos:
        monto = float(movimiento.monto or 0.0)
        if movimiento.tipo == 'cargo':
            saldo += monto
        else:
            saldo -= monto
    return round(saldo, 2)


@clientes_bp.route('/')
@login_required
def index():
    tab = request.args.get('tab', 'clientes')
    q = request.args.get('q', '')

    if tab == 'proveedores':
        if q:
            proveedores = Proveedor.query.filter(
                db.or_(
                    Proveedor.nombre.ilike(f'%{q}%'),
                    Proveedor.apellido.ilike(f'%{q}%'),
                    Proveedor.telefono.ilike(f'%{q}%'),
                    Proveedor.email.ilike(f'%{q}%'),
                )
            ).order_by(Proveedor.apellido).all()
        else:
            proveedores = Proveedor.query.order_by(Proveedor.apellido).all()
        _adjuntar_saldos_proveedores(proveedores)
        proveedores_ids = [p.id for p in proveedores]
        ingresos_count = {}
        if proveedores_ids:
            rows = (db.session.query(IngresoMercaderia.proveedor_id, func.count(IngresoMercaderia.id))
                    .filter(IngresoMercaderia.proveedor_id.in_(proveedores_ids))
                    .group_by(IngresoMercaderia.proveedor_id)
                    .all())
            ingresos_count = {pid: cnt for pid, cnt in rows}
        return render_template('clientes/index.html', clientes=[], proveedores=proveedores,
                               talleres_count={}, ingresos_count=ingresos_count,
                               tab=tab, q=q)

    if q:
        clientes = Cliente.query.filter(
            db.or_(
                Cliente.nombre.ilike(f'%{q}%'),
                Cliente.apellido.ilike(f'%{q}%'),
                Cliente.telefono.ilike(f'%{q}%'),
                Cliente.email.ilike(f'%{q}%'),
            )
        ).order_by(Cliente.apellido).all()
    else:
        clientes = Cliente.query.order_by(Cliente.apellido).all()
    _adjuntar_saldos_clientes(clientes)
    cliente_ids = [c.id for c in clientes]
    talleres_count = {}
    if cliente_ids:
        rows = (db.session.query(Taller.cliente_id, func.count(Taller.id))
                .filter(Taller.cliente_id.in_(cliente_ids))
                .group_by(Taller.cliente_id)
                .all())
        talleres_count = {cid: cnt for cid, cnt in rows}
    return render_template('clientes/index.html', clientes=clientes, proveedores=[],
                           talleres_count=talleres_count, ingresos_count={},
                           tab=tab, q=q)


@clientes_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if request.method == 'POST':
        cliente = Cliente(
            nombre=request.form['nombre'].strip(),
            apellido=request.form['apellido'].strip(),
            telefono=request.form.get('telefono', '').strip(),
            email=request.form.get('email', '').strip(),
            direccion=request.form.get('direccion', '').strip(),
            cuit=request.form.get('cuit', '').strip() or None,
            condicion_iva=request.form.get('condicion_iva', 'CF'),
            notas=request.form.get('notas', '').strip(),
        )
        db.session.add(cliente)
        db.session.commit()
        flash('Cliente creado correctamente.', 'success')
        return redirect(url_for('clientes.index'))
    return render_template('clientes/form.html', entity=None, titulo='Nuevo Cliente',
                           cancel_url=url_for('clientes.index'), es_cliente=True)


@clientes_bp.route('/<int:id>')
@login_required
def detalle(id):
    cliente = (
        Cliente.query
        .options(
            selectinload(Cliente.talleres).selectinload(Taller.productos_usados),
            selectinload(Cliente.talleres).selectinload(Taller.servicios_usados),
            selectinload(Cliente.ventas).selectinload(Venta.items),
        )
        .filter_by(id=id)
        .first_or_404()
    )
    movimientos_cc = (
        ClienteCuentaCorrienteMovimiento.query
        .filter_by(cliente_id=cliente.id)
        .order_by(ClienteCuentaCorrienteMovimiento.fecha.desc())
        .all()
    )
    cliente.saldo_cc = _calcular_saldo_desde_movimientos(movimientos_cc)
    formas_pago_cc = [fp for fp in FORMAS_PAGO if fp[0] != 'cuenta_corriente']
    return render_template(
        'clientes/detail.html',
        cliente=cliente,
        movimientos_cc=movimientos_cc,
        formas_pago_cc=formas_pago_cc,
    )


@clientes_bp.route('/<int:id>/cuenta_corriente/pago', methods=['POST'])
@login_required
def registrar_pago_cc(id):
    cliente = Cliente.query.get_or_404(id)

    try:
        monto = round(float(request.form.get('monto') or 0), 2)
    except (TypeError, ValueError):
        monto = 0

    if monto <= 0:
        flash('Ingrese un monto válido para registrar el pago.', 'danger')
        return redirect(url_for('clientes.detalle', id=cliente.id))

    forma_pago = request.form.get('forma_pago', 'efectivo')
    formas_validas = dict(FORMAS_PAGO)
    if forma_pago not in formas_validas or forma_pago == 'cuenta_corriente':
        flash('Forma de pago inválida para registrar el pago.', 'danger')
        return redirect(url_for('clientes.detalle', id=cliente.id))

    concepto = request.form.get('concepto', '').strip() or 'Pago de cuenta corriente'
    movimientos_cc = (
        ClienteCuentaCorrienteMovimiento.query
        .filter_by(cliente_id=cliente.id)
        .order_by(ClienteCuentaCorrienteMovimiento.fecha.asc(), ClienteCuentaCorrienteMovimiento.id.asc())
        .all()
    )
    asignaciones = distribuir_monto_entre_cuentas(
        obtener_saldos_por_cuenta_desde_movimientos(movimientos_cc),
        monto,
    )

    for cuenta, importe in asignaciones.items():
        registrar_movimiento_cuenta_corriente(
            cliente_id=cliente.id,
            tipo='abono',
            monto=importe,
            concepto=concepto,
            cuenta=cuenta,
            referencia_tipo='cliente',
            referencia_id=cliente.id,
        )

        db.session.add(MovimientoCaja(
            tipo='ingreso',
            cuenta=cuenta,
            forma_pago=forma_pago,
            concepto=f'Pago CC - {cliente.nombre_completo}',
            monto=importe,
            referencia_tipo='cliente',
            referencia_id=cliente.id,
        ))
    db.session.commit()

    flash('Pago de cuenta corriente registrado correctamente.', 'success')
    return redirect(url_for('clientes.detalle', id=cliente.id))


@clientes_bp.route('/nuevo_rapido', methods=['POST'])
@login_required
def nuevo_rapido():
    nombre = request.form.get('nombre', '').strip()
    apellido = request.form.get('apellido', '').strip()
    if not nombre or not apellido:
        return jsonify({'error': 'Nombre y apellido son obligatorios.'}), 400
    cliente = Cliente(
        nombre=nombre,
        apellido=apellido,
        telefono=request.form.get('telefono', '').strip(),
        email=request.form.get('email', '').strip(),
        direccion=request.form.get('direccion', '').strip(),
        notas=request.form.get('notas', '').strip(),
    )
    db.session.add(cliente)
    db.session.commit()
    return jsonify({'id': cliente.id, 'nombre_completo': cliente.nombre_completo,
                    'telefono': cliente.telefono})


@clientes_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    cliente = Cliente.query.get_or_404(id)
    if request.method == 'POST':
        cliente.nombre = request.form['nombre'].strip()
        cliente.apellido = request.form['apellido'].strip()
        cliente.telefono = request.form.get('telefono', '').strip()
        cliente.email = request.form.get('email', '').strip()
        cliente.direccion = request.form.get('direccion', '').strip()
        cliente.cuit = request.form.get('cuit', '').strip() or None
        cliente.condicion_iva = request.form.get('condicion_iva', 'CF')
        cliente.notas = request.form.get('notas', '').strip()
        db.session.commit()
        flash('Cliente actualizado correctamente.', 'success')
        return redirect(url_for('clientes.detalle', id=cliente.id))
    return render_template('clientes/form.html', entity=cliente, titulo='Editar Cliente',
                           cancel_url=url_for('clientes.detalle', id=cliente.id), es_cliente=True)


@clientes_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar(id):
    cliente = Cliente.query.get_or_404(id)
    if cliente.talleres or cliente.ventas:
        flash('No se puede eliminar un cliente con talleres o ventas asociadas.', 'danger')
        return redirect(url_for('clientes.detalle', id=id))
    db.session.delete(cliente)
    db.session.commit()
    flash('Cliente eliminado.', 'success')
    return redirect(url_for('clientes.index'))


# ── Proveedores ──────────────────────────────────────────────────────────────

@clientes_bp.route('/proveedor/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_proveedor():
    if request.method == 'POST':
        proveedor = Proveedor(
            nombre=request.form['nombre'].strip(),
            apellido=request.form['apellido'].strip(),
            telefono=request.form.get('telefono', '').strip(),
            email=request.form.get('email', '').strip(),
            direccion=request.form.get('direccion', '').strip(),
            notas=request.form.get('notas', '').strip(),
        )
        db.session.add(proveedor)
        db.session.commit()
        flash('Proveedor creado correctamente.', 'success')
        return redirect(url_for('clientes.index', tab='proveedores'))
    return render_template('clientes/form.html', entity=None, titulo='Nuevo Proveedor',
                           cancel_url=url_for('clientes.index', tab='proveedores'), es_cliente=False)


@clientes_bp.route('/proveedor/<int:id>')
@login_required
def detalle_proveedor(id):
    proveedor = (
        Proveedor.query
        .options(selectinload(Proveedor.ingresos).selectinload(IngresoMercaderia.items))
        .filter_by(id=id)
        .first_or_404()
    )
    movimientos_cc = (
        ProveedorCuentaCorrienteMovimiento.query
        .filter_by(proveedor_id=proveedor.id)
        .order_by(ProveedorCuentaCorrienteMovimiento.fecha.desc())
        .all()
    )
    proveedor.saldo_cc = _calcular_saldo_desde_movimientos(movimientos_cc)
    formas_pago_cc = [fp for fp in FORMAS_PAGO if fp[0] != 'cuenta_corriente']
    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
    return render_template(
        'clientes/detail_proveedor.html',
        proveedor=proveedor,
        movimientos_cc=movimientos_cc,
        formas_pago_cc=formas_pago_cc,
        productos=productos,
    )


@clientes_bp.route('/proveedor/<int:id>/cuenta_corriente/pago', methods=['POST'])
@login_required
def registrar_pago_cc_proveedor(id):
    proveedor = Proveedor.query.get_or_404(id)

    try:
        monto = round(float(request.form.get('monto') or 0), 2)
    except (TypeError, ValueError):
        monto = 0

    if monto <= 0:
        flash('Ingrese un monto válido para registrar el pago al proveedor.', 'danger')
        return redirect(url_for('clientes.detalle_proveedor', id=proveedor.id))

    forma_pago = request.form.get('forma_pago', 'efectivo')
    formas_validas = dict(FORMAS_PAGO)
    if forma_pago not in formas_validas or forma_pago == 'cuenta_corriente':
        flash('Forma de pago inválida para registrar pago de proveedor.', 'danger')
        return redirect(url_for('clientes.detalle_proveedor', id=proveedor.id))

    concepto = request.form.get('concepto', '').strip() or 'Pago de cuenta corriente a proveedor'
    movimientos_cc = (
        ProveedorCuentaCorrienteMovimiento.query
        .filter_by(proveedor_id=proveedor.id)
        .order_by(ProveedorCuentaCorrienteMovimiento.fecha.asc(), ProveedorCuentaCorrienteMovimiento.id.asc())
        .all()
    )
    asignaciones = distribuir_monto_entre_cuentas(
        obtener_saldos_por_cuenta_desde_movimientos(movimientos_cc),
        monto,
    )

    for cuenta, importe in asignaciones.items():
        registrar_movimiento_cc_proveedor(
            proveedor_id=proveedor.id,
            tipo='abono',
            monto=importe,
            concepto=concepto,
            cuenta=cuenta,
            referencia_tipo='proveedor',
            referencia_id=proveedor.id,
        )

        db.session.add(MovimientoCaja(
            tipo='egreso',
            cuenta=cuenta,
            forma_pago=forma_pago,
            concepto=f'Pago CC proveedor - {proveedor.nombre_completo}',
            monto=importe,
            referencia_tipo='proveedor',
            referencia_id=proveedor.id,
        ))
    db.session.commit()

    flash('Pago al proveedor registrado correctamente.', 'success')
    return redirect(url_for('clientes.detalle_proveedor', id=proveedor.id))


@clientes_bp.route('/proveedor/<int:id>/cuenta_corriente/devolucion', methods=['POST'])
@login_required
def registrar_devolucion_proveedor(id):
    proveedor = Proveedor.query.get_or_404(id)
    producto_id = request.form.get('producto_id')

    try:
        cantidad = int(request.form.get('cantidad') or 0)
    except (TypeError, ValueError):
        cantidad = 0

    try:
        precio = round(float(request.form.get('precio') or 0), 2)
    except (TypeError, ValueError):
        precio = 0

    if not producto_id:
        flash('Debe seleccionar un producto para devolver al proveedor.', 'danger')
        return redirect(url_for('clientes.detalle_proveedor', id=proveedor.id))
    if cantidad <= 0 or precio <= 0:
        flash('Cantidad y precio deben ser mayores a cero.', 'danger')
        return redirect(url_for('clientes.detalle_proveedor', id=proveedor.id))

    producto = Producto.query.get_or_404(int(producto_id))
    if producto.stock_actual < cantidad:
        flash(f'Stock insuficiente para devolver "{producto.nombre}" (disponible: {producto.stock_actual}).', 'danger')
        return redirect(url_for('clientes.detalle_proveedor', id=proveedor.id))

    total = round(cantidad * precio, 2)
    modo = request.form.get('modo', 'cuenta_corriente')
    if modo not in ('cuenta_corriente', 'efectivo', 'mercado_pago'):
        flash('Modo de devolución inválido.', 'danger')
        return redirect(url_for('clientes.detalle_proveedor', id=proveedor.id))

    producto.stock_actual -= cantidad
    cuenta = obtener_cuenta_producto(producto, 'compra')

    concepto_cc = f'Devolución mercadería: {producto.nombre} x{cantidad}'
    registrar_movimiento_cc_proveedor(
        proveedor_id=proveedor.id,
        tipo='abono',
        monto=total,
        concepto=concepto_cc,
        cuenta=cuenta,
        referencia_tipo='devolucion_proveedor',
        referencia_id=producto.id,
    )

    if modo != 'cuenta_corriente':
        db.session.add(MovimientoCaja(
            tipo='ingreso',
            cuenta=cuenta,
            forma_pago=modo,
            concepto=f'Reintegro devolución proveedor - {proveedor.nombre_completo}',
            monto=total,
            referencia_tipo='proveedor',
            referencia_id=proveedor.id,
        ))

    db.session.commit()
    if modo == 'cuenta_corriente':
        flash('Devolución registrada. Se descontó del stock y se acreditó en cuenta corriente del proveedor.', 'success')
    else:
        flash('Devolución registrada. Se descontó del stock y se registró ingreso en caja.', 'success')
    return redirect(url_for('clientes.detalle_proveedor', id=proveedor.id))


@clientes_bp.route('/proveedor/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_proveedor(id):
    proveedor = Proveedor.query.get_or_404(id)
    if request.method == 'POST':
        proveedor.nombre = request.form['nombre'].strip()
        proveedor.apellido = request.form['apellido'].strip()
        proveedor.telefono = request.form.get('telefono', '').strip()
        proveedor.email = request.form.get('email', '').strip()
        proveedor.direccion = request.form.get('direccion', '').strip()
        proveedor.notas = request.form.get('notas', '').strip()
        db.session.commit()
        flash('Proveedor actualizado correctamente.', 'success')
        return redirect(url_for('clientes.detalle_proveedor', id=proveedor.id))
    return render_template('clientes/form.html', entity=proveedor, titulo='Editar Proveedor',
                           cancel_url=url_for('clientes.detalle_proveedor', id=proveedor.id), es_cliente=False)


@clientes_bp.route('/proveedor/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_proveedor(id):
    proveedor = Proveedor.query.get_or_404(id)
    if proveedor.ingresos:
        flash('No se puede eliminar un proveedor con ingresos de mercadería asociados.', 'danger')
        return redirect(url_for('clientes.detalle_proveedor', id=id))
    db.session.delete(proveedor)
    db.session.commit()
    flash('Proveedor eliminado.', 'success')
    return redirect(url_for('clientes.index', tab='proveedores'))
