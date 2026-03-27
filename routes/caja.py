from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import db, MovimientoCaja, CUENTAS_CAJA, FORMAS_PAGO
from datetime import datetime, date
from sqlalchemy import func, case

caja_bp = Blueprint('caja', __name__)


@caja_bp.route('/')
@login_required
def index():
    today = date.today().strftime('%Y-%m-%d')
    forma_pago_filter = request.args.get('forma_pago', '')

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
        query = query.filter_by(forma_pago=forma_pago_filter)

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
        key = fp or 'efectivo'
        if mov_tipo == 'ingreso':
            saldos_fp[key] = saldos_fp.get(key, 0.0) + total
        elif mov_tipo == 'egreso':
            saldos_fp[key] = saldos_fp.get(key, 0.0) - total

    return render_template('caja/index.html',
                           movimientos=movimientos,
                           total_ingresos=total_ingresos,
                           total_egresos=total_egresos,
                           balance=balance,
                           fecha_desde=fecha_desde,
                           fecha_hasta=fecha_hasta,
                           tipo=tipo,
                           forma_pago_filter=forma_pago_filter,
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
            forma_pago=request.form.get('forma_pago', 'efectivo'),
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
    if mov.referencia_tipo in ('taller', 'venta'):
        flash('No se puede eliminar un movimiento generado automáticamente.', 'danger')
        return redirect(url_for('caja.index'))
    db.session.delete(mov)
    db.session.commit()
    flash('Movimiento eliminado.', 'success')
    return redirect(url_for('caja.index'))
