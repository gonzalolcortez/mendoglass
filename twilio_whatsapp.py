import logging
import os

from twilio.rest import Client


ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = "whatsapp:+14155238886"

logger = logging.getLogger(__name__)


def _normalizar_numero(numero):
    """Normaliza el número a dígitos para formato E.164 sin prefijo '+'."""
    if numero is None:
        return ""
    numero_str = str(numero).strip()
    if numero_str.startswith("+"):
        numero_str = numero_str[1:]
    return "".join(ch for ch in numero_str if ch.isdigit())


def enviar_whatsapp(numero, mensaje):
    """Envía un WhatsApp usando Twilio Sandbox.

    Args:
        numero: Número destino, con o sin '+' (ej: 5491123456789).
        mensaje: Texto a enviar.

    Returns:
        SID del mensaje enviado o None si falla.
    """
    if not ACCOUNT_SID or not AUTH_TOKEN:
        logger.warning(
            "[Twilio WhatsApp] Credenciales faltantes. Configure TWILIO_ACCOUNT_SID y TWILIO_AUTH_TOKEN."
        )
        return None

    numero_limpio = _normalizar_numero(numero)
    if not numero_limpio:
        logger.warning("[Twilio WhatsApp] Número de destino inválido: %r", numero)
        return None

    try:
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
        mensaje_enviado = client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            body=mensaje,
            to=f"whatsapp:+{numero_limpio}",
        )
        logger.info(
            "[Twilio WhatsApp] Mensaje enviado correctamente. to=%s sid=%s",
            numero_limpio,
            mensaje_enviado.sid,
        )
        return mensaje_enviado.sid
    except Exception as exc:
        logger.exception("[Twilio WhatsApp] Error al enviar mensaje a %s: %s", numero_limpio, exc)
        return None
