"""Entidades del dominio de facturación independientes del estándar XML/ERP."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from decimal import ROUND_HALF_UP, Decimal

from invoice_xml.domain.exceptions import InvoiceDomainError

TWO_DECIMALS = Decimal("0.01")


def round_money(amount: Decimal) -> Decimal:
    """Redondea importes monetarios a 2 decimales usando ROUND_HALF_UP."""
    return amount.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Address:
    """Dirección postal de un participante comercial."""

    street: str
    city: str
    country_code: str
    postal_zone: str | None = None

    def __post_init__(self) -> None:
        if not self.street.strip():
            raise InvoiceDomainError("La dirección (street) no puede estar vacía.")
        if not self.city.strip():
            raise InvoiceDomainError("La ciudad (city) no puede estar vacía.")
        if len(self.country_code.strip()) != 2 or not self.country_code.isalpha():
            raise InvoiceDomainError(
                f"El código de país debe ser ISO 3166-1 alpha-2 (recibido: '{self.country_code}')."
            )


@dataclass(frozen=True)
class Party:
    """Emisor (vendedor) o receptor (cliente) de la factura."""

    tax_id: str
    tax_scheme_id: str
    legal_name: str
    address: Address
    registration_name: str | None = None
    email: str | None = None

    def __post_init__(self) -> None:
        if not self.tax_id.strip():
            raise InvoiceDomainError("El identificador fiscal (tax_id) es obligatorio.")
        if not self.legal_name.strip():
            raise InvoiceDomainError(
                "El nombre comercial o razón social es obligatorio."
            )

    @property
    def effective_registration_name(self) -> str:
        return self.registration_name or self.legal_name


@dataclass(frozen=True)
class InvoiceLine:
    """Línea individual de producto o servicio facturado."""

    line_id: str
    item_name: str
    quantity: Decimal
    unit_price: Decimal
    unit_code: str = "EA"  # UN/ECE Rec 20 (EA = Each / Unidad)
    tax_rate: Decimal = Decimal("0.18")
    tax_category_id: str = "S"  # Standard rate (UN/ECE 5305)
    tax_scheme_id: str = "VAT"
    item_code: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.line_id.strip():
            raise InvoiceDomainError(
                "El identificador de línea (line_id) es obligatorio."
            )
        if not self.item_name.strip():
            raise InvoiceDomainError(
                "El nombre del producto/servicio (item_name) es obligatorio."
            )
        if self.quantity <= Decimal(0):
            raise InvoiceDomainError("La cantidad de la línea debe ser mayor que cero.")
        if self.unit_price < Decimal(0):
            raise InvoiceDomainError("El precio unitario no puede ser negativo.")
        if self.tax_rate < Decimal(0):
            raise InvoiceDomainError("La tasa de impuesto no puede ser negativa.")

    @property
    def line_extension_amount(self) -> Decimal:
        """Subtotal neto de la línea antes de impuestos."""
        return round_money(self.quantity * self.unit_price)

    @property
    def tax_amount(self) -> Decimal:
        """Monto de impuesto calculado para la línea."""
        return round_money(self.line_extension_amount * self.tax_rate)


@dataclass(frozen=True)
class Invoice:
    """Agregado raíz de Factura comercial para generación UBL 2.1."""

    invoice_id: str
    issue_date: date
    currency_code: str
    supplier: Party
    customer: Party
    lines: tuple[InvoiceLine, ...]
    invoice_type_code: str = "380"  # UN/ECE 1001: 380 = Commercial Invoice
    issue_time: time | None = None
    due_date: date | None = None
    order_reference_id: str | None = (
        None  # Referencia al Pedido de Venta (ej. Odoo SO001)
    )
    note: str | None = None
    customization_id: str = "urn:oasis:names:specification:ubl:xpath:Invoice-2.1"
    profile_id: str = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
    ubl_version_id: str = "2.1"
    tax_groups: dict[tuple[str, str, Decimal], Decimal] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.invoice_id.strip():
            raise InvoiceDomainError(
                "El número de factura (invoice_id) es obligatorio."
            )
        if len(self.currency_code.strip()) != 3 or not self.currency_code.isalpha():
            raise InvoiceDomainError(
                f"La moneda debe ser código ISO 4217 de 3 letras (recibido: '{self.currency_code}')."
            )
        if not self.lines:
            raise InvoiceDomainError(
                "La factura debe contener al menos una línea de detalle."
            )
        if self.due_date is not None and self.due_date < self.issue_date:
            raise InvoiceDomainError(
                "La fecha de vencimiento no puede ser anterior a la fecha de emisión."
            )

        grouped: dict[tuple[str, str, Decimal], Decimal] = {}
        for line in self.lines:
            key = (line.tax_scheme_id, line.tax_category_id, line.tax_rate)
            grouped[key] = (
                grouped.get(key, Decimal("0.00")) + line.line_extension_amount
            )
        object.__setattr__(self, "tax_groups", grouped)

    @property
    def line_extension_total(self) -> Decimal:
        """Suma neta de todas las líneas sin impuestos."""
        return round_money(
            sum((line.line_extension_amount for line in self.lines), Decimal("0.00"))
        )

    @property
    def tax_total_amount(self) -> Decimal:
        """Suma total de impuestos agrupados por categoría/tasa."""
        total = Decimal("0.00")
        for (_, _, rate), taxable in self.tax_groups.items():
            total += round_money(taxable * rate)
        return round_money(total)

    @property
    def tax_inclusive_amount(self) -> Decimal:
        """Total con impuestos incluidos."""
        return round_money(self.line_extension_total + self.tax_total_amount)

    @property
    def payable_amount(self) -> Decimal:
        """Importe total a pagar."""
        return self.tax_inclusive_amount
