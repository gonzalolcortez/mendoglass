from flask import Blueprint, render_template
from models import db, Cliente, Taller, Producto, MovimientoCaja, Venta
from datetime import datetime, date
from sqlalchemy import func

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    today = date.today()

    ingresos_hoy = db.session.query(func.sum(MovimientoCaja.monto)).filter(
        MovimientoCaja.tipo == 'ingreso',
        func.date(MovimientoCaja.fecha) == today
    ).scalar() or 0.0

    egresos_hoy = db.session.query(func.sum(MovimientoCaja.monto)).filter(
        MovimientoCaja.tipo == 'egreso',
        func.date(MovimientoCaja.fecha) == today
    ).scalar() or 0.0

    reparaciones_activas = Taller.query.filter(
        Taller.estado.notin_(['entregado', 'cancelado'])
    ).count()

    productos_bajo_stock = Producto.query.filter(
        Producto.stock_actual <= Producto.stock_minimo,
        Producto.activo == True
    ).all()

    ventas_hoy = Venta.query.filter(
        func.date(Venta.fecha) == today
    ).count()

    ultimos_talleres = Taller.query.order_by(Taller.created_at.desc()).limit(5).all()
    ultimos_movimientos = MovimientoCaja.query.order_by(MovimientoCaja.fecha.desc()).limit(5).all()

    return render_template('index.html',
                           ingresos_hoy=ingresos_hoy,
                           egresos_hoy=egresos_hoy,
                           reparaciones_activas=reparaciones_activas,
                           productos_bajo_stock=productos_bajo_stock,
                           ventas_hoy=ventas_hoy,
                           ultimos_talleres=ultimos_talleres,
                           ultimos_movimientos=ultimos_movimientos)
