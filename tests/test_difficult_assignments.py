import copy
import json
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from difficult_assignments import attach_ledger, make_directory_review_ledger, make_ledger, merge_ledger, parse_page, preserve_ledger


class DifficultAssignmentsTest(unittest.TestCase):
    def directory_fixture(self):
        winner = {"page": 1, "slot_id": "924077", "center_code": "03004341",
                  "specialty_code": "127", "candidate_name": "MIGUEL CARPIO, MARIA DE LOS REMEDIOS"}
        evidence = {"official_name": "MIGUEL CARPIO, MARIA DE LOS REMEDIOS", "center_code": "03004341",
                    "exact_name_results": 1, "checked_at": "2026-09-21T20:00:00+02:00",
                    "search_url": "https://sede.gva.es/va/cercador-persones?nombre=MARIA",
                    "department_url": "https://sede.gva.es/detall-departament?id_dept=21793"}
        review = {"decision": "verified_center_match", "winner": winner, "evidence": evidence}
        offer = {"slot_id": "924077", "center_code": "03004341", "specialty_code": "127", "body": "maestros",
                 "placement_type": "vacante", "hours": 11.5, "english_requirement": False, "itinerant": False,
                 "center_name_pdf": "CEIP Cardenal Belluga", "municipality": "Dolores", "observations": "PCT Lectora"}
        return review, offer, {"academic_year": "2026/2027", "people": []}

    def test_directory_evidence_is_distinct_from_provisional_pdf(self):
        review, offer, positions = self.directory_fixture()
        review["evidence"]["official_name"] = "MIGUEL CARPIO, MARIA DE LOS REMEDIOS".replace("MARIA", "MAR\u00cdA")
        ledger = make_directory_review_ledger([review], [offer], positions, "2026-09-11", "hash", "260911_par.pdf")
        self.assertFalse(ledger["source"]["is_definitive_resolution"])
        self.assertEqual(ledger["verification_basis"], "reviewed_directory_cross_reference")
        self.assertEqual(ledger["awards"][0]["detail"][3], 11.5)
        self.assertEqual(ledger["awards"][0]["detail"][9], "PCT Lectora")
        self.assertNotIn("positions", ledger["awards"][0])
        attach_ledger(positions, ledger)
        self.assertEqual(positions["people"], [])

    def test_directory_mismatches_and_ambiguities_fail_closed(self):
        for field, value in [("official_name", "OTHER PERSON"), ("center_code", "03000000"),
                             ("exact_name_results", 2), ("checked_at", ""),
                             ("department_url", "https://example.com/"), ("search_url", "https://sede.gva.es.example.com/")]:
            review, offer, positions = self.directory_fixture()
            review["evidence"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                make_directory_review_ledger([review], [offer], positions, "2026-09-11", "hash", "test.pdf")
        for flag in ("competing_assignment", "multiple_possible_posts", "later_post_evidence"):
            review, offer, positions = self.directory_fixture()
            review[flag] = True
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                make_directory_review_ledger([review], [offer], positions, "2026-09-11", "hash", "test.pdf")
        review, offer, positions = self.directory_fixture()
        with self.assertRaises(ValueError):
            make_directory_review_ledger([review, review], [offer], positions, "2026-09-11", "hash", "test.pdf")

    def test_automatic_rebuild_preserves_reviewed_ledger_only_for_same_year(self):
        review, offer, positions = self.directory_fixture()
        ledger = make_directory_review_ledger([review], [offer], positions, "2026-09-11", "hash", "test.pdf")
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "difficult_assignments.json").write_text(json.dumps(ledger), encoding="utf8")
            rebuilt = {"academic_year": "2026/2027", "people": [], "reference_date": "2026-09-22"}
            preserve_ledger(rebuilt, directory)
            self.assertEqual(rebuilt["difficult_assignments"], ledger)
            self.assertEqual(rebuilt["reference_date"], "2026-09-22")
            next_year = {"academic_year": "2027/2028", "people": []}
            preserve_ledger(next_year, directory)
            self.assertNotIn("difficult_assignments", next_year)

    def test_official_pdf_award_has_priority_over_directory(self):
        review, offer, positions = self.directory_fixture()
        review["evidence"]["assignment_inference"] = "ordered_candidate_and_current_workplace_match"
        ledger = make_directory_review_ledger([review], [offer], positions, "2026-09-11", "hash", "test.pdf")
        positions["people"] = [["Test", review["winner"]["candidate_name"],
                                 [["127", 1, 1, 1, None, None, None, None, "A"]], "maestros", [], "u"]]
        with self.assertRaisesRegex(ValueError, "Official PDF"):
            make_directory_review_ledger([review], [offer], positions, "2026-09-11", "hash", "test.pdf")
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "difficult_assignments.json").write_text(json.dumps(ledger), encoding="utf8")
            preserve_ledger(positions, directory)
            self.assertEqual(positions["difficult_assignments"]["awards"], [])
            self.assertEqual(positions["people"][0][2][0][8], "A")

    def test_award_labels_do_not_create_pool_membership_or_replace_catalog(self):
        review, offer, positions = self.directory_fixture()
        labels = [{"code": "127", "es": "PT", "va": "PT", "body": "maestros"}]
        ledger = make_directory_review_ledger([review], [offer], positions, "2026-09-11", "hash", "test.pdf", labels)
        attach_ledger(positions, ledger)
        self.assertEqual(positions["specialties"], labels)
        self.assertEqual(positions["people"], [])
        positions["specialties"][0]["es"] = "Existing reviewed name"
        attach_ledger(positions, ledger)
        self.assertEqual(positions["specialties"][0]["es"], "Existing reviewed name")
        self.assertEqual(len(positions["specialties"]), 1)

    def test_directory_cannot_replace_official_difficult_coverage_awards(self):
        review, offer, positions = self.directory_fixture()
        official = make_ledger([review["winner"]], [offer], positions, "2026-09-11", "hash", "final.pdf")
        for day in ("2026-09-11", "2026-09-18"):
            inferred = make_directory_review_ledger([review], [offer], positions, day, "hash", "provisional.pdf")
            self.assertFalse(inferred["awards"][0]["verification"]["is_definitive_resolution"])
            self.assertTrue(inferred["awards"][0]["verification"]["assignment_inference"])
            with self.subTest(day=day), self.assertRaisesRegex(ValueError, "Official PDF"):
                merge_ledger(official, inferred)
        inferred = make_directory_review_ledger([review], [offer], positions, "2026-09-11", "hash", "provisional.pdf")
        self.assertEqual(merge_ledger(inferred, official)["awards"], official["awards"])

    def test_master_special_education_post_keeps_existing_pool_numbers(self):
        review, offer, positions = self.directory_fixture()
        review["winner"]["specialty_code"] = offer["specialty_code"] = "151"
        person = ["Test", review["winner"]["candidate_name"], [["126", 100, 90]], "maestros", [500, 450], "u"]
        positions["people"] = [person]
        original = copy.deepcopy(person)
        ledger = make_directory_review_ledger([review], [offer], positions, "2026-09-11", "hash", "test.pdf")
        self.assertEqual(ledger["awards"][0]["specialty_code"], "126")
        self.assertEqual(ledger["awards"][0]["offered_specialty_code"], "151")
        self.assertEqual(person, original)
        positions["people"] = []
        ledger = make_directory_review_ledger([review], [offer], positions, "2026-09-11", "hash", "test.pdf")
        self.assertEqual(ledger["awards"][0]["specialty_code"], "151")

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
