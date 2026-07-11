from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import update_adjudicaciones as updater


class SecondaryHeaderSpecialtyTests(unittest.TestCase):
    def test_empty_legacy_dataset_is_upgraded_without_downloads(self) -> None:
        data = {"schema_version": 1, "cuts": {"inicio": {"rows": []}}}
        self.assertTrue(updater.migrate_secondary_header_policy(data, {}))
        self.assertEqual(data["schema_version"], updater.SCHEMA_VERSION)

    def test_current_schema_does_not_migrate_again(self) -> None:
        data = {"schema_version": updater.SCHEMA_VERSION}
        self.assertFalse(updater.migrate_secondary_header_policy(data, {}))

    def test_legacy_migration_rebuilds_start_and_course(self) -> None:
        start_url = "https://example.test/start-sec.pdf"
        course_url = "https://example.test/course-sec.pdf"
        maestro_start = ["M1", "120", 10, "INFANTIL", "CEIP", "LLOC", "maestros", "", "inicio"]
        maestro_course = ["M2", "128", 20, "PRIMARIA", "CEIP", "LLOC", "maestros", "sub_determinada", "curso"]
        data = {
            "schema_version": 2,
            "cuts": {
                "inicio": {
                    "rows": [maestro_start, ["S1", "219", 999, "TECNOLOGIA", "IES", "LLOC", "secundaria", "", "inicio"]],
                    "pdfs": {"secundaria": {"url": start_url}},
                },
                "curso": {
                    "rows": [maestro_start, maestro_course],
                    "pdfs": [{"body": "secundaria", "url": course_url, "published_date": "2026-06-02"}],
                },
            },
            "processed_pdfs": {},
        }
        parsed_start = updater.ParsedPdf(
            start_url,
            "start-sha",
            "secundaria",
            "2025-07-30",
            [["S1", "219", 95, "TECNOLOGIA", "IES", "LLOC", "secundaria", "vacante"]],
        )
        parsed_course = updater.ParsedPdf(
            course_url,
            "course-sha",
            "secundaria",
            "2026-06-02",
            [["S2", "219", 40, "TECNOLOGIA", "IES", "LLOC", "secundaria", "sub_indeterminada"]],
        )
        with patch.object(updater, "http_get", return_value=b"pdf"), patch.object(
            updater,
            "parse_pdf",
            side_effect=[parsed_start, parsed_course],
        ):
            self.assertTrue(updater.migrate_secondary_header_policy(data, {}))

        self.assertEqual(data["schema_version"], updater.SCHEMA_VERSION)
        self.assertIn(maestro_start, data["cuts"]["inicio"]["rows"])
        self.assertIn(maestro_course, data["cuts"]["curso"]["rows"])
        start_rows = {updater.row_key(row): row for row in data["cuts"]["inicio"]["rows"]}
        course_rows = {updater.row_key(row): row for row in data["cuts"]["curso"]["rows"]}
        self.assertEqual(start_rows["S1|219|secundaria"][2], 95)
        self.assertEqual(course_rows["S2|219|secundaria"][2], 40)

    def test_pdfplumber_header_order(self) -> None:
        text = """Altres Cossos / Otros Cuerpos
PROFESSORS D'ENSENYAMENT SECUNDARI
219 TECNOLOGIA
95 GOMEZ NEBOT, HECTOR
"""
        self.assertEqual(updater.secondary_page_specialty(text), ("219", "TECNOLOGIA"))

    def test_pypdf_header_order(self) -> None:
        text = """Altres Cossos / Otros Cuerpos
PROFESSORS D'ENSENYAMENT SECUNDARI
TECNOLOGIA 219
95
"""
        self.assertEqual(updater.secondary_page_specialty(text), ("219", "TECNOLOGIA"))

    def test_header_name_can_contain_comma(self) -> None:
        text = """Altres Cossos / Otros Cuerpos
PROFESSORS D'ENSENYAMENT SECUNDARI
2A5 MAQUINES, SERVEIS I PRODUCCIO
1 DOCENTE, PRUEBA
"""
        self.assertEqual(
            updater.secondary_page_specialty(text),
            ("2A5", "MAQUINES, SERVEIS I PRODUCCIO"),
        )

    def test_cross_pool_duplicate_is_ignored(self) -> None:
        block = [
            "912 ORTEGA FERNANDEZ, RUBEN Voluntaria",
            "918342 ALMASSORA(12000251)IES ALVARO FALOMIR",
            "206 / MATEMATIQUES",
            "Jornada completa VACANT Adjudicat",
        ]
        row = updater.parse_block(block, "secundaria", ("219", "TECNOLOGIA"))
        self.assertIsNone(row)

    def test_matching_header_and_position_specialty_is_canonical(self) -> None:
        block = [
            "95 GOMEZ NEBOT, HECTOR Peticion: 1 Voluntaria",
            "921979 ALMASSORA(12000251)IES ALVARO FALOMIR",
            "219 / TECNOLOGIA",
            "Jornada completa VACANT Adjudicat",
        ]
        row = updater.parse_block(block, "secundaria", ("219", "TECNOLOGIA"))
        self.assertIsNotNone(row)
        self.assertEqual(row.cut, 95)
        self.assertEqual(row.center_code, "12000251")
        self.assertEqual(row.specialty_code, "219")
        self.assertEqual(row.specialty_name, "TECNOLOGIA")

    def test_maestros_keeps_assignment_specialty(self) -> None:
        block = [
            "553 DOCENTE, PRUEBA",
            "900001 ASPE(03002743)CEIP LA SERRANICA",
            "128 / EDUCACIO PRIMARIA",
            "VACANT Adjudicat",
        ]
        row = updater.parse_block(block, "maestros")
        self.assertIsNotNone(row)
        self.assertEqual(row.specialty_code, "128")


if __name__ == "__main__":
    unittest.main()
