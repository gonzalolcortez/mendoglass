from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import db, Cliente

clientes_bp = Blueprint('clientes', __name__)


@clientes_bp.route('/')
def index():
    q = request.args.get('q', '')
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
    return render_template('clientes/index.html', clientes=clientes, q=q)


@clientes_bp.route('/nuevo', methods=['GET', 'POST'])
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
    return render_template('clientes/form.html', cliente=None, titulo='Nuevo Cliente')


@clientes_bp.route('/<int:id>')
def detalle(id):
    cliente = Cliente.query.get_or_404(id)
    return render_template('clientes/detail.html', cliente=cliente)


@clientes_bp.route('/nuevo_rapido', methods=['POST'])
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
    return render_template('clientes/form.html', cliente=cliente, titulo='Editar Cliente')


@clientes_bp.route('/<int:id>/eliminar', methods=['POST'])
def eliminar(id):
    cliente = Cliente.query.get_or_404(id)
    if cliente.talleres or cliente.ventas:
        flash('No se puede eliminar un cliente con talleres o ventas asociadas.', 'danger')
        return redirect(url_for('clientes.detalle', id=id))
    db.session.delete(cliente)
    db.session.commit()
    flash('Cliente eliminado.', 'success')
    return redirect(url_for('clientes.index'))
