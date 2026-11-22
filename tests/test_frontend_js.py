"""Frontend JS (aed-validator.js, aed-import.js) against the shared cases, run in headless Chrome or Edge.

Skipped when no Chromium-based browser is found; set CHROME_PATH to point at one.
"""

import html
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import helpers
from helpers import FRONTEND_DIR, apply_changes, load_cases, load_json

helpers.setup_paths()

from aed.importing import export_record, to_csv  # noqa: E402
from test_importing import check_case, stored_examples  # noqa: E402

CANDIDATES = [
    os.environ.get("CHROME_PATH"),
    shutil.which("chrome"),
    shutil.which("google-chrome"),
    shutil.which("chromium"),
    shutil.which("msedge"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
BROWSER = next((path for path in CANDIDATES if path and Path(path).exists()), None)
SCRIPTS = ("aed-schema.js", "aed-validator.js", "aed-import.js", "aed-hours.js")

RUNNER = r"""
var validation = DATA.validation.map(function (c) {
  var r = AedValidator.validate(c.record);
  return {name: c.name, errors: Object.keys(r.errors).sort(), messages: r.errors};
});
var imports = Promise.all(DATA.imports.map(function (c) {
  return AedImport.parseFileAsync(c.content, c.format).then(function (rows) {
    var own = c.own || [], all = c.all || own;
    var plan = AedImport.planImport(rows, own, all, {operator_name: "Instytucja testowa"});
    return {
      file_error: false,
      rows: rows,
      errors: plan.errors.map(function (e) { return [e.row, e.field]; }),
      summary: plan.summary,
      actions: plan.actions.map(function (a) { return [a.row, a.action, a.duplicate_of, a.duplicate_of_row]; })
    };
  }, function (e) { if (e instanceof AedImport.ImportFileError) return {file_error: true}; throw e; });
}));
var exported = AedImport.toCsv(AED_EXAMPLES.map(function (row) {
  var r = AedValidator.validate(row, {provider: false}).cleaned;
  r.uuid = row.id; r.source = row.source; r.verified_at = row.verified_at;
  return AedImport.exportRecord(r);
}));
var hours = DATA.hours.status.map(function (c) { return AedHours.statusAt(c[0], new Date(c[1])); });
var described = DATA.hours.describe.map(function (c) { return AedHours.describe(c[0]); });
RESULT = imports.then(function (imported) {  // XLSX files are read asynchronously
  return {validation: validation, imports: imported, exported: exported, hours: hours, described: described};
});
"""

PAGE = """<!doctype html><meta charset="utf-8"><body><pre id="out"></pre>{scripts}
<script>
var DATA = {data}, RESULT = null;
function show(value) {{ document.getElementById("out").textContent = "RESULT" + JSON.stringify(value) + "END"; }}
function fail(e) {{ show({{error: String(e && e.stack || e)}}); }}
try {{ {runner} Promise.resolve(RESULT).then(show, fail); }} catch (e) {{ fail(e); }}
</script>"""


@unittest.skipUnless(BROWSER, "no Chrome/Edge found (set CHROME_PATH)")
class FrontendJsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validation_cases = [dict(case, record=apply_changes(case["changes"])) for case in load_cases()]
        cls.import_cases = load_json("import_cases.json")["cases"]
        cls.hours_cases = load_json("opening_hours_cases.json")
        data = json.dumps(
            {"validation": cls.validation_cases, "imports": cls.import_cases, "hours": cls.hours_cases}, ensure_ascii=False
        )
        scripts = "".join("<script>{0}</script>".format((FRONTEND_DIR / n).read_text(encoding="utf-8")) for n in SCRIPTS)
        page = PAGE.format(scripts=scripts, data=data.replace("</", "<\\/"), runner=RUNNER)
        with tempfile.TemporaryDirectory() as tmp:
            page_path = Path(tmp) / "frontend.html"
            page_path.write_text(page, encoding="utf-8")
            out = subprocess.run(
                # the virtual time budget lets the asynchronous XLSX reading finish before the DOM is dumped
                [
                    BROWSER,
                    "--headless",
                    "--disable-gpu",
                    f"--user-data-dir={tmp}",
                    "--virtual-time-budget=20000",
                    "--dump-dom",
                    page_path.as_uri(),
                ],
                capture_output=True,
                timeout=90,
            ).stdout.decode("utf-8", "replace")
        marker = '<pre id="out">RESULT'
        if marker not in out:
            raise AssertionError("browser produced no result")
        cls.result = json.loads(html.unescape(out.split(marker, 1)[1].split("END</pre>", 1)[0]))

    def test_runner_had_no_errors(self):
        self.assertNotIn("error", self.result, self.result.get("error"))

    def test_validation_cases(self):
        results = {r["name"]: r for r in self.result["validation"]}
        for case in self.validation_cases:
            with self.subTest(case["name"]):
                result = results[case["name"]]
                self.assertEqual(result["errors"], sorted(case["errors"]), result["messages"])
                for field, message in case.get("messages", {}).items():
                    self.assertEqual(result["messages"][field], message)

    def test_import_cases(self):
        for case, result in zip(self.import_cases, self.result["imports"]):
            with self.subTest(case["name"]):
                check_case(self, case, result)

    def test_opening_hours_status(self):
        for (value, moment, expected), result in zip(self.hours_cases["status"], self.result["hours"]):
            with self.subTest(value=value, moment=moment):
                self.assertEqual(result, expected)

    def test_opening_hours_description(self):
        self.assertEqual(self.result["described"], [c[1] for c in self.hours_cases["describe"]])

    def test_opening_hours_always_open(self):
        self.assertEqual(self.result["always"], [c[1] for c in self.hours_cases["always"]])

    def test_csv_export_matches_python(self):
        self.assertEqual(self.result["exported"], to_csv([export_record(r) for r in stored_examples()]))


if __name__ == "__main__":
    unittest.main()
