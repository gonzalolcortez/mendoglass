from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Producto

stock_bp = Blueprint('stock', __name__)


@stock_bp.route('/')
def index():
    filtro = request.args.get('filtro', 'todos')
    query = Producto.query.filter_by(activo=True)
    if filtro == 'bajo':
        productos = [p for p in query.all() if p.stock_actual <= p.stock_minimo]
    elif filtro == 'ok':
        productos = [p for p in query.all() if p.stock_actual > p.stock_minimo]
    else:
        productos = query.order_by(Producto.nombre).all()
    return render_template('stock/index.html', productos=productos, filtro=filtro)


@stock_bp.route('/ajuste/<int:id>', methods=['GET', 'POST'])
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
