"""
Módulo de conexión con ARCA (ex AFIP) mediante el web service WSFEv1.

Usa la librería ``pyafipws`` para autenticación (WSAA) y emisión de
comprobantes (WSFEv1).  Cuando las variables de entorno con los
certificados no están configuradas el cliente opera en modo HOMOLOGACIÓN
(ambiente de pruebas), lo que permite desarrollar y testear sin
certificados reales.

Variables de entorno esperadas:
    ARCA_CUIT / AFIP_CUIT              CUIT del emisor (sin guiones)
    ARCA_CERT / AFIP_CERT              Contenido PEM del certificado X.509
    ARCA_KEY / AFIP_KEY                Contenido PEM de la clave privada
    ARCA_CERT_PATH / AFIP_CERT_PATH    Ruta a archivo .crt/.pem (opcional)
    ARCA_KEY_PATH / AFIP_KEY_PATH      Ruta a archivo .key/.pem (opcional)
    ARCA_PROD / AFIP_PROD              "true" para producción; otro valor = homo

Referencia AFIP:
    https://www.afip.gob.ar/fe/documentos/manual_desarrollador_COMPG_v2_9.pdf
"""

import os
import logging
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# WSDLs
# ──────────────────────────────────────────────────────────────
_WSAA_WSDL_HOMO = 'https://wsaahomo.afip.gov.ar/ws/services/LoginCms?WSDL'
_WSAA_WSDL_PROD = 'https://wsaa.afip.gov.ar/ws/services/LoginCms?WSDL'

_WSFE_WSDL_HOMO = (
    'https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL'
)
_WSFE_WSDL_PROD = (
    'https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL'
)

# ──────────────────────────────────────────────────────────────
# Tipos de IVA AFIP
# ──────────────────────────────────────────────────────────────
IVA_EXENTO = 3        # Exento
IVA_0 = 4             # 0 %
IVA_10_5 = 8          # 10.5 %
IVA_21 = 5            # 21 %
IVA_27 = 6            # 27 %

# Alícuota estándar para Responsables Inscriptos
ALICUOTA_IVA_DEFECTO = 21.0
ID_IVA_DEFECTO = IVA_21


class AfipError(Exception):
    """Excepción genérica para errores devueltos por ARCA/AFIP."""


def _env_first(*names: str) -> str:
    """Devuelve la primera variable de entorno no vacía."""
    for name in names:
        value = os.environ.get(name, '').strip()
        if value:
            return value
    return ''


def _es_produccion() -> bool:
    return _env_first('ARCA_PROD', 'AFIP_PROD').lower() == 'true'


def _wsdl_wsaa() -> str:
    return _WSAA_WSDL_PROD if _es_produccion() else _WSAA_WSDL_HOMO


def _wsdl_wsfe() -> str:
    return _WSFE_WSDL_PROD if _es_produccion() else _WSFE_WSDL_HOMO


def _normalizar_pem(valor: str) -> str:
    """Normaliza PEM cuando llega con saltos escapados (\\n)."""
    return valor.replace('\\n', '\n') if '\\n' in valor else valor


def _cert_key_paths() -> tuple[str | None, str | None, bool]:
    """Obtiene rutas de certificado y clave para WSAA.

    Prioridad:
    1) Rutas directas (ARCA_CERT_PATH/ARCA_KEY_PATH o AFIP_*)
    2) Contenido PEM en variables de entorno (ARCA_CERT/ARCA_KEY o AFIP_*)

    Returns:
        (cert_path, key_path, temporales)
    """
    cert_path = _env_first('ARCA_CERT_PATH', 'AFIP_CERT_PATH')
    key_path = _env_first('ARCA_KEY_PATH', 'AFIP_KEY_PATH')

    if cert_path and key_path:
        if not os.path.exists(cert_path):
            raise AfipError(f'No existe el certificado en {cert_path}')
        if not os.path.exists(key_path):
            raise AfipError(f'No existe la clave privada en {key_path}')
        return cert_path, key_path, False

    cert_pem = _normalizar_pem(_env_first('ARCA_CERT', 'AFIP_CERT'))
    key_pem = _normalizar_pem(_env_first('ARCA_KEY', 'AFIP_KEY'))
    if not cert_pem or not key_pem:
        return None, None, False

    cert_file = tempfile.NamedTemporaryFile(
        mode='w', suffix='.crt', delete=False
    )
    cert_file.write(cert_pem)
    cert_file.close()

    key_file = tempfile.NamedTemporaryFile(
        mode='w', suffix='.key', delete=False
    )
    key_file.write(key_pem)
    key_file.close()

    return cert_file.name, key_file.name, True


def _limpiar_archivos(*paths):
    for p in paths:
        try:
            if p:
                os.unlink(p)
        except OSError:
            pass


def _endpoint_desde_wsdl(wsdl_url: str) -> str:
    return wsdl_url.split('?', 1)[0]


def _extraer_token_y_sign(ta_xml: str) -> tuple[str, str]:
    try:
        raiz = ET.fromstring(ta_xml)
    except ET.ParseError as exc:
        raise AfipError(f'No se pudo parsear el TA devuelto por WSAA: {exc}') from exc

    token = raiz.findtext('.//token') or ''
    sign = raiz.findtext('.//sign') or ''
    if not token or not sign:
        raise AfipError('WSAA devolvió un TA sin token/sign.')
    return token, sign


def _extraer_ta_desde_soap(xml_respuesta: str) -> str:
    try:
        raiz = ET.fromstring(xml_respuesta)
    except ET.ParseError as exc:
        raise AfipError(f'No se pudo parsear la respuesta SOAP de WSAA: {exc}') from exc

    fault = raiz.find('.//{http://schemas.xmlsoap.org/soap/envelope/}Fault')
    if fault is not None:
        faultcode = fault.findtext('faultcode') or 'SOAP Fault'
        faultstring = fault.findtext('faultstring') or 'Error no informado por WSAA'
        raise AfipError(f'WSAA rechazó la autenticación ({faultcode}): {faultstring}')

    ta_node = raiz.find('.//{http://wsaa.view.sua.dvadac.desein.afip.gov}loginCmsReturn')
    if ta_node is None:
        ta_node = raiz.find('.//loginCmsReturn')
    if ta_node is None or not (ta_node.text or '').strip():
        raise AfipError('WSAA no devolvió loginCmsReturn en la respuesta SOAP.')

    return unescape(ta_node.text or '').strip()


def _obtener_ta_por_soap_directo(cert_path: str, key_path: str) -> tuple[str, str]:
    try:
        from pyafipws.wsaa import WSAA  # type: ignore
    except ImportError as exc:
        raise AfipError(
            'No se pudo importar pyafipws.wsaa para el fallback SOAP directo. '
            f'Error original: {exc}. '
            'Instalá dependencias: pyafipws y setuptools.'
        ) from exc

    wsaa = WSAA()
    tra = wsaa.CreateTRA('wsfe')
    cms = wsaa.SignTRA(tra, cert_path, key_path)

    endpoint = _endpoint_desde_wsdl(_wsdl_wsaa())
    envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov">
  <soapenv:Header/>
  <soapenv:Body>
    <wsaa:loginCms>
      <wsaa:in0>{cms}</wsaa:in0>
    </wsaa:loginCms>
  </soapenv:Body>
</soapenv:Envelope>'''.encode('utf-8')

    request = urllib.request.Request(
        endpoint,
        data=envelope,
        headers={
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': '',
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            respuesta_xml = response.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        respuesta_error = exc.read().decode('utf-8', errors='replace')
        ta_xml = _extraer_ta_desde_soap(respuesta_error)
        return _extraer_token_y_sign(ta_xml)
    except Exception as exc:
        raise AfipError(f'Error llamando WSAA por SOAP directo: {exc}') from exc

    ta_xml = _extraer_ta_desde_soap(respuesta_xml)
    return _extraer_token_y_sign(ta_xml)


# ──────────────────────────────────────────────────────────────
# Autenticación WSAA
# ──────────────────────────────────────────────────────────────

def _obtener_ta(cert_path: str, key_path: str) -> tuple:
    """Obtiene Token y Sign mediante WSAA.

    Returns:
        tuple: (token, sign)

    Raises:
        AfipError: si la autenticación falla.
    """
    try:
        from pyafipws.wsaa import WSAA  # type: ignore
    except ImportError as exc:
        raise AfipError(
            'No se pudo importar pyafipws.wsaa. '
            f'Error original: {exc}. '
            'Instalá dependencias: pyafipws y setuptools.'
        ) from exc

    wsaa = WSAA()
    try:
        ta_xml = wsaa.Autenticar(
            'wsfe',
            cert_path,
            key_path,
            wsdl=_wsdl_wsaa(),
            proxy=None,
            cacert=None,
            debug=False,
        )
    except Exception as exc:
        logger.warning(
            'Fallo autenticacion WSAA via WSDL, reintentando por SOAP directo: %s',
            exc,
        )
        return _obtener_ta_por_soap_directo(cert_path, key_path)

    if not ta_xml:
        raise AfipError(
            f'WSAA devolvió respuesta vacía. Errores: {wsaa.Excepcion}'
        )

    return wsaa.Token, wsaa.Sign


# ──────────────────────────────────────────────────────────────
# Cliente WSFEv1 principal
# ──────────────────────────────────────────────────────────────

class AfipClient:
    """Envuelve el ciclo completo de autenticación + emisión de facturas."""

    def __init__(self):
        self.cuit = _env_first('ARCA_CUIT', 'AFIP_CUIT')
        self._token = None
        self._sign = None
        self._wsfe = None

    # ── conexión ──────────────────────────────────────────────

    def conectar(self):
        """Autentica y establece la conexión con WSFEv1.

        Raises:
            AfipError: si faltan certificados o la conexión falla.
        """
        if not self.cuit:
            raise AfipError(
                'CUIT no configurado. '
                'Definí la variable de entorno con el CUIT del emisor.'
            )

        cert_path, key_path, es_temporal = _cert_key_paths()
        if not cert_path:
            raise AfipError(
                'Certificado digital no configurado. '
                'Definí ARCA_CERT/ARCA_KEY (o AFIP_*) o ARCA_CERT_PATH/ARCA_KEY_PATH.'
            )

        try:
            self._token, self._sign = _obtener_ta(cert_path, key_path)
        finally:
            if es_temporal:
                _limpiar_archivos(cert_path, key_path)

        try:
            from pyafipws.wsfev1 import WSFEv1  # type: ignore
        except ImportError as exc:
            raise AfipError(
                'No se pudo importar pyafipws.wsfev1. '
                f'Error original: {exc}. '
                'Instalá dependencias: pyafipws y setuptools.'
            ) from exc

        wsfe = WSFEv1()
        wsfe.Conectar(wsdl=_wsdl_wsfe(), proxy=None, cacert=None)
        wsfe.Cuit = self.cuit
        wsfe.Token = self._token
        wsfe.Sign = self._sign
        self._wsfe = wsfe

    def _wsfe_conectado(self):
        if self._wsfe is None:
            self.conectar()
        return self._wsfe

    # ── consultas ─────────────────────────────────────────────

    def ultimo_numero(self, tipo_cbte: int, punto_vta: int) -> int:
        """Devuelve el último número de comprobante autorizado.

        Args:
            tipo_cbte: Código AFIP del tipo de comprobante (1, 6, 11…).
            punto_vta: Punto de venta.

        Returns:
            Último número autorizado (0 si no hay ninguno).

        Raises:
            AfipError: ante cualquier error de comunicación.
        """
        wsfe = self._wsfe_conectado()
        try:
            ultimo = wsfe.CompUltimoAutorizado(tipo_cbte, punto_vta)
        except Exception as exc:
            raise AfipError(f'Error consultando último número: {exc}') from exc

        if wsfe.Excepcion:
            raise AfipError(wsfe.Excepcion)

        return int(ultimo or 0)

    # ── solicitud de CAE ──────────────────────────────────────

    def solicitar_cae(
        self,
        tipo_cbte: int,
        punto_vta: int,
        numero: int,
        fecha: str,                   # 'YYYYMMDD'
        concepto: int,                # 1=Productos, 2=Servicios, 3=Mixto
        tipo_doc: int,                # 80=CUIT, 86=CUIL, 96=DNI, 99=CF
        nro_doc: str,                 # CUIT/DNI del destinatario
        imp_neto: float,
        imp_iva: float,
        imp_total: float,
        ivas: list | None = None,
        moneda_id: str = 'PES',
        moneda_ctz: float = 1.0,
        fecha_serv_desde: str | None = None,  # 'YYYYMMDD' – requerido si concepto in (2,3)
        fecha_serv_hasta: str | None = None,  # 'YYYYMMDD' – requerido si concepto in (2,3)
        condicion_iva_receptor_id: int | None = None,
    ) -> dict:
        """Envía un comprobante a ARCA y devuelve el resultado.

        Para comprobantes de Servicios (concepto=2) o Mixto (concepto=3)
        ARCA exige ``fecha_serv_desde`` y ``fecha_serv_hasta``.  Si no se
        suministran se usa ``fecha`` como período de un día.

        Args:
            ivas: Lista de dicts con las alicuotas de IVA del comprobante.
                  Cada dict debe tener las claves ``iva_id`` (int, codigo AFIP),
                  ``base_imp`` (float, importe neto gravado) e ``importe``
                  (float, monto de IVA).  Si se omite y ``imp_iva > 0`` se
                  asume una unica alicuota al 21 % sobre todo el neto.

        Returns:
            dict con claves: cae, vencimiento_cae, numero, resultado.

        Raises:
            AfipError: si ARCA rechaza el comprobante o hay error de red.
        """
        wsfe = self._wsfe_conectado()

        # Para servicios/mixto ARCA requiere el período de prestación
        if concepto in (2, 3):
            fecha_serv_desde = fecha_serv_desde or fecha
            fecha_serv_hasta = fecha_serv_hasta or fecha

        # Construir la factura
        try:
            wsfe.CrearFactura(
                concepto=concepto,
                tipo_doc=tipo_doc,
                nro_doc=nro_doc,
                tipo_cbte=tipo_cbte,
                punto_vta=punto_vta,
                cbt_desde=numero,
                cbt_hasta=numero,
                imp_total=round(imp_total, 2),
                imp_tot_conc=0.00,
                imp_neto=round(imp_neto, 2),
                imp_iva=round(imp_iva, 2),
                imp_trib=0.00,
                imp_op_ex=0.00,
                fecha_cbte=fecha,
                moneda_id=moneda_id,
                moneda_ctz=moneda_ctz,
                fecha_serv_desde=fecha_serv_desde,
                fecha_serv_hasta=fecha_serv_hasta,
                condicion_iva_receptor_id=condicion_iva_receptor_id,
            )
        except Exception as exc:
            raise AfipError(f'Error construyendo la factura: {exc}') from exc

        # Agregar alícuotas de IVA.  ARCA permite múltiples alícuotas por
        # comprobante (p.ej. items al 21 % e items al 10.5 %).
        if imp_iva > 0:
            if ivas:
                for iva in ivas:
                    wsfe.AgregarIva(
                        iva_id=iva['iva_id'],
                        base_imp=round(iva['base_imp'], 2),
                        importe=round(iva['importe'], 2),
                    )
            else:
                # Fallback: una única alícuota al 21 % sobre todo el neto
                wsfe.AgregarIva(
                    iva_id=IVA_21,
                    base_imp=round(imp_neto, 2),
                    importe=round(imp_iva, 2),
                )

        # Solicitar CAE
        try:
            wsfe.CAESolicitar()
        except Exception as exc:
            raise AfipError(f'Error solicitando CAE: {exc}') from exc

        if wsfe.Resultado != 'A':
            errores = wsfe.ErrMsg or wsfe.Obs or wsfe.Excepcion or 'Comprobante rechazado por ARCA'
            raise AfipError(f'ARCA rechazó el comprobante: {errores}')

        return {
            'cae': wsfe.CAE,
            'vencimiento_cae': wsfe.Vencimiento,   # 'YYYYMMDD'
            'numero': int(wsfe.CbtDesde or numero),
            'resultado': wsfe.Resultado,
        }


# ──────────────────────────────────────────────────────────────
# Helpers para determinar tipo de documento del receptor
# ──────────────────────────────────────────────────────────────

def tipo_doc_receptor(condicion_iva: str, cuit: str | None) -> tuple:
    """Devuelve (tipo_doc_afip, nro_doc) según condición de IVA del receptor.

    Args:
        condicion_iva: 'CF', 'RI', 'M' o 'EX'.
        cuit: CUIT del receptor (puede ser None para CF).

    Returns:
        (tipo_doc_afip: int, nro_doc: str)
    """
    if condicion_iva == 'CF' or not cuit:
        return 99, '0'    # Consumidor Final
    cuit_limpio = cuit.replace('-', '').replace('.', '').strip()
    return 80, cuit_limpio   # CUIT


def validar_cuit(cuit: str) -> bool:
    """Verifica el dígito verificador de un CUIT/CUIL argentino.

    Args:
        cuit: CUIT con o sin guiones.

    Returns:
        True si es válido.
    """
    cuit_limpio = cuit.replace('-', '').replace('.', '').replace(' ', '')
    if len(cuit_limpio) != 11 or not cuit_limpio.isdigit():
        return False

    multiplicadores = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    suma = sum(int(d) * m for d, m in zip(cuit_limpio[:10], multiplicadores))
    dv_esperado = 11 - (suma % 11)
    if dv_esperado == 11:
        dv_esperado = 0
    elif dv_esperado == 10:
        return False   # CUIT inválido por definición

    return int(cuit_limpio[10]) == dv_esperado
