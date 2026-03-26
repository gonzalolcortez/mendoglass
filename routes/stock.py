from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import db, Producto
from sqlalchemy.orm import joinedload

stock_bp = Blueprint('stock', __name__)


@stock_bp.route('/')
@login_required
def index():
    filtro = request.args.get('filtro', 'todos')
    query = Producto.query.options(joinedload(Producto.categoria)).filter_by(activo=True)
    if filtro == 'bajo':
        productos = query.filter(Producto.stock_actual <= Producto.stock_minimo).order_by(Producto.nombre).all()
    elif filtro == 'ok':
        productos = query.filter(Producto.stock_actual > Producto.stock_minimo).order_by(Producto.nombre).all()
    else:
        productos = query.order_by(Producto.nombre).all()
    total_compra = sum(p.stock_actual * p.precio_compra for p in productos)
    total_venta = sum(p.stock_actual * p.precio_venta for p in productos)
    return render_template('stock/index.html', productos=productos, filtro=filtro,
                           total_compra=total_compra, total_venta=total_venta)


@stock_bp.route('/ajuste/<int:id>', methods=['GET', 'POST'])
@login_required
def ajuste(id):
    producto = Producto.query.get_or_404(id)
    if request.method == 'POST':
        tipo = request.form.get('tipo')
        cantidad = int(request.form.get('cantidad', 0))
        if tipo == 'set':
            producto.stock_actual = cantidad
        elif tipo == 'add':
            producto.stock_actual += cantidad
        elif tipo == 'sub':
            if producto.stock_actual - cantidad < 0:
                flash('No hay suficiente stock para restar esa cantidad.', 'danger')
                return redirect(url_for('stock.ajuste', id=id))
            producto.stock_actual -= cantidad
        db.session.commit()
        flash(f'Stock de "{producto.nombre}" actualizado a {producto.stock_actual} {producto.unidad}.', 'success')
        return redirect(url_for('stock.index'))
    return render_template('stock/ajuste.html', producto=producto)
