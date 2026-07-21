from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import update_adjudicaciones as updater


class CenterOverrideTests(unittest.TestCase):
    def test_override_file_is_valid_and_unique(self) -> None:
        rows = updater.load_center_overrides()
        codes = [str(row[0]) for row in rows]

        self.assertEqual(len(rows), 21)
        self.assertEqual(len(codes), len(set(codes)))
        self.assertIn("03021750", codes)
        self.assertIn("03022092", codes)
        self.assertIn("12008624", codes)

    def test_merge_replaces_existing_rows_and_adds_missing_rows(self) -> None:
        existing = [["A", "Original"] + [""] * 14]
        replacement = ["A", "Corregido"] + [""] * 12 + [39.0, -0.4]
        addition = ["B", "Nuevo"] + [""] * 12 + [40.0, 0.1]

        merged = updater.merge_center_overrides(existing, [replacement, addition])
        by_code = {row[0]: row for row in merged}

        self.assertEqual(len(merged), 2)
        self.assertEqual(by_code["A"], replacement)
        self.assertEqual(by_code["B"], addition)

    def test_load_centers_keeps_overrides_when_guide_is_unavailable(self) -> None:
        override = ["MANUAL", "Centro manual"] + [""] * 12 + [39.0, -0.4]
        with patch.object(updater, "http_get", side_effect=TimeoutError("sin guia")), patch.object(
            updater,
            "load_center_overrides",
            return_value=[override],
        ):
            centers, by_code = updater.load_centers([])

        self.assertEqual(centers, [override])
        self.assertEqual(by_code["MANUAL"]["name"], "Centro manual")

    def test_load_centers_keeps_overrides_after_a_guide_refresh(self) -> None:
        csv_data = (
            "codcen,cod_estado,dlibre,dgenerica_cas,dgenerica_val,regimen,direccion,codpos,telef,mail,web,"
            "noms_mun,localidad_oficial,comarca,provincia,latitud,longitud\n"
            "GUIA,A,Centro guia,Centro Público,Centre Públic,Público,Calle 1,46000,960000000,guia@example.es,,"
            "València,,València,València/Valencia,39.4,-0.4\n"
        ).encode("utf-8")
        override = ["MANUAL", "Centro manual"] + [""] * 12 + [39.0, -0.5]
        with patch.object(updater, "http_get", return_value=csv_data), patch.object(
            updater,
            "load_center_overrides",
            return_value=[override],
        ):
            centers, by_code = updater.load_centers([])

        self.assertEqual({row[0] for row in centers}, {"GUIA", "MANUAL"})
        self.assertEqual(set(by_code), {"GUIA", "MANUAL"})

    def test_every_cut_center_has_a_geolocated_center_record(self) -> None:
        data = json.loads(updater.DATA_PATH.read_text(encoding="utf-8"))
        centers = {str(row[0]): row for row in data["centers"]}
        cut_codes = {
            str(row[0])
            for period in ("inicio", "curso")
            for row in data["cuts"][period]["rows"]
        }

        self.assertEqual(cut_codes - centers.keys(), set())
        for code in cut_codes:
            self.assertTrue(all(isinstance(centers[code][index], (int, float)) for index in (14, 15)))


class CenterWebsiteOverrideTests(unittest.TestCase):
    def test_web_override_file_is_valid_and_blocks_removed_site(self) -> None:
        websites = updater.load_center_web_overrides()

        self.assertEqual(len(websites), 745)
        self.assertEqual(sum(url is not None for url in websites.values()), 744)
        self.assertIsNone(websites["03003644"])
        self.assertEqual(
            websites["12003699"],
            "https://portal.edu.gva.es/ceip_blasco_castello/",
        )

    def test_web_overrides_change_only_the_web_fields(self) -> None:
        first = ["03000001", "Centro uno"] + [""] * 14
        second = ["03000002", "Centro dos"] + [""] * 14
        first[5] = "Calle original"
        first[9] = "https://example.test/anterior/"
        first[10] = "https://example.test/val/"
        second[9] = "https://example.test/eliminada/"
        second[10] = "https://example.test/eliminada-val/"

        merged = updater.merge_center_web_overrides(
            [first, second],
            {
                "03000001": "https://portal.edu.gva.es/03000001/",
                "03000002": None,
                "99999999": "https://portal.edu.gva.es/99999999/",
            },
        )
        by_code = {row[0]: row for row in merged}

        self.assertEqual(by_code["03000001"][5], "Calle original")
        self.assertEqual(by_code["03000001"][9], "https://portal.edu.gva.es/03000001/")
        self.assertEqual(by_code["03000001"][10], "https://example.test/val/")
        self.assertEqual(by_code["03000002"][9:11], ["", ""])
        self.assertEqual(len(merged), 2)

    def test_invalid_web_override_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "webs.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "websites": {"03000001": "javascript:alert(1)"},
                        "blocked": {},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                updater.load_center_web_overrides(path)

    def test_load_centers_keeps_web_override_without_guide(self) -> None:
        existing = ["03000001", "Centro existente"] + [""] * 12 + [39.0, -0.4]
        with patch.object(updater, "http_get", side_effect=TimeoutError("sin guia")), patch.object(
            updater,
            "load_center_overrides",
            return_value=[],
        ), patch.object(
            updater,
            "load_center_web_overrides",
            return_value={"03000001": "https://portal.edu.gva.es/03000001/"},
        ):
            centers, _ = updater.load_centers([existing])

        self.assertEqual(centers[0][9], "https://portal.edu.gva.es/03000001/")

    def test_load_centers_keeps_web_override_after_guide_refresh(self) -> None:
        csv_data = (
            "codcen,cod_estado,dlibre,dgenerica_cas,dgenerica_val,regimen,direccion,codpos,telef,mail,web,"
            "noms_mun,localidad_oficial,comarca,provincia,latitud,longitud\n"
            "03000001,A,Centro guia,Centro Publico,Centre Public,Publico,Calle 1,03000,960000000,"
            "centro@example.es,,Alacant,,Alacanti,Alacant/Alicante,38.3,-0.4\n"
        ).encode("utf-8")
        with patch.object(updater, "http_get", return_value=csv_data), patch.object(
            updater,
            "load_center_overrides",
            return_value=[],
        ), patch.object(
            updater,
            "load_center_web_overrides",
            return_value={"03000001": "https://portal.edu.gva.es/03000001/"},
        ):
            centers, _ = updater.load_centers([])

        self.assertEqual(centers[0][9], "https://portal.edu.gva.es/03000001/")


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
        data = {
            "schema_version": updater.SCHEMA_VERSION,
            "cut_policy": {"version": 4},
            "cuts": {"inicio": {"rows": []}},
        }
        self.assertTrue(updater.migrate_secondary_header_policy(data, {}))
        self.assertEqual(data["schema_version"], updater.SCHEMA_VERSION)
        self.assertEqual(data["cut_policy"], updater.CUT_POLICY)

    def test_current_policy_does_not_migrate_again(self) -> None:
        data = {
            "schema_version": updater.SCHEMA_VERSION,
            "cut_policy": updater.CUT_POLICY,
        }
        self.assertFalse(updater.migrate_secondary_header_policy(data, {}))

    def test_legacy_migration_rebuilds_start_and_course(self) -> None:
        start_url = "https://example.test/start-sec.pdf"
        course_url = "https://example.test/course-sec.pdf"
        maestro_start = ["M1", "120", 10, "INFANTIL", "CEIP", "LLOC", "maestros", "", "inicio"]
        maestro_course = ["M2", "128", 20, "PRIMARIA", "CEIP", "LLOC", "maestros", "sub_determinada", "curso"]
        data = {
            "schema_version": 2,
            "cut_policy": {"version": 4},
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
TECNOLOGIA219
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

    def test_different_awarded_specialty_is_not_a_cut(self) -> None:
        block = [
            "912 ORTEGA FERNANDEZ, RUBEN Voluntaria",
            "918342 ALMASSORA(12000251)IES ALVARO FALOMIR",
            "206 / MATEMATIQUES",
            "Jornada completa VACANT Adjudicat",
        ]
        row = updater.parse_block(block, "secundaria", ("219", "TECNOLOGIA"))
        self.assertIsNone(row)

    def test_canos_is_geography_but_not_mathematics(self) -> None:
        block = [
            "1940 CANOS CABEDO, MARIA DE LA PURIFICACION Voluntaria",
            "875307 BORRIANA(12000704)IES JAUME I",
            "205 / GEOGRAFIA I HISTORIA",
            "Jornada completa VACANT Adjudicat",
        ]
        self.assertIsNone(
            updater.parse_block(block, "secundaria", ("206", "MATEMATIQUES"))
        )

        geography = updater.parse_block(
            [
                "230 CANOS CABEDO, MARIA DE LA PURIFICACION Voluntaria",
                "875307 BORRIANA(12000704)IES JAUME I",
                "205 / GEOGRAFIA I HISTORIA",
                "Jornada completa VACANT Adjudicat",
            ],
            "secundaria",
            ("205", "GEOGRAFIA I HISTORIA"),
        )
        self.assertIsNotNone(geography)
        self.assertEqual(geography.cut, 230)
        self.assertEqual(geography.specialty_code, "205")

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
