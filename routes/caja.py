import io

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required
from models import (
    db,
    MovimientoCaja,
    ClienteCuentaCorrienteMovimiento,
    Cliente,
    CUENTAS_CAJA,
    FORMAS_PAGO,
    normalizar_forma_pago,
)
from datetime import datetime, date
from sqlalchemy import func, case
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

caja_bp = Blueprint('caja', __name__)


@caja_bp.route('/')
@login_required
def index():
    vista = request.args.get('vista', 'caja').strip() or 'caja'
    if vista not in ('caja', 'cuentas_corrientes'):
        vista = 'caja'
    orden = (request.args.get('orden') or 'asc').strip().lower()
    if orden not in ('asc', 'desc'):
        orden = 'asc'

    today = date.today().strftime('%Y-%m-%d')
    forma_pago_filter = normalizar_forma_pago(request.args.get('forma_pago', ''), default='')
    referencia_filter = request.args.get('referencia', '').strip()

    # Si se filtra por forma de pago desde las tarjetas, no aplicar fecha por defecto
    if forma_pago_filter:
        fecha_desde = request.args.get('fecha_desde', '')
        fecha_hasta = request.args.get('fecha_hasta', '')
    else:
        fecha_desde = request.args.get('fecha_desde', today)
        fecha_hasta = request.args.get('fecha_hasta', today)

    tipo = request.args.get('tipo', '')

    query_base = MovimientoCaja.query
    if tipo in ('ingreso', 'egreso'):
        query_base = query_base.filter_by(tipo=tipo)
    if forma_pago_filter:
        if forma_pago_filter == 'banco':
            query_base = query_base.filter(MovimientoCaja.forma_pago.in_(['banco', 'transferencia', 'transferencia_bancaria']))
        else:
            query_base = query_base.filter_by(forma_pago=forma_pago_filter)
    if referencia_filter == 'tecnico_cc':
        query_base = query_base.filter_by(referencia_tipo='tecnico_cc')

    query = query_base
    dt_desde = None
    if fecha_desde:
        try:
            dt_desde = datetime.strptime(fecha_desde, '%Y-%m-%d')
            query = query.filter(MovimientoCaja.fecha >= dt_desde)
        except ValueError:
            dt_desde = None
    if fecha_hasta:
        try:
            dt_hasta = datetime.strptime(fecha_hasta, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(MovimientoCaja.fecha <= dt_hasta)
        except ValueError:
            pass

    saldo_inicial = 0.0
    if dt_desde is not None:
        ingresos_previos, egresos_previos = query_base.filter(MovimientoCaja.fecha < dt_desde).with_entities(
            func.coalesce(func.sum(case((MovimientoCaja.tipo == 'ingreso', MovimientoCaja.monto), else_=0.0)), 0.0),
            func.coalesce(func.sum(case((MovimientoCaja.tipo == 'egreso', MovimientoCaja.monto), else_=0.0)), 0.0),
        ).first()
        saldo_inicial = (ingresos_previos or 0.0) - (egresos_previos or 0.0)

    # Para saldo acumulado por fila necesitamos recorrer de más antiguo a más nuevo.
    movimientos_asc = query.order_by(MovimientoCaja.fecha.asc(), MovimientoCaja.id.asc()).all()

    saldo_acumulado = saldo_inicial
    movimientos = []
    for mov in movimientos_asc:
        ingreso = (mov.monto or 0.0) if mov.tipo == 'ingreso' else 0.0
        egreso = (mov.monto or 0.0) if mov.tipo == 'egreso' else 0.0
        saldo_acumulado += ingreso - egreso
        movimientos.append({
            'mov': mov,
            'ingreso': ingreso,
            'egreso': egreso,
            'saldo': saldo_acumulado,
        })

    saldo_final = saldo_acumulado
    if orden == 'desc':
        movimientos.reverse()

    total_ingresos, total_egresos = query.with_entities(
        func.coalesce(func.sum(case((MovimientoCaja.tipo == 'ingreso', MovimientoCaja.monto), else_=0.0)), 0.0),
        func.coalesce(func.sum(case((MovimientoCaja.tipo == 'egreso', MovimientoCaja.monto), else_=0.0)), 0.0),
    ).first()
    balance = total_ingresos - total_egresos

    # Saldos por forma de pago usando agregación DB (todos los movimientos, sin filtro).
    rows_fp = (
        db.session.query(MovimientoCaja.tipo, MovimientoCaja.forma_pago, func.sum(MovimientoCaja.monto))
        .group_by(MovimientoCaja.tipo, MovimientoCaja.forma_pago)
        .all()
    )

    saldos_fp = {}
    for mov_tipo, fp, total in rows_fp:
        key = normalizar_forma_pago(fp)
        if mov_tipo == 'ingreso':
            saldos_fp[key] = saldos_fp.get(key, 0.0) + total
        elif mov_tipo == 'egreso':
            saldos_fp[key] = saldos_fp.get(key, 0.0) - total

    query_cc = ClienteCuentaCorrienteMovimiento.query.join(Cliente)
    if fecha_desde:
        try:
            query_cc = query_cc.filter(ClienteCuentaCorrienteMovimiento.fecha >= datetime.strptime(fecha_desde, '%Y-%m-%d'))
        except ValueError:
            pass
    if fecha_hasta:
        try:
            dt_hasta = datetime.strptime(fecha_hasta, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query_cc = query_cc.filter(ClienteCuentaCorrienteMovimiento.fecha <= dt_hasta)
        except ValueError:
            pass

    movimientos_cc = query_cc.order_by(ClienteCuentaCorrienteMovimiento.fecha.desc()).all()
    total_cargos_cc = sum((m.monto or 0.0) for m in movimientos_cc if m.tipo == 'cargo')
    total_abonos_cc = sum((m.monto or 0.0) for m in movimientos_cc if m.tipo == 'abono')
    saldo_cc = total_cargos_cc - total_abonos_cc

    return render_template('caja/index.html',
                           movimientos=movimientos,
                           movimientos_cc=movimientos_cc,
                           total_ingresos=total_ingresos,
                           total_egresos=total_egresos,
                           balance=balance,
                           total_cargos_cc=total_cargos_cc,
                           total_abonos_cc=total_abonos_cc,
                           saldo_cc=saldo_cc,
                           fecha_desde=fecha_desde,
                           fecha_hasta=fecha_hasta,
                           saldo_inicial=saldo_inicial,
                           saldo_final=saldo_final,
                           tipo=tipo,
                           orden=orden,
                           vista=vista,
                           forma_pago_filter=forma_pago_filter,
                           referencia_filter=referencia_filter,
                           saldos_fp=saldos_fp,
                           formas_pago=FORMAS_PAGO,
                           cuentas_caja=CUENTAS_CAJA)


def _build_movimientos_caja(args):
    today = date.today().strftime('%Y-%m-%d')
    forma_pago_filter = normalizar_forma_pago(args.get('forma_pago', ''), default='')
    referencia_filter = args.get('referencia', '').strip()
    orden = (args.get('orden') or 'asc').strip().lower()
    if orden not in ('asc', 'desc'):
        orden = 'asc'

    if forma_pago_filter:
        fecha_desde = args.get('fecha_desde', '')
        fecha_hasta = args.get('fecha_hasta', '')
    else:
        fecha_desde = args.get('fecha_desde', today)
        fecha_hasta = args.get('fecha_hasta', today)

    tipo = args.get('tipo', '')

    query_base = MovimientoCaja.query
    if tipo in ('ingreso', 'egreso'):
        query_base = query_base.filter_by(tipo=tipo)
    if forma_pago_filter:
        if forma_pago_filter == 'banco':
            query_base = query_base.filter(MovimientoCaja.forma_pago.in_(['banco', 'transferencia', 'transferencia_bancaria']))
        else:
            query_base = query_base.filter_by(forma_pago=forma_pago_filter)
    if referencia_filter == 'tecnico_cc':
        query_base = query_base.filter_by(referencia_tipo='tecnico_cc')

    query = query_base
    dt_desde = None
    if fecha_desde:
        try:
            dt_desde = datetime.strptime(fecha_desde, '%Y-%m-%d')
            query = query.filter(MovimientoCaja.fecha >= dt_desde)
        except ValueError:
            dt_desde = None
    if fecha_hasta:
        try:
            dt_hasta = datetime.strptime(fecha_hasta, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(MovimientoCaja.fecha <= dt_hasta)
        except ValueError:
            pass

    saldo_inicial = 0.0
    if dt_desde is not None:
        ingresos_previos, egresos_previos = query_base.filter(MovimientoCaja.fecha < dt_desde).with_entities(
            func.coalesce(func.sum(case((MovimientoCaja.tipo == 'ingreso', MovimientoCaja.monto), else_=0.0)), 0.0),
            func.coalesce(func.sum(case((MovimientoCaja.tipo == 'egreso', MovimientoCaja.monto), else_=0.0)), 0.0),
        ).first()
        saldo_inicial = (ingresos_previos or 0.0) - (egresos_previos or 0.0)

    movimientos_asc = query.order_by(MovimientoCaja.fecha.asc(), MovimientoCaja.id.asc()).all()
    saldo_acumulado = saldo_inicial
    movimientos = []
    for mov in movimientos_asc:
        ingreso = (mov.monto or 0.0) if mov.tipo == 'ingreso' else 0.0
        egreso = (mov.monto or 0.0) if mov.tipo == 'egreso' else 0.0
        saldo_acumulado += ingreso - egreso
        movimientos.append({
            'mov': mov,
            'ingreso': ingreso,
            'egreso': egreso,
            'saldo': saldo_acumulado,
        })

    if orden == 'desc':
        movimientos.reverse()

    return {
        'movimientos': movimientos,
        'saldo_inicial': saldo_inicial,
        'saldo_final': saldo_acumulado,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'tipo': tipo,
        'forma_pago_filter': forma_pago_filter,
        'referencia_filter': referencia_filter,
        'orden': orden,
    }


def _exportar_caja_xlsx(contexto):
    cuentas_dict = dict(CUENTAS_CAJA)
    formas_dict = dict(FORMAS_PAGO)

    workbook = Workbook()
    ws = workbook.active
    ws.title = 'Caja'
    ws.append(['Fecha', 'Cuenta', 'Forma de Pago', 'Concepto', 'Ingreso', 'Egreso', 'Saldo'])
    ws.append(['', '', '', 'Saldo inicial', '', '', contexto['saldo_inicial']])

    for r in contexto['movimientos']:
        mov = r['mov']
        fp = mov.forma_pago or 'efectivo'
        fp_label = 'Banco' if fp in ['transferencia', 'transferencia_bancaria'] else formas_dict.get(fp, fp or '-')
        ws.append([
            mov.fecha.strftime('%d/%m/%Y %H:%M') if mov.fecha else '',
            cuentas_dict.get(mov.cuenta or 'otro', mov.cuenta or '-'),
            fp_label,
            mov.concepto,
            r['ingreso'] or '',
            r['egreso'] or '',
            r['saldo'],
        ])

    ws.append(['', '', '', 'Saldo final', '', '', contexto['saldo_final']])

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


def _exportar_caja_pdf(contexto):
    cuentas_dict = dict(CUENTAS_CAJA)
    formas_dict = dict(FORMAS_PAGO)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    story = [Paragraph('Movimientos de Caja', styles['Title']), Spacer(1, 12)]

    data = [['Fecha', 'Cuenta', 'Forma Pago', 'Concepto', 'Ingreso', 'Egreso', 'Saldo']]
    data.append(['', '', '', 'Saldo inicial', '', '', f"${contexto['saldo_inicial']:.2f}"])

    for r in contexto['movimientos']:
        mov = r['mov']
        fp = mov.forma_pago or 'efectivo'
        fp_label = 'Banco' if fp in ['transferencia', 'transferencia_bancaria'] else formas_dict.get(fp, fp or '-')
        data.append([
            mov.fecha.strftime('%d/%m/%Y %H:%M') if mov.fecha else '',
            cuentas_dict.get(mov.cuenta or 'otro', mov.cuenta or '-'),
            fp_label,
            mov.concepto,
            f"${r['ingreso']:.2f}" if r['ingreso'] else '',
            f"${r['egreso']:.2f}" if r['egreso'] else '',
            f"${r['saldo']:.2f}",
        ])

    data.append(['', '', '', 'Saldo final', '', '', f"${contexto['saldo_final']:.2f}"])

    tabla = Table(data, hAlign='LEFT', colWidths=[95, 105, 110, 220, 80, 80, 80])
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dbe5f1')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f5f5f5')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f5f5f5')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (3, 1), (3, 1), 'Helvetica-Bold'),
        ('FONTNAME', (3, -1), (3, -1), 'Helvetica-Bold'),
        ('ALIGN', (4, 1), (6, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]))

    story.append(tabla)
    doc.build(story)
    buffer.seek(0)
    return buffer


@caja_bp.route('/export/<formato>')
@login_required
def exportar(formato):
    contexto = _build_movimientos_caja(request.args)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if formato == 'xlsx':
        buffer = _exportar_caja_xlsx(contexto)
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'caja_{timestamp}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    if formato == 'pdf':
        buffer = _exportar_caja_pdf(contexto)
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'caja_{timestamp}.pdf',
            mimetype='application/pdf',
        )

    return ('Formato no soportado', 400)


@caja_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if request.method == 'POST':
        mov = MovimientoCaja(
            tipo=request.form['tipo'],
            cuenta=request.form.get('cuenta', 'otro'),
            forma_pago=normalizar_forma_pago(request.form.get('forma_pago', 'efectivo')),
            concepto=request.form['concepto'].strip(),
            monto=float(request.form['monto']),
            referencia_tipo='manual',
            notas=request.form.get('notas', '').strip(),
            fecha=datetime.now(),
        )
        db.session.add(mov)
        db.session.commit()
        flash('Movimiento registrado en Caja.', 'success')
        return redirect(url_for('caja.index'))
    return render_template('caja/form.html', cuentas=CUENTAS_CAJA, formas_pago=FORMAS_PAGO)


@caja_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar(id):
    mov = MovimientoCaja.query.get_or_404(id)
    if mov.referencia_tipo in ('taller', 'venta', 'tecnico_cc'):
        flash('No se puede eliminar un movimiento generado automáticamente.', 'danger')
        return redirect(url_for('caja.index'))
    db.session.delete(mov)
    db.session.commit()
    flash('Movimiento eliminado.', 'success')
    return redirect(url_for('caja.index'))
