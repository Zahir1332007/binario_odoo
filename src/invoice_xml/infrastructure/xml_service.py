"""Servicios de serialización XML UBL 2.1 y validación estricta contra Invoice XSD 2.1."""

from __future__ import annotations

from pathlib import Path

from lxml import etree
from xsdata.formats.dataclass.context import XmlContext
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig

from invoice_xml.domain.exceptions import XmlSchemaValidationError
from invoice_xml.infrastructure.ubl_models.maindoc.ubl_invoice_2_1 import (
    Invoice as UblInvoice,
)

UBL_NS_MAP = {
    None: "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
}

DEFAULT_INVOICE_XSD_PATH = (
    Path(__file__).resolve().parents[3]
    / "schemas"
    / "ubl-2.1"
    / "maindoc"
    / "UBL-Invoice-2.1.xsd"
)


def serialize_ubl_invoice(ubl_invoice: UblInvoice, *, pretty_print: bool = True) -> str:
    """Serializa una instancia `UblInvoice` a XML UTF-8 con namespaces OASIS UBL 2.1."""
    config = SerializerConfig(
        encoding="UTF-8",
        xml_declaration=True,
        indent="  " if pretty_print else None,
    )
    serializer = XmlSerializer(context=XmlContext(), config=config)
    return serializer.render(ubl_invoice, ns_map=UBL_NS_MAP)


class XsdValidator:
    """Validador contra el esquema oficial OASIS UBL-Invoice-2.1.xsd."""

    def __init__(self, xsd_path: Path | str = DEFAULT_INVOICE_XSD_PATH) -> None:
        self.xsd_path = Path(xsd_path)
        if not self.xsd_path.exists():
            raise FileNotFoundError(
                f"No se encontró el archivo XSD en '{self.xsd_path}'."
            )
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        schema_doc = etree.parse(str(self.xsd_path), parser=parser)
        self._schema = etree.XMLSchema(schema_doc)

    def validate(self, xml_content: str | bytes) -> None:
        """Valida un documento XML contra Invoice XSD 2.1; lanza `XmlSchemaValidationError` si falla."""
        raw_bytes = (
            xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content
        )
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        try:
            xml_doc = etree.fromstring(raw_bytes, parser=parser)
        except etree.XMLSyntaxError as exc:
            raise XmlSchemaValidationError(
                f"El contenido no es un XML bien formado: {exc}",
                details=[str(exc)],
            ) from exc

        if not self._schema.validate(xml_doc):
            errors = [
                f"Línea {err.line}: {err.message}" for err in self._schema.error_log
            ]
            raise XmlSchemaValidationError(
                f"El XML generado no cumple con {self.xsd_path.name} ({len(errors)} error(es)).",
                details=errors,
            )
