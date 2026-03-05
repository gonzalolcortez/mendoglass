from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from models import db, Cliente, Proveedor

clientes_bp = Blueprint('clientes', __name__)


@clientes_bp.route('/')
@login_required
def index():
    tab = request.args.get('tab', 'clientes')
    q = request.args.get('q', '')

    if tab == 'proveedores':
        if q:
            proveedores = Proveedor.query.filter(
                db.or_(
                    Proveedor.nombre.ilike(f'%{q}%'),
                    Proveedor.apellido.ilike(f'%{q}%'),
                    Proveedor.telefono.ilike(f'%{q}%'),
                    Proveedor.email.ilike(f'%{q}%'),
                )
            ).order_by(Proveedor.apellido).all()
        else:
            proveedores = Proveedor.query.order_by(Proveedor.apellido).all()
        return render_template('clientes/index.html', clientes=[], proveedores=proveedores,
                               tab=tab, q=q)

    if q:
        clientes = Cliente.query.filter(
            db.or_(
                Cliente.nombre.ilike(f'%{q}%'),
                Cliente.apellido.ilike(f'%{q}%'),
                Cliente.telefono.ilike(f'%{q}%'),
                Cliente.email.ilike(f'%{q}%'),
            )
        ).order_by(Cliente.apellido).all()
    else:
        clientes = Cliente.query.order_by(Cliente.apellido).all()
    return render_template('clientes/index.html', clientes=clientes, proveedores=[],
                           tab=tab, q=q)


@clientes_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if request.method == 'POST':
        cliente = Cliente(
            nombre=request.form['nombre'].strip(),
            apellido=request.form['apellido'].strip(),
            telefono=request.form.get('telefono', '').strip(),
            email=request.form.get('email', '').strip(),
            direccion=request.form.get('direccion', '').strip(),
            notas=request.form.get('notas', '').strip(),
        )
        db.session.add(cliente)
        db.session.commit()
        flash('Cliente creado correctamente.', 'success')
        return redirect(url_for('clientes.index'))
    return render_template('clientes/form.html', entity=None, titulo='Nuevo Cliente',
                           cancel_url=url_for('clientes.index'))


@clientes_bp.route('/<int:id>')
@login_required
def detalle(id):
    cliente = Cliente.query.get_or_404(id)
    return render_template('clientes/detail.html', cliente=cliente)


@clientes_bp.route('/nuevo_rapido', methods=['POST'])
@login_required
def nuevo_rapido():
    nombre = request.form.get('nombre', '').strip()
    apellido = request.form.get('apellido', '').strip()
    if not nombre or not apellido:
        return jsonify({'error': 'Nombre y apellido son obligatorios.'}), 400
    cliente = Cliente(
        nombre=nombre,
        apellido=apellido,
        telefono=request.form.get('telefono', '').strip(),
        email=request.form.get('email', '').strip(),
        direccion=request.form.get('direccion', '').strip(),
        notas=request.form.get('notas', '').strip(),
    )
    db.session.add(cliente)
    db.session.commit()
    return jsonify({'id': cliente.id, 'nombre_completo': cliente.nombre_completo,
                    'telefono': cliente.telefono})


@clientes_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    cliente = Cliente.query.get_or_404(id)
    if request.method == 'POST':
        cliente.nombre = request.form['nombre'].strip()
        cliente.apellido = request.form['apellido'].strip()
        cliente.telefono = request.form.get('telefono', '').strip()
        cliente.email = request.form.get('email', '').strip()
        cliente.direccion = request.form.get('direccion', '').strip()
        cliente.notas = request.form.get('notas', '').strip()
        db.session.commit()
        flash('Cliente actualizado correctamente.', 'success')
        return redirect(url_for('clientes.detalle', id=cliente.id))
    return render_template('clientes/form.html', entity=cliente, titulo='Editar Cliente',
                           cancel_url=url_for('clientes.detalle', id=cliente.id))


@clientes_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar(id):
    cliente = Cliente.query.get_or_404(id)
    if cliente.talleres or cliente.ventas:
        flash('No se puede eliminar un cliente con talleres o ventas asociadas.', 'danger')
        return redirect(url_for('clientes.detalle', id=id))
    db.session.delete(cliente)
    db.session.commit()
    flash('Cliente eliminado.', 'success')
    return redirect(url_for('clientes.index'))


# ── Proveedores ──────────────────────────────────────────────────────────────

@clientes_bp.route('/proveedor/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_proveedor():
    if request.method == 'POST':
        proveedor = Proveedor(
            nombre=request.form['nombre'].strip(),
            apellido=request.form['apellido'].strip(),
            telefono=request.form.get('telefono', '').strip(),
            email=request.form.get('email', '').strip(),
            direccion=request.form.get('direccion', '').strip(),
            notas=request.form.get('notas', '').strip(),
        )
        db.session.add(proveedor)
        db.session.commit()
        flash('Proveedor creado correctamente.', 'success')
        return redirect(url_for('clientes.index', tab='proveedores'))
    return render_template('clientes/form.html', entity=None, titulo='Nuevo Proveedor',
                           cancel_url=url_for('clientes.index', tab='proveedores'))


@clientes_bp.route('/proveedor/<int:id>')
@login_required
def detalle_proveedor(id):
    proveedor = Proveedor.query.get_or_404(id)
    return render_template('clientes/detail_proveedor.html', proveedor=proveedor)


@clientes_bp.route('/proveedor/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_proveedor(id):
    proveedor = Proveedor.query.get_or_404(id)
    if request.method == 'POST':
        proveedor.nombre = request.form['nombre'].strip()
        proveedor.apellido = request.form['apellido'].strip()
        proveedor.telefono = request.form.get('telefono', '').strip()
        proveedor.email = request.form.get('email', '').strip()
        proveedor.direccion = request.form.get('direccion', '').strip()
        proveedor.notas = request.form.get('notas', '').strip()
        db.session.commit()
        flash('Proveedor actualizado correctamente.', 'success')
        return redirect(url_for('clientes.detalle_proveedor', id=proveedor.id))
    return render_template('clientes/form.html', entity=proveedor, titulo='Editar Proveedor',
                           cancel_url=url_for('clientes.detalle_proveedor', id=proveedor.id))


@clientes_bp.route('/proveedor/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_proveedor(id):
    proveedor = Proveedor.query.get_or_404(id)
    if proveedor.ingresos:
        flash('No se puede eliminar un proveedor con ingresos de mercadería asociados.', 'danger')
        return redirect(url_for('clientes.detalle_proveedor', id=id))
    db.session.delete(proveedor)
    db.session.commit()
    flash('Proveedor eliminado.', 'success')
    return redirect(url_for('clientes.index', tab='proveedores'))
