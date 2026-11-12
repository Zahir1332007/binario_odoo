"""Traductor desde el modelo de dominio puro hacia modelos UBL 2.1 generados desde el XSD."""

from __future__ import annotations

from decimal import Decimal

from xsdata.models.datatype import XmlDate, XmlTime

from invoice_xml.domain.models import Invoice, InvoiceLine, Party, round_money
from invoice_xml.infrastructure.ubl_models.common import (
    ubl_common_aggregate_components_2_1 as cac,
)
from invoice_xml.infrastructure.ubl_models.common import (
    ubl_common_basic_components_2_1 as cbc,
)
from invoice_xml.infrastructure.ubl_models.maindoc.ubl_invoice_2_1 import (
    Invoice as UblInvoice,
)


def _build_ubl_party(party: Party) -> cac.Party:
    """Construye un nodo UBL `cac:Party` reutilizable para emisor o receptor."""
    postal_zone = (
        cbc.PostalZone(value=party.address.postal_zone)
        if party.address.postal_zone
        else None
    )
    country = cac.Country(
        identification_code=cbc.IdentificationCode(value=party.address.country_code)
    )
    postal_address = cac.PostalAddress(
        street_name=cbc.StreetName(value=party.address.street),
        city_name=cbc.CityName(value=party.address.city),
        postal_zone=postal_zone,
        country=country,
    )
    registration_address = cac.RegistrationAddress(
        address_type_code=cbc.AddressTypeCode(
            value="0000",
            list_agency_name="PE:SUNAT",
            list_name="Establecimientos anexos",
        ),
        city_name=cbc.CityName(value=party.address.city),
        postal_zone=postal_zone,
        address_line=[cac.AddressLine(line=cbc.Line(value=party.address.street))],
        country=country,
    )

    return cac.Party(
        party_identification=[
            cac.PartyIdentification(
                id=cbc.Id(
                    value=party.tax_id,
                    scheme_id=party.document_type_code,
                    scheme_name="Documento de Identidad",
                    scheme_agency_name="PE:SUNAT",
                    scheme_uri="urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo06",
                )
            )
        ],
        party_name=[cac.PartyName(name=cbc.Name(value=party.legal_name))],
        postal_address=postal_address,
        party_tax_scheme=[
            cac.PartyTaxScheme(
                company_id=cbc.CompanyId(
                    value=party.tax_id,
                    scheme_id=party.document_type_code,
                    scheme_name="Documento de Identidad",
                    scheme_agency_name="PE:SUNAT",
                    scheme_uri="urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo06",
                ),
                tax_scheme=cac.TaxScheme(id=cbc.Id(value=party.tax_scheme_id)),
            )
        ],
        party_legal_entity=[
            cac.PartyLegalEntity(
                registration_name=cbc.RegistrationName(
                    value=party.effective_registration_name
                ),
                company_id=cbc.CompanyId(value=party.tax_id),
                registration_address=registration_address,
            )
        ],
        contact=cac.Contact(electronic_mail=cbc.ElectronicMail(value=party.email))
        if party.email
        else None,
    )


def _resolve_sunat_tax_metadata(rate: Decimal) -> tuple[str, str, str, str]:
    """Devuelve `(tax_scheme_id, tax_scheme_name, tax_type_code, exemption_code)` SUNAT."""
    if rate > Decimal(0):
        return ("1000", "IGV", "VAT", "10")
    return ("9997", "EXO", "VAT", "20")


def _build_sunat_tax_category(
    cls: type[cac.TaxCategory | cac.ClassifiedTaxCategory],
    category_id: str,
    rate: Decimal,
    include_exemption_reason: bool,
) -> cac.TaxCategory | cac.ClassifiedTaxCategory:
    """Construye `cac:TaxCategory` o `cac:ClassifiedTaxCategory` para OASIS UBL 2.1 y SUNAT."""
    scheme_code, scheme_name, tax_type_code, exemption_code = (
        _resolve_sunat_tax_metadata(rate)
    )
    return cls(
        id=cbc.Id(value=category_id),
        percent=cbc.Percent(value=round_money(rate * Decimal(100))),
        tax_exemption_reason_code=(
            cbc.TaxExemptionReasonCode(
                value=exemption_code,
                list_agency_name="PE:SUNAT",
                list_name="Afectacion del IGV",
                list_uri="urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo07",
            )
            if include_exemption_reason
            else None
        ),
        tax_scheme=cac.TaxScheme(
            id=cbc.Id(
                value=scheme_code,
                scheme_name="Codigo de tributos",
                scheme_agency_name="PE:SUNAT",
                scheme_uri="urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo05",
            ),
            name=cbc.Name(value=scheme_name),
            tax_type_code=cbc.TaxTypeCode(value=tax_type_code),
        ),
    )


def _build_ubl_tax_total(invoice: Invoice) -> cac.TaxTotal:
    """Construye el bloque `cac:TaxTotal` agrupado por esquema, categoría y tasa."""
    currency = invoice.currency_code
    subtotals = [
        cac.TaxSubtotal(
            taxable_amount=cbc.TaxableAmount(
                value=round_money(taxable), currency_id=currency
            ),
            tax_amount=cbc.TaxAmount(
                value=round_money(taxable * rate), currency_id=currency
            ),
            tax_category=_build_sunat_tax_category(
                cac.TaxCategory,
                category_id=category_id,
                rate=rate,
                include_exemption_reason=False,
            ),
        )
        for (_scheme_id, category_id, rate), taxable in invoice.tax_groups.items()
    ]
    return cac.TaxTotal(
        tax_amount=cbc.TaxAmount(value=invoice.tax_total_amount, currency_id=currency),
        tax_subtotal=subtotals,
    )


def _build_ubl_invoice_line(line: InvoiceLine, currency: str) -> cac.InvoiceLine:
    """Convierte una línea de dominio en un elemento `cac:InvoiceLine` UBL 2.1."""
    unit_price_incl_tax = round_money(line.unit_price * (Decimal(1) + line.tax_rate))
    item = cac.Item(
        description=[cbc.Description(value=line.description or line.item_name)],
        name=cbc.Name(value=line.item_name),
        sellers_item_identification=(
            cac.SellersItemIdentification(id=cbc.Id(value=line.item_code))
            if line.item_code
            else None
        ),
        classified_tax_category=[
            _build_sunat_tax_category(
                cac.ClassifiedTaxCategory,
                category_id=line.tax_category_id,
                rate=line.tax_rate,
                include_exemption_reason=False,
            )
        ],
    )
    return cac.InvoiceLine(
        id=cbc.Id(value=line.line_id),
        invoiced_quantity=cbc.InvoicedQuantity(
            value=line.quantity, unit_code=line.unit_code
        ),
        line_extension_amount=cbc.LineExtensionAmount(
            value=line.line_extension_amount,
            currency_id=currency,
        ),
        pricing_reference=cac.PricingReference(
            alternative_condition_price=[
                cac.AlternativeConditionPrice(
                    price_amount=cbc.PriceAmount(
                        value=unit_price_incl_tax, currency_id=currency
                    ),
                    price_type_code=cbc.PriceTypeCode(
                        value="01",
                        list_name="Tipo de Precio",
                        list_agency_name="PE:SUNAT",
                        list_uri="urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo16",
                    ),
                )
            ]
        ),
        tax_total=[
            cac.TaxTotal(
                tax_amount=cbc.TaxAmount(value=line.tax_amount, currency_id=currency),
                tax_subtotal=[
                    cac.TaxSubtotal(
                        taxable_amount=cbc.TaxableAmount(
                            value=line.line_extension_amount, currency_id=currency
                        ),
                        tax_amount=cbc.TaxAmount(
                            value=line.tax_amount, currency_id=currency
                        ),
                        tax_category=_build_sunat_tax_category(
                            cac.TaxCategory,
                            category_id=line.tax_category_id,
                            rate=line.tax_rate,
                            include_exemption_reason=True,
                        ),
                    )
                ],
            )
        ],
        item=item,
        price=cac.Price(
            price_amount=cbc.PriceAmount(value=line.unit_price, currency_id=currency)
        ),
    )


def _build_ubl_signature(supplier: Party) -> cac.Signature:
    """Construye el nodo `cac:Signature` requerido por perfiles SUNAT/OSE."""
    return cac.Signature(
        id=cbc.Id(value=supplier.tax_id),
        signatory_party=cac.SignatoryParty(
            party_identification=[
                cac.PartyIdentification(
                    id=cbc.Id(
                        value=supplier.tax_id, scheme_id=supplier.document_type_code
                    )
                )
            ],
            party_name=[cac.PartyName(name=cbc.Name(value=supplier.legal_name))],
        ),
        digital_signature_attachment=cac.DigitalSignatureAttachment(
            external_reference=cac.ExternalReference(uri=cbc.Uri(value="#SignatureSP"))
        ),
    )


def _build_ubl_payment_terms(invoice: Invoice) -> list[cac.PaymentTerms]:
    """Construye `cac:PaymentTerms` según regla SUNAT (Contado o Crédito con cuota)."""
    if invoice.due_date is not None and invoice.due_date > invoice.issue_date:
        currency = invoice.currency_code
        return [
            cac.PaymentTerms(
                id=cbc.Id(value="FormaPago"),
                payment_means_id=[cbc.PaymentMeansId(value="Credito")],
                amount=cbc.Amount(value=invoice.payable_amount, currency_id=currency),
            ),
            cac.PaymentTerms(
                id=cbc.Id(value="FormaPago"),
                payment_means_id=[cbc.PaymentMeansId(value="Cuota001")],
                amount=cbc.Amount(value=invoice.payable_amount, currency_id=currency),
                payment_due_date=cbc.PaymentDueDate(
                    value=XmlDate.from_date(invoice.due_date)
                ),
            ),
        ]
    return [
        cac.PaymentTerms(
            id=cbc.Id(value="FormaPago"),
            payment_means_id=[cbc.PaymentMeansId(value="Contado")],
        )
    ]


def domain_to_ubl_invoice(invoice: Invoice) -> UblInvoice:
    """Mapea un agregado `Invoice` del dominio al modelo `Invoice` de OASIS UBL 2.1."""
    currency = invoice.currency_code
    return UblInvoice(
        ublversion_id=cbc.UblversionId(value=invoice.ubl_version_id),
        customization_id=cbc.CustomizationId(
            value=invoice.customization_id, scheme_agency_name="PE:SUNAT"
        ),
        profile_id=cbc.ProfileId(
            value=invoice.profile_id,
            scheme_name="Tipo de Operacion",
            scheme_agency_name="PE:SUNAT",
            scheme_uri="urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo51",
        ),
        id=cbc.Id(value=invoice.invoice_id),
        issue_date=cbc.IssueDate(value=XmlDate.from_date(invoice.issue_date)),
        issue_time=cbc.IssueTime(value=XmlTime.from_time(invoice.issue_time))
        if invoice.issue_time
        else None,
        due_date=cbc.DueDate(value=XmlDate.from_date(invoice.due_date))
        if invoice.due_date
        else None,
        invoice_type_code=cbc.InvoiceTypeCode(
            value=invoice.invoice_type_code,
            list_id="0101",
            list_agency_name="PE:SUNAT",
            list_name="Tipo de Documento",
            list_uri="urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo01",
        ),
        note=[cbc.Note(value=invoice.note)] if invoice.note else [],
        document_currency_code=cbc.DocumentCurrencyCode(
            value=currency,
            list_id="ISO 4217 Alpha",
            list_name="Currency",
            list_agency_name="United Nations Economic Commission for Europe",
        ),
        line_count_numeric=cbc.LineCountNumeric(value=Decimal(len(invoice.lines))),
        order_reference=cac.OrderReference(id=cbc.Id(value=invoice.order_reference_id))
        if invoice.order_reference_id
        else None,
        signature=[_build_ubl_signature(invoice.supplier)],
        accounting_supplier_party=cac.AccountingSupplierParty(
            party=_build_ubl_party(invoice.supplier)
        ),
        accounting_customer_party=cac.AccountingCustomerParty(
            party=_build_ubl_party(invoice.customer)
        ),
        payment_terms=_build_ubl_payment_terms(invoice),
        tax_total=[_build_ubl_tax_total(invoice)],
        legal_monetary_total=cac.LegalMonetaryTotal(
            line_extension_amount=cbc.LineExtensionAmount(
                value=invoice.line_extension_total, currency_id=currency
            ),
            tax_exclusive_amount=cbc.TaxExclusiveAmount(
                value=invoice.line_extension_total, currency_id=currency
            ),
            tax_inclusive_amount=cbc.TaxInclusiveAmount(
                value=invoice.tax_inclusive_amount, currency_id=currency
            ),
            payable_amount=cbc.PayableAmount(
                value=invoice.payable_amount, currency_id=currency
            ),
        ),
        invoice_line=[
            _build_ubl_invoice_line(line, currency) for line in invoice.lines
        ],
    )
