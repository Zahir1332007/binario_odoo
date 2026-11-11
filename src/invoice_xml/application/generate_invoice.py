"""Caso de uso de generación de XML UBL 2.1 a partir de dominio o payload de Odoo."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from invoice_xml.application.odoo_adapter import odoo_payload_to_domain
from invoice_xml.application.ports import OdooInvoiceGateway
from invoice_xml.domain.models import Invoice
from invoice_xml.infrastructure.mapper import domain_to_ubl_invoice
from invoice_xml.infrastructure.xml_service import XsdValidator, serialize_ubl_invoice


class GenerateInvoiceXmlUseCase:
    """Orquesta la conversión, serialización y validación XSD 2.1 de una factura."""

    def __init__(self, validator: XsdValidator | None = None) -> None:
        self._validator = validator

    @property
    def validator(self) -> XsdValidator:
        if self._validator is None:
            self._validator = XsdValidator()
        return self._validator

    def execute(
        self,
        invoice: Invoice,
        *,
        validate_xsd: bool = True,
        pretty_print: bool = True,
    ) -> str:
        """Genera el XML UBL 2.1 para una factura de dominio y opcionalmente lo valida."""
        ubl_invoice = domain_to_ubl_invoice(invoice)
        xml_output = serialize_ubl_invoice(ubl_invoice, pretty_print=pretty_print)
        if validate_xsd:
            self.validator.validate(xml_output)
        return xml_output

    def execute_from_odoo(
        self,
        payload: Mapping[str, Any],
        *,
        validate_xsd: bool = True,
        pretty_print: bool = True,
    ) -> str:
        """Genera el XML UBL 2.1 directamente desde un payload de Odoo Ventas/Facturación."""
        invoice = odoo_payload_to_domain(payload)
        return self.execute(
            invoice, validate_xsd=validate_xsd, pretty_print=pretty_print
        )

    def execute_from_odoo_gateway(
        self,
        gateway: OdooInvoiceGateway,
        *,
        document_number: str | None = None,
        source: Literal["invoice", "sale"] = "invoice",
        validate_xsd: bool = True,
        pretty_print: bool = True,
    ) -> str:
        """Consulta Odoo a través del puerto `OdooInvoiceGateway` y genera el XML UBL 2.1."""
        if source == "invoice":
            payload = gateway.fetch_invoice_payload(document_number)
        elif source == "sale":
            payload = gateway.fetch_sale_order_payload(document_number)
        else:
            raise ValueError(
                f"Origen Odoo no soportado: '{source}'. Use 'invoice' o 'sale'."
            )
        return self.execute_from_odoo(
            payload, validate_xsd=validate_xsd, pretty_print=pretty_print
        )

    def execute_to_file(
        self,
        invoice: Invoice,
        output_path: Path | str,
        *,
        validate_xsd: bool = True,
        pretty_print: bool = True,
    ) -> Path:
        """Genera el XML validado y lo persiste en disco con codificación UTF-8."""
        xml_output = self.execute(
            invoice,
            validate_xsd=validate_xsd,
            pretty_print=pretty_print,
        )
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(xml_output, encoding="utf-8")
        return destination
