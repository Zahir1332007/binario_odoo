"""Interfaz de línea de comandos para generar facturas XML UBL 2.1 desde Odoo o modo demo."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from invoice_xml.application import GenerateInvoiceXmlUseCase
from invoice_xml.domain.exceptions import InvoiceDomainError, XmlSchemaValidationError
from invoice_xml.infrastructure import (
    DEFAULT_XML_ENCODING,
    OdooConnectionConfig,
    OdooConnectionError,
    OdooXmlRpcClient,
)

DEMO_ODOO_PAYLOAD = {
    "name": "FE01-00000573",
    "invoice_date": "2026-11-11",
    "invoice_date_due": "2026-12-11",
    "currency": "PEN",
    "invoice_origin": "SO0001",
    "narration": "Factura electrónica generada bajo estándar SUNAT Perú UBL 2.1",
    "company": {
        "vat": "20123456789",
        "name": "Empresa Demo Perú S.A.C.",
        "street": "Av. Universitaria s/n",
        "city": "Tingo María",
        "zip": "10131",
        "country_code": "PE",
        "email": "ventas@empresademo.pe",
    },
    "partner": {
        "vat": "20987654321",
        "name": "Cliente Demo S.R.L.",
        "street": "Jr. Alameda Perú 210",
        "city": "Tingo María",
        "zip": "10131",
        "country_code": "PE",
        "email": "compras@clientedemo.pe",
    },
    "invoice_lines": [
        {
            "default_code": "ODOO-SRV-01",
            "name": "Servicio de consultoría Odoo Ventas",
            "quantity": "1",
            "price_unit": "850.00",
            "uom_code": "ZZ",
            "tax_ids": [{"name": "IGV 18%", "amount": 18.0}],
        }
    ],
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="invoice-xml",
        description="Genera facturas XML OASIS UBL 2.1 validadas contra XSD 2.1 desde Odoo.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Genera un XML de ejemplo sin conectarse a Odoo.",
    )
    parser.add_argument(
        "--source",
        choices=("invoice", "sale"),
        default="invoice",
        help="Origen en Odoo: 'invoice' (account.move) o 'sale' (sale.order).",
    )
    parser.add_argument(
        "--number",
        default=None,
        help="Número exacto en Odoo (ej. INV/2026/0001 o S00001). Si se omite, toma el más reciente.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Archivo (.xml) o carpeta de salida (genera {RUC}-{TIPO}-{SERIE}-{CORRELATIVO}.xml). Si se omite, imprime en stdout.",
    )
    parser.add_argument(
        "--series",
        default=None,
        help="Serie SUNAT de 4 caracteres cuando Odoo usa numeración interna (ej. F001 o FE01).",
    )
    parser.add_argument(
        "--encoding",
        default=DEFAULT_XML_ENCODING,
        help=f"Codificación XML de salida (por defecto {DEFAULT_XML_ENCODING}).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    use_case = GenerateInvoiceXmlUseCase()

    try:
        if args.demo:
            payload = dict(DEMO_ODOO_PAYLOAD)
            if args.series:
                payload["series"] = args.series
            if args.output:
                saved = use_case.execute_from_odoo_to_file(
                    payload, args.output, encoding=args.encoding
                )
                print(f"XML UBL 2.1 validado ({args.encoding}) y guardado en: {saved}")
            else:
                print(use_case.execute_from_odoo(payload, encoding=args.encoding))
        else:
            config = OdooConnectionConfig.from_env()
            client = OdooXmlRpcClient(config)
            if args.output:
                saved = use_case.execute_from_odoo_gateway_to_file(
                    client,
                    args.output,
                    document_number=args.number,
                    source=args.source,
                    series=args.series,
                    encoding=args.encoding,
                )
                print(f"XML UBL 2.1 validado ({args.encoding}) y guardado en: {saved}")
            else:
                print(
                    use_case.execute_from_odoo_gateway(
                        client,
                        document_number=args.number,
                        source=args.source,
                        encoding=args.encoding,
                    )
                )
    except (OdooConnectionError, InvoiceDomainError, XmlSchemaValidationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
