from flask import Blueprint, render_template, request
from flask_login import login_required
from models import db, MovimientoCaja, CUENTAS_CAJA
from datetime import datetime
from sqlalchemy import func, extract

contabilidad_bp = Blueprint('contabilidad', __name__)


@contabilidad_bp.route('/')
@login_required
def index():
    anio = request.args.get('anio', datetime.utcnow().year, type=int)

    # Ingresos y egresos por mes del año seleccionado
    meses_data = []
    for mes in range(1, 13):
        ingresos = db.session.query(func.sum(MovimientoCaja.monto)).filter(
            MovimientoCaja.tipo == 'ingreso',
            extract('year', MovimientoCaja.fecha) == anio,
            extract('month', MovimientoCaja.fecha) == mes,
        ).scalar() or 0.0

        egresos = db.session.query(func.sum(MovimientoCaja.monto)).filter(
            MovimientoCaja.tipo == 'egreso',
            extract('year', MovimientoCaja.fecha) == anio,
            extract('month', MovimientoCaja.fecha) == mes,
        ).scalar() or 0.0

        meses_data.append({
            'mes': mes,
            'nombre': _nombre_mes(mes),
            'ingresos': ingresos,
            'egresos': egresos,
            'ganancia': ingresos - egresos,
        })

    total_ingresos = sum(m['ingresos'] for m in meses_data)
    total_egresos = sum(m['egresos'] for m in meses_data)
    total_ganancia = total_ingresos - total_egresos

    # Años disponibles
    anios = db.session.query(
        extract('year', MovimientoCaja.fecha).label('anio')
    ).distinct().order_by('anio').all()
    anios = [int(a.anio) for a in anios] or [datetime.utcnow().year]
    if datetime.utcnow().year not in anios:
        anios.append(datetime.utcnow().year)
    anios.sort(reverse=True)

    # Saldo acumulado por cuenta (todos los movimientos)
    # Saldo acumulado por cuenta (todos los movimientos) — dos queries con GROUP BY
    rows_ing = db.session.query(
        MovimientoCaja.cuenta, func.sum(MovimientoCaja.monto)
    ).filter_by(tipo='ingreso').group_by(MovimientoCaja.cuenta).all()
    rows_egr = db.session.query(
        MovimientoCaja.cuenta, func.sum(MovimientoCaja.monto)
    ).filter_by(tipo='egreso').group_by(MovimientoCaja.cuenta).all()

    ing_por_cuenta = {cuenta: total for cuenta, total in rows_ing}
    egr_por_cuenta = {cuenta: total for cuenta, total in rows_egr}

    saldos_cuentas = []
    for cuenta_val, cuenta_label in CUENTAS_CAJA:
        ing = ing_por_cuenta.get(cuenta_val, 0.0)
        egr = egr_por_cuenta.get(cuenta_val, 0.0)
        saldos_cuentas.append({
            'cuenta': cuenta_val,
            'nombre': cuenta_label,
            'ingresos': ing,
            'egresos': egr,
            'saldo': ing - egr,
        })

    return render_template('contabilidad/index.html',
                           meses_data=meses_data,
                           total_ingresos=total_ingresos,
                           total_egresos=total_egresos,
                           total_ganancia=total_ganancia,
                           anio=anio,
                           anios=anios,
                           saldos_cuentas=saldos_cuentas)


@contabilidad_bp.route('/cuenta/<cuenta>')
@login_required
def detalle_cuenta(cuenta):
    cuentas_dict = dict(CUENTAS_CAJA)
    nombre_cuenta = cuentas_dict.get(cuenta, cuenta)

    movimientos = MovimientoCaja.query.filter_by(cuenta=cuenta)\
        .order_by(MovimientoCaja.fecha.asc()).all()

    # Calcular saldo progresivo
    saldo = 0.0
    movimientos_con_saldo = []
    for m in movimientos:
        if m.tipo == 'ingreso':
            saldo += m.monto
        else:
            saldo -= m.monto
        movimientos_con_saldo.append({
            'mov': m,
            'ingreso': m.monto if m.tipo == 'ingreso' else None,
            'egreso': m.monto if m.tipo == 'egreso' else None,
            'saldo': saldo,
        })

    total_ingresos = sum(r['ingreso'] for r in movimientos_con_saldo if r['ingreso'])
    total_egresos = sum(r['egreso'] for r in movimientos_con_saldo if r['egreso'])

    return render_template('contabilidad/cuenta.html',
                           cuenta=cuenta,
                           nombre_cuenta=nombre_cuenta,
                           movimientos_con_saldo=movimientos_con_saldo,
                           total_ingresos=total_ingresos,
                           total_egresos=total_egresos,
                           saldo_final=saldo)


def _nombre_mes(n):
    nombres = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
               'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    return nombres[n - 1]
