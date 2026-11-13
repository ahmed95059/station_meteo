"""Lecture reproductible des documents fournis (dépendances de développement)."""
import json
import sys
from pathlib import Path

from openpyxl import load_workbook
from pypdf import PdfReader

sys.stdout.reconfigure(encoding="utf-8")
folder = Path(sys.argv[1])
for name in ["stationMeteo_eleves.xlsx", "TP Instrumentation n°1 2024 - Sujet.pdf",
             "TP Instrumentation n°2 2024 - Sujet.pdf", "Python  Instrumentation - Support de cours.pdf"]:
    print(f"\n===== {name} =====")
    path = folder / name
    if path.suffix == ".xlsx":
        book = load_workbook(path, data_only=True)
        for sheet in book:
            print(f"Feuille {sheet.title}, {sheet.max_row} lignes")
            for row in sheet:
                cells = [f"{c.coordinate}: {c.value}" for c in row if c.value is not None]
                if cells:
                    print(" | ".join(cells))
    else:
        for index, page in enumerate(PdfReader(path).pages, 1):
            print(f"\n--- Page {index} ---\n{page.extract_text()}")
