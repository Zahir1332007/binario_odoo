"""Caso de uso de generación de XML UBL 2.1 a partir de dominio o payload de Odoo."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from invoice_xml.application.odoo_adapter import odoo_payload_to_domain
from invoice_xml.application.ports import OdooInvoiceGateway
from invoice_xml.domain.models import Invoice
from invoice_xml.infrastructure.mapper import domain_to_ubl_invoice
from invoice_xml.infrastructure.xml_service import (
    DEFAULT_XML_ENCODING,
    XsdValidator,
    serialize_ubl_invoice,
    write_xml_file,
)


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
        encoding: str = DEFAULT_XML_ENCODING,
    ) -> str:
        """Genera el XML UBL 2.1 para una factura de dominio y opcionalmente lo valida."""
        ubl_invoice = domain_to_ubl_invoice(invoice)
        xml_output = serialize_ubl_invoice(
            ubl_invoice, pretty_print=pretty_print, encoding=encoding
        )
        if validate_xsd:
            self.validator.validate(xml_output)
        return xml_output

    def execute_from_odoo(
        self,
        payload: Mapping[str, Any],
        *,
        validate_xsd: bool = True,
        pretty_print: bool = True,
        encoding: str = DEFAULT_XML_ENCODING,
    ) -> str:
        """Genera el XML UBL 2.1 directamente desde un payload de Odoo Ventas/Facturación."""
        invoice = odoo_payload_to_domain(payload)
        return self.execute(
            invoice,
            validate_xsd=validate_xsd,
            pretty_print=pretty_print,
            encoding=encoding,
        )

    def execute_from_odoo_gateway(
        self,
        gateway: OdooInvoiceGateway,
        *,
        document_number: str | None = None,
        source: Literal["invoice", "sale"] = "invoice",
        validate_xsd: bool = True,
        pretty_print: bool = True,
        encoding: str = DEFAULT_XML_ENCODING,
    ) -> str:
        """Consulta Odoo a través del puerto `OdooInvoiceGateway` y genera el XML UBL 2.1."""
        payload = self._fetch_gateway_payload(gateway, document_number, source)
        return self.execute_from_odoo(
            payload,
            validate_xsd=validate_xsd,
            pretty_print=pretty_print,
            encoding=encoding,
        )

    def _fetch_gateway_payload(
        self,
        gateway: OdooInvoiceGateway,
        document_number: str | None,
        source: Literal["invoice", "sale"],
    ) -> Mapping[str, Any]:
        if source == "invoice":
            return gateway.fetch_invoice_payload(document_number)
        if source == "sale":
            return gateway.fetch_sale_order_payload(document_number)
        raise ValueError(
            f"Origen Odoo no soportado: '{source}'. Use 'invoice' o 'sale'."
        )

    def execute_to_file(
        self,
        invoice: Invoice,
        output_path: Path | str,
        *,
        validate_xsd: bool = True,
        pretty_print: bool = True,
        encoding: str = DEFAULT_XML_ENCODING,
    ) -> Path:
        """Genera el XML validado y lo persiste en disco con su codificación declarada."""
        xml_output = self.execute(
            invoice,
            validate_xsd=validate_xsd,
            pretty_print=pretty_print,
            encoding=encoding,
        )
        target = Path(output_path)
        if target.is_dir() or target.suffix.lower() != ".xml":
            target = target / invoice.sunat_filename
        return write_xml_file(xml_output, target)

    def execute_from_odoo_to_file(
        self,
        payload: Mapping[str, Any],
        output_path: Path | str,
        *,
        validate_xsd: bool = True,
        pretty_print: bool = True,
        encoding: str = DEFAULT_XML_ENCODING,
    ) -> Path:
        """Convierte payload Odoo, valida XML y guarda en archivo o carpeta usando nombre SUNAT."""
        invoice = odoo_payload_to_domain(payload)
        return self.execute_to_file(
            invoice,
            output_path,
            validate_xsd=validate_xsd,
            pretty_print=pretty_print,
            encoding=encoding,
        )

    def execute_from_odoo_gateway_to_file(
        self,
        gateway: OdooInvoiceGateway,
        output_path: Path | str,
        *,
        document_number: str | None = None,
        source: Literal["invoice", "sale"] = "invoice",
        series: str | None = None,
        validate_xsd: bool = True,
        pretty_print: bool = True,
        encoding: str = DEFAULT_XML_ENCODING,
    ) -> Path:
        """Consulta Odoo y guarda el XML en disco usando el nombre oficial SUNAT si se pasa carpeta."""
        payload = dict(self._fetch_gateway_payload(gateway, document_number, source))
        if series:
            payload["series"] = series
        return self.execute_from_odoo_to_file(
            payload,
            output_path,
            validate_xsd=validate_xsd,
            pretty_print=pretty_print,
            encoding=encoding,
        )
