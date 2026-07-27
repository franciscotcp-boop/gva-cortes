from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from offered_positions import ITEM_FIELDS, build_payload
from update_offered_positions import (
    academic_year_for_check,
    document_date_hint,
    links_for_latest_target_document,
    merge_snapshot,
    offered_position_links,
    prune_expired_difficult,
    reconcile_after_adjudication,
    update_from_page,
    valid_academic_year,
)


def sample_item(
    order: int,
    center_code: str = "03000001",
    *,
    specialty_code: str = "128",
    difficult: bool = False,
    snapshot_date: str = "2026-09-07",
) -> list:
    return [
        order,
        "maestros",
        specialty_code,
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
        "",
        difficult,
        snapshot_date,
        False,
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
        replacement = published_payload(
            "2026-09-09",
            [sample_item(3, snapshot_date="2026-09-09")],
            "new",
        )

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
        self.assertEqual(len(saved["items"]), 1)
        self.assertEqual(saved["items"][0][0], 1)
        self.assertEqual(saved["items"][0][7], "000003")
        self.assertEqual(saved["items"][0][15], "2026-09-09")

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

    def test_ordinary_and_difficult_snapshots_replace_only_their_own_kind(self) -> None:
        ordinary = published_payload(
            "2026-09-07",
            [sample_item(1, snapshot_date="2026-09-07")],
            "ordinary-old",
        )
        ordinary["source"]["kind"] = "ordinary"
        ordinary["snapshots"] = {
            "ordinary": {
                "publication_date": "2026-09-07",
                "source": ordinary["source"],
            }
        }
        difficult = published_payload(
            "2026-09-11",
            [sample_item(2, difficult=True, snapshot_date="2026-09-11")],
            "difficult",
        )
        difficult["source"]["kind"] = "difficult"
        merged = merge_snapshot(ordinary, difficult, "difficult")

        replacement = published_payload(
            "2026-09-09",
            [sample_item(3, center_code="03000002", snapshot_date="2026-09-09")],
            "ordinary-new",
        )
        replacement["source"]["kind"] = "ordinary"
        final = merge_snapshot(merged, replacement, "ordinary")

        self.assertEqual(len(final["items"]), 2)
        self.assertEqual(set(final["snapshots"]), {"ordinary", "difficult"})
        difficult_rows = [row for row in final["items"] if row[14] is True]
        ordinary_rows = [row for row in final["items"] if row[14] is False]
        self.assertEqual(difficult_rows[0][7], "000002")
        self.assertEqual(ordinary_rows[0][5], "03000002")

    def test_difficult_positions_expire_when_the_calendar_day_changes(self) -> None:
        payload = published_payload(
            "2026-09-11",
            [
                sample_item(1, snapshot_date="2026-09-09"),
                sample_item(2, difficult=True, snapshot_date="2026-09-11"),
            ],
            "mixed",
        )
        payload["snapshots"] = {
            "ordinary": {"publication_date": "2026-09-09", "source": {}},
            "difficult": {"publication_date": "2026-09-11", "source": {}},
        }

        same_day, removed_same_day = prune_expired_difficult(
            payload, date(2026, 9, 11)
        )
        next_day, removed_next_day = prune_expired_difficult(
            payload, date(2026, 9, 12)
        )

        self.assertEqual(removed_same_day, 0)
        self.assertEqual(len(same_day["items"]), 2)
        self.assertEqual(removed_next_day, 1)
        self.assertEqual(len(next_day["items"]), 1)
        self.assertNotIn("difficult", next_day["snapshots"])

    def test_adjudication_removes_filled_slot_and_keeps_unfilled_offer(self) -> None:
        payload = published_payload(
            "2026-09-09",
            [
                sample_item(1, snapshot_date="2026-09-09"),
                sample_item(2, center_code="03000002", snapshot_date="2026-09-09"),
            ],
            "ordinary",
        )
        payload["snapshots"] = {
            "ordinary": {"publication_date": "2026-09-09", "source": payload["source"]}
        }
        self.output.write_text(json.dumps(payload), encoding="utf-8")

        result = reconcile_after_adjudication(
            output=self.output,
            assignments=[
                SimpleNamespace(
                    slot_id="000001",
                    center_code="03000001",
                    specialty_code="128",
                )
            ],
            academic_year="2026-2027",
            adjudication_date="2026-09-10",
        )

        saved = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(result["removed"], 1)
        self.assertEqual(result["remaining"], 1)
        self.assertEqual(saved["items"][0][7], "000002")
        self.assertIs(saved["items"][0][16], True)


if __name__ == "__main__":
    unittest.main()
