"""Entidades del dominio de facturación independientes del estándar XML/ERP."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, time
from decimal import ROUND_HALF_UP, Decimal

from invoice_xml.domain.exceptions import InvoiceDomainError

TWO_DECIMALS = Decimal("0.01")
INVOICE_ID_PATTERN = re.compile(r"^[A-Z0-9]{4}-\d{1,8}$")
_TRAILING_DIGITS_RE = re.compile(r"(\d+)$")


def round_money(amount: Decimal) -> Decimal:
    """Redondea importes monetarios a 2 decimales usando ROUND_HALF_UP."""
    return amount.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)


def normalize_invoice_id(
    raw_id: str, default_series: str = "F001", correlative_width: int = 8
) -> str:
    """Normaliza un comprobante al formato SUNAT/OSE `'SERIE-00000001'` (correlativo de 8 dígitos)."""
    cleaned = raw_id.strip().upper()
    if not cleaned:
        raise InvoiceDomainError("El número de factura (invoice_id) es obligatorio.")
    if INVOICE_ID_PATTERN.match(cleaned):
        series, num_part = cleaned.split("-", 1)
        correlative = int(num_part)
        if correlative <= 0:
            raise InvoiceDomainError(
                f"El correlativo de la factura debe ser mayor que cero (recibido: '{raw_id}')."
            )
        return f"{series}-{correlative:0{correlative_width}d}"

    match = _TRAILING_DIGITS_RE.search(cleaned)
    if not match:
        raise InvoiceDomainError(
            f"No se pudo obtener un correlativo numérico desde '{raw_id}' para formar SERIE-CORRELATIVO (ej. FE01-00000573)."
        )
    correlative = int(match.group(1))
    if correlative <= 0:
        raise InvoiceDomainError(
            f"El correlativo de la factura debe ser mayor que cero (recibido: '{raw_id}')."
        )
    series = default_series.strip().upper()
    if not re.match(r"^[A-Z0-9]{4}$", series):
        raise InvoiceDomainError(
            f"La serie debe tener 4 caracteres alfanuméricos (recibido: '{default_series}')."
        )
    return f"{series}-{correlative:0{correlative_width}d}"


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
    document_type_code: str = "6"  # Catálogo 06 SUNAT: 6 = RUC, 1 = DNI

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
    invoice_type_code: str = "01"  # Catálogo 01 SUNAT / UBL 2.1: 01 = Factura
    issue_time: time | None = None
    due_date: date | None = None
    order_reference_id: str | None = (
        None  # Referencia al Pedido de Venta (ej. Odoo SO001)
    )
    note: str | None = None
    customization_id: str = "2.0"
    profile_id: str = "0101"
    ubl_version_id: str = "2.1"
    tax_groups: dict[tuple[str, str, Decimal], Decimal] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.invoice_id.strip():
            raise InvoiceDomainError(
                "El número de factura (invoice_id) es obligatorio."
            )
        if not INVOICE_ID_PATTERN.match(self.invoice_id):
            raise InvoiceDomainError(
                f"El ID '{self.invoice_id}' es inválido para OSE/UBL: debe tener formato SERIE-CORRELATIVO con '-' (ej. FFF1-1 o F001-1)."
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

    @property
    def sunat_filename(self) -> str:
        """Nombre oficial SUNAT Perú: `{RUC}-{TIPO}-{SERIE}-{CORRELATIVO_8D}.xml`."""
        series, correlative = self.invoice_id.split("-", 1)
        return (
            f"{self.supplier.tax_id}-{self.invoice_type_code}"
            f"-{series}-{int(correlative):08d}.xml"
        )
