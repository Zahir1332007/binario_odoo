"""Adaptador para transformar estructuras del módulo de Ventas/Facturación de Odoo al dominio."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from invoice_xml.domain.exceptions import InvoiceDomainError
from invoice_xml.domain.models import (
    Address,
    Invoice,
    InvoiceLine,
    Party,
    normalize_invoice_id,
)


def _parse_party(raw: Mapping[str, Any], role_name: str) -> Party:
    try:
        address = Address(
            street=str(raw["street"]),
            city=str(raw["city"]),
            country_code=str(raw["country_code"]).upper(),
            postal_zone=str(raw["zip"]) if raw.get("zip") else None,
        )
        return Party(
            tax_id=str(raw["vat"]),
            tax_scheme_id=str(raw.get("tax_scheme_id", "VAT")),
            legal_name=str(raw["name"]),
            registration_name=str(raw.get("registration_name") or raw["name"]),
            address=address,
            email=str(raw["email"]) if raw.get("email") else None,
        )
    except KeyError as exc:
        raise InvoiceDomainError(
            f"Falta el campo obligatorio {exc} en los datos de {role_name} provenientes de Odoo."
        ) from exc


def _parse_tax_rate(line_raw: Mapping[str, Any]) -> Decimal:
    if "tax_rate" in line_raw and line_raw["tax_rate"] is not None:
        return Decimal(str(line_raw["tax_rate"]))
    taxes = line_raw.get("tax_ids")
    if isinstance(taxes, list) and taxes:
        total_pct = sum(
            Decimal(str(t.get("amount", 0))) for t in taxes if isinstance(t, Mapping)
        )
        return total_pct / Decimal(100)
    return Decimal("0.00")


def odoo_payload_to_domain(payload: Mapping[str, Any]) -> Invoice:
    """Convierte un diccionario exportado de Odoo Ventas/Facturación en un agregado Invoice.

    Campos esperados (estilo Odoo `account.move` / `sale.order`):
      - `name`: número de factura (ej. 'INV/2026/0001')
      - `invoice_date`: fecha ISO 'YYYY-MM-DD'
      - `currency`: código ISO 4217 (ej. 'USD', 'PEN')
      - `company`: datos del emisor (`vat`, `name`, `street`, `city`, `country_code`, ...)
      - `partner`: datos del cliente (`vat`, `name`, `street`, `city`, `country_code`, ...)
      - `invoice_lines`: lista de líneas (`name`, `quantity`, `price_unit`, `tax_rate` o `tax_ids`)
    """
    try:
        default_series = str(payload.get("series") or "F001")
        invoice_id = normalize_invoice_id(
            str(payload["name"]), default_series=default_series
        )
        issue_date = date.fromisoformat(str(payload["invoice_date"]))
        currency_code = str(payload["currency"]).upper()
        supplier = _parse_party(payload["company"], "emisor (company)")
        customer = _parse_party(payload["partner"], "cliente (partner)")
        raw_lines = payload["invoice_lines"]
    except KeyError as exc:
        raise InvoiceDomainError(
            f"Falta el campo obligatorio {exc} en el payload de Odoo."
        ) from exc
    except ValueError as exc:
        raise InvoiceDomainError(
            f"Formato inválido en fecha o dato numérico de Odoo: {exc}"
        ) from exc

    if not isinstance(raw_lines, list):
        raise InvoiceDomainError("El campo 'invoice_lines' debe ser una lista.")

    lines: list[InvoiceLine] = []
    for idx, raw_line in enumerate(raw_lines, start=1):
        try:
            tax_rate = _parse_tax_rate(raw_line)
            tax_category = str(
                raw_line.get("tax_category_id")
                or ("S" if tax_rate > Decimal(0) else "E")
            )
            lines.append(
                InvoiceLine(
                    line_id=str(raw_line.get("line_id") or idx),
                    item_name=str(raw_line["name"]),
                    item_code=str(raw_line["default_code"])
                    if raw_line.get("default_code")
                    else None,
                    description=str(raw_line["description"])
                    if raw_line.get("description")
                    else None,
                    quantity=Decimal(str(raw_line["quantity"])),
                    unit_price=Decimal(str(raw_line["price_unit"])),
                    unit_code=str(raw_line.get("uom_code", "NIU")),
                    tax_rate=tax_rate,
                    tax_category_id=tax_category,
                    tax_scheme_id=str(raw_line.get("tax_scheme_id", "VAT")),
                )
            )
        except KeyError as exc:
            raise InvoiceDomainError(
                f"Falta el campo obligatorio {exc} en la línea {idx} de Odoo."
            ) from exc

    due_date_raw = payload.get("invoice_date_due")
    due_date = date.fromisoformat(str(due_date_raw)) if due_date_raw else None

    return Invoice(
        invoice_id=invoice_id,
        issue_date=issue_date,
        due_date=due_date,
        currency_code=currency_code,
        supplier=supplier,
        customer=customer,
        lines=tuple(lines),
        invoice_type_code=str(payload.get("invoice_type_code", "01")),
        order_reference_id=str(payload["invoice_origin"])
        if payload.get("invoice_origin")
        else None,
        note=str(payload["narration"]) if payload.get("narration") else None,
    )
