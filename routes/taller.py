from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import db, Taller, TallerProducto, TallerServicio, Cliente, Producto, Servicio, MovimientoCaja, Tecnico, FORMAS_PAGO, CUENTAS_CAJA, Categoria
from datetime import datetime
from whatsapp_api import enviar_whatsapp

taller_bp = Blueprint('taller', __name__)

ESTADOS = [
    ('recibido', 'Recibido'),
    ('diagnostico', 'En Diagnóstico'),
    ('en_reparacion', 'En Reparación'),
    ('sin_solucion', 'Sin Solución'),
    ('listo', 'Listo'),
    ('entregado', 'Entregado'),
    ('cancelado', 'Cancelado'),
]


def _next_numero():
    last = db.session.query(db.func.max(Taller.numero)).scalar()
    return (last or 0) + 1


@taller_bp.route('/')
@login_required
def index():
    estado = request.args.get('estado', '')
    q = request.args.get('q', '')
    query = Taller.query
    if estado:
        query = query.filter_by(estado=estado)
    if q:
        clientes_ids = [c.id for c in Cliente.query.filter(
            db.or_(Cliente.nombre.ilike(f'%{q}%'), Cliente.apellido.ilike(f'%{q}%'))
        ).all()]
        query = query.filter(
            db.or_(
                Taller.marca.ilike(f'%{q}%'),
                Taller.modelo.ilike(f'%{q}%'),
                Taller.cliente_id.in_(clientes_ids) if clientes_ids else False,
            )
        )
    # Orders with pending debt (entregado but unpaid) appear first
    talleres = query.order_by(
        db.case((db.and_(Taller.estado == 'entregado', Taller.pagado.is_(False)), 0), else_=1),
        Taller.created_at.desc()
    ).all()
    return render_template('taller/index.html', talleres=talleres, estados=ESTADOS,
                           estado_filtro=estado, q=q)


@taller_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    clientes = Cliente.query.order_by(Cliente.apellido).all()
    tecnicos = Tecnico.query.filter_by(activo=True).order_by(Tecnico.nombre).all()
    tecnicos_nombres = [t.nombre_display for t in tecnicos]
    if request.method == 'POST':
        fecha_est = None
        if request.form.get('fecha_estimada_entrega'):
            try:
                fecha_est = datetime.strptime(request.form['fecha_estimada_entrega'], '%Y-%m-%d')
            except ValueError:
                pass
        taller = Taller(
            numero=_next_numero(),
            cliente_id=int(request.form['cliente_id']),
            tipo_equipo=request.form.get('tipo_equipo', '').strip(),
            marca=request.form.get('marca', '').strip(),
            modelo=request.form.get('modelo', '').strip(),
            descripcion_problema=request.form['descripcion_problema'].strip(),
            observaciones=request.form.get('observaciones', '').strip(),
            estado=request.form.get('estado', 'recibido'),
            costo_estimado=float(request.form.get('costo_estimado') or 0),
            costo_reparacion=float(request.form.get('costo_reparacion') or 0),
            tecnico=request.form.get('tecnico', '').strip(),
            fecha_estimada_entrega=fecha_est,
        )
        db.session.add(taller)
        db.session.commit()

        # Send WhatsApp notification to the client
        try:
            cliente = taller.cliente
            if cliente and cliente.telefono:
                equipo_parts = [p for p in [taller.tipo_equipo, taller.marca, taller.modelo] if p]
                equipo = " ".join(equipo_parts) if equipo_parts else "Sin especificar"
                mensaje = (
                    f"🔧 Servicio Técnico\n\n"
                    f"Hola {cliente.nombre_completo}\n\n"
                    f"Su equipo fue recibido correctamente.\n\n"
                    f"📋 Orden: #{taller.numero}\n"
                    f"📱 Equipo: {equipo}\n"
                    f"🛠 Problema: {taller.descripcion_problema}\n\n"
                    f"Estado actual: En diagnóstico\n\n"
                    f"Le avisaremos cuando haya novedades."
                )
                enviar_whatsapp(cliente.telefono, mensaje)
        except Exception:
            pass

        flash(f'Orden de taller #{taller.numero} creada correctamente.', 'success')
        return redirect(url_for('taller.detalle', id=taller.id))
    return render_template('taller/form.html', taller=None, clientes=clientes,
                           estados=ESTADOS, tecnicos=tecnicos, tecnicos_nombres=tecnicos_nombres,
                           titulo='Nueva Orden de Taller')


@taller_bp.route('/<int:id>')
@login_required
def detalle(id):
    taller = Taller.query.get_or_404(id)
    productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
    servicios = Servicio.query.filter_by(activo=True).order_by(Servicio.nombre).all()
    categorias = Categoria.query.order_by(Categoria.nombre).all()
    return render_template('taller/detail.html', taller=taller, estados=ESTADOS,
                           productos=productos, servicios=servicios, categorias=categorias,
                           formas_pago=FORMAS_PAGO, cuentas_caja=CUENTAS_CAJA)


@taller_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    taller = Taller.query.get_or_404(id)
    clientes = Cliente.query.order_by(Cliente.apellido).all()
    tecnicos = Tecnico.query.filter_by(activo=True).order_by(Tecnico.nombre).all()
    tecnicos_nombres = [t.nombre_display for t in tecnicos]
    if request.method == 'POST':
        fecha_est = taller.fecha_estimada_entrega
        if request.form.get('fecha_estimada_entrega'):
            try:
                fecha_est = datetime.strptime(request.form['fecha_estimada_entrega'], '%Y-%m-%d')
            except ValueError:
                pass
        taller.cliente_id = int(request.form['cliente_id'])
        taller.tipo_equipo = request.form.get('tipo_equipo', '').strip()
        taller.marca = request.form.get('marca', '').strip()
        taller.modelo = request.form.get('modelo', '').strip()
        taller.descripcion_problema = request.form['descripcion_problema'].strip()
        taller.observaciones = request.form.get('observaciones', '').strip()
        taller.estado = request.form.get('estado', taller.estado)
        taller.costo_estimado = float(request.form.get('costo_estimado') or 0)
        taller.costo_reparacion = float(request.form.get('costo_reparacion') or 0)
        taller.tecnico = request.form.get('tecnico', '').strip()
        taller.fecha_estimada_entrega = fecha_est
        db.session.commit()
        flash('Orden de taller actualizada.', 'success')
        return redirect(url_for('taller.detalle', id=taller.id))
    return render_template('taller/form.html', taller=taller, clientes=clientes,
                           estados=ESTADOS, tecnicos=tecnicos, tecnicos_nombres=tecnicos_nombres,
                           titulo=f'Editar Orden #{taller.numero}')


@taller_bp.route('/<int:id>/agregar_producto', methods=['POST'])
@login_required
def agregar_producto(id):
    taller = Taller.query.get_or_404(id)
    producto_id = int(request.form['producto_id'])
    cantidad = int(request.form.get('cantidad', 1))
    producto = Producto.query.get_or_404(producto_id)

    if producto.stock_actual < cantidad:
        flash(f'Stock insuficiente. Solo hay {producto.stock_actual} {producto.unidad} disponibles.', 'danger')
        return redirect(url_for('taller.detalle', id=id))

    tp = TallerProducto(
        taller_id=taller.id,
        producto_id=producto_id,
        cantidad=cantidad,
        precio_unitario=producto.precio_venta,
    )
    producto.stock_actual -= cantidad
    db.session.add(tp)
    db.session.commit()
    flash(f'Producto "{producto.nombre}" agregado a la orden.', 'success')
    return redirect(url_for('taller.detalle', id=id))


@taller_bp.route('/<int:id>/quitar_producto/<int:tp_id>', methods=['POST'])
@login_required
def quitar_producto(id, tp_id):
    tp = TallerProducto.query.get_or_404(tp_id)
    tp.producto.stock_actual += tp.cantidad
    db.session.delete(tp)
    db.session.commit()
    flash('Producto quitado de la orden.', 'success')
    return redirect(url_for('taller.detalle', id=id))


@taller_bp.route('/<int:id>/agregar_servicio', methods=['POST'])
@login_required
def agregar_servicio(id):
    taller = Taller.query.get_or_404(id)
    servicio_id = int(request.form['servicio_id'])
    servicio = Servicio.query.get_or_404(servicio_id)
    precio = float(request.form.get('precio') or servicio.precio)

    ts = TallerServicio(
        taller_id=taller.id,
        servicio_id=servicio_id,
        precio=precio,
    )
    db.session.add(ts)
    db.session.commit()
    flash(f'Servicio "{servicio.nombre}" agregado a la orden.', 'success')
    return redirect(url_for('taller.detalle', id=id))


@taller_bp.route('/<int:id>/quitar_servicio/<int:ts_id>', methods=['POST'])
@login_required
def quitar_servicio(id, ts_id):
    ts = TallerServicio.query.get_or_404(ts_id)
    db.session.delete(ts)
    db.session.commit()
    flash('Servicio quitado de la orden.', 'success')
    return redirect(url_for('taller.detalle', id=id))


@taller_bp.route('/<int:id>/entregar', methods=['POST'])
@login_required
def entregar(id):
    taller = Taller.query.get_or_404(id)
    if taller.estado == 'entregado':
        flash('Esta orden ya fue entregada.', 'warning')
        return redirect(url_for('taller.detalle', id=id))

    forma_pago = request.form.get('forma_pago', 'efectivo')
    taller.estado = 'entregado'
    taller.forma_pago = forma_pago
    taller.fecha_entrega = datetime.utcnow()

    if forma_pago == 'cuenta_corriente':
        taller.pagado = False
        db.session.commit()
        flash(f'Orden #{taller.numero} entregada en cuenta corriente. La deuda queda pendiente de cobro.', 'warning')
    else:
        taller.pagado = True
        monto = taller.total_final
        mov = MovimientoCaja(
            tipo='ingreso',
            cuenta='servicio_tecnico',
            forma_pago=forma_pago,
            concepto=f'Reparación #{taller.numero} - {taller.cliente.nombre_completo}',
            monto=monto,
            referencia_tipo='taller',
            referencia_id=taller.id,
            fecha=datetime.utcnow(),
        )
        db.session.add(mov)
        db.session.commit()
        flash(f'Orden #{taller.numero} marcada como entregada y paga. Se registró ingreso de ${monto:.2f} en Caja.', 'success')
    return redirect(url_for('taller.detalle', id=id))


@taller_bp.route('/<int:id>/cobrar_deuda', methods=['POST'])
@login_required
def cobrar_deuda(id):
    taller = Taller.query.get_or_404(id)
    if taller.pagado:
        flash('Esta orden ya fue pagada.', 'warning')
        return redirect(url_for('taller.detalle', id=id))

    forma_pago = request.form.get('forma_pago', 'efectivo')
    monto = taller.total_final
    taller.pagado = True
    taller.forma_pago = forma_pago

    mov = MovimientoCaja(
        tipo='ingreso',
        cuenta='servicio_tecnico',
        forma_pago=forma_pago,
        concepto=f'Cobro cuenta corriente #{taller.numero} - {taller.cliente.nombre_completo}',
        monto=monto,
        referencia_tipo='taller',
        referencia_id=taller.id,
        fecha=datetime.utcnow(),
    )
    db.session.add(mov)
    db.session.commit()
    flash(f'Deuda de la orden #{taller.numero} cobrada. Se registró ingreso de ${monto:.2f} en Caja.', 'success')
    return redirect(url_for('taller.detalle', id=id))


@taller_bp.route('/<int:id>/cambiar_estado', methods=['POST'])
@login_required
def cambiar_estado(id):
    taller = Taller.query.get_or_404(id)
    nuevo_estado = request.form.get('estado')
    estados_validos = [e[0] for e in ESTADOS]
    if nuevo_estado in estados_validos:
        taller.estado = nuevo_estado
        db.session.commit()
        flash(f'Estado actualizado a "{dict(ESTADOS)[nuevo_estado]}".', 'success')
    return redirect(url_for('taller.detalle', id=id))


@taller_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar(id):
    taller = Taller.query.get_or_404(id)
    # Devolver stock de los productos usados
    for tp in taller.productos_usados:
        tp.producto.stock_actual += tp.cantidad
    db.session.delete(taller)
    db.session.commit()
    flash('Orden de taller eliminada.', 'success')
    return redirect(url_for('taller.index'))


@taller_bp.route('/<int:id>/imprimir')
@login_required
def imprimir(id):
    taller = Taller.query.get_or_404(id)
    return render_template('taller/print.html', taller=taller)


@taller_bp.route('/<int:id>/ticket')
@login_required
def ticket(id):
    taller = Taller.query.get_or_404(id)
    orden = {
        'fecha': taller.fecha_ingreso.strftime('%d/%m/%Y'),
        'numero': taller.numero,
        'cliente': taller.cliente.nombre_completo,
        'equipo': taller.tipo_equipo or '—',
        'marca': taller.marca or '—',
        'modelo': taller.modelo or '—',
        'problema': taller.descripcion_problema,
        'precio': f"{taller.costo_estimado:.2f}" if taller.costo_estimado is not None else '—',
        'tecnico': taller.tecnico or '—',
        'entrega': taller.fecha_estimada_entrega.strftime('%d/%m/%Y') if taller.fecha_estimada_entrega else '—',
    }
    return render_template('taller/ticket.html', orden=orden)
