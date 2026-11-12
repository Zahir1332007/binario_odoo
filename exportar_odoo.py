"""Ejecuta la exportación XML UBL 2.1 desde Odoo leyendo las credenciales del archivo .env."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from invoice_xml.cli import main

if __name__ == "__main__":
    argv = sys.argv[1:] or ["--source", "invoice", "-o", "salida"]
    raise SystemExit(main(argv))
