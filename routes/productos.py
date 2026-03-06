from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from models import (db, Producto, Servicio, Categoria, Proveedor,
                    IngresoMercaderia, IngresoMercaderiaItem, MovimientoCaja, FORMAS_PAGO)
from datetime import datetime

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


# ── Ingreso de Mercadería ────────────────────────────────────────────────────

@productos_bp.route('/ingreso-mercaderia')
@login_required
def ingresos_mercaderia():
    ingresos = IngresoMercaderia.query.order_by(IngresoMercaderia.fecha.desc()).all()
    return render_template('productos/ingresos_mercaderia.html', ingresos=ingresos)


@productos_bp.route('/ingreso-mercaderia/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_ingreso_mercaderia():
    productos_obj = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
    proveedores = Proveedor.query.order_by(Proveedor.apellido).all()
    productos_json = [{'id': p.id, 'nombre': p.nombre, 'precio_compra': p.precio_compra,
                       'stock_actual': p.stock_actual, 'codigo_barras': p.codigo_barras or ''}
                      for p in productos_obj]

    if request.method == 'POST':
        proveedor_id = request.form.get('proveedor_id') or None
        forma_pago = request.form.get('forma_pago', 'efectivo')
        notas = request.form.get('notas', '').strip()

        nombres = request.form.getlist('item_nombre[]')
        producto_ids = request.form.getlist('item_producto_id[]')
        cantidades = request.form.getlist('item_cantidad[]')
        precios = request.form.getlist('item_precio_compra[]')

        if not nombres:
            flash('Debe agregar al menos un producto.', 'danger')
            return render_template('productos/ingreso_mercaderia.html',
                                   productos=productos_json, proveedores=proveedores,
                                   formas_pago=FORMAS_PAGO)

        ingreso = IngresoMercaderia(
            proveedor_id=proveedor_id,
            forma_pago=forma_pago,
            notas=notas,
            fecha=datetime.utcnow(),
        )
        db.session.add(ingreso)
        db.session.flush()

        total = 0.0
        for nombre, pid_str, cant_str, precio_str in zip(nombres, producto_ids, cantidades, precios):
            nombre = nombre.strip()
            if not nombre:
                continue
            cant = int(cant_str or 1)
            precio = float(precio_str or 0)
            subtotal = cant * precio
            total += subtotal

            if pid_str and pid_str != '0':
                prod = Producto.query.get(int(pid_str))
                if prod:
                    prod.stock_actual += cant
                    prod.precio_compra = precio
                    pid = prod.id
                else:
                    pid = None
            else:
                # Create a new product with basic info
                prod = Producto(
                    nombre=nombre,
                    precio_compra=precio,
                    precio_venta=precio,
                    stock_actual=cant,
                    stock_minimo=5,
                    activo=True,
                )
                db.session.add(prod)
                db.session.flush()
                pid = prod.id

            item = IngresoMercaderiaItem(
                ingreso_id=ingreso.id,
                producto_id=pid,
                nombre_producto=nombre,
                cantidad=cant,
                precio_compra=precio,
                subtotal=subtotal,
            )
            db.session.add(item)

        ingreso.total = total

        mov = MovimientoCaja(
            tipo='egreso',
            cuenta='compra_mercaderia',
            forma_pago=forma_pago,
            concepto=f'Ingreso de Mercadería #{ingreso.id}',
            monto=total,
            referencia_tipo='ingreso_mercaderia',
            referencia_id=ingreso.id,
            fecha=datetime.utcnow(),
        )
        db.session.add(mov)
        db.session.commit()
        flash(f'Ingreso de mercadería registrado por ${total:.2f}. Stock y caja actualizados.', 'success')
        return redirect(url_for('productos.ingresos_mercaderia'))

    return render_template('productos/ingreso_mercaderia.html',
                           productos=productos_json, proveedores=proveedores,
                           formas_pago=FORMAS_PAGO,
                           categorias=Categoria.query.order_by(Categoria.nombre).all())


# ── API: Crear producto desde modal ─────────────────────────────────────────

@productos_bp.route('/api/nuevo-producto', methods=['POST'])
@login_required
def api_nuevo_producto():
    try:
        data = request.get_json(force=True, silent=False) or {}
    except Exception:
        return jsonify({'ok': False, 'error': 'Cuerpo JSON inválido.'}), 400
    if not isinstance(data, dict):
        return jsonify({'ok': False, 'error': 'Cuerpo JSON inválido.'}), 400
    nombre = (data.get('nombre') or '').strip()
    if not nombre:
        return jsonify({'ok': False, 'error': 'El nombre es obligatorio.'}), 400
    try:
        precio_venta = float(data.get('precio_venta') or 0)
    except (ValueError, TypeError):
        return jsonify({'ok': False, 'error': 'Precio de venta inválido.'}), 400
    try:
        precio_compra = float(data.get('precio_compra') or 0)
        stock_minimo = int(data.get('stock_minimo') or 5)
    except (ValueError, TypeError):
        return jsonify({'ok': False, 'error': 'Datos numéricos inválidos.'}), 400

    categoria_id = data.get('categoria_id') or None
    if categoria_id:
        try:
            categoria_id = int(categoria_id)
        except (ValueError, TypeError):
            categoria_id = None

    prod = Producto(
        nombre=nombre,
        descripcion=(data.get('descripcion') or '').strip(),
        codigo_barras=(data.get('codigo_barras') or '').strip() or None,
        categoria_id=categoria_id,
        precio_compra=precio_compra,
        precio_venta=precio_venta,
        stock_actual=0,
        stock_minimo=stock_minimo,
        unidad=(data.get('unidad') or 'unidad').strip(),
        activo=True,
    )
    db.session.add(prod)
    db.session.commit()
    return jsonify({
        'ok': True,
        'producto': {
            'id': prod.id,
            'nombre': prod.nombre,
            'precio_compra': prod.precio_compra,
            'stock_actual': prod.stock_actual,
            'codigo_barras': prod.codigo_barras or '',
        }
    }), 201

