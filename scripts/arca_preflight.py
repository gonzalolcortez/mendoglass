import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from modules.facturacion.afip_client import AfipClient, AfipError


TIPOS_CBTE = {
    1: 'Factura A',
    6: 'Factura B',
    11: 'Factura C',
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Valida autenticacion ARCA/WSFE y consulta ultimo comprobante autorizado.'
    )
    parser.add_argument(
        '--tipo-cbte',
        type=int,
        default=6,
        help='Codigo AFIP del comprobante. Default: 6 (Factura B).',
    )
    parser.add_argument(
        '--punto-vta',
        type=int,
        default=1,
        help='Punto de venta a consultar. Default: 1.',
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    print('=== ARCA Preflight ===')
    print(f"Ambiente: {'produccion' if os.environ.get('ARCA_PROD', '').lower() == 'true' else 'homologacion'}")
    print(f"CUIT: {os.environ.get('ARCA_CUIT') or os.environ.get('AFIP_CUIT') or '(no configurado)'}")
    print(f"Cert path: {os.environ.get('ARCA_CERT_PATH') or os.environ.get('AFIP_CERT_PATH') or '(por variable PEM)'}")
    print(f"Key path: {os.environ.get('ARCA_KEY_PATH') or os.environ.get('AFIP_KEY_PATH') or '(por variable PEM)'}")
    print(f"Consulta: tipo_cbte={args.tipo_cbte} ({TIPOS_CBTE.get(args.tipo_cbte, 'Otro')}), punto_vta={args.punto_vta}")

    try:
        afip = AfipClient()
        afip.conectar()
        ultimo = afip.ultimo_numero(args.tipo_cbte, args.punto_vta)
    except AfipError as exc:
        print(f'ERROR_ARCA={exc}')
        return 1
    except Exception as exc:
        print(f'ERROR_NO_CONTROLADO={exc}')
        return 1

    print('AUTH_OK=true')
    print(f'ULTIMO_NUMERO={ultimo}')
    print('PRECHECK_OK=true')
    return 0


if __name__ == '__main__':
    sys.exit(main())