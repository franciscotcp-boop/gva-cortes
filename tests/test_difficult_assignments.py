import copy
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from difficult_assignments import attach_ledger, make_ledger, merge_ledger, parse_page


class DifficultAssignmentsTest(unittest.TestCase):
    def test_arrow_uses_nearest_header_not_other_rows(self):
        text = ("121 INGLES\n846181 03019007PUESTO :\n"
                "OTHER PERSON1 NAME 11/09/2026 10:00:00 GVRTE/2026/1 846181\n"
                "--> TEST SURNAME1 ANA 11/09/2026 10:00:00 GVRTE/2026/1 846181 S\n"
                "152PEDAGOGIA\n923728 12002208PUESTO :\n"
                "--> OTHER SURNAME9 LUIS 11/09/2026 10:00:00 GVRTE/2026/2 923728\n")
        rows = parse_page(text, 2)
        self.assertEqual([r["slot_id"] for r in rows], ["846181", "923728"])
        self.assertEqual(rows[1]["specialty_code"], "152")
        self.assertNotIn("draw_order", rows[1])

    def test_mismatching_slot_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_page("121 INGLES\n846181 03019007PUESTO :\n--> TEST SURNAME1 ANA 11/09/2026 10:00:00 GVRTE/2026/1 923728", 1)

    def test_provisional_ledger_rejected(self):
        positions = {"academic_year": "2026/2027", "people": []}
        for ledger in [{"status": "provisional", "awards": []},
                       {"status": "definitive", "awards": [{"provisional": True}]}]:
            with self.assertRaises(ValueError):
                attach_ledger(positions, ledger)
        self.assertNotIn("difficult_assignments", positions)
        with self.assertRaises(ValueError):
            make_ledger([], [], positions, "2026-09-11", "test", "test.pdf", provisional=True)

    def test_extension_preserves_all_original_data(self):
        positions = {"academic_year": "2026/2027", "people": [["Test", "TEST", [["120", 20, 10]], "maestros"]], "reference_date": "2026-09-10"}
        before = copy.deepcopy(positions)
        ledger = {"status": "definitive", "academic_year": "2026/2027", "awards": []}
        attach_ledger(positions, ledger)
        self.assertEqual({k: v for k, v in positions.items() if k != "difficult_assignments"}, before)
        attach_ledger(positions, {**ledger, "academic_year": "2027/2028"})
        self.assertEqual(positions, before)

    def test_new_results_preserve_other_days_and_replace_corrections(self):
        previous = {"academic_year": "2026/2027", "source": {"date": "2026-09-11"},
                    "awards": [{"date": "2026-09-11", "id": "old"}]}
        incoming = {"academic_year": "2026/2027", "source": {"date": "2026-09-18"},
                    "awards": [{"date": "2026-09-18", "id": "new"}]}
        merged = merge_ledger(previous, incoming)
        self.assertEqual([a["id"] for a in merged["awards"]], ["old", "new"])
        corrected = {**incoming, "awards": [{"date": "2026-09-18", "id": "corrected"}]}
        self.assertEqual([a["id"] for a in merge_ledger(merged, corrected)["awards"]], ["old", "corrected"])


if __name__ == "__main__":
    unittest.main()
