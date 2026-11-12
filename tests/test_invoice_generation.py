"""Pruebas unitarias de generación y validación XML OASIS UBL 2.1 (Invoice XSD 2.1)."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest
from lxml import etree
from xsdata.formats.dataclass.parsers import XmlParser

from invoice_xml.application import GenerateInvoiceXmlUseCase
from invoice_xml.domain import (
    Address,
    Invoice,
    InvoiceDomainError,
    InvoiceLine,
    Party,
    XmlSchemaValidationError,
)
from invoice_xml.infrastructure import (
    DEFAULT_INVOICE_XSD_PATH,
    XsdValidator,
    encode_xml_bytes,
)
from invoice_xml.infrastructure.ubl_models.maindoc.ubl_invoice_2_1 import (
    Invoice as UblInvoice,
)

NS = {
    "inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}


@pytest.fixture(scope="module")
def xsd_validator() -> XsdValidator:
    """Instancia compartida del validador compilado a partir de UBL-Invoice-2.1.xsd."""
    return XsdValidator(DEFAULT_INVOICE_XSD_PATH)


@pytest.fixture
def sample_invoice() -> Invoice:
    supplier = Party(
        tax_id="20123456789",
        tax_scheme_id="VAT",
        legal_name="Selva Tech S.A.C.",
        registration_name="Selva Tech Sociedad Anónima Cerrada",
        address=Address(
            street="Av. Raymondi 450",
            city="Tingo María",
            postal_zone="10131",
            country_code="PE",
        ),
        email="facturacion@selvatech.pe",
    )
    customer = Party(
        tax_id="20987654321",
        tax_scheme_id="VAT",
        legal_name="Comercial Agrícola UNAS S.R.L.",
        address=Address(
            street="Jr. Enrique Pimentel 120",
            city="Huánuco",
            postal_zone="10001",
            country_code="PE",
        ),
        email="compras@agricolaunas.pe",
    )
    lines = (
        InvoiceLine(
            line_id="1",
            item_code="SRV-ODOO-01",
            item_name="Implementación módulo Ventas Odoo",
            description="Configuración y despliegue desde código fuente",
            quantity=Decimal(2),
            unit_price=Decimal("500.00"),
            unit_code="ZZ",
            tax_rate=Decimal("0.18"),
        ),
        InvoiceLine(
            line_id="2",
            item_code="LIC-SUP-02",
            item_name="Soporte técnico mensual",
            quantity=Decimal(3),
            unit_price=Decimal("100.50"),
            unit_code="MON",
            tax_rate=Decimal("0.18"),
        ),
    )
    return Invoice(
        invoice_id="F001-0000123",
        issue_date=date(2026, 11, 11),
        issue_time=time(15, 30, 0),
        due_date=date(2026, 12, 11),
        currency_code="PEN",
        order_reference_id="SO-2026-0042",
        note="Factura generada desde módulo de Ventas Odoo",
        supplier=supplier,
        customer=customer,
        lines=lines,
    )


def test_generates_valid_ubl_21_xml_from_domain(
    xsd_validator: XsdValidator,
    sample_invoice: Invoice,
) -> None:
    use_case = GenerateInvoiceXmlUseCase(validator=xsd_validator)

    xml_output = use_case.execute(sample_invoice)

    assert xml_output.startswith('<?xml version="1.0" encoding="ISO-8859-1"?>')

    # Validación explícita contra el archivo XSD oficial OASIS UBL 2.1
    xsd_validator.validate(xml_output)

    root = etree.fromstring(encode_xml_bytes(xml_output))
    assert root.tag == "{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Invoice"
    assert root.findtext("cbc:UBLVersionID", namespaces=NS) == "2.1"
    assert root.findtext("cbc:CustomizationID", namespaces=NS) == "2.0"
    assert root.findtext("cbc:ProfileID", namespaces=NS) == "0101"
    invoice_type = root.find("cbc:InvoiceTypeCode", namespaces=NS)
    assert invoice_type is not None
    assert invoice_type.text == "01"
    assert invoice_type.attrib["listID"] == "0101"
    assert root.findtext("cbc:ID", namespaces=NS) == "F001-0000123"
    assert root.findtext("cbc:IssueDate", namespaces=NS) == "2026-11-11"
    assert root.findtext("cbc:DueDate", namespaces=NS) == "2026-12-11"
    assert root.findtext("cbc:DocumentCurrencyCode", namespaces=NS) == "PEN"
    assert root.findtext("cbc:LineCountNumeric", namespaces=NS) == "2"
    assert root.findtext("cac:OrderReference/cbc:ID", namespaces=NS) == "SO-2026-0042"

    # Verificación de cálculos monetarios: (2*500.00) + (3*100.50) = 1301.50; IGV 18% = 234.27; Total = 1535.77
    assert root.findtext("cac:TaxTotal/cbc:TaxAmount", namespaces=NS) == "234.27"
    assert (
        root.findtext("cac:LegalMonetaryTotal/cbc:LineExtensionAmount", namespaces=NS)
        == "1301.50"
    )
    assert (
        root.findtext("cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount", namespaces=NS)
        == "1535.77"
    )
    assert (
        root.findtext("cac:LegalMonetaryTotal/cbc:PayableAmount", namespaces=NS)
        == "1535.77"
    )

    xml_lines = root.findall("cac:InvoiceLine", namespaces=NS)
    assert len(xml_lines) == 2
    assert (
        xml_lines[0].findtext("cac:Item/cbc:Name", namespaces=NS)
        == "Implementación módulo Ventas Odoo"
    )
    assert (
        xml_lines[0].find("cbc:InvoicedQuantity", namespaces=NS).attrib["unitCode"]
        == "ZZ"
    )
    supplier_id = root.find(
        "cac:AccountingSupplierParty/cac:Party/cac:PartyIdentification/cbc:ID",
        namespaces=NS,
    )
    customer_id = root.find(
        "cac:AccountingCustomerParty/cac:Party/cac:PartyIdentification/cbc:ID",
        namespaces=NS,
    )
    assert supplier_id is not None and supplier_id.attrib["schemeID"] == "6"
    assert customer_id is not None and customer_id.attrib["schemeID"] == "6"
    assert (
        root.findtext(
            "cac:Signature/cac:SignatoryParty/cac:PartyIdentification/cbc:ID",
            namespaces=NS,
        )
        == "20123456789"
    )
    assert (
        root.findtext(
            "cac:AccountingSupplierParty/cac:Party/cac:PartyLegalEntity/cac:RegistrationAddress/cbc:AddressTypeCode",
            namespaces=NS,
        )
        == "0000"
    )
    assert (
        root.findtext(
            "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cac:TaxScheme/cbc:ID",
            namespaces=NS,
        )
        == "1000"
    )
    assert (
        xml_lines[0].findtext(
            "cac:PricingReference/cac:AlternativeConditionPrice/cbc:PriceTypeCode",
            namespaces=NS,
        )
        == "01"
    )
    payment_terms = root.findall("cac:PaymentTerms", namespaces=NS)
    assert len(payment_terms) == 2
    assert (
        payment_terms[0].findtext("cbc:PaymentMeansID", namespaces=NS) == "Credito"
    )
    assert (
        payment_terms[1].findtext("cbc:PaymentMeansID", namespaces=NS) == "Cuota001"
    )


def test_generates_valid_xml_from_odoo_sales_payload_with_mixed_taxes(
    xsd_validator: XsdValidator,
) -> None:
    odoo_payload = {
        "name": "INV/2026/00088",
        "invoice_date": "2026-11-11",
        "invoice_date_due": "2026-11-26",
        "currency": "USD",
        "invoice_origin": "SO0088",
        "narration": "Venta exportada desde Odoo & validada contra XSD 2.1",
        "company": {
            "vat": "20555111222",
            "name": "Andes ERP Solutions",
            "street": "Calle Comercio 890",
            "city": "Lima",
            "zip": "15001",
            "country_code": "PE",
            "email": "billing@andeserp.com",
        },
        "partner": {
            "vat": "US-99887766",
            "name": "Northwind Trading <USA> & Co.",
            "street": "742 Evergreen Terrace",
            "city": "Miami",
            "zip": "33101",
            "country_code": "US",
        },
        "invoice_lines": [
            {
                "default_code": "PRD-100",
                "name": "Suscripción ERP Anual",
                "quantity": "1",
                "price_unit": "1000.00",
                "tax_ids": [{"name": "VAT 18%", "amount": 18}],
            },
            {
                "default_code": "PRD-200",
                "name": "Capacitación exonerada",
                "quantity": "2",
                "price_unit": "150.00",
                "tax_rate": "0.00",
            },
        ],
    }

    use_case = GenerateInvoiceXmlUseCase(validator=xsd_validator)
    xml_output = use_case.execute_from_odoo(odoo_payload)

    xsd_validator.validate(xml_output)

    root = etree.fromstring(encode_xml_bytes(xml_output))
    assert root.findtext("cbc:ID", namespaces=NS) == "F001-00000088"
    assert (
        root.findtext(
            "cac:AccountingCustomerParty/cac:Party/cac:PartyName/cbc:Name",
            namespaces=NS,
        )
        == "Northwind Trading <USA> & Co."
    )
    # Dos grupos impositivos: 18% sobre 1000.00 (180.00) y 0% sobre 300.00 (0.00)
    subtotals = root.findall("cac:TaxTotal/cac:TaxSubtotal", namespaces=NS)
    assert len(subtotals) == 2
    assert (
        root.findtext("cac:LegalMonetaryTotal/cbc:PayableAmount", namespaces=NS)
        == "1480.00"
    )


def test_roundtrip_parsing_with_xsdata_generated_model(
    xsd_validator: XsdValidator,
    sample_invoice: Invoice,
) -> None:
    use_case = GenerateInvoiceXmlUseCase(validator=xsd_validator)
    xml_output = use_case.execute(sample_invoice)

    parsed = XmlParser().from_string(xml_output, UblInvoice)
    assert parsed.id.value == "F001-0000123"
    assert parsed.document_currency_code is not None
    assert parsed.document_currency_code.value == "PEN"
    assert parsed.legal_monetary_total.payable_amount.value == Decimal("1535.77")
    assert len(parsed.invoice_line) == 2


def test_writes_xml_file_to_disk(
    tmp_path,
    xsd_validator: XsdValidator,
    sample_invoice: Invoice,
) -> None:
    use_case = GenerateInvoiceXmlUseCase(validator=xsd_validator)
    output_file = tmp_path / "out" / "F001-0000123.xml"

    saved_path = use_case.execute_to_file(sample_invoice, output_file)

    assert saved_path.exists()
    raw_bytes = saved_path.read_bytes()
    assert raw_bytes.startswith(b'<?xml version="1.0" encoding="ISO-8859-1"?>')
    xsd_validator.validate(raw_bytes)
    root = etree.fromstring(raw_bytes)
    assert (
        root.findtext(
            "cac:AccountingSupplierParty/cac:Party/cac:PostalAddress/cbc:CityName",
            namespaces=NS,
        )
        == "Tingo María"
    )


def test_iso_8859_1_escapes_non_latin1_characters_safely(
    tmp_path,
    xsd_validator: XsdValidator,
    sample_invoice: Invoice,
) -> None:
    use_case = GenerateInvoiceXmlUseCase(validator=xsd_validator)
    invoice_with_euro = Invoice(
        invoice_id=sample_invoice.invoice_id,
        issue_date=sample_invoice.issue_date,
        currency_code="EUR",
        supplier=sample_invoice.supplier,
        customer=sample_invoice.customer,
        lines=sample_invoice.lines,
        note="Precio referencial: 100 € — Tingo María",
    )
    saved_path = use_case.execute_to_file(invoice_with_euro, tmp_path / "euro_iso.xml")
    raw_bytes = saved_path.read_bytes()
    xsd_validator.validate(raw_bytes)
    root = etree.fromstring(raw_bytes)
    assert (
        root.findtext("cbc:Note", namespaces=NS)
        == "Precio referencial: 100 € — Tingo María"
    )


def test_domain_validates_and_normalizes_ose_series_invoice_id(
    sample_invoice: Invoice,
) -> None:
    from invoice_xml.domain import normalize_invoice_id

    assert normalize_invoice_id("INV/2026/00002") == "F001-00000002"
    assert normalize_invoice_id("FE01-573") == "FE01-00000573"
    assert normalize_invoice_id("f001-0000123") == "F001-00000123"
    assert sample_invoice.sunat_filename == "20123456789-01-F001-00000123.xml"

    with pytest.raises(InvoiceDomainError, match="SERIE-CORRELATIVO"):
        Invoice(
            invoice_id="INV/2026/00002",
            issue_date=date(2026, 11, 11),
            currency_code="USD",
            supplier=sample_invoice.supplier,
            customer=sample_invoice.customer,
            lines=sample_invoice.lines,
        )

    with pytest.raises(InvoiceDomainError, match="correlativo numérico"):
        normalize_invoice_id("SIN-NUMEROS")


def test_domain_rejects_invalid_invoice_data(sample_invoice: Invoice) -> None:
    with pytest.raises(InvoiceDomainError, match="al menos una línea"):
        Invoice(
            invoice_id="F001-1",
            issue_date=date(2026, 11, 11),
            currency_code="USD",
            supplier=sample_invoice.supplier,
            customer=sample_invoice.customer,
            lines=(),
        )

    with pytest.raises(InvoiceDomainError, match="mayor que cero"):
        InvoiceLine(
            line_id="1",
            item_name="Producto inválido",
            quantity=Decimal(0),
            unit_price=Decimal("10.00"),
        )

    with pytest.raises(InvoiceDomainError, match="ISO 4217"):
        Invoice(
            invoice_id="F001-2",
            issue_date=date(2026, 11, 11),
            currency_code="SOLES",
            supplier=sample_invoice.supplier,
            customer=sample_invoice.customer,
            lines=sample_invoice.lines,
        )

    with pytest.raises(InvoiceDomainError, match="fecha de vencimiento"):
        Invoice(
            invoice_id="F001-3",
            issue_date=date(2026, 11, 11),
            due_date=date(2026, 11, 10),
            currency_code="USD",
            supplier=sample_invoice.supplier,
            customer=sample_invoice.customer,
            lines=sample_invoice.lines,
        )


def test_odoo_adapter_rejects_incomplete_payload() -> None:
    use_case = GenerateInvoiceXmlUseCase()
    with pytest.raises(InvoiceDomainError, match="Falta el campo obligatorio"):
        use_case.execute_from_odoo({"name": "INV/1"})


def test_odoo_adapter_rejects_invalid_date_format() -> None:
    use_case = GenerateInvoiceXmlUseCase()
    with pytest.raises(InvoiceDomainError, match="Formato inválido"):
        use_case.execute_from_odoo(
            {
                "name": "INV/1",
                "invoice_date": "11-11-2026",
                "currency": "USD",
                "company": {
                    "vat": "123",
                    "name": "Empresa",
                    "street": "Av 1",
                    "city": "Lima",
                    "country_code": "PE",
                },
                "partner": {
                    "vat": "456",
                    "name": "Cliente",
                    "street": "Av 2",
                    "city": "Lima",
                    "country_code": "PE",
                },
                "invoice_lines": [],
            }
        )


def test_generates_compact_xml_when_pretty_print_disabled(
    xsd_validator: XsdValidator,
    sample_invoice: Invoice,
) -> None:
    use_case = GenerateInvoiceXmlUseCase(validator=xsd_validator)
    compact_xml = use_case.execute(sample_invoice, pretty_print=False)
    xsd_validator.validate(compact_xml)
    assert "\n  <" not in compact_xml


def test_xsd_validator_rejects_non_compliant_and_malformed_xml(
    xsd_validator: XsdValidator,
    tmp_path,
) -> None:
    invalid_ubl_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
             xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
        <cbc:ID>BAD-001</cbc:ID>
    </Invoice>
    """
    with pytest.raises(XmlSchemaValidationError) as exc_info:
        xsd_validator.validate(invalid_ubl_xml)

    assert len(exc_info.value.details) > 0

    with pytest.raises(XmlSchemaValidationError, match="XML bien formado"):
        xsd_validator.validate("<Invoice><broken>")

    with pytest.raises(FileNotFoundError):
        XsdValidator(tmp_path / "missing.xsd")
