"""Import, duplicate detection and export (backend/aed/importing.py). Run: python -m unittest discover -s tests"""

import csv
import io
import json
import unittest

import helpers
from helpers import example_rows, load_json

helpers.setup_paths()

from aed.importing import (  # noqa: E402
    ImportFileError,
    distance_m,
    export_record,
    name_similarity,
    parse_file,
    plan_import,
    to_csv,
    to_geojson,
)
from aed.validation import field_names, validate_record  # noqa: E402

DEFAULT_OPERATOR = "Instytucja testowa"


def stored_examples():
    """Example records as a backend stores them (cleaned values + uuid/source/verified_at)."""
    records = []
    for row in example_rows():
        cleaned, _errors = validate_record(row)
        records.append(dict(cleaned, uuid=row["id"], source=row["source"], verified_at=row["verified_at"]))
    return records


def run_case(case):
    """Python implementation of a shared case -> comparable result (same shape as the JS runner)."""
    try:
        rows = parse_file(case["content"], case["format"])
    except ImportFileError:
        return {"file_error": True}
    plan = plan_import(rows, case.get("own", []), case.get("all", case.get("own", [])), DEFAULT_OPERATOR)
    return {
        "file_error": False,
        "errors": [[e["row"], e["field"]] for e in plan["errors"]],
        "summary": plan["summary"],
        "actions": [[a["row"], a["action"], a["duplicate_of"], a["duplicate_of_row"]] for a in plan["actions"]],
    }


def check_case(test, case, result):
    expect = case["expect"]
    test.assertEqual(result["file_error"], expect.get("file_error", False), result)
    if result["file_error"]:
        return
    test.assertEqual(result["errors"], expect.get("errors", []), result)
    for key, value in expect.get("summary", {}).items():
        test.assertEqual(result["summary"][key], value, (key, result["summary"]))
    if "actions" in expect:
        test.assertEqual(result["actions"], expect["actions"])


class SharedImportCasesTest(unittest.TestCase):
    def test_shared_cases(self):
        for case in load_json("import_cases.json")["cases"]:
            with self.subTest(case["name"]):
                check_case(self, case, run_case(case))


class DuplicateHelpersTest(unittest.TestCase):
    def test_distance(self):
        self.assertAlmostEqual(distance_m(50.0, 19.0, 50.001, 19.0), 111.2, delta=0.5)

    def test_name_similarity_ignores_case_and_diacritics(self):
        self.assertEqual(name_similarity("Urząd Gminy Łódź", "urzad gminy lodz"), 1.0)
        self.assertLess(name_similarity("Dworzec PKP", "Biblioteka"), 0.5)


class ExportTest(unittest.TestCase):
    def exported_csv(self):
        return to_csv([export_record(r) for r in stored_examples()])

    def test_csv_export_round_trips_to_the_example_file(self):
        rows = list(csv.DictReader(io.StringIO(self.exported_csv())))
        self.assertEqual(list(rows[0]), field_names())
        self.assertEqual(rows, example_rows())

    def test_exported_csv_can_be_imported_again(self):
        plan = plan_import(parse_file(self.exported_csv(), "csv"), [], [], DEFAULT_OPERATOR)
        self.assertEqual(plan["errors"], [])
        self.assertEqual(plan["summary"]["create"], 5)

    def test_geojson_export(self):
        collection = to_geojson([export_record(r) for r in stored_examples()], data_date="2026-11-21")
        feature = collection["features"][0]
        self.assertEqual(feature["geometry"], {"type": "Point", "coordinates": [19.937, 50.059]})
        self.assertIs(feature["properties"]["indoor"], True)
        self.assertIsNone(feature["properties"]["access_notes"])
        self.assertEqual(collection["metadata"]["data_date"], "2026-11-21")
        plan = plan_import(parse_file(json.dumps(collection), "geojson"), [], [], DEFAULT_OPERATOR)
        self.assertEqual(plan["errors"], [])


if __name__ == "__main__":
    unittest.main()
