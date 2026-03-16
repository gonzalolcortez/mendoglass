"""
Generador de PDF para comprobantes electrónicos.

Usa ReportLab para construir el PDF y la librería qrcode para el
código QR obligatorio según la resolución AFIP 1702/2024.

El QR codifica la URL:
    https://www.afip.gob.ar/fe/qr/?p=<base64url(json)>

donde json contiene los datos del comprobante.
"""

import io
import json
import base64
import logging
import os
from datetime import date

logger = logging.getLogger(__name__)

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph,
        Spacer, HRFlowable, Image,
    )
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False
    logger.warning('reportlab no disponible; la generación de PDF estará deshabilitada.')

try:
    import qrcode as qrcode_lib
    QRCODE_OK = True
except ImportError:
    QRCODE_OK = False
    logger.warning('qrcode no disponible; el QR no se incluirá en el PDF.')


# ──────────────────────────────────────────────────────────────
# QR obligatorio AFIP / ARCA
# ──────────────────────────────────────────────────────────────

def _build_qr_url(factura, cuit_emisor):
    """Construye la URL del QR según especificación AFIP.

    Args:
        factura: Objeto Factura ya emitido (debe tener CAE y número).
        cuit_emisor: CUIT del emisor (string sin guiones).

    Returns:
        URL como str.
    """
    tipo_doc_rec = 99   # Consumidor Final por defecto
    nro_doc_rec = 0
    if factura.cliente.condicion_iva != 'CF' and factura.cliente.cuit:
        tipo_doc_rec = 80
        nro_doc_rec = int(
            factura.cliente.cuit.replace('-', '').replace('.', '')
        )

    payload = {
        'ver': 1,
        'fecha': factura.fecha.strftime('%Y-%m-%d'),
        'cuit': int(cuit_emisor),
        'ptoVta': factura.punto_vta,
        'tipoCmp': factura.tipo_cbte,
        'nroCmp': factura.numero,
        'importe': float(factura.total),
        'moneda': 'PES',
        'ctz': 1,
        'tipoDocRec': tipo_doc_rec,
        'nroDocRec': nro_doc_rec,
        'tipoCodAut': 'E',
        'codAut': int(factura.cae) if factura.cae else 0,
    }
    json_str = json.dumps(payload, separators=(',', ':'))
    encoded = base64.urlsafe_b64encode(json_str.encode()).decode()
    return f'https://www.afip.gob.ar/fe/qr/?p={encoded}'


def _generar_imagen_qr(url):
    """Genera la imagen QR como BytesIO.

    Returns:
        BytesIO con la imagen PNG, o None si qrcode no está disponible.
    """
    if not QRCODE_OK:
        return None
    qr = qrcode_lib.QRCode(
        version=1,
        error_correction=qrcode_lib.constants.ERROR_CORRECT_M,
        box_size=4,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf


# ──────────────────────────────────────────────────────────────
# Generación del PDF
# ──────────────────────────────────────────────────────────────

def generar_pdf(factura, cuit_emisor=None, nombre_empresa=None, logo_path=None):
    """Genera el PDF del comprobante electrónico.

    Args:
        factura: Objeto Factura con sus items y cliente cargados.
        cuit_emisor: CUIT del emisor (toma de AFIP_CUIT si es None).
        nombre_empresa: Razón social del emisor.
        logo_path: Ruta al logo de la empresa (opcional).

    Returns:
        BytesIO con el contenido del PDF.

    Raises:
        RuntimeError: si reportlab no está instalado.
    """
    if not REPORTLAB_OK:
        raise RuntimeError(
            'reportlab no está instalado. '
            'Ejecutá: pip install reportlab'
        )

    cuit_emisor = cuit_emisor or os.environ.get('AFIP_CUIT', '—')
    nombre_empresa = nombre_empresa or os.environ.get(
        'EMPRESA_NOMBRE', 'Mi Empresa'
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    style_normal = styles['Normal']
    style_h1 = ParagraphStyle(
        'h1_fact', parent=styles['Heading1'],
        fontSize=16, spaceAfter=2
    )
    style_h2 = ParagraphStyle(
        'h2_fact', parent=styles['Heading2'],
        fontSize=11, spaceAfter=2
    )
    style_small = ParagraphStyle(
        'small', parent=style_normal, fontSize=8, leading=10
    )
    style_center = ParagraphStyle(
        'center', parent=style_normal, alignment=TA_CENTER
    )
    style_right = ParagraphStyle(
        'right', parent=style_normal, alignment=TA_RIGHT
    )
    style_bold_center = ParagraphStyle(
        'bold_center', parent=style_normal,
        alignment=TA_CENTER, fontName='Helvetica-Bold', fontSize=10
    )

    story = []

    # ── Encabezado ────────────────────────────────────────────
    letra = factura.letra

    header_data = []

    # Columna izquierda: logo + datos emisor
    emisor_lines = [
        Paragraph(f'<b>{nombre_empresa}</b>', style_h2),
        Paragraph(f'CUIT: {cuit_emisor}', style_small),
        Paragraph(
            f'Punto de Venta: <b>{factura.punto_vta:04d}</b>', style_small
        ),
    ]
    if logo_path and os.path.exists(logo_path):
        logo_img = Image(logo_path, width=40 * mm, height=20 * mm)
        emisor_lines.insert(0, logo_img)

    # Columna central: letra del comprobante
    letra_cell = [
        Spacer(1, 2 * mm),
        Paragraph(f'<b>{letra}</b>', ParagraphStyle(
            'letra', parent=style_normal,
            fontSize=36, alignment=TA_CENTER, fontName='Helvetica-Bold',
        )),
        Paragraph(factura.tipo_cbte_display, style_center),
    ]

    # Columna derecha: número y fecha
    derecha_lines = [
        Paragraph(
            f'N° <b>{factura.numero_display}</b>', style_right
        ),
        Paragraph(
            f'Fecha: <b>{factura.fecha.strftime("%d/%m/%Y")}</b>', style_right
        ),
        Paragraph(
            f'Estado: {factura.estado.capitalize()}', style_small
        ),
    ]

    header_data = [[emisor_lines, letra_cell, derecha_lines]]
    header_table = Table(header_data, colWidths=[65 * mm, 50 * mm, 65 * mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (1, 0), (1, 0), 1.5, colors.black),
        ('LEFTPADDING', (1, 0), (1, 0), 4),
        ('RIGHTPADDING', (1, 0), (1, 0), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width='100%', thickness=1, color=colors.black))
    story.append(Spacer(1, 3 * mm))

    # ── Datos del cliente ─────────────────────────────────────
    cliente = factura.cliente
    story.append(Paragraph('<b>Receptor</b>', style_h2))

    receptor_data = [
        ['Nombre / Razón Social:', cliente.nombre],
        ['Condición IVA:', dict(CONDICIONES_IVA_MAP).get(
            cliente.condicion_iva, cliente.condicion_iva
        )],
        ['CUIT:', cliente.cuit or '—'],
        ['Domicilio:', cliente.direccion or '—'],
        ['E-mail:', cliente.email or '—'],
    ]
    receptor_table = Table(receptor_data, colWidths=[55 * mm, 125 * mm])
    receptor_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(receptor_table)
    story.append(Spacer(1, 4 * mm))

    # ── Detalle ───────────────────────────────────────────────
    story.append(Paragraph('<b>Detalle</b>', style_h2))

    det_header = ['Descripción', 'Cant.', 'Precio Unit.', 'Subtotal']
    det_rows = [det_header]
    for it in factura.items:
        det_rows.append([
            Paragraph(it.descripcion, style_small),
            f'{float(it.cantidad):.2f}',
            f'$ {float(it.precio_unitario):,.2f}',
            f'$ {float(it.subtotal):,.2f}',
        ])

    det_table = Table(
        det_rows,
        colWidths=[100 * mm, 20 * mm, 30 * mm, 30 * mm],
    )
    det_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1f2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fb')]),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#e5e7eb')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(det_table)
    story.append(Spacer(1, 4 * mm))

    # ── Totales ───────────────────────────────────────────────
    totales_data = []
    if factura.tipo_cbte in (1, 3):   # Factura A / NC A: IVA discriminado
        totales_data.append(['Subtotal neto:', f'$ {float(factura.subtotal):,.2f}'])
        totales_data.append([f'IVA 21 %:', f'$ {float(factura.iva):,.2f}'])
    totales_data.append(['TOTAL:', f'$ {float(factura.total):,.2f}'])

    tot_table = Table(totales_data, colWidths=[130 * mm, 50 * mm])
    tot_style = [
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]
    last = len(totales_data) - 1
    tot_style += [
        ('FONTNAME', (0, last), (-1, last), 'Helvetica-Bold'),
        ('FONTSIZE', (0, last), (-1, last), 11),
        ('LINEABOVE', (0, last), (-1, last), 1, colors.black),
    ]
    tot_table.setStyle(TableStyle(tot_style))
    story.append(tot_table)
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 4 * mm))

    # ── CAE + QR ─────────────────────────────────────────────
    cae_qr_data = []

    cae_info = [
        Paragraph('<b>Información del CAE</b>', style_h2),
        Paragraph(f'CAE N°: <b>{factura.cae or "—"}</b>', style_normal),
        Paragraph(
            f'Vencimiento CAE: <b>'
            f'{factura.vencimiento_cae.strftime("%d/%m/%Y") if factura.vencimiento_cae else "—"}'
            f'</b>',
            style_normal,
        ),
        Spacer(1, 2 * mm),
        Paragraph('Forma de pago: ' + (factura.forma_pago or '—'), style_small),
    ]

    # QR
    qr_cell = []
    if factura.cae and factura.numero:
        qr_url = _build_qr_url(factura, cuit_emisor)
        qr_buf = _generar_imagen_qr(qr_url)
        if qr_buf:
            qr_img = Image(qr_buf, width=35 * mm, height=35 * mm)
            qr_cell.append(qr_img)
            qr_cell.append(
                Paragraph(
                    'Código QR obligatorio\nAFIP / ARCA',
                    ParagraphStyle(
                        'qr_label', parent=style_small, alignment=TA_CENTER
                    ),
                )
            )

    cae_qr_data.append([cae_info, qr_cell])
    cae_table = Table(cae_qr_data, colWidths=[130 * mm, 50 * mm])
    cae_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (1, 0), (1, 0), 0.5, colors.grey),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
    ]))
    story.append(cae_table)

    # ── Notas ─────────────────────────────────────────────────
    if factura.notas:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph('<b>Observaciones:</b>', style_small))
        story.append(Paragraph(factura.notas, style_small))

    # ── Pie de página ─────────────────────────────────────────
    story.append(Spacer(1, 8 * mm))
    story.append(HRFlowable(width='100%', thickness=0.3, color=colors.grey))
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            'Comprobante generado electrónicamente. '
            'Verificá su validez en www.afip.gob.ar/fe/qr',
            ParagraphStyle(
                'footer', parent=style_small,
                alignment=TA_CENTER, textColor=colors.grey,
            ),
        )
    )

    doc.build(story)
    buf.seek(0)
    return buf


# ──────────────────────────────────────────────────────────────
# Constante auxiliar para el PDF (evita importar models dentro de la función)
# ──────────────────────────────────────────────────────────────
CONDICIONES_IVA_MAP = {
    'CF': 'Consumidor Final',
    'RI': 'Responsable Inscripto',
    'M':  'Monotributista',
    'EX': 'Exento',
}
