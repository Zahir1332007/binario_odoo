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
│       ├── domain/                      # Entidades puras (Invoice, InvoiceLine, Party) con Decimal
│       ├── application/                 # Caso de uso y adaptador desde Odoo Ventas
│       └── infrastructure/
│           ├── ubl_models/              # Dataclasses generadas desde UBL-Invoice-2.1.xsd (xsdata)
│           ├── mapper.py                # Traductor Dominio -> UBL 2.1
│           └── xml_service.py           # Serializador XML UTF-8 + Validador XSD 2.1 (lxml)
├── tests/
│   └── test_invoice_generation.py       # Suite de pruebas unitarias de generación y validación XSD
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
```

*(En Linux/macOS activar con `source .venv/bin/activate`).*

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

