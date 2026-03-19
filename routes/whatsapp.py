from flask import Blueprint, request, Response


whatsapp_bp = Blueprint('whatsapp', __name__)


def _twiml_message(texto):
    return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response><Message>{texto}</Message></Response>"


@whatsapp_bp.route('/whatsapp', methods=['POST'])
def webhook_whatsapp():
    body = (request.form.get('Body') or '').strip().lower()

    if body == 'hola':
        respuesta = 'Hola. Gracias por escribirnos. Si queres consultar una orden, envia: orden 1234'
    elif body.startswith('orden '):
        numero_orden = body.replace('orden ', '', 1).strip()
        if numero_orden.isdigit():
            respuesta = f'Estado de la orden {numero_orden}: En diagnostico (mock)'
        else:
            respuesta = 'Formato invalido. Ejemplo correcto: orden 1234'
    else:
        respuesta = 'No entendi tu mensaje. Escribi hola o orden 1234'

    return Response(_twiml_message(respuesta), mimetype='application/xml')
