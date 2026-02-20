from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Venta, VentaItem, Producto, Servicio, Cliente, MovimientoCaja
from datetime import datetime

ventas_bp = Blueprint('ventas', __name__)


@ventas_bp.route('/')
def index():
    ventas = Venta.query.order_by(Venta.fecha.desc()).all()
    return render_template('ventas/index.html', ventas=ventas)


@ventas_bp.route('/nueva', methods=['GET', 'POST'])
def nueva():
    clientes = Cliente.query.order_by(Cliente.apellido).all()
    productos_obj = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
    servicios_obj = Servicio.query.filter_by(activo=True).order_by(Servicio.nombre).all()

    productos_json = [{'id': p.id, 'nombre': p.nombre, 'precio_venta': p.precio_venta, 'stock_actual': p.stock_actual} for p in productos_obj]
    servicios_json = [{'id': s.id, 'nombre': s.nombre, 'precio': s.precio} for s in servicios_obj]

    if request.method == 'POST':
        cliente_id = request.form.get('cliente_id') or None
        descuento = float(request.form.get('descuento') or 0)
        notas = request.form.get('notas', '').strip()

        tipos = request.form.getlist('item_tipo[]')
        item_ids = request.form.getlist('item_id[]')
        cantidades = request.form.getlist('item_cantidad[]')

        if not tipos:
            flash('Debe agregar al menos un producto o servicio.', 'danger')
            return render_template('ventas/form.html', clientes=clientes,
                                   productos=productos_json, servicios=servicios_json)

        venta = Venta(
            cliente_id=cliente_id,
            descuento=descuento,
            notas=notas,
            fecha=datetime.utcnow(),
        )
        db.session.add(venta)
        db.session.flush()

        subtotal = 0.0
        errores = []
        items_ok = []

        for tipo, iid, cant_str in zip(tipos, item_ids, cantidades):
            cant = int(cant_str or 1)
            if tipo == 'producto':
                prod = Producto.query.get(int(iid))
                if not prod:
                    continue
                if prod.stock_actual < cant:
                    errores.append(f'Stock insuficiente para "{prod.nombre}" (disponible: {prod.stock_actual}).')
                    continue
                precio = prod.precio_venta
                sub = precio * cant
                items_ok.append(('producto', prod, cant, precio, sub))
                subtotal += sub
            elif tipo == 'servicio':
                serv = Servicio.query.get(int(iid))
                if not serv:
                    continue
                precio = serv.precio
                sub = precio * cant
                items_ok.append(('servicio', serv, cant, precio, sub))
                subtotal += sub

        if errores:
            db.session.rollback()
            for e in errores:
                flash(e, 'danger')
            return render_template('ventas/form.html', clientes=clientes,
                                   productos=productos_json, servicios=servicios_json)

        for tipo, obj, cant, precio, sub in items_ok:
            vi = VentaItem(
                venta_id=venta.id,
                tipo=tipo,
                producto_id=obj.id if tipo == 'producto' else None,
                servicio_id=obj.id if tipo == 'servicio' else None,
                cantidad=cant,
                precio_unitario=precio,
                subtotal=sub,
            )
            db.session.add(vi)
            if tipo == 'producto':
                obj.stock_actual -= cant

        total = subtotal - descuento
        venta.subtotal = subtotal
        venta.total = total
        venta.pagado = True

        cliente_nombre = ''
        if cliente_id:
            from models import Cliente as ClienteModel
            c = ClienteModel.query.get(int(cliente_id))
            if c:
                cliente_nombre = f' - {c.nombre_completo}'

        mov = MovimientoCaja(
            tipo='ingreso',
        concepto=f'Venta #{venta.id}{cliente_nombre or " - Mostrador"}',
            monto=total,
            referencia_tipo='venta',
            referencia_id=venta.id,
            fecha=datetime.utcnow(),
        )
        db.session.add(mov)
        db.session.commit()
        flash(f'Venta registrada por ${total:.2f}. Stock actualizado.', 'success')
        return redirect(url_for('ventas.index'))

    return render_template('ventas/form.html', clientes=clientes,
                           productos=productos_json, servicios=servicios_json)


@ventas_bp.route('/<int:id>/eliminar', methods=['POST'])
def eliminar(id):
    venta = Venta.query.get_or_404(id)
    # Devolver stock
    for item in venta.items:
        if item.tipo == 'producto' and item.producto:
            item.producto.stock_actual += item.cantidad
    MovimientoCaja.query.filter_by(referencia_tipo='venta', referencia_id=venta.id).delete()
    db.session.delete(venta)
    db.session.commit()
    flash('Venta eliminada y stock devuelto.', 'success')
    return redirect(url_for('ventas.index'))
