import io
import json
from pathlib import Path
import sys
import unittest
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from automation_receipt import build_receipt, load_program_reviews, read_archive


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

    def test_pending_program_reviews_belong_to_the_current_run_and_attempt(self):
        case = {"slot_id": "841479", "candidate_name": "VICEDO DURA, GUILLERMO",
                "center_code": "03012980", "post_specialty_code": "297",
                "candidate_pools": [{"specialty_code": "256", "position": 230}]}
        environment = {"GITHUB_RUN_ID": "17", "GITHUB_RUN_ATTEMPT": "2", "GITHUB_SHA": "abc", "RESULT_CURSO": "failure"}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "program-review-pending.json"
            report = {"schema_version": 1, "run_id": "17", "run_attempt": "2", "cases": [case]}
            path.write_text(json.dumps(report), encoding="utf8")
            self.assertEqual(load_program_reviews(environment, path), [case])
            self.assertEqual(load_program_reviews({**environment, "GITHUB_RUN_ATTEMPT": "3"}, path), [])
            self.assertEqual(load_program_reviews({**environment, "GITHUB_RUN_ID": "18"}, path), [])
            receipt = build_receipt("curso", environment, load_program_reviews(environment, path))
            self.assertEqual(receipt["program_reviews"], [case])
            self.assertEqual(receipt["source_outcomes"], {"curso": "failure"})
            self.assertEqual(receipt["publication_outcome"], "skipped")
            path.write_text(json.dumps({**report, "cases": ["invalid"]}), encoding="utf8")
            with self.assertRaises(ValueError):
                load_program_reviews(environment, path)
