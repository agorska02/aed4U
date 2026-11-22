"""Generate the XLSX files for providers from the reference data scope (schema/aed.schema.json):

- schema/aed-template.xlsx — empty "Dane" sheet with the template columns, drop-down lists for dictionary
  fields, date and text column formats, plus "Instrukcja" (field descriptions) and "Słowniki" (codes) sheets;
- frontend/demo/aed-import-demo.xlsx — the demo import file (same rows as aed-import-demo.csv) with typed
  cells (numbers, true/false, dates), to show the XLSX import.

Run after editing the schema or the demo CSV:

    python tools/build_xlsx_files.py

tests/test_schema_files.py fails if the generated files are out of date.
"""

import csv
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from xlsx_writer import DATE, TEXT, Sheet, column_letter, workbook_bytes  # noqa: E402

SCHEMA = ROOT / "schema" / "aed.schema.json"
TEMPLATE_CSV = ROOT / "schema" / "aed-template.csv"
DEMO_CSV = ROOT / "frontend" / "demo" / "aed-import-demo.csv"
TEMPLATE = ROOT / "schema" / "aed-template.xlsx"
DEMO = ROOT / "frontend" / "demo" / "aed-import-demo.xlsx"

DICTIONARY_SHEET = "Słowniki"
# Typed as text so that Excel keeps e.g. "7/9" (not a date), "31-004" and leading zeros.
TEXT_COLUMNS = ("street_number", "postal_code", "serial_number", "internal_contact_phone", "opening_hours")
WIDE_COLUMNS = ("location_name", "location_description", "opening_hours", "access_notes", "building_type_other")


def load_fields():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return {f["name"]: f for f in schema["fields"]}


def read_csv(path):
    with open(str(path), encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def dictionary_sheet(fields, columns):
    """Codes and labels of every dictionary field used in `columns`; returns (sheet, {field: list formula})."""
    enum_fields = [fields[name] for name in columns if fields[name].get("constraints", {}).get("enum")]
    table = []
    formulas = {}
    widths = {}
    for position, field in enumerate(enum_fields):
        code_col = position * 3
        codes = field["constraints"]["enum"]
        labels = field.get("x-enumLabels", {})
        while len(table) < len(codes) + 1:
            table.append([])
        for row_index, (code, label) in enumerate([(field["name"], field["title"])] + [(c, labels.get(c, "")) for c in codes]):
            row = table[row_index]
            row.extend([None] * (code_col + 2 - len(row)))
            row[code_col], row[code_col + 1] = code, label
        letter = column_letter(code_col)
        formulas[field["name"]] = f"'{DICTIONARY_SHEET}'!${letter}$2:${letter}${len(codes) + 1}"
        widths[code_col] = 18
        widths[code_col + 1] = 26
    return Sheet(DICTIONARY_SHEET, table, widths=widths), formulas


def instruction_sheet(fields, columns):
    rows = [
        ["Kolumna", "Nazwa", "Wymagane", "Opis"],
        ["", "Wypełnij arkusz „Dane” – jeden wiersz to jedno urządzenie. Importowany jest tylko pierwszy arkusz.", "", ""],
        ["", "Pola słownikowe wybierz z listy (kody i ich znaczenie – arkusz „Słowniki”). Daty wpisz jako daty.", "", ""],
    ]
    for name in columns:
        field = fields[name]
        constraints = field.get("constraints", {})
        if constraints.get("required"):
            required = "tak"
        elif field.get("x-requiredIf"):
            other, value = next(iter(field["x-requiredIf"].items()))
            required = f"gdy {other} = {value}"
        else:
            required = ""
        rows.append([name, field["title"], required, field.get("description", "")])
    return Sheet("Instrukcja", rows, widths={0: 24, 1: 30, 2: 22, 3: 110})


def data_sheet(fields, columns, rows, formulas):
    column_styles = {}
    widths = {}
    validations = []
    for index, name in enumerate(columns):
        field = fields[name]
        if field.get("type") == "date":
            column_styles[index] = DATE
        elif name in TEXT_COLUMNS:
            column_styles[index] = TEXT
        widths[index] = 32 if name in WIDE_COLUMNS else max(14, len(name) + 2)
        if name in formulas:
            validations.append((index, formulas[name], "Wybierz kod z listy – znaczenie kodów jest w arkuszu „Słowniki”."))
        elif field.get("type") == "boolean":
            validations.append((index, '"true,false"', "Wpisz true (tak) albo false (nie)."))
    return Sheet("Dane", [columns] + rows, widths=widths, column_styles=column_styles, validations=validations)


def typed(field, value):
    """CSV text -> cell value of the type a spreadsheet user would enter."""
    if value == "":
        return None
    kind = field.get("type")
    if kind == "boolean":
        return value == "true"
    if kind == "date":
        return datetime.date.fromisoformat(value)
    if kind in ("number", "integer") and field["name"] not in TEXT_COLUMNS:
        return float(value) if kind == "number" else int(value)
    return value


def render_template():
    fields = load_fields()
    columns = read_csv(TEMPLATE_CSV)[0]
    dictionaries, formulas = dictionary_sheet(fields, columns)
    return workbook_bytes([data_sheet(fields, columns, [], formulas), instruction_sheet(fields, columns), dictionaries])


def render_demo():
    fields = load_fields()
    table = read_csv(DEMO_CSV)
    columns = table[0]
    rows = [[typed(fields[name], value) for name, value in zip(columns, row)] for row in table[1:]]
    dictionaries, formulas = dictionary_sheet(fields, columns)
    return workbook_bytes([data_sheet(fields, columns, rows, formulas), dictionaries])


def main():
    TEMPLATE.write_bytes(render_template())
    DEMO.write_bytes(render_demo())
    print(f"Written {TEMPLATE}\nWritten {DEMO}")


if __name__ == "__main__":
    main()
