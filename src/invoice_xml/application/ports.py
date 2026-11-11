"""Puertos (interfaces) de la capa de aplicación para integraciones externas."""

from __future__ import annotations

from typing import Any, Protocol


class OdooInvoiceGateway(Protocol):
    """Contrato para obtener datos de facturación o venta desde una instancia Odoo."""

    def fetch_invoice_payload(
        self, invoice_number: str | None = None
    ) -> dict[str, Any]:
        """Obtiene una factura confirmada (`account.move`) en formato normalizado."""
        ...

    def fetch_sale_order_payload(self, order_name: str | None = None) -> dict[str, Any]:
        """Obtiene una orden de venta confirmada (`sale.order`) en formato normalizado."""
        ...
