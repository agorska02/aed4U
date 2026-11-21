"""Python validator (backend/aed/validation.py) against the shared cases. Run: python -m unittest discover -s tests"""

import datetime
import unittest
from decimal import Decimal

import helpers
from helpers import apply_changes, example_rows, load_cases

helpers.setup_paths()

from aed.validation import OPENING_HOURS_RE, enum_choices, validate_record  # noqa: E402


class SharedCasesTest(unittest.TestCase):
    def test_shared_cases(self):
        for case in load_cases():
            with self.subTest(case["name"]):
                _cleaned, errors = validate_record(apply_changes(case["changes"]))
                self.assertEqual(sorted(errors), sorted(case["errors"]), errors)
                for field, message in case.get("messages", {}).items():
                    self.assertEqual(errors[field], message)


class ValidatorTest(unittest.TestCase):
    def test_all_example_rows_are_valid_published_records(self):
        for row in example_rows():
            with self.subTest(row["id"]):
                self.assertEqual(validate_record(row, provider=False)[1], {})  # incl. system, without internal fields

    def test_values_are_converted(self):
        cleaned, _errors = validate_record(apply_changes({"floor": "-1"}))
        self.assertIs(cleaned["indoor"], True)
        self.assertEqual(cleaned["floor"], -1)
        self.assertEqual(cleaned["latitude"], Decimal("50.059000"))
        self.assertEqual(cleaned["data_date"], datetime.date(2026, 11, 15))

    def test_optional_skips_required_check(self):
        record = apply_changes({"location_name": ""})
        self.assertIn("location_name", validate_record(record)[1])
        self.assertEqual(validate_record(record, optional=("location_name",))[1], {})

    def test_enum_choices_have_polish_labels(self):
        self.assertIn(("public", "dostępny publicznie"), enum_choices("access"))

    def test_opening_hours_subset(self):
        for value in (
            "24/7",
            "Mo-Su 00:00-24:00",
            "Mo-Fr 07:30-15:30; Sa 09:00-13:00",
            "Mo-Fr 08:00-12:00,13:00-16:00; PH off",
            "May-Sep 08:00-20:00",
            "Jun-Aug Mo-Fr 08:00-16:00; Jun-Aug Sa,Su,PH off",
            "Nov-Feb PH 10:00-14:00",
        ):
            self.assertRegex(value, OPENING_HOURS_RE)
        for value in (
            "całą dobę",
            "8-16",
            "Mo-Fr 8:00-16:00",
            "Mo-Fr 08:00-16:00;; Sa off",
            "Maj-Wrz 08:00-20:00",
            "Mo-Fr May-Sep 08:00-16:00",
        ):
            self.assertNotRegex(value, OPENING_HOURS_RE)


if __name__ == "__main__":
    unittest.main()
