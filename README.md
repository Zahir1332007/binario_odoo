# Generación de Factura Electrónica XML a partir de Invoice XSD 2.1 (OASIS UBL 2.1)

Componente en Python desarrollado bajo un enfoque **Schema-First** y **Arquitectura en Capas** para generar facturas electrónicas **XML estándar OASIS UBL 2.1** a partir de datos comerciales provenientes del módulo de **Ventas de Odoo**, validando cada documento generado contra el esquema oficial `UBL-Invoice-2.1.xsd`.

> La descripción detallada del caso de negocio y las decisiones arquitectónicas se encuentran en [docs/descripcion_caso.md](docs/descripcion_caso.md).

---

## Estructura del Proyecto

```text
├── docs/
│   └── descripcion_caso.md              # Descripción del caso (Odoo Ventas -> UBL 2.1)
├── schemas/
│   └── ubl-2.1/
│       ├── maindoc/UBL-Invoice-2.1.xsd  # Esquema XSD 2.1 oficial OASIS
│       └── common/                      # Esquemas comunes importados por Invoice XSD 2.1
├── src/
│   └── invoice_xml/
│       ├── cli.py                       # CLI para modo demo o conexión en vivo con Odoo
│       ├── domain/                      # Entidades puras (Invoice, InvoiceLine, Party) con Decimal
│       ├── application/                 # Casos de uso, puerto OdooInvoiceGateway y adaptador Odoo
│       └── infrastructure/
│           ├── ubl_models/              # Dataclasses generadas desde UBL-Invoice-2.1.xsd (xsdata)
│           ├── mapper.py                # Traductor Dominio -> UBL 2.1
│           ├── odoo_client.py           # Conector XML-RPC hacia Odoo (`account.move` / `sale.order`)
│           └── xml_service.py           # Serializador XML UTF-8 + Validador XSD 2.1 (lxml)
├── tests/
│   ├── test_invoice_generation.py       # Pruebas unitarias de generación y validación XSD
│   └── test_odoo_client.py              # Pruebas unitarias del conector XML-RPC de Odoo (mocks)
├── .env.example
├── pyproject.toml
└── requirements.txt
```

---

## Instalación rápida tras `git clone`

Requisitos: **Python 3.11+** y **Git**.

```powershell
git clone <URL_DEL_REPOSITORIO>
cd 2do-parcial

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

*(En Linux/macOS activar con `source .venv/bin/activate`).*

---

## Conexión con Odoo (API XML-RPC)

El conector `OdooXmlRpcClient` se comunica con Odoo (por ejemplo, instalado localmente desde binarios en `http://localhost:8069`) usando `xmlrpc.client`.

1. Copia `.env.example` como `.env` (ignorado por Git) y coloca tus credenciales de Odoo:

```dotenv
ODOO_URL=http://localhost:8069
ODOO_DB=tu_base_de_datos
ODOO_USER=tu_usuario@correo.com
ODOO_API_KEY=tu_api_key_o_password
```

2. Genera un XML UBL 2.1 validado contra el XSD 2.1 ejecutando directamente `exportar_odoo.py` (carga `.env` y `src/` automáticamente):

```powershell
# Exportar la última factura publicada (account.move) a salida/factura_odoo.xml
python exportar_odoo.py

# O especificando origen/número/salida
python exportar_odoo.py --source invoice --number "INV/2026/0001" -o salida/factura.xml
python exportar_odoo.py --source sale --number "S00042" -o salida/pedido.xml

# Modo demo offline (sin requerir Odoo encendido)
python exportar_odoo.py --demo -o salida/demo.xml
```

---

## Ejecución de pruebas unitarias

Las pruebas unitarias validan reglas de dominio, cálculos monetarios con `Decimal`, adaptación desde un payload de Ventas de Odoo, round-trip de deserialización y **validación estricta contra `schemas/ubl-2.1/maindoc/UBL-Invoice-2.1.xsd`**:

```powershell
pytest
```

---

## Regeneración de modelos Python desde Invoice XSD 2.1 (referencia)

Los modelos en `src/invoice_xml/infrastructure/ubl_models/` ya están generados y versionados para funcionamiento offline inmediato. Si deseas regenerarlos directamente desde el XSD:

```powershell
cd src
xsdata generate ..\schemas\ubl-2.1\maindoc\UBL-Invoice-2.1.xsd --package invoice_xml.infrastructure.ubl_models --relative-imports --structure-style filenames
```

