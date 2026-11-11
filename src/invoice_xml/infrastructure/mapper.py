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
    postal_address = cac.PostalAddress(
        street_name=cbc.StreetName(value=party.address.street),
        city_name=cbc.CityName(value=party.address.city),
        postal_zone=cbc.PostalZone(value=party.address.postal_zone)
        if party.address.postal_zone
        else None,
        country=cac.Country(
            identification_code=cbc.IdentificationCode(value=party.address.country_code)
        ),
    )

    return cac.Party(
        party_identification=[cac.PartyIdentification(id=cbc.Id(value=party.tax_id))],
        party_name=[cac.PartyName(name=cbc.Name(value=party.legal_name))],
        postal_address=postal_address,
        party_tax_scheme=[
            cac.PartyTaxScheme(
                company_id=cbc.CompanyId(value=party.tax_id),
                tax_scheme=cac.TaxScheme(id=cbc.Id(value=party.tax_scheme_id)),
            )
        ],
        party_legal_entity=[
            cac.PartyLegalEntity(
                registration_name=cbc.RegistrationName(
                    value=party.effective_registration_name
                ),
                company_id=cbc.CompanyId(value=party.tax_id),
            )
        ],
        contact=cac.Contact(electronic_mail=cbc.ElectronicMail(value=party.email))
        if party.email
        else None,
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
            tax_category=cac.TaxCategory(
                id=cbc.Id(value=category_id),
                percent=cbc.Percent(value=round_money(rate * Decimal(100))),
                tax_scheme=cac.TaxScheme(id=cbc.Id(value=scheme_id)),
            ),
        )
        for (scheme_id, category_id, rate), taxable in invoice.tax_groups.items()
    ]
    return cac.TaxTotal(
        tax_amount=cbc.TaxAmount(value=invoice.tax_total_amount, currency_id=currency),
        tax_subtotal=subtotals,
    )


def _build_ubl_invoice_line(line: InvoiceLine, currency: str) -> cac.InvoiceLine:
    """Convierte una línea de dominio en un elemento `cac:InvoiceLine` UBL 2.1."""
    item = cac.Item(
        description=[cbc.Description(value=line.description)]
        if line.description
        else [],
        name=cbc.Name(value=line.item_name),
        sellers_item_identification=(
            cac.SellersItemIdentification(id=cbc.Id(value=line.item_code))
            if line.item_code
            else None
        ),
        classified_tax_category=[
            cac.ClassifiedTaxCategory(
                id=cbc.Id(value=line.tax_category_id),
                percent=cbc.Percent(value=round_money(line.tax_rate * Decimal(100))),
                tax_scheme=cac.TaxScheme(id=cbc.Id(value=line.tax_scheme_id)),
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
        tax_total=[
            cac.TaxTotal(
                tax_amount=cbc.TaxAmount(value=line.tax_amount, currency_id=currency)
            )
        ],
        item=item,
        price=cac.Price(
            price_amount=cbc.PriceAmount(value=line.unit_price, currency_id=currency)
        ),
    )


def domain_to_ubl_invoice(invoice: Invoice) -> UblInvoice:
    """Mapea un agregado `Invoice` del dominio al modelo `Invoice` de OASIS UBL 2.1."""
    currency = invoice.currency_code
    return UblInvoice(
        ublversion_id=cbc.UblversionId(value=invoice.ubl_version_id),
        customization_id=cbc.CustomizationId(value=invoice.customization_id),
        profile_id=cbc.ProfileId(value=invoice.profile_id),
        id=cbc.Id(value=invoice.invoice_id),
        issue_date=cbc.IssueDate(value=XmlDate.from_date(invoice.issue_date)),
        issue_time=cbc.IssueTime(value=XmlTime.from_time(invoice.issue_time))
        if invoice.issue_time
        else None,
        due_date=cbc.DueDate(value=XmlDate.from_date(invoice.due_date))
        if invoice.due_date
        else None,
        invoice_type_code=cbc.InvoiceTypeCode(value=invoice.invoice_type_code),
        note=[cbc.Note(value=invoice.note)] if invoice.note else [],
        document_currency_code=cbc.DocumentCurrencyCode(value=currency),
        line_count_numeric=cbc.LineCountNumeric(value=Decimal(len(invoice.lines))),
        order_reference=cac.OrderReference(id=cbc.Id(value=invoice.order_reference_id))
        if invoice.order_reference_id
        else None,
        accounting_supplier_party=cac.AccountingSupplierParty(
            party=_build_ubl_party(invoice.supplier)
        ),
        accounting_customer_party=cac.AccountingCustomerParty(
            party=_build_ubl_party(invoice.customer)
        ),
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
