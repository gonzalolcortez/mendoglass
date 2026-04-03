from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import (
    db,
    MovimientoCaja,
    ClienteCuentaCorrienteMovimiento,
    Cliente,
    CUENTAS_CAJA,
    FORMAS_PAGO,
    normalizar_forma_pago,
)
from datetime import datetime, date
from sqlalchemy import func, case

caja_bp = Blueprint('caja', __name__)


@caja_bp.route('/')
@login_required
def index():
    vista = request.args.get('vista', 'caja').strip() or 'caja'
    if vista not in ('caja', 'cuentas_corrientes'):
        vista = 'caja'

    today = date.today().strftime('%Y-%m-%d')
    forma_pago_filter = normalizar_forma_pago(request.args.get('forma_pago', ''), default='')
    referencia_filter = request.args.get('referencia', '').strip()

    # Si se filtra por forma de pago desde las tarjetas, no aplicar fecha por defecto
    if forma_pago_filter:
        fecha_desde = request.args.get('fecha_desde', '')
        fecha_hasta = request.args.get('fecha_hasta', '')
    else:
        fecha_desde = request.args.get('fecha_desde', today)
        fecha_hasta = request.args.get('fecha_hasta', today)

    tipo = request.args.get('tipo', '')

    query = MovimientoCaja.query
    if fecha_desde:
        try:
            query = query.filter(MovimientoCaja.fecha >= datetime.strptime(fecha_desde, '%Y-%m-%d'))
        except ValueError:
            pass
    if fecha_hasta:
        try:
            dt_hasta = datetime.strptime(fecha_hasta, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(MovimientoCaja.fecha <= dt_hasta)
        except ValueError:
            pass
    if tipo in ('ingreso', 'egreso'):
        query = query.filter_by(tipo=tipo)
    if forma_pago_filter:
        if forma_pago_filter == 'banco':
            query = query.filter(MovimientoCaja.forma_pago.in_(['banco', 'transferencia', 'transferencia_bancaria']))
        else:
            query = query.filter_by(forma_pago=forma_pago_filter)
    if referencia_filter == 'tecnico_cc':
        query = query.filter_by(referencia_tipo='tecnico_cc')

    movimientos = query.order_by(MovimientoCaja.fecha.desc()).all()

    total_ingresos, total_egresos = query.with_entities(
        func.coalesce(func.sum(case((MovimientoCaja.tipo == 'ingreso', MovimientoCaja.monto), else_=0.0)), 0.0),
        func.coalesce(func.sum(case((MovimientoCaja.tipo == 'egreso', MovimientoCaja.monto), else_=0.0)), 0.0),
    ).first()
    balance = total_ingresos - total_egresos

    # Saldos por forma de pago usando agregación DB (todos los movimientos, sin filtro).
    rows_fp = (
        db.session.query(MovimientoCaja.tipo, MovimientoCaja.forma_pago, func.sum(MovimientoCaja.monto))
        .group_by(MovimientoCaja.tipo, MovimientoCaja.forma_pago)
        .all()
    )

    saldos_fp = {}
    for mov_tipo, fp, total in rows_fp:
        key = normalizar_forma_pago(fp)
        if mov_tipo == 'ingreso':
            saldos_fp[key] = saldos_fp.get(key, 0.0) + total
        elif mov_tipo == 'egreso':
            saldos_fp[key] = saldos_fp.get(key, 0.0) - total

    query_cc = ClienteCuentaCorrienteMovimiento.query.join(Cliente)
    if fecha_desde:
        try:
            query_cc = query_cc.filter(ClienteCuentaCorrienteMovimiento.fecha >= datetime.strptime(fecha_desde, '%Y-%m-%d'))
        except ValueError:
            pass
    if fecha_hasta:
        try:
            dt_hasta = datetime.strptime(fecha_hasta, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query_cc = query_cc.filter(ClienteCuentaCorrienteMovimiento.fecha <= dt_hasta)
        except ValueError:
            pass

    movimientos_cc = query_cc.order_by(ClienteCuentaCorrienteMovimiento.fecha.desc()).all()
    total_cargos_cc = sum((m.monto or 0.0) for m in movimientos_cc if m.tipo == 'cargo')
    total_abonos_cc = sum((m.monto or 0.0) for m in movimientos_cc if m.tipo == 'abono')
    saldo_cc = total_cargos_cc - total_abonos_cc

    return render_template('caja/index.html',
                           movimientos=movimientos,
                           movimientos_cc=movimientos_cc,
                           total_ingresos=total_ingresos,
                           total_egresos=total_egresos,
                           balance=balance,
                           total_cargos_cc=total_cargos_cc,
                           total_abonos_cc=total_abonos_cc,
                           saldo_cc=saldo_cc,
                           fecha_desde=fecha_desde,
                           fecha_hasta=fecha_hasta,
                           tipo=tipo,
                           vista=vista,
                           forma_pago_filter=forma_pago_filter,
                           referencia_filter=referencia_filter,
                           saldos_fp=saldos_fp,
                           formas_pago=FORMAS_PAGO,
                           cuentas_caja=CUENTAS_CAJA)


@caja_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if request.method == 'POST':
        mov = MovimientoCaja(
            tipo=request.form['tipo'],
            cuenta=request.form.get('cuenta', 'otro'),
            forma_pago=normalizar_forma_pago(request.form.get('forma_pago', 'efectivo')),
            concepto=request.form['concepto'].strip(),
            monto=float(request.form['monto']),
            referencia_tipo='manual',
            notas=request.form.get('notas', '').strip(),
            fecha=datetime.now(),
        )
        db.session.add(mov)
        db.session.commit()
        flash('Movimiento registrado en Caja.', 'success')
        return redirect(url_for('caja.index'))
    return render_template('caja/form.html', cuentas=CUENTAS_CAJA, formas_pago=FORMAS_PAGO)


@caja_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar(id):
    mov = MovimientoCaja.query.get_or_404(id)
    if mov.referencia_tipo in ('taller', 'venta', 'tecnico_cc'):
        flash('No se puede eliminar un movimiento generado automáticamente.', 'danger')
        return redirect(url_for('caja.index'))
    db.session.delete(mov)
    db.session.commit()
    flash('Movimiento eliminado.', 'success')
    return redirect(url_for('caja.index'))
