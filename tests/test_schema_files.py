"""Consistency of the reference data scope files (schema/)."""

import csv
import json
import unittest

import helpers
from helpers import FRONTEND_DIR, SCHEMA_DIR

helpers.setup_paths()

import build_frontend_schema  # noqa: E402
from aed.validation import (  # noqa: E402
    field_names,
    institution_field_names,
    load_schema,
    published_field_names,
)

ENUM_DICTIONARIES = {
    "access": "access.csv",
    "device_status": "device_status.csv",
    "pediatric": "pediatric.csv",
    "street_type": "street_types.csv",
}


def read_csv(path):
    with open(str(path), encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


class SchemaFilesTest(unittest.TestCase):
    def setUp(self):
        self.schema = load_schema()
        self.by_name = {f["name"]: f for f in self.schema["fields"]}

    def test_schema_is_valid_json_with_unique_names(self):
        json.loads((SCHEMA_DIR / "aed.schema.json").read_text(encoding="utf-8"))
        names = field_names()
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(self.schema["primaryKey"], "id")

    def test_every_provider_field_has_title_and_known_group(self):
        groups = {g["name"] for g in self.schema["x-groups"]}
        for field in self.schema["fields"]:
            with self.subTest(field["name"]):
                self.assertTrue(field.get("title"))
                if not field.get("x-system"):
                    self.assertIn(field.get("x-group"), groups)

    def test_dictionaries_match_schema_enums_and_labels(self):
        for name, filename in ENUM_DICTIONARIES.items():
            with self.subTest(name):
                rows = read_csv(SCHEMA_DIR / "dictionaries" / filename)[1:]
                field = self.by_name[name]
                self.assertEqual([r[0] for r in rows], field["constraints"]["enum"])
                self.assertEqual({r[0]: r[1] for r in rows}, field["x-enumLabels"])
        voivodeships = [r[0] for r in read_csv(SCHEMA_DIR / "dictionaries" / "voivodeships.csv")[1:]]
        self.assertEqual(voivodeships, self.by_name["voivodeship"]["constraints"]["enum"])

    def test_template_and_example_headers_follow_schema(self):
        self.assertEqual(read_csv(SCHEMA_DIR / "aed-template.csv")[0], field_names(provider_only=True))
        self.assertEqual(read_csv(SCHEMA_DIR / "aed-example.csv")[0], published_field_names())

    def test_institution_and_internal_fields(self):
        self.assertEqual(institution_field_names(), ["operator_name", "operator_regon", "contact_phone", "contact_email"])
        self.assertNotIn("internal_contact_phone", published_field_names())
        self.assertIn("internal_contact_phone", field_names(provider_only=True))
        for name in institution_field_names():
            self.assertNotIn(name, field_names(provider_only=True))

    def test_generated_frontend_schema_is_up_to_date(self):
        current = (FRONTEND_DIR / "aed-schema.js").read_text(encoding="utf-8")
        self.assertEqual(current, build_frontend_schema.render(), "run: python tools/build_frontend_schema.py")


if __name__ == "__main__":
    unittest.main()
