import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from modules.facturacion.afip_client import AfipClient, AfipError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Consulta puntos de venta habilitados en ARCA/WSFE y opcionalmente sondea un rango.'
    )
    parser.add_argument('--tipo-cbte', type=int, default=6)
    parser.add_argument('--scan-desde', type=int)
    parser.add_argument('--scan-hasta', type=int)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    ambiente = 'produccion' if os.environ.get('ARCA_PROD', '').lower() == 'true' else 'homologacion'
    print('=== ARCA Puntos de Venta ===')
    print(f'Ambiente: {ambiente}')
    print(f"CUIT: {os.environ.get('ARCA_CUIT') or os.environ.get('AFIP_CUIT') or '(no configurado)'}")
    print(f'Tipo comprobante para sonda: {args.tipo_cbte}')

    try:
        client = AfipClient()
        client.conectar()
        wsfe = client._wsfe_conectado()
    except AfipError as exc:
        print(f'ERROR_AUTH={exc}')
        return 1

    puntos = wsfe.ParamGetPtosVenta('|')
    print('PUNTOS_OFICIALES=')
    if puntos:
        for punto in puntos:
            print(punto)
    else:
        print('(sin resultados)')

    err_msg = getattr(wsfe, 'ErrMsg', '') or ''
    obs = getattr(wsfe, 'Obs', '') or ''
    if err_msg:
        print(f'ERRMSG={err_msg}')
    if obs:
        print(f'OBS={obs}')

    if args.scan_desde is None or args.scan_hasta is None:
        return 0

    print('SCAN_RESULTADOS=')
    for punto in range(args.scan_desde, args.scan_hasta + 1):
        try:
            ultimo = client.ultimo_numero(args.tipo_cbte, punto)
            print(f'pto={punto}|ok=true|ultimo={ultimo}')
        except AfipError as exc:
            print(f'pto={punto}|ok=false|error={exc}')

    return 0


if __name__ == '__main__':
    sys.exit(main())