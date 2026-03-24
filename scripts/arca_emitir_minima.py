import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from modules.facturacion.afip_client import AfipClient, AfipError


AFIP_IVA_ID = {
    0.0: 4,
    10.5: 8,
    21.0: 5,
    27.0: 6,
}

TIPOS_CBTE = {
    1: 'Factura A',
    6: 'Factura B',
    11: 'Factura C',
}

TIPOS_DOC = {
    80: 'CUIT',
    86: 'CUIL',
    96: 'DNI',
    99: 'Consumidor Final',
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Emision controlada de factura minima ARCA. Por defecto solo previsualiza.'
    )
    parser.add_argument('--punto-vta', type=int, default=1)
    parser.add_argument('--tipo-cbte', type=int, default=6)
    parser.add_argument('--importe-total', type=float, default=1.0)
    parser.add_argument('--alicuota-iva', type=float, default=21.0)
    parser.add_argument('--tipo-doc', type=int, default=99)
    parser.add_argument('--nro-doc', default='0')
    parser.add_argument('--concepto', type=int, default=1)
    parser.add_argument('--emitir', action='store_true')
    parser.add_argument(
        '--confirmacion',
        default='',
        help='Debe ser exactamente EMITIR para habilitar la emision real.',
    )
    return parser


def calcular_importes(total: float, alicuota_iva: float) -> tuple[float, float, list | None]:
    total = round(total, 2)
    if alicuota_iva <= 0:
        return total, 0.0, None

    divisor = 1 + (alicuota_iva / 100)
    imp_neto = round(total / divisor, 2)
    imp_iva = round(total - imp_neto, 2)
    ivas = [
        {
            'iva_id': AFIP_IVA_ID.get(alicuota_iva, 5),
            'base_imp': imp_neto,
            'importe': imp_iva,
        }
    ]
    return imp_neto, imp_iva, ivas


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    ambiente = 'produccion' if os.environ.get('ARCA_PROD', '').lower() == 'true' else 'homologacion'
    fecha = datetime.now().strftime('%Y%m%d')
    imp_neto, imp_iva, ivas = calcular_importes(args.importe_total, args.alicuota_iva)

    print('=== ARCA Emision Minima ===')
    print(f'Ambiente: {ambiente}')
    print(f'CUIT emisor: {os.environ.get("ARCA_CUIT") or os.environ.get("AFIP_CUIT") or "(no configurado)"}')
    print(f'Tipo comprobante: {args.tipo_cbte} ({TIPOS_CBTE.get(args.tipo_cbte, "Otro")})')
    print(f'Punto de venta: {args.punto_vta}')
    print(f'Receptor: tipo_doc={args.tipo_doc} ({TIPOS_DOC.get(args.tipo_doc, "Otro")}), nro_doc={args.nro_doc}')
    print(f'Importes: total={args.importe_total:.2f}, neto={imp_neto:.2f}, iva={imp_iva:.2f}')

    try:
        afip = AfipClient()
        afip.conectar()
        ultimo = afip.ultimo_numero(args.tipo_cbte, args.punto_vta)
        siguiente = ultimo + 1
    except AfipError as exc:
        print(f'ERROR_PRECHECK={exc}')
        return 1

    print(f'ULTIMO_NUMERO={ultimo}')
    print(f'PROXIMO_NUMERO={siguiente}')

    if not args.emitir:
        print('MODO=simulacion')
        print('EMISION_REAL=false')
        print('Para emitir de verdad usar: --emitir --confirmacion EMITIR')
        return 0

    if args.confirmacion != 'EMITIR':
        print('ERROR_CONFIRMACION=Debe pasar --confirmacion EMITIR para emitir realmente.')
        return 1

    try:
        resultado = afip.solicitar_cae(
            tipo_cbte=args.tipo_cbte,
            punto_vta=args.punto_vta,
            numero=siguiente,
            fecha=fecha,
            concepto=args.concepto,
            tipo_doc=args.tipo_doc,
            nro_doc=str(args.nro_doc),
            imp_neto=imp_neto,
            imp_iva=imp_iva,
            imp_total=round(args.importe_total, 2),
            ivas=ivas,
        )
    except AfipError as exc:
        print(f'ERROR_EMISION={exc}')
        return 1

    print('EMISION_REAL=true')
    print(f"CAE={resultado['cae']}")
    print(f"VENCIMIENTO_CAE={resultado.get('vencimiento_cae', '')}")
    print(f"NUMERO={resultado['numero']}")
    print(f"RESULTADO={resultado['resultado']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())