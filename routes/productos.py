from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import db, Producto, Servicio, Categoria

productos_bp = Blueprint('productos', __name__)


@productos_bp.route('/')
@login_required
def index():
    tab = request.args.get('tab', 'productos')
    q = request.args.get('q', '').strip()
    categoria_id = request.args.get('categoria_id', '')

    productos_query = Producto.query
    if q:
        productos_query = productos_query.filter(Producto.nombre.ilike(f'%{q}%'))
    if categoria_id:
        try:
            productos_query = productos_query.filter_by(categoria_id=int(categoria_id))
        except ValueError:
            categoria_id = ''
    productos = productos_query.order_by(Producto.nombre).all()

    servicios = Servicio.query.order_by(Servicio.nombre).all()
    categorias = Categoria.query.order_by(Categoria.nombre).all()
    return render_template('productos/index.html', productos=productos, servicios=servicios,
                           categorias=categorias, tab=tab, q=q, categoria_id=categoria_id)


# ── Categorías ──────────────────────────────────────────────────────────────

@productos_bp.route('/categoria/nueva', methods=['POST'])
@login_required
def nueva_categoria():
    nombre = request.form.get('nombre', '').strip()
    if nombre:
        cat = Categoria(nombre=nombre)
        db.session.add(cat)
        db.session.commit()
        flash('Categoría creada.', 'success')
    return redirect(url_for('productos.index'))


@productos_bp.route('/categoria/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_categoria(id):
    cat = Categoria.query.get_or_404(id)
    if cat.productos:
        flash('No se puede eliminar una categoría con productos asociados.', 'danger')
    else:
        db.session.delete(cat)
        db.session.commit()
        flash('Categoría eliminada.', 'success')
    return redirect(url_for('productos.index'))


# ── Productos ────────────────────────────────────────────────────────────────

@productos_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_producto():
    categorias = Categoria.query.order_by(Categoria.nombre).all()
    if request.method == 'POST':
        prod = Producto(
            nombre=request.form['nombre'].strip(),
            descripcion=request.form.get('descripcion', '').strip(),
            codigo_barras=request.form.get('codigo_barras', '').strip(),
            categoria_id=request.form.get('categoria_id') or None,
            precio_compra=float(request.form.get('precio_compra') or 0),
            precio_venta=float(request.form['precio_venta']),
            stock_actual=int(request.form.get('stock_actual') or 0),
            stock_minimo=int(request.form.get('stock_minimo') or 5),
            unidad=request.form.get('unidad', 'unidad').strip(),
            activo='activo' in request.form,
        )
        db.session.add(prod)
        db.session.commit()
        flash('Producto creado correctamente.', 'success')
        return redirect(url_for('productos.index'))
    return render_template('productos/form.html', producto=None, categorias=categorias,
                           titulo='Nuevo Producto', tipo='producto')


@productos_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_producto(id):
    prod = Producto.query.get_or_404(id)
    categorias = Categoria.query.order_by(Categoria.nombre).all()
    if request.method == 'POST':
        prod.nombre = request.form['nombre'].strip()
        prod.descripcion = request.form.get('descripcion', '').strip()
        prod.codigo_barras = request.form.get('codigo_barras', '').strip()
        prod.categoria_id = request.form.get('categoria_id') or None
        prod.precio_compra = float(request.form.get('precio_compra') or 0)
        prod.precio_venta = float(request.form['precio_venta'])
        prod.stock_minimo = int(request.form.get('stock_minimo') or 5)
        prod.unidad = request.form.get('unidad', 'unidad').strip()
        prod.activo = 'activo' in request.form
        db.session.commit()
        flash('Producto actualizado.', 'success')
        return redirect(url_for('productos.index'))
    return render_template('productos/form.html', producto=prod, categorias=categorias,
                           titulo='Editar Producto', tipo='producto')


@productos_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_producto(id):
    prod = Producto.query.get_or_404(id)
    prod.activo = False
    db.session.commit()
    flash('Producto desactivado.', 'success')
    return redirect(url_for('productos.index'))


# ── Servicios ────────────────────────────────────────────────────────────────

@productos_bp.route('/servicio/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_servicio():
    if request.method == 'POST':
        serv = Servicio(
            nombre=request.form['nombre'].strip(),
            descripcion=request.form.get('descripcion', '').strip(),
            precio=float(request.form['precio']),
            activo='activo' in request.form,
        )
        db.session.add(serv)
        db.session.commit()
        flash('Servicio creado correctamente.', 'success')
        return redirect(url_for('productos.index', tab='servicios'))
    return render_template('productos/form.html', producto=None, categorias=[],
                           titulo='Nuevo Servicio', tipo='servicio')


@productos_bp.route('/servicio/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_servicio(id):
    serv = Servicio.query.get_or_404(id)
    if request.method == 'POST':
        serv.nombre = request.form['nombre'].strip()
        serv.descripcion = request.form.get('descripcion', '').strip()
        serv.precio = float(request.form['precio'])
        serv.activo = 'activo' in request.form
        db.session.commit()
        flash('Servicio actualizado.', 'success')
        return redirect(url_for('productos.index', tab='servicios'))
    return render_template('productos/form.html', producto=serv, categorias=[],
                           titulo='Editar Servicio', tipo='servicio')


@productos_bp.route('/servicio/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_servicio(id):
    serv = Servicio.query.get_or_404(id)
    serv.activo = False
    db.session.commit()
    flash('Servicio desactivado.', 'success')
    return redirect(url_for('productos.index', tab='servicios'))
