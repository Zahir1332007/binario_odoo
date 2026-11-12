"""Capa de infraestructura para mapeo, serialización, validación XSD e integración Odoo."""

from invoice_xml.infrastructure.mapper import domain_to_ubl_invoice
from invoice_xml.infrastructure.odoo_client import (
    OdooConnectionConfig,
    OdooConnectionError,
    OdooXmlRpcClient,
)
from invoice_xml.infrastructure.xml_service import (
    DEFAULT_INVOICE_XSD_PATH,
    DEFAULT_XML_ENCODING,
    XsdValidator,
    encode_xml_bytes,
    serialize_ubl_invoice,
    write_xml_file,
)

__all__ = [
    "DEFAULT_INVOICE_XSD_PATH",
    "DEFAULT_XML_ENCODING",
    "OdooConnectionConfig",
    "OdooConnectionError",
    "OdooXmlRpcClient",
    "XsdValidator",
    "domain_to_ubl_invoice",
    "encode_xml_bytes",
    "serialize_ubl_invoice",
    "write_xml_file",
]
