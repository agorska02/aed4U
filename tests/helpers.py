"""Shared helpers for the prototype tests (standard library only)."""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schema"
FRONTEND_DIR = ROOT / "frontend"


def setup_paths():
    """Make backend/aed (Django-independent modules) and tools/ importable. Call before importing them."""
    for path in (str(ROOT / "backend"), str(ROOT / "tools")):
        if path not in sys.path:
            sys.path.insert(0, path)


setup_paths()


def load_json(name):
    return json.loads((Path(__file__).parent / name).read_text(encoding="utf-8"))


def load_cases():
    return load_json("validation_cases.json")["cases"]


def example_rows():
    with open(str(SCHEMA_DIR / "aed-example.csv"), encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def base_provider_record():
    from aed.validation import field_names

    provider = set(field_names(provider_only=True))
    record = {key: value for key, value in example_rows()[0].items() if key in provider}
    record["serial_number"] = "SN-TEST-0001"  # internal field, not in the published example file
    return record


def apply_changes(changes):
    record = base_provider_record()
    record.update(changes)
    return record
