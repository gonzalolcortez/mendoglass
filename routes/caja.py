from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, MovimientoCaja
from datetime import datetime, date

caja_bp = Blueprint('caja', __name__)


@caja_bp.route('/')
def index():
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
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

    return render_template('caja/index.html',
                           movimientos=movimientos,
                           total_ingresos=total_ingresos,
                           total_egresos=total_egresos,
                           balance=balance,
                           fecha_desde=fecha_desde,
                           fecha_hasta=fecha_hasta,
                           tipo=tipo)


@caja_bp.route('/nuevo', methods=['GET', 'POST'])
def nuevo():
    if request.method == 'POST':
        mov = MovimientoCaja(
            tipo=request.form['tipo'],
            concepto=request.form['concepto'].strip(),
            monto=float(request.form['monto']),
            referencia_tipo=request.form.get('referencia_tipo', 'otro'),
            notas=request.form.get('notas', '').strip(),
            fecha=datetime.utcnow(),
        )
        db.session.add(mov)
        db.session.commit()
        flash('Movimiento registrado en Caja.', 'success')
        return redirect(url_for('caja.index'))
    return render_template('caja/form.html')


@caja_bp.route('/<int:id>/eliminar', methods=['POST'])
def eliminar(id):
    mov = MovimientoCaja.query.get_or_404(id)
    if mov.referencia_tipo in ('taller', 'venta'):
        flash('No se puede eliminar un movimiento generado automáticamente.', 'danger')
        return redirect(url_for('caja.index'))
    db.session.delete(mov)
    db.session.commit()
    flash('Movimiento eliminado.', 'success')
    return redirect(url_for('caja.index'))
