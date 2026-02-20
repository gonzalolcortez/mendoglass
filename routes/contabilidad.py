from flask import Blueprint, render_template, request
from models import db, MovimientoCaja
from datetime import datetime
from sqlalchemy import func, extract

contabilidad_bp = Blueprint('contabilidad', __name__)


@contabilidad_bp.route('/')
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

    return render_template('contabilidad/index.html',
                           meses_data=meses_data,
                           total_ingresos=total_ingresos,
                           total_egresos=total_egresos,
                           total_ganancia=total_ganancia,
                           anio=anio,
                           anios=anios)


def _nombre_mes(n):
    nombres = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
               'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    return nombres[n - 1]
