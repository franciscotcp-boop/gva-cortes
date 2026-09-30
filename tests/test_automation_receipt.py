import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from automation_receipt import build_receipt, read_archive


class AutomationReceiptTests(unittest.TestCase):
    def test_preserves_the_exact_selected_source_and_outcomes(self):
        receipt = build_receipt("puestos", {"GITHUB_RUN_ID": "17", "GITHUB_RUN_ATTEMPT": "2",
            "GITHUB_SHA": "abc", "RESULT_PUESTOS": "success", "RESULT_VALIDATION": "success",
            "RESULT_PUBLICATION": "success"})
        self.assertEqual(receipt["modes"], ["puestos"])
        self.assertEqual(receipt["source_outcomes"], {"puestos": "success"})
        self.assertEqual(receipt["run_attempt"], 2)

    def test_failed_checks_are_not_recorded_as_successes(self):
        receipt = build_receipt("curso,puestos", {"GITHUB_RUN_ID": "17", "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_SHA": "abc", "RESULT_CURSO": "failure", "RESULT_PUESTOS": "success"})
        self.assertEqual(receipt["source_outcomes"]["curso"], "failure")
        self.assertEqual(receipt["publication_outcome"], "skipped")

    def test_empty_or_unknown_sources_are_rejected(self):
        for modes in ("", "unknown"):
            with self.assertRaises(ValueError):
                build_receipt(modes, {})

    def test_reads_json_from_zip_without_extracting_files(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("automation-check.json", json.dumps({"run_id": 17}))
        self.assertEqual(read_archive(stream.getvalue()), {"run_id": 17})

    def test_rejects_oversized_compressed_receipts(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("automation-check.json", " " * (128 * 1024 + 1))
        with self.assertRaises(ValueError):
            read_archive(stream.getvalue())
