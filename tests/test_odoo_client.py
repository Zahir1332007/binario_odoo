"""Pruebas unitarias del conector XML-RPC de Odoo y generación XML UBL 2.1."""

from __future__ import annotations

import xmlrpc.client
from typing import Any

import pytest
from lxml import etree

from invoice_xml.application import GenerateInvoiceXmlUseCase
from invoice_xml.cli import main as cli_main
from invoice_xml.infrastructure import (
    DEFAULT_INVOICE_XSD_PATH,
    OdooConnectionConfig,
    OdooConnectionError,
    OdooXmlRpcClient,
    XsdValidator,
    encode_xml_bytes,
)

NS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}


class FakeCommonProxy:
    def __init__(self, uid: int | bool = 7, raise_exc: Exception | None = None) -> None:
        self.uid = uid
        self.raise_exc = raise_exc

    def authenticate(
        self, db: str, username: str, api_key: str, env: dict
    ) -> int | bool:
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.uid


class FakeObjectProxy:
    def __init__(self, tables: dict[str, dict[int, dict[str, Any]]]) -> None:
        self.tables = tables
        self.calls: list[tuple[str, str, list[Any], dict[str, Any]]] = []

    def execute_kw(
        self,
        db: str,
        uid: int,
        api_key: str,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any],
    ) -> Any:
        self.calls.append((model, method, args, kwargs))
        records = self.tables.get(model, {})
        if method == "search":
            domain = args[0] if args else []
            matched = [
                rec_id
                for rec_id, rec in sorted(records.items(), reverse=True)
                if self._matches(rec, domain)
            ]
            limit = kwargs.get("limit")
            return matched[:limit] if limit else matched
        if method == "read":
            ids = args[0] if args else []
            fields = kwargs.get("fields", [])
            result = []
            for rec_id in ids:
                if rec_id in records:
                    rec = records[rec_id]
                    item = {"id": rec_id}
                    for f in fields:
                        item[f] = rec.get(f, False)
                    result.append(item)
            return result
        raise AssertionError(f"Método no esperado en mock: {model}.{method}")

    @staticmethod
    def _matches(record: dict[str, Any], domain: list[Any]) -> bool:
        for clause in domain:
            field, op, expected = clause
            actual = record.get(field)
            if op == "=" and actual != expected:
                return False
            if op == "in" and actual not in expected:
                return False
        return True


def _sample_odoo_tables() -> dict[str, dict[int, dict[str, Any]]]:
    return {
        "res.country": {
            173: {"code": "PE"},
        },
        "res.currency": {
            156: {"name": "PEN"},
        },
        "res.company": {
            1: {"partner_id": [10, "Mi Empresa SAC"], "email": "empresa@odoo.pe"},
        },
        "res.partner": {
            10: {
                "vat": "20111222333",
                "name": "Mi Empresa Odoo S.A.C.",
                "street": "Av. Lima 100",
                "city": "Tingo María",
                "zip": "10131",
                "country_id": [173, "Peru"],
                "email": False,
            },
            20: {
                "vat": "20444555666",
                "name": "Cliente Corporativo E.I.R.L.",
                "street": "Jr. Amazonas 250",
                "city": "Huánuco",
                "zip": "10001",
                "country_id": [173, "Peru"],
                "email": "cliente@corp.pe",
            },
        },
        "product.product": {
            101: {"default_code": "PROD-A"},
        },
        "account.tax": {
            5: {"name": "IGV 18%", "amount": 18.0},
        },
        "account.move": {
            42: {
                "name": "INV/2026/0042",
                "move_type": "out_invoice",
                "state": "posted",
                "invoice_date": "2026-11-11",
                "invoice_date_due": "2026-12-11",
                "invoice_origin": "S00042",
                "narration": "<p>Emitida desde <b>Odoo</b></p>",
                "currency_id": [156, "PEN"],
                "company_id": [1, "Mi Empresa SAC"],
                "partner_id": [20, "Cliente Corporativo"],
                "invoice_line_ids": [1001, 1002],
            }
        },
        "account.move.line": {
            1001: {
                "name": "Sección de servicios",
                "product_id": False,
                "quantity": 0.0,
                "price_unit": 0.0,
                "tax_ids": [],
                "display_type": "line_section",
            },
            1002: {
                "name": "[PROD-A] Licencia ERP",
                "product_id": [101, "[PROD-A] Licencia ERP"],
                "quantity": 2.0,
                "price_unit": 250.0,
                "tax_ids": [5],
                "display_type": "product",
            },
        },
        "sale.order": {
            77: {
                "name": "S00042",
                "state": "sale",
                "date_order": "2026-11-11 14:22:10",
                "validity_date": "2026-11-30",
                "note": "<p>Pedido confirmado</p>",
                "currency_id": [156, "PEN"],
                "company_id": [1, "Mi Empresa SAC"],
                "partner_id": [20, "Cliente Corporativo"],
                "order_line": [2001, 2002],
            }
        },
        "sale.order.line": {
            2001: {
                "name": "Nota informativa",
                "product_id": False,
                "product_uom_qty": 0.0,
                "price_unit": 0.0,
                "tax_id": [],
                "display_type": "line_note",
            },
            2002: {
                "name": "Licencia ERP Anual",
                "product_id": [101, "[PROD-A] Licencia ERP"],
                "product_uom_qty": 3.0,
                "price_unit": 100.0,
                "tax_id": [5],
                "display_type": False,
            },
        },
    }


@pytest.fixture(scope="module")
def xsd_validator() -> XsdValidator:
    return XsdValidator(DEFAULT_INVOICE_XSD_PATH)


@pytest.fixture
def odoo_config() -> OdooConnectionConfig:
    return OdooConnectionConfig(
        url="http://localhost:8069/",
        db="unas_odoo",
        username="admin@unas.edu.pe",
        api_key="secret-api-key",
    )


def test_config_from_env_reads_variables_and_supports_password_fallback() -> None:
    cfg = OdooConnectionConfig.from_env(
        {
            "ODOO_URL": "http://localhost:8069/",
            "ODOO_DB": "erp_db",
            "ODOO_USER": "user@erp.pe",
            "ODOO_PASSWORD": "legacy-password",
        }
    )
    assert cfg.url == "http://localhost:8069"
    assert cfg.api_key == "legacy-password"

    with pytest.raises(OdooConnectionError, match="Faltan variables de entorno"):
        OdooConnectionConfig.from_env({"ODOO_URL": "http://localhost:8069"})

    with pytest.raises(OdooConnectionError, match="http:// o https://"):
        OdooConnectionConfig(url="localhost:8069", db="db", username="u", api_key="k")


def test_odoo_client_generates_valid_ubl_xml_from_account_move(
    odoo_config: OdooConnectionConfig,
    xsd_validator: XsdValidator,
) -> None:
    client = OdooXmlRpcClient(
        odoo_config,
        common_proxy=FakeCommonProxy(uid=7),
        object_proxy=FakeObjectProxy(_sample_odoo_tables()),
    )
    use_case = GenerateInvoiceXmlUseCase(validator=xsd_validator)

    xml_output = use_case.execute_from_odoo_gateway(
        client, document_number="INV/2026/0042", source="invoice"
    )
    xsd_validator.validate(xml_output)

    root = etree.fromstring(encode_xml_bytes(xml_output))
    assert root.findtext("cbc:ID", namespaces=NS) == "F001-00000042"
    assert root.findtext("cbc:Note", namespaces=NS) == "Emitida desde Odoo"
    assert root.findtext("cac:OrderReference/cbc:ID", namespaces=NS) == "S00042"
    assert root.findtext("cbc:LineCountNumeric", namespaces=NS) == "1"
    assert (
        root.findtext(
            "cac:InvoiceLine/cac:Item/cac:SellersItemIdentification/cbc:ID",
            namespaces=NS,
        )
        == "PROD-A"
    )
    assert (
        root.findtext("cac:LegalMonetaryTotal/cbc:PayableAmount", namespaces=NS)
        == "590.00"
    )


def test_odoo_client_generates_valid_ubl_xml_from_sale_order(
    odoo_config: OdooConnectionConfig,
    xsd_validator: XsdValidator,
) -> None:
    client = OdooXmlRpcClient(
        odoo_config,
        common_proxy=FakeCommonProxy(uid=7),
        object_proxy=FakeObjectProxy(_sample_odoo_tables()),
    )
    use_case = GenerateInvoiceXmlUseCase(validator=xsd_validator)

    xml_output = use_case.execute_from_odoo_gateway(
        client, document_number="S00042", source="sale"
    )
    xsd_validator.validate(xml_output)

    root = etree.fromstring(encode_xml_bytes(xml_output))
    assert root.findtext("cbc:ID", namespaces=NS) == "F001-00000042"
    assert root.findtext("cbc:IssueDate", namespaces=NS) == "2026-11-11"
    assert root.findtext("cbc:DueDate", namespaces=NS) == "2026-11-30"
    assert (
        root.findtext("cac:LegalMonetaryTotal/cbc:PayableAmount", namespaces=NS)
        == "354.00"
    )


def test_odoo_client_handles_auth_network_and_missing_record_errors(
    odoo_config: OdooConnectionConfig,
) -> None:
    bad_auth = OdooXmlRpcClient(
        odoo_config,
        common_proxy=FakeCommonProxy(uid=False),
        object_proxy=FakeObjectProxy(_sample_odoo_tables()),
    )
    with pytest.raises(OdooConnectionError, match="Autenticación rechazada"):
        bad_auth.fetch_invoice_payload()

    unreachable = OdooXmlRpcClient(
        odoo_config,
        common_proxy=FakeCommonProxy(raise_exc=OSError("Connection refused")),
        object_proxy=FakeObjectProxy(_sample_odoo_tables()),
    )
    with pytest.raises(OdooConnectionError, match="No se pudo conectar"):
        unreachable.fetch_invoice_payload()

    not_found = OdooXmlRpcClient(
        odoo_config,
        common_proxy=FakeCommonProxy(uid=7),
        object_proxy=FakeObjectProxy(_sample_odoo_tables()),
    )
    with pytest.raises(OdooConnectionError, match="No se encontró"):
        not_found.fetch_invoice_payload("INV/9999/9999")


def test_odoo_client_rejects_incomplete_partner_fields(
    odoo_config: OdooConnectionConfig,
) -> None:
    tables = _sample_odoo_tables()
    tables["res.partner"][20]["vat"] = False
    client = OdooXmlRpcClient(
        odoo_config,
        common_proxy=FakeCommonProxy(uid=7),
        object_proxy=FakeObjectProxy(tables),
    )
    with pytest.raises(OdooConnectionError, match="campos obligatorios: vat"):
        client.fetch_invoice_payload()


def test_odoo_client_handles_xmlrpc_fault(odoo_config: OdooConnectionConfig) -> None:
    class FaultCommonProxy:
        def authenticate(self, *_args: Any) -> int:
            raise xmlrpc.client.Fault(1, "Access Denied")

    client = OdooXmlRpcClient(
        odoo_config,
        common_proxy=FaultCommonProxy(),
        object_proxy=FakeObjectProxy({}),
    )
    with pytest.raises(OdooConnectionError, match="No se pudo conectar"):
        client.authenticate()


def test_cli_demo_writes_valid_xml_file(tmp_path, xsd_validator: XsdValidator) -> None:
    out_file = tmp_path / "demo_invoice.xml"
    exit_code = cli_main(["--demo", "-o", str(out_file)])

    assert exit_code == 0
    assert out_file.exists()
    raw_bytes = out_file.read_bytes()
    assert raw_bytes.startswith(b'<?xml version="1.0" encoding="ISO-8859-1"?>')
    xsd_validator.validate(raw_bytes)

    sunat_dir = tmp_path / "cpe"
    assert cli_main(["--demo", "-o", str(sunat_dir)]) == 0
    expected_sunat_file = sunat_dir / "20123456789-01-FE01-00000573.xml"
    assert expected_sunat_file.exists()
    xsd_validator.validate(expected_sunat_file.read_bytes())


def test_config_from_env_reads_dotenv_file_and_prefers_os_environ(
    tmp_path, monkeypatch
) -> None:
    for var in ("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_API_KEY", "ODOO_PASSWORD"):
        monkeypatch.delenv(var, raising=False)

    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(
        "# Comentario de prueba\n"
        'ODOO_URL="http://localhost:8069/"\n'
        "ODOO_DB=mi_bd_odoo\n"
        "ODOO_USER='admin@odoo.pe'\n"
        "ODOO_API_KEY=clave-desde-dotenv\n",
        encoding="utf-8",
    )

    cfg = OdooConnectionConfig.from_env(dotenv_path=dotenv_file)
    assert cfg.url == "http://localhost:8069"
    assert cfg.db == "mi_bd_odoo"
    assert cfg.username == "admin@odoo.pe"
    assert cfg.api_key == "clave-desde-dotenv"

    monkeypatch.setenv("ODOO_API_KEY", "clave-desde-entorno")
    cfg_override = OdooConnectionConfig.from_env(dotenv_path=dotenv_file)
    assert cfg_override.api_key == "clave-desde-entorno"
