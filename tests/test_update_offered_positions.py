from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from offered_positions import ITEM_FIELDS, build_payload
from update_offered_positions import (
    academic_year_for_check,
    document_date_hint,
    links_for_latest_target_document,
    offered_position_links,
    update_from_page,
    valid_academic_year,
)


def sample_item(order: int, center_code: str = "03000001") -> list:
    return [
        order,
        "maestros",
        "128",
        "Alicante",
        "ELX",
        center_code,
        "CEIP DE PRUEBA",
        f"{order:06d}",
        23.0,
        False,
        False,
        "",
        "vacante",
    ]


def published_payload(publication_date: str, items: list[list], sha: str) -> dict:
    payload = build_payload(
        specialties=[
            {
                "code": "128",
                "es": "Educación Primaria",
                "va": "Educació Primària",
                "body": "maestros",
            }
        ],
        academic_year="2026-2027",
        status="published",
        publication_date=publication_date,
        source={"url": "https://example.test/puestos.pdf", "sha256": sha},
        items=items,
    )
    payload["item_fields"] = ITEM_FIELDS
    return payload


class OfferedPositionLinkTests(unittest.TestCase):
    def test_finds_only_offered_position_pdfs(self) -> None:
        html = b"""
        <a href="/docs/260602_pue_prov.pdf">Listado de puestos ofertados</a>
        <a href="/docs/260602_lis_mae.pdf">Listado de adjudicacion</a>
        <a href="/docs/notas.pdf">Notas</a>
        """
        links = offered_position_links(html, "https://ceice.gva.es/pagina")
        self.assertEqual(len(links), 1)
        self.assertTrue(links[0]["url"].endswith("260602_pue_prov.pdf"))

    def test_reads_compact_date_and_prioritizes_correction(self) -> None:
        original = {
            "url": "https://example.test/260909_pue_prov.pdf",
            "text": "Puestos ofertados",
        }
        correction = {
            "url": "https://example.test/260909_pue_prov_corr.pdf",
            "text": "Corrección de errores de puestos ofertados",
        }
        older = {
            "url": "https://example.test/260907_pue_prov.pdf",
            "text": "Puestos ofertados",
        }
        self.assertEqual(document_date_hint(original), date(2026, 9, 9))
        self.assertEqual(
            links_for_latest_target_document(
                [older, original, correction], "2026-2027"
            ),
            [correction],
        )

    def test_academic_year_boundary_keeps_july_first_in_previous_course(self) -> None:
        self.assertEqual(academic_year_for_check(date(2027, 7, 1)), "2026-2027")
        self.assertEqual(academic_year_for_check(date(2027, 7, 2)), "2027-2028")
        self.assertEqual(academic_year_for_check(date(2026, 9, 1)), "2026-2027")
        self.assertTrue(valid_academic_year("2999-3000"))


class OfferedPositionUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.output = self.root / "puestos.json"
        self.specialties = self.root / "posiciones.json"
        self.centers = self.root / "centros.json"
        self.specialties.write_text(
            json.dumps(
                {
                    "specialties": [
                        {
                            "code": "128",
                            "es": "Educación Primaria",
                            "va": "Educació Primària",
                            "body": "maestros",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.centers.write_text(
            json.dumps(
                {
                    "centers": [
                        {
                            "codigo": "03000001",
                            "nombre": "CEIP DE PRUEBA",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_new_pdf_replaces_instead_of_accumulating(self) -> None:
        self.output.write_text(
            json.dumps(
                published_payload("2026-09-07", [sample_item(1), sample_item(2)], "old")
            ),
            encoding="utf-8",
        )
        page_url = "https://ceice.gva.es/pagina"
        pdf_url = "https://ceice.gva.es/docs/260909_pue_prov.pdf"
        html = f'<a href="{pdf_url}">Puestos ofertados</a>'.encode()
        replacement = published_payload("2026-09-09", [sample_item(3)], "new")

        def fetch(url: str) -> bytes:
            return html if url == page_url else b"%PDF-test"

        with patch(
            "update_offered_positions.parse_downloaded_pdf",
            return_value=replacement,
        ):
            result = update_from_page(
                page_url=page_url,
                output=self.output,
                specialties_path=self.specialties,
                centers_path=self.centers,
                target_year="2026-2027",
                fetch=fetch,
            )

        saved = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(result["result"], "updated")
        self.assertEqual(saved["items"], [sample_item(3)])

    def test_new_course_without_pdf_clears_previous_snapshot(self) -> None:
        old = published_payload("2026-06-02", [sample_item(1)], "old")
        old["academic_year"] = "2025-2026"
        self.output.write_text(json.dumps(old), encoding="utf-8")
        html = (
            '<a href="https://ceice.gva.es/docs/260602_pue_prov.pdf">'
            "Puestos ofertados</a>"
        ).encode()

        result = update_from_page(
            page_url="https://ceice.gva.es/pagina",
            output=self.output,
            specialties_path=self.specialties,
            centers_path=self.centers,
            target_year="2026-2027",
            fetch=lambda _: html,
        )

        saved = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(result["result"], "new_academic_year_without_offers")
        self.assertEqual(saved["academic_year"], "2026-2027")
        self.assertEqual(saved["items"], [])
        self.assertEqual(saved["status"], "awaiting_first_continuous_adjudication")


if __name__ == "__main__":
    unittest.main()
