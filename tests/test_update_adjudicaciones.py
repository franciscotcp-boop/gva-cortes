from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import update_adjudicaciones as updater


class ResilientHttpTests(unittest.TestCase):
    def test_retries_after_two_minutes_and_allows_a_longer_attempt(self) -> None:
        clock = [0.0]
        attempts: list[float] = []
        sleeps: list[float] = []

        def monotonic() -> float:
            return clock[0]

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            clock[0] += seconds

        def request(_url: str, *, timeout_seconds: float) -> bytes:
            attempts.append(timeout_seconds)
            clock[0] += timeout_seconds
            if len(attempts) < 3:
                raise TimeoutError("timed out")
            return b"respuesta"

        result = updater.resilient_http_get(
            "https://example.test/adjudicaciones",
            retry_window_seconds=20,
            initial_timeout_seconds=2,
            retry_timeout_seconds=5,
            retry_delay_seconds=1,
            request_fn=request,
            sleep_fn=sleep,
            monotonic_fn=monotonic,
        )

        self.assertEqual(result, b"respuesta")
        self.assertEqual(attempts, [2, 5, 5])
        self.assertEqual(sleeps, [1, 1])

    def test_stops_when_the_total_retry_window_is_exhausted(self) -> None:
        clock = [0.0]
        attempts: list[float] = []

        def monotonic() -> float:
            return clock[0]

        def sleep(seconds: float) -> None:
            clock[0] += seconds

        def request(_url: str, *, timeout_seconds: float) -> bytes:
            attempts.append(timeout_seconds)
            clock[0] += timeout_seconds
            raise TimeoutError("timed out")

        with self.assertRaises(TimeoutError):
            updater.resilient_http_get(
                "https://example.test/adjudicaciones",
                retry_window_seconds=6,
                initial_timeout_seconds=2,
                retry_timeout_seconds=5,
                retry_delay_seconds=1,
                request_fn=request,
                sleep_fn=sleep,
                monotonic_fn=monotonic,
            )

        self.assertEqual(attempts, [2, 3])

    def test_does_not_retry_a_permanent_http_error(self) -> None:
        attempts = []

        def request(url: str, *, timeout_seconds: float) -> bytes:
            attempts.append(timeout_seconds)
            raise updater.urllib.error.HTTPError(url, 404, "Not Found", {}, None)

        with self.assertRaises(updater.urllib.error.HTTPError):
            updater.resilient_http_get(
                "https://example.test/no-existe",
                retry_window_seconds=20,
                request_fn=request,
                sleep_fn=lambda _seconds: self.fail("No debe esperar ante un error 404"),
            )

        self.assertEqual(len(attempts), 1)


class PeriodMetadataTests(unittest.TestCase):
    def test_start_year_is_derived_for_every_successive_year(self) -> None:
        cases = {
            "2025-2026": 2025,
            "2028-2029": 2028,
            "2999-3000": 2999,
            "3000-3001": 3000,
        }
        for school_year, expected in cases.items():
            with self.subTest(school_year=school_year):
                self.assertEqual(
                    updater.start_year_from_school_year(school_year),
                    expected,
                )

    def test_invalid_school_year_is_not_published(self) -> None:
        for value in (None, "", "2028", "2028-2030", "year-2028"):
            with self.subTest(value=value):
                self.assertIsNone(updater.start_year_from_school_year(value))

    def test_existing_json_gets_start_year_without_touching_rows(self) -> None:
        rows = [["03012736", "218", 526]]
        data = {
            "cuts": {
                "inicio": {
                    "school_year": "2028-2029",
                    "rows": rows,
                }
            }
        }
        self.assertTrue(updater.ensure_period_metadata(data))
        self.assertEqual(data["cuts"]["inicio"]["start_year"], 2028)
        self.assertIs(data["cuts"]["inicio"]["rows"], rows)
        self.assertFalse(updater.ensure_period_metadata(data))


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
