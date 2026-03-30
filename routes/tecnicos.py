from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import (
    db,
    Tecnico,
    TecnicoCuentaCorrienteMovimiento,
    MovimientoCaja,
    Producto,
    CUENTAS_CAJA,
    FORMAS_PAGO,
    obtener_saldos_tecnicos,
    registrar_movimiento_cc_tecnico,
)

tecnicos_bp = Blueprint('tecnicos', __name__)


def _adjuntar_saldos_tecnicos(tecnicos):
    saldos = obtener_saldos_tecnicos([tecnico.id for tecnico in tecnicos]) if tecnicos else {}
    for tecnico in tecnicos:
        tecnico.saldo_cc = saldos.get(tecnico.id, 0.0)


def _calcular_saldo_desde_movimientos(movimientos):
    saldo = 0.0
    for movimiento in movimientos:
        monto = float(movimiento.monto or 0.0)
        if movimiento.tipo == 'cargo':
            saldo += monto
        else:
            saldo -= monto
    return round(saldo, 2)


@tecnicos_bp.route('/')
@login_required
def index():
    tecnicos = Tecnico.query.order_by(Tecnico.nombre).all()
    _adjuntar_saldos_tecnicos(tecnicos)
    return render_template('tecnicos/index.html', tecnicos=tecnicos)


@tecnicos_bp.route('/<int:id>')
@login_required
def detalle(id):
    tecnico = Tecnico.query.get_or_404(id)
    movimientos_cc = (
        TecnicoCuentaCorrienteMovimiento.query
        .filter_by(tecnico_id=tecnico.id)
        .order_by(TecnicoCuentaCorrienteMovimiento.fecha.desc())
        .all()
    )
    tecnico.saldo_cc = _calcular_saldo_desde_movimientos(movimientos_cc)
    cuentas_disponibles = [cuenta for cuenta in CUENTAS_CAJA if cuenta[0] != 'matias']
    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
    return render_template(
        'tecnicos/detail.html',
        tecnico=tecnico,
        movimientos_cc=movimientos_cc,
        cuentas_disponibles=cuentas_disponibles,
        formas_pago=FORMAS_PAGO,
        productos=productos,
    )


@tecnicos_bp.route('/<int:id>/cuenta-corriente/movimiento', methods=['POST'])
@login_required
def registrar_movimiento(id):
    tecnico = Tecnico.query.get_or_404(id)

    tipo = request.form.get('tipo', 'cargo')
    if tipo not in ('cargo', 'abono'):
        flash('Tipo de movimiento inválido para cuenta corriente de técnico.', 'danger')
        return redirect(url_for('tecnicos.detalle', id=tecnico.id))

    try:
        monto = round(float(request.form.get('monto') or 0), 2)
    except (TypeError, ValueError):
        monto = 0

    if monto <= 0:
        flash('Ingrese un monto válido para el movimiento.', 'danger')
        return redirect(url_for('tecnicos.detalle', id=tecnico.id))

    cuenta = request.form.get('cuenta', 'tecnicos')
    cuentas_validas = dict(CUENTAS_CAJA)
    if cuenta not in cuentas_validas:
        flash('Cuenta contable inválida para el movimiento del técnico.', 'danger')
        return redirect(url_for('tecnicos.detalle', id=tecnico.id))

    forma_pago = request.form.get('forma_pago', 'cuenta_corriente')
    formas_validas = dict(FORMAS_PAGO)
    if forma_pago not in formas_validas:
        flash('Forma de pago inválida para el movimiento del técnico.', 'danger')
        return redirect(url_for('tecnicos.detalle', id=tecnico.id))

    concepto = request.form.get('concepto', '').strip()
    if not concepto:
        concepto = 'Movimiento de cuenta corriente de técnico'

    registrar_movimiento_cc_tecnico(
        tecnico_id=tecnico.id,
        tipo=tipo,
        monto=monto,
        concepto=concepto,
        cuenta=cuenta,
        forma_pago=forma_pago,
        referencia_tipo='tecnico',
        referencia_id=tecnico.id,
    )

    mov_caja = MovimientoCaja(
        tipo='egreso' if tipo == 'cargo' else 'ingreso',
        cuenta=cuenta,
        forma_pago=forma_pago,
        concepto=f'Técnico {tecnico.nombre_display}: {concepto}',
        monto=monto,
        referencia_tipo='tecnico_cc',
        referencia_id=tecnico.id,
    )
    db.session.add(mov_caja)
    db.session.commit()

    if tipo == 'cargo':
        flash('Movimiento registrado. Aumentó la deuda del técnico y se impactó Contabilidad/Caja.', 'success')
    else:
        flash('Movimiento registrado. Se acreditó al técnico y se impactó Contabilidad/Caja.', 'success')
    return redirect(url_for('tecnicos.detalle', id=tecnico.id))


@tecnicos_bp.route('/<int:id>/cuenta-corriente/stock', methods=['POST'])
@login_required
def registrar_movimiento_stock(id):
    tecnico = Tecnico.query.get_or_404(id)

    tipo = request.form.get('tipo', 'cargo')
    if tipo not in ('cargo', 'abono'):
        flash('Tipo de movimiento inválido para stock de técnico.', 'danger')
        return redirect(url_for('tecnicos.detalle', id=tecnico.id))

    producto_id = request.form.get('producto_id')
    if not producto_id:
        flash('Debe seleccionar un producto para registrar el movimiento.', 'danger')
        return redirect(url_for('tecnicos.detalle', id=tecnico.id))

    try:
        producto = Producto.query.get_or_404(int(producto_id))
    except (TypeError, ValueError):
        flash('Producto inválido.', 'danger')
        return redirect(url_for('tecnicos.detalle', id=tecnico.id))

    try:
        cantidad = int(request.form.get('cantidad') or 0)
    except (TypeError, ValueError):
        cantidad = 0
    if cantidad <= 0:
        flash('La cantidad debe ser mayor a cero.', 'danger')
        return redirect(url_for('tecnicos.detalle', id=tecnico.id))

    try:
        precio_unitario = round(float(request.form.get('precio_unitario') or 0), 2)
    except (TypeError, ValueError):
        precio_unitario = 0.0
    if precio_unitario <= 0:
        precio_base = producto.precio_venta or producto.precio_compra or 0.0
        precio_unitario = round(float(precio_base or 0.0), 2)
    if precio_unitario <= 0:
        flash('El producto no tiene precio base. Ingrese un precio unitario válido.', 'danger')
        return redirect(url_for('tecnicos.detalle', id=tecnico.id))

    cuenta = request.form.get('cuenta', 'compra_repuestos')
    cuentas_validas = dict(CUENTAS_CAJA)
    if cuenta not in cuentas_validas:
        flash('Cuenta contable inválida para movimiento de stock.', 'danger')
        return redirect(url_for('tecnicos.detalle', id=tecnico.id))

    forma_pago = request.form.get('forma_pago', 'cuenta_corriente')
    formas_validas = dict(FORMAS_PAGO)
    if forma_pago not in formas_validas:
        flash('Forma de registro inválida para movimiento de stock.', 'danger')
        return redirect(url_for('tecnicos.detalle', id=tecnico.id))

    if tipo == 'cargo' and producto.stock_actual < cantidad:
        flash(f'Stock insuficiente para "{producto.nombre}" (disponible: {producto.stock_actual}).', 'danger')
        return redirect(url_for('tecnicos.detalle', id=tecnico.id))

    total = round(cantidad * precio_unitario, 2)
    if tipo == 'cargo':
        producto.stock_actual -= cantidad
        concepto = f'Retiro técnico: {producto.nombre} x{cantidad}'
    else:
        producto.stock_actual += cantidad
        concepto = f'Devolución técnico: {producto.nombre} x{cantidad}'

    registrar_movimiento_cc_tecnico(
        tecnico_id=tecnico.id,
        tipo=tipo,
        monto=total,
        concepto=concepto,
        cuenta=cuenta,
        forma_pago=forma_pago,
        referencia_tipo='tecnico_stock',
        referencia_id=producto.id,
    )

    mov_caja = MovimientoCaja(
        tipo='egreso' if tipo == 'cargo' else 'ingreso',
        cuenta=cuenta,
        forma_pago=forma_pago,
        concepto=f'Técnico {tecnico.nombre_display}: {concepto}',
        monto=total,
        referencia_tipo='tecnico_cc',
        referencia_id=tecnico.id,
    )
    db.session.add(mov_caja)
    db.session.commit()

    if tipo == 'cargo':
        flash('Retiro registrado. Se descontó stock y se cargó en cuenta corriente del técnico.', 'success')
    else:
        flash('Devolución registrada. Se sumó stock y se abonó en cuenta corriente del técnico.', 'success')
    return redirect(url_for('tecnicos.detalle', id=tecnico.id))


@tecnicos_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if request.method == 'POST':
        es_tercerizado = request.form.get('es_tercerizado') == '1'
        tecnico = Tecnico(
            nombre=request.form['nombre'].strip(),
            es_tercerizado=es_tercerizado,
            empresa_tercerizado=request.form.get('empresa_tercerizado', '').strip() if es_tercerizado else None,
        )
        db.session.add(tecnico)
        db.session.commit()
        flash('Técnico creado correctamente.', 'success')
        return redirect(url_for('tecnicos.index'))
    return render_template('tecnicos/form.html', tecnico=None, titulo='Nuevo Técnico')


@tecnicos_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    tecnico = Tecnico.query.get_or_404(id)
    if request.method == 'POST':
        es_tercerizado = request.form.get('es_tercerizado') == '1'
        tecnico.nombre = request.form['nombre'].strip()
        tecnico.es_tercerizado = es_tercerizado
        tecnico.empresa_tercerizado = request.form.get('empresa_tercerizado', '').strip() if es_tercerizado else None
        db.session.commit()
        flash('Técnico actualizado.', 'success')
        return redirect(url_for('tecnicos.detalle', id=tecnico.id))
    return render_template('tecnicos/form.html', tecnico=tecnico, titulo='Editar Técnico')


@tecnicos_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar(id):
    tecnico = Tecnico.query.get_or_404(id)
    tecnico.activo = not tecnico.activo
    db.session.commit()
    estado = 'activado' if tecnico.activo else 'desactivado'
    flash(f'Técnico {estado}.', 'success')
    return redirect(url_for('tecnicos.index'))
