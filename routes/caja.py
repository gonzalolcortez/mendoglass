from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import db, MovimientoCaja, CUENTAS_CAJA, FORMAS_PAGO
from datetime import datetime, date
from sqlalchemy import func

caja_bp = Blueprint('caja', __name__)


@caja_bp.route('/')
@login_required
def index():
    today = date.today().strftime('%Y-%m-%d')
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

    movimientos = query.order_by(MovimientoCaja.fecha.desc()).all()

    total_ingresos = sum(m.monto for m in movimientos if m.tipo == 'ingreso')
    total_egresos = sum(m.monto for m in movimientos if m.tipo == 'egreso')
    balance = total_ingresos - total_egresos

    # Saldos por forma de pago usando agregación DB (todos los movimientos, sin filtro)
    rows_ing = db.session.query(
        MovimientoCaja.forma_pago, func.sum(MovimientoCaja.monto)
    ).filter_by(tipo='ingreso').group_by(MovimientoCaja.forma_pago).all()

    rows_egr = db.session.query(
        MovimientoCaja.forma_pago, func.sum(MovimientoCaja.monto)
    ).filter_by(tipo='egreso').group_by(MovimientoCaja.forma_pago).all()

    saldos_fp = {}
    for fp, total in rows_ing:
        saldos_fp[fp or 'efectivo'] = saldos_fp.get(fp or 'efectivo', 0.0) + total
    for fp, total in rows_egr:
        saldos_fp[fp or 'efectivo'] = saldos_fp.get(fp or 'efectivo', 0.0) - total

    return render_template('caja/index.html',
                           movimientos=movimientos,
                           total_ingresos=total_ingresos,
                           total_egresos=total_egresos,
                           balance=balance,
                           fecha_desde=fecha_desde,
                           fecha_hasta=fecha_hasta,
                           tipo=tipo,
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
            fecha=datetime.utcnow(),
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
