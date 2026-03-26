from flask import Blueprint, render_template
from flask_login import login_required
from models import db, Cliente, Taller, Producto, MovimientoCaja, Venta
from datetime import datetime, date
from sqlalchemy import func
from sqlalchemy.orm import joinedload, load_only

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    today = date.today()

    montos_hoy_rows = (
        db.session.query(MovimientoCaja.tipo, func.sum(MovimientoCaja.monto))
        .filter(func.date(MovimientoCaja.fecha) == today)
        .group_by(MovimientoCaja.tipo)
        .all()
    )
    montos_hoy = {tipo: total for tipo, total in montos_hoy_rows}
    ingresos_hoy = montos_hoy.get('ingreso', 0.0) or 0.0
    egresos_hoy = montos_hoy.get('egreso', 0.0) or 0.0

    counts = db.session.query(
        db.session.query(func.count(Taller.id))
        .filter(Taller.estado.notin_(['entregado', 'cancelado']))
        .scalar_subquery()
        .label('reparaciones_activas'),
        db.session.query(func.count(Venta.id))
        .filter(func.date(Venta.fecha) == today)
        .scalar_subquery()
        .label('ventas_hoy'),
    ).one()
    reparaciones_activas = counts.reparaciones_activas or 0
    ventas_hoy = counts.ventas_hoy or 0

    productos_bajo_stock = Producto.query.options(
        load_only(Producto.id, Producto.nombre, Producto.stock_actual, Producto.unidad)
    ).filter(
        Producto.stock_actual <= Producto.stock_minimo,
        Producto.activo == True
    ).order_by(Producto.stock_actual.asc(), Producto.nombre.asc()).limit(5).all()

    ultimos_talleres = (
        Taller.query
        .options(
            load_only(Taller.id, Taller.numero, Taller.estado, Taller.marca, Taller.modelo, Taller.created_at),
            joinedload(Taller.cliente).load_only(Cliente.id, Cliente.nombre, Cliente.apellido),
        )
        .order_by(Taller.created_at.desc())
        .limit(5)
        .all()
    )
    ultimos_movimientos = MovimientoCaja.query.options(
        load_only(MovimientoCaja.id, MovimientoCaja.tipo, MovimientoCaja.concepto, MovimientoCaja.monto, MovimientoCaja.fecha)
    ).order_by(MovimientoCaja.fecha.desc()).limit(5).all()

    return render_template('index.html',
                           ingresos_hoy=ingresos_hoy,
                           egresos_hoy=egresos_hoy,
                           reparaciones_activas=reparaciones_activas,
                           productos_bajo_stock=productos_bajo_stock,
                           ventas_hoy=ventas_hoy,
                           ultimos_talleres=ultimos_talleres,
                           ultimos_movimientos=ultimos_movimientos)
