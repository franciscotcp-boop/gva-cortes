from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from update_source_data import (
    Adjudication,
    allowed_accreditation_years,
    detection_block,
    enrich_status_details_and_context,
    merge_accreditations,
    load_json,
    position_document,
    preferred_accreditation_links,
    recalculate_english_positions,
    rows_from_accreditation_table,
    save_json_atomic,
    select_position_pair,
)
from update_adjudicaciones import detect_itinerant, detect_placement_type


class SourceDocumentTests(unittest.TestCase):
    def test_position_pair_requires_both_bodies_and_uses_latest_year(self) -> None:
        links = [
            {
                "url": "https://example.test/ini_2026_par_pro_int_lis_mae.pdf",
                "text": "Listado provisional Maestros",
            },
            {
                "url": "https://example.test/ini_2026_par_pro_int_lis_sec.pdf",
                "text": "Listado provisional Otros Cuerpos",
            },
            {
                "url": "https://example.test/ini_2025_par_pro_int_lis_mae.pdf",
                "text": "Listado provisional Maestros",
            },
            {
                "url": "https://example.test/ini_2025_par_pro_int_lis_sec.pdf",
                "text": "Listado provisional Otros Cuerpos",
            },
        ]
        selected = select_position_pair(links)
        self.assertIsNotNone(selected)
        self.assertEqual(selected[0], 2026)
        self.assertEqual(set(selected[1]), {"maestros", "secundaria"})
        self.assertEqual(position_document(links[0]), ("maestros", 2026))

    def test_correction_replaces_regular_document_for_same_date(self) -> None:
        regular = {
            "url": "https://example.test/2026-03-02.pdf",
            "text": "2026-03-02",
            "province": "Alicante",
            "date": "2026-03-02",
        }
        correction = {
            "url": "https://example.test/2026-03-02-correccion-de-errores.pdf",
            "text": "2026-03-02 correccion de errores",
            "province": "Alicante",
            "date": "2026-03-02",
        }
        self.assertEqual(preferred_accreditation_links([correction, regular]), [correction])

    def test_accreditation_year_window_includes_next_course_in_july(self) -> None:
        self.assertEqual(
            allowed_accreditation_years(date(2026, 7, 23)),
            {"2025-2026", "2026-2027"},
        )

    def test_pypdf_joined_vacancy_and_itinerant_labels_are_restored(self) -> None:
        block = detection_block(["VACANTItinerante", "23 horas"])
        self.assertEqual(detect_placement_type(block), "vacante")
        self.assertTrue(detect_itinerant(block))

    def test_only_the_actually_awarded_specialty_is_marked_awarded(self) -> None:
        master_positions = [
            ["124", 1, 1, 1, 1, None, None, [0, 0, 0, None, None], "N", None],
            ["128", 1, 1, 1, 1, None, None, [0, 0, 0, None, None], "N", None],
        ]
        secondary_positions = [
            ["3A1", 6, 6, 6, 6, None, None, [0, 0, 0, None, None], "N", None],
            ["3A9", 6, 6, 6, 6, None, None, [0, 0, 0, None, None], "N", None],
        ]
        data = {
            "people": [
                ["Oscar", "BERENGUER JOVER, OSCAR", master_positions, "maestros", [1, 1], "m"],
                ["David", "MARTINEZ MARTINEZ, DAVID", secondary_positions, "otros", None, "m"],
            ]
        }
        master_rows = [
            {
                "official_name": "BERENGUER JOVER, OSCAR",
                "adjudication_position": 1,
                "raw_status": "A",
            }
        ]
        secondary_rows = [
            {
                "official_name": "MARTINEZ MARTINEZ, DAVID",
                "specialty_code": code,
                "position": 6,
                "adjudication_position": 6,
                "raw_status": "A",
            }
            for code in ("3A1", "3A9")
        ]
        assignments = [
            Adjudication(1, "BERENGUER JOVER, OSCAR", "03000001", "124", "Musica", "Centro", "Alacant", "maestros", "vacante", False, 23, False),
            Adjudication(6, "MARTINEZ MARTINEZ, DAVID", "46000001", "3A9", "Serveis", "Centre", "Valencia", "secundaria", "vacante", False, "C", False),
        ]
        enrich_status_details_and_context(
            data,
            master_rows,
            secondary_rows,
            assignments,
            "2026-07-15",
            {},
        )
        self.assertEqual([row[8] for row in master_positions], ["A", "N"])
        self.assertEqual([row[8] for row in secondary_positions], ["N", "A"])


class AccreditationParserTests(unittest.TestCase):
    def test_compressed_accreditation_state_round_trips(self) -> None:
        payload = {"schema_version": 1, "records": [{"official_name": "LOPEZ, MARIA"}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "english.json.gz"
            save_json_atomic(path, payload)
            self.assertEqual(load_json(path), payload)

    def test_table_keeps_only_english_b2_or_higher_without_exclusion(self) -> None:
        table = [
            ["Apellido1", "Apellido2", "Nombre", "Idioma", "Nivel", "Motivos Exclusión"],
            ["LOPEZ", "GARCIA", "MARIA", "Inglés", "B2", ""],
            ["PEREZ", "SOLER", "ANA", "Francés", "C2", ""],
            ["RUIZ", "MARTI", "JOAN", "Anglés", "C1", ""],
            ["MORA", "VIDAL", "LUIS", "Inglés", "C2", "No procede"],
            ["GIL", "SANCHO", "PAU", "Inglés", "B1", ""],
        ]
        source = {
            "url": "https://example.test/a.pdf",
            "date": "2026-06-30",
            "academic_year": "2025-2026",
        }
        rows = rows_from_accreditation_table(table, "Valencia", source)
        self.assertEqual([row["official_name"] for row in rows], ["LOPEZ GARCIA, MARIA", "RUIZ MARTI, JOAN"])
        self.assertEqual([row["level"] for row in rows], ["B2", "C1"])

    def test_merge_is_cumulative_and_idempotent(self) -> None:
        payload = {
            "schema_version": 1,
            "records": [],
            "processed_documents": [],
        }
        row = {
            "official_name": "LOPEZ GARCIA, MARIA",
            "display_name": "Maria Lopez Garcia",
            "level": "B2",
            "province": "Valencia",
            "date": "2026-06-30",
            "academic_year": "2025-2026",
            "source_url": "https://example.test/a.pdf",
        }
        document = {
            "url": row["source_url"],
            "sha256": "abc",
            "date": row["date"],
            "province": row["province"],
            "academic_year": row["academic_year"],
            "correction": False,
            "records": 1,
        }
        self.assertTrue(merge_accreditations(payload, [row], [document]))
        snapshot = copy.deepcopy(payload)
        self.assertFalse(merge_accreditations(payload, [row], [document]))
        self.assertEqual(payload, snapshot)

    def test_recalculation_preserves_double_credential_rule(self) -> None:
        positions = {
            "people": [
                ["Uno", "UNO, PERSONA", [["121", 1, 1, 1, 1, None, None], ["128", 1, 1, 1, 1, None, None]], "maestros", [1, 1]],
                ["Dos", "DOS, PERSONA", [["128", 2, 2, 2, 2, None, None]], "maestros", [2, 2]],
                ["Tres", "TRES, PERSONA", [["121", 2, 2, 3, 3, None, None], ["128", 3, 3, 3, 3, None, None]], "maestros", [3, 3]],
            ],
            "english_requirement": {},
        }
        accreditations = {
            "updated_at": "2026-07-01",
            "records": [
                {"official_name": "UNO, PERSONA"},
                {"official_name": "DOS, PERSONA"},
            ],
        }
        self.assertTrue(recalculate_english_positions(positions, accreditations))
        self.assertEqual(positions["people"][0][2][1][6], 2)
        self.assertEqual(positions["people"][1][2][0][6], 3)
        self.assertEqual(positions["people"][2][2][1][6], 4)


if __name__ == "__main__":
    unittest.main()
