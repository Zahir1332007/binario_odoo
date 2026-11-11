"""Cliente XML-RPC para consultar facturas y órdenes de venta desde Odoo."""

from __future__ import annotations

import os
import re
import xmlrpc.client
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_DEFAULT_DOTENV_PATH = Path(__file__).resolve().parents[3] / ".env"


def _load_dotenv(dotenv_path: Path) -> dict[str, str]:
    """Lee pares KEY=VALUE desde un archivo .env sin dependencias externas."""
    if not dotenv_path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        if key:
            values[key] = val
    return values


class OdooConnectionError(RuntimeError):
    """Error de conexión, autenticación o lectura de registros en Odoo."""


@dataclass(frozen=True)
class OdooConnectionConfig:
    """Parámetros de conexión XML-RPC hacia una instancia Odoo."""

    url: str
    db: str
    username: str
    api_key: str

    def __post_init__(self) -> None:
        cleaned_url = self.url.strip().rstrip("/")
        if not cleaned_url.startswith(("http://", "https://")):
            raise OdooConnectionError(
                f"La URL de Odoo debe iniciar con http:// o https:// (recibido: '{self.url}')."
            )
        if not self.db.strip():
            raise OdooConnectionError(
                "El nombre de la base de datos Odoo (db) es obligatorio."
            )
        if not self.username.strip():
            raise OdooConnectionError("El usuario de Odoo (username) es obligatorio.")
        if not self.api_key.strip():
            raise OdooConnectionError("La API Key o contraseña de Odoo es obligatoria.")
        object.__setattr__(self, "url", cleaned_url)

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        dotenv_path: Path | str | None = None,
    ) -> OdooConnectionConfig:
        """Carga credenciales de Odoo desde variables de entorno o un archivo `.env`."""
        if environ is not None:
            env = environ
        else:
            env_file = (
                Path(dotenv_path)
                if dotenv_path is not None
                else (
                    Path.cwd() / ".env"
                    if (Path.cwd() / ".env").is_file()
                    else _DEFAULT_DOTENV_PATH
                )
            )
            env = {**_load_dotenv(env_file), **os.environ}
        url = env.get("ODOO_URL", "").strip()
        db = env.get("ODOO_DB", "").strip()
        username = env.get("ODOO_USER", "").strip()
        api_key = (env.get("ODOO_API_KEY") or env.get("ODOO_PASSWORD") or "").strip()

        missing = [
            name
            for name, val in (
                ("ODOO_URL", url),
                ("ODOO_DB", db),
                ("ODOO_USER", username),
                ("ODOO_API_KEY", api_key),
            )
            if not val
        ]
        if missing:
            raise OdooConnectionError(
                "Faltan variables de entorno para conectar con Odoo: "
                + ", ".join(missing)
            )
        return cls(url=url, db=db, username=username, api_key=api_key)


def _strip_html(raw_text: Any) -> str | None:
    if not raw_text or raw_text is False:
        return None
    cleaned = _HTML_TAG_RE.sub(" ", str(raw_text)).strip()
    return re.sub(r"\s+", " ", cleaned) or None


def _extract_m2o_id(value: Any, field_name: str) -> int:
    if isinstance(value, (list, tuple)) and value and isinstance(value[0], int):
        return value[0]
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise OdooConnectionError(
        f"El campo relacional '{field_name}' no tiene un registro asignado en Odoo."
    )


class OdooXmlRpcClient:
    """Adaptador de salida que obtiene datos comerciales desde Odoo vía XML-RPC."""

    def __init__(
        self,
        config: OdooConnectionConfig,
        *,
        common_proxy: Any | None = None,
        object_proxy: Any | None = None,
    ) -> None:
        self.config = config
        self._common = common_proxy or xmlrpc.client.ServerProxy(
            f"{config.url}/xmlrpc/2/common",
            allow_none=True,
        )
        self._object = object_proxy or xmlrpc.client.ServerProxy(
            f"{config.url}/xmlrpc/2/object",
            allow_none=True,
        )
        self._uid: int | None = None

    def authenticate(self) -> int:
        """Autentica contra `/xmlrpc/2/common` y retorna el UID del usuario en Odoo."""
        if self._uid is not None:
            return self._uid
        try:
            uid = self._common.authenticate(
                self.config.db,
                self.config.username,
                self.config.api_key,
                {},
            )
        except (xmlrpc.client.Error, OSError) as exc:
            raise OdooConnectionError(
                f"No se pudo conectar al servicio XML-RPC de Odoo en '{self.config.url}': {exc}"
            ) from exc

        if not uid or isinstance(uid, bool):
            raise OdooConnectionError(
                "Autenticación rechazada por Odoo. Verifique ODOO_DB, ODOO_USER y ODOO_API_KEY."
            )
        self._uid = int(uid)
        return self._uid

    def _execute_kw(
        self,
        model: str,
        method: str,
        args: Sequence[Any],
        kwargs: Mapping[str, Any] | None = None,
    ) -> Any:
        uid = self.authenticate()
        try:
            return self._object.execute_kw(
                self.config.db,
                uid,
                self.config.api_key,
                model,
                method,
                list(args),
                dict(kwargs or {}),
            )
        except (xmlrpc.client.Error, OSError) as exc:
            raise OdooConnectionError(
                f"Error ejecutando {model}.{method} en Odoo: {exc}"
            ) from exc

    def _read_many(
        self, model: str, ids: Sequence[int], fields: list[str]
    ) -> list[dict[str, Any]]:
        if not ids:
            return []
        return list(self._execute_kw(model, "read", [list(ids)], {"fields": fields}))

    def _read_one(
        self, model: str, record_id: int, fields: list[str]
    ) -> dict[str, Any]:
        records = self._read_many(model, [record_id], fields)
        if not records:
            raise OdooConnectionError(
                f"No se encontró el registro {model}(id={record_id}) en Odoo."
            )
        return records[0]

    def _search_latest(
        self,
        model: str,
        domain: list[Any],
        fields: list[str],
        not_found_msg: str,
    ) -> dict[str, Any]:
        ids = self._execute_kw(
            model,
            "search",
            [domain],
            {"limit": 1, "order": "id desc"},
        )
        if not ids:
            raise OdooConnectionError(not_found_msg)
        return self._read_one(model, ids[0], fields)

    def _resolve_partner(
        self, partner_id: int, *, fallback_email: str | None = None
    ) -> dict[str, Any]:
        partner = self._read_one(
            "res.partner",
            partner_id,
            ["vat", "name", "street", "city", "zip", "country_id", "email"],
        )
        country_id = _extract_m2o_id(
            partner.get("country_id"), "res.partner.country_id"
        )
        country = self._read_one("res.country", country_id, ["code"])

        missing_fields = [
            fname
            for fname in ("vat", "name", "street", "city")
            if not partner.get(fname)
        ]
        if missing_fields:
            raise OdooConnectionError(
                f"El contacto '{partner.get('name') or partner_id}' en Odoo no tiene "
                f"completos los campos obligatorios: {', '.join(missing_fields)}."
            )

        return {
            "vat": str(partner["vat"]),
            "name": str(partner["name"]),
            "street": str(partner["street"]),
            "city": str(partner["city"]),
            "zip": str(partner["zip"]) if partner.get("zip") else None,
            "country_code": str(country["code"]).upper(),
            "email": str(partner["email"]) if partner.get("email") else fallback_email,
        }

    def _resolve_company_and_customer(
        self, company_field: Any, partner_field: Any
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        company_id = _extract_m2o_id(company_field, "company_id")
        company = self._read_one("res.company", company_id, ["partner_id", "email"])
        supplier_partner_id = _extract_m2o_id(
            company.get("partner_id"), "res.company.partner_id"
        )
        customer_partner_id = _extract_m2o_id(partner_field, "partner_id")

        company_email = str(company["email"]) if company.get("email") else None
        supplier = self._resolve_partner(
            supplier_partner_id, fallback_email=company_email
        )
        customer = self._resolve_partner(customer_partner_id)
        return supplier, customer

    def _resolve_currency(self, currency_field: Any) -> str:
        currency_id = _extract_m2o_id(currency_field, "currency_id")
        currency = self._read_one("res.currency", currency_id, ["name"])
        return str(currency["name"]).upper()

    def _resolve_lines(
        self,
        *,
        line_model: str,
        line_ids: Sequence[int],
        qty_field: str,
        tax_field: str,
    ) -> list[dict[str, Any]]:
        raw_lines = self._read_many(
            line_model,
            line_ids,
            ["name", "product_id", qty_field, "price_unit", tax_field, "display_type"],
        )
        billable_lines = [
            line
            for line in raw_lines
            if line.get("display_type") in (False, None, "product")
        ]

        product_ids = sorted(
            {
                line["product_id"][0]
                for line in billable_lines
                if isinstance(line.get("product_id"), (list, tuple))
                and line["product_id"]
            }
        )
        tax_ids = sorted(
            {
                tid
                for line in billable_lines
                for tid in (line.get(tax_field) or [])
                if isinstance(tid, int)
            }
        )

        products_by_id = {
            p["id"]: p
            for p in self._read_many("product.product", product_ids, ["default_code"])
        }
        taxes_by_id = {
            t["id"]: t
            for t in self._read_many("account.tax", tax_ids, ["name", "amount"])
        }

        normalized_lines: list[dict[str, Any]] = []
        for line in billable_lines:
            prod_field = line.get("product_id")
            default_code = None
            if isinstance(prod_field, (list, tuple)) and prod_field:
                product = products_by_id.get(prod_field[0], {})
                if product.get("default_code"):
                    default_code = str(product["default_code"])

            line_taxes = [
                {
                    "name": str(taxes_by_id[tid]["name"]),
                    "amount": taxes_by_id[tid]["amount"],
                }
                for tid in (line.get(tax_field) or [])
                if tid in taxes_by_id
            ]
            normalized_lines.append(
                {
                    "name": str(line["name"]),
                    "default_code": default_code,
                    "quantity": str(line[qty_field]),
                    "price_unit": str(line["price_unit"]),
                    "tax_ids": line_taxes,
                }
            )
        return normalized_lines

    def fetch_invoice_payload(
        self, invoice_number: str | None = None
    ) -> dict[str, Any]:
        """Obtiene una factura publicada (`account.move`) desde Odoo."""
        domain: list[Any] = [
            ["move_type", "=", "out_invoice"],
            ["state", "=", "posted"],
        ]
        if invoice_number:
            domain.append(["name", "=", invoice_number])

        move = self._search_latest(
            "account.move",
            domain,
            [
                "name",
                "invoice_date",
                "invoice_date_due",
                "invoice_origin",
                "narration",
                "currency_id",
                "company_id",
                "partner_id",
                "invoice_line_ids",
            ],
            not_found_msg=(
                f"No se encontró ninguna factura publicada '{invoice_number}' en Odoo."
                if invoice_number
                else "No existen facturas de cliente publicadas (out_invoice) en Odoo."
            ),
        )
        if not move.get("invoice_date"):
            raise OdooConnectionError(
                f"La factura '{move.get('name')}' no tiene fecha de emisión (invoice_date) en Odoo."
            )

        supplier, customer = self._resolve_company_and_customer(
            move.get("company_id"), move.get("partner_id")
        )
        currency = self._resolve_currency(move.get("currency_id"))
        lines = self._resolve_lines(
            line_model="account.move.line",
            line_ids=move.get("invoice_line_ids") or [],
            qty_field="quantity",
            tax_field="tax_ids",
        )

        return {
            "name": str(move["name"]),
            "invoice_date": str(move["invoice_date"]),
            "invoice_date_due": str(move["invoice_date_due"])
            if move.get("invoice_date_due")
            else None,
            "currency": currency,
            "invoice_origin": str(move["invoice_origin"])
            if move.get("invoice_origin")
            else None,
            "narration": _strip_html(move.get("narration")),
            "company": supplier,
            "partner": customer,
            "invoice_lines": lines,
        }

    def fetch_sale_order_payload(self, order_name: str | None = None) -> dict[str, Any]:
        """Obtiene una orden de venta confirmada (`sale.order`) desde Odoo Ventas."""
        domain: list[Any] = [["state", "in", ["sale", "done"]]]
        if order_name:
            domain.append(["name", "=", order_name])

        order = self._search_latest(
            "sale.order",
            domain,
            [
                "name",
                "date_order",
                "validity_date",
                "note",
                "currency_id",
                "company_id",
                "partner_id",
                "order_line",
            ],
            not_found_msg=(
                f"No se encontró ninguna orden de venta confirmada '{order_name}' en Odoo."
                if order_name
                else "No existen órdenes de venta confirmadas en Odoo."
            ),
        )
        if not order.get("date_order"):
            raise OdooConnectionError(
                f"La orden de venta '{order.get('name')}' no tiene date_order en Odoo."
            )

        supplier, customer = self._resolve_company_and_customer(
            order.get("company_id"), order.get("partner_id")
        )
        currency = self._resolve_currency(order.get("currency_id"))
        lines = self._resolve_lines(
            line_model="sale.order.line",
            line_ids=order.get("order_line") or [],
            qty_field="product_uom_qty",
            tax_field="tax_id",
        )

        return {
            "name": str(order["name"]),
            "invoice_date": str(order["date_order"])[:10],
            "invoice_date_due": str(order["validity_date"])
            if order.get("validity_date")
            else None,
            "currency": currency,
            "invoice_origin": str(order["name"]),
            "narration": _strip_html(order.get("note")),
            "company": supplier,
            "partner": customer,
            "invoice_lines": lines,
        }
