"""Interfaz de línea de comandos para generar facturas XML UBL 2.1 desde Odoo o modo demo."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from invoice_xml.application import GenerateInvoiceXmlUseCase
from invoice_xml.domain.exceptions import InvoiceDomainError, XmlSchemaValidationError
from invoice_xml.infrastructure import (
    OdooConnectionConfig,
    OdooConnectionError,
    OdooXmlRpcClient,
)

DEMO_ODOO_PAYLOAD = {
    "name": "INV/2026/0001",
    "invoice_date": "2026-11-11",
    "invoice_date_due": "2026-12-11",
    "currency": "PEN",
    "invoice_origin": "SO0001",
    "narration": "Factura generada en modo demo compatible con Odoo Ventas",
    "company": {
        "vat": "20123456789",
        "name": "Empresa Demo Odoo S.A.C.",
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
        help="Ruta de archivo donde guardar el XML generado. Si se omite, imprime en stdout.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    use_case = GenerateInvoiceXmlUseCase()

    try:
        if args.demo:
            xml_output = use_case.execute_from_odoo(DEMO_ODOO_PAYLOAD)
        else:
            config = OdooConnectionConfig.from_env()
            client = OdooXmlRpcClient(config)
            xml_output = use_case.execute_from_odoo_gateway(
                client,
                document_number=args.number,
                source=args.source,
            )
    except (OdooConnectionError, InvoiceDomainError, XmlSchemaValidationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(xml_output, encoding="utf-8")
        print(f"XML UBL 2.1 validado y guardado en: {args.output}")
    else:
        print(xml_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
