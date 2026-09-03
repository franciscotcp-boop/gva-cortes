from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from position_context import PositionContextUpdater


def position(code: str, initial: int, after: int, context: list | None = None) -> list:
    return [code, initial, initial, after, after, None, None, context or [0, 0, 0, None, None]]


def assignment(
    name: str,
    code: str,
    center: str,
    cut: int,
    body: str = "secundaria",
    *,
    placement_type: str = "vacante",
    workload: int | str = "C",
    english_requirement: bool = False,
    itinerant: bool = False,
    center_name: str = "Centro de prueba",
    locality: str = "Localidad de prueba",
    observations: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        candidate_name=name,
        specialty_code=code,
        center_code=center,
        cut=cut,
        body=body,
        placement_type=placement_type,
        workload=workload,
        english_requirement=english_requirement,
        itinerant=itinerant,
        center_name=center_name,
        locality=locality,
        observations=observations,
    )


def status(name: str, code: str | None, order: int, value: str) -> SimpleNamespace:
    return SimpleNamespace(
        candidate_name=name,
        specialty_code=code,
        position=order,
        status=value,
    )


def parsed(
    date: str,
    body: str,
    assignments: list[SimpleNamespace],
    suffix: str = "1",
    statuses: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        published_date=date,
        body=body,
        assignments=assignments,
        statuses=statuses or [],
        url=f"https://example.test/{body}-{suffix}.pdf",
        sha256=f"sha-{body}-{suffix}",
    )


class PositionContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.positions_path = root / "posiciones.json"
        self.state_path = root / "state.json"
        self.positions = {
            "schema_version": 7,
            "academic_year": "2026/2027",
            "position_fields": [
                "specialty_code",
                "position_at_course_start",
                "position_without_deactivated",
                "position_after_adjudication",
                "position_after_adjudication_without_deactivated",
                "english_requirement_position",
                "last_awarded",
                "additional_information",
            ],
            "people": [
                ["Gemma", "VIZCAINO SANCHIS, GEMMA", [position("3A1", 6, 4)], "otros", None],
                ["Salvador", "MARTINEZ GUIJARRO, SALVADOR", [position("3A1", 8, 6, [9, 9, 9, {"old": True}, [1, 2, 3, 4]])], "otros", None],
                ["David", "MARTINEZ MARTINEZ, DAVID", [position("3A1", 9, 7), position("3A9", 3, 2)], "otros", None],
                ["Lucia", "ARCE RAMOS, LUCIA", [position("127", 20, 14)], "maestros", [25, 14]],
                ["Maria Nieves", "FERNANDEZ CASTILLO, MARIA NIEVES", [position("2B9", 3, 1)], "otros", None],
            ],
            "additional_information": {
                "future_history_available": False,
            },
        }
        self.positions_path.write_text(json.dumps(self.positions), encoding="utf-8")

    def load_positions(self) -> dict:
        return json.loads(self.positions_path.read_text(encoding="utf-8"))

    def test_start_assignment_counts_only_same_specialty_and_people_ahead(self) -> None:
        updater = PositionContextUpdater(self.positions_path, self.state_path)
        updater.apply(
            [
                parsed(
                    "2026-07-15",
                    "secundaria",
                    [
                        assignment("VIZCAINO SANCHIS, GEMMA", "3A1", "03010442", 4),
                        assignment("MARTINEZ MARTINEZ, DAVID", "3A9", "12000001", 2),
                    ],
                )
            ],
            "inicio",
        )
        self.assertTrue(updater.save())

        data = self.load_positions()
        salvador = data["people"][1][2][0][7]
        david_3a1 = data["people"][2][2][0][7]
        self.assertEqual(salvador[:3], [1, 0, 0])
        self.assertEqual(david_3a1[:3], [1, 0, 0])
        self.assertEqual(salvador[3:], [{"old": True}, [1, 2, 3, 4]])

    def test_later_assignment_replaces_the_previous_province(self) -> None:
        updater = PositionContextUpdater(self.positions_path, self.state_path)
        updater.apply(
            [parsed("2026-07-15", "secundaria", [assignment("VIZCAINO SANCHIS, GEMMA", "3A1", "03010442", 4)])],
            "inicio",
        )
        updater.save()

        updater = PositionContextUpdater(self.positions_path, self.state_path)
        updater.apply(
            [parsed("2026-09-08", "secundaria", [assignment("VIZCAINO SANCHIS, GEMMA", "3A1", "46000001", 1)], "2")],
            "curso",
        )
        updater.save()

        data = self.load_positions()
        self.assertEqual(data["people"][1][2][0][7][:3], [0, 1, 0])
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(len(state["assignments"]), 1)

    def test_pdf_from_another_course_is_not_applied(self) -> None:
        updater = PositionContextUpdater(self.positions_path, self.state_path)
        changed = updater.apply(
            [parsed("2027-07-15", "secundaria", [assignment("VIZCAINO SANCHIS, GEMMA", "3A1", "03010442", 4)])],
            "inicio",
        )
        self.assertFalse(changed)
        self.assertFalse(updater.save())
        self.assertFalse(self.state_path.exists())

    def test_an_older_course_pdf_cannot_replace_a_newer_assignment(self) -> None:
        updater = PositionContextUpdater(self.positions_path, self.state_path)
        updater.apply(
            [parsed("2026-07-15", "secundaria", [assignment("VIZCAINO SANCHIS, GEMMA", "3A1", "03010442", 4)])],
            "inicio",
        )
        updater.apply(
            [parsed("2026-10-01", "secundaria", [assignment("VIZCAINO SANCHIS, GEMMA", "3A1", "46000001", 1)], "new")],
            "curso",
        )
        updater.apply(
            [parsed("2026-09-08", "secundaria", [assignment("VIZCAINO SANCHIS, GEMMA", "3A1", "12000001", 2)], "old")],
            "curso",
        )
        updater.save()

        data = self.load_positions()
        self.assertEqual(data["people"][1][2][0][7][:3], [0, 1, 0])

    def test_award_details_are_published_and_a_continuous_award_replaces_them(self) -> None:
        updater = PositionContextUpdater(self.positions_path, self.state_path)
        updater.apply(
            [
                parsed(
                    "2026-07-15",
                    "secundaria",
                    [
                        assignment(
                            "VIZCAINO SANCHIS, GEMMA",
                            "3A1",
                            "03010442",
                            4,
                            workload="C",
                            itinerant=True,
                            center_name="CIPFP Canastell",
                            locality="Sant Vicent del Raspeig",
                            observations="PROA+ fins 30/06/2027",
                        )
                    ],
                )
            ],
            "inicio",
        )
        updater.save()

        data = self.load_positions()
        gemma = data["people"][0][2][0]
        self.assertEqual(gemma[8], "A")
        self.assertEqual(
            gemma[9],
            [
                "I",
                "2026-07-15",
                "vacante",
                "C",
                "03010442",
                False,
                True,
                "CIPFP Canastell",
                "Sant Vicent del Raspeig",
                "PROA+ fins 30/06/2027",
            ],
        )

        updater = PositionContextUpdater(self.positions_path, self.state_path)
        updater.apply(
            [
                parsed(
                    "2026-09-08",
                    "secundaria",
                    [
                        assignment(
                            "VIZCAINO SANCHIS, GEMMA",
                            "3A1",
                            "46000001",
                            1,
                            placement_type="sub_indeterminada",
                            workload=18,
                            center_name="IES de prueba",
                            locality="Valencia",
                        )
                    ],
                    "continuous",
                )
            ],
            "curso",
        )
        updater.save()

        detail = self.load_positions()["people"][0][2][0][9]
        self.assertEqual(detail[:5], ["C", "2026-09-08", "sub_indeterminada", 18, "46000001"])
        self.assertEqual(detail[7:], ["IES de prueba", "Valencia", ""])

    def test_master_fpa_alias_is_attached_to_the_registered_specialty_card(self) -> None:
        updater = PositionContextUpdater(self.positions_path, self.state_path)
        updater.apply(
            [
                parsed(
                    "2026-09-03",
                    "maestros",
                    [assignment("ARCE RAMOS, LUCIA", "152", "46022221", 14, "maestros")],
                )
            ],
            "curso",
        )
        updater.save()

        card = self.load_positions()["people"][3][2][0]
        self.assertEqual(card[8], "A")
        self.assertEqual(card[9][0], "C")
        self.assertEqual(card[9][4], "46022221")

    def test_secondary_specialty_suffix_does_not_break_identity_matching(self) -> None:
        updater = PositionContextUpdater(self.positions_path, self.state_path)
        updater.apply(
            [
                parsed(
                    "2026-09-03",
                    "secundaria",
                    [
                        assignment(
                            "FERNANDEZ CASTILLO, MARIA NIEVES ( Esp: 358 )",
                            "2B9",
                            "46000001",
                            1,
                        )
                    ],
                )
            ],
            "curso",
        )
        updater.save()

        card = self.load_positions()["people"][4][2][0]
        self.assertEqual(card[8], "A")
        self.assertEqual(card[9][4], "46000001")

    def test_continuous_snapshot_updates_positions_statuses_and_new_profiles(self) -> None:
        updater = PositionContextUpdater(self.positions_path, self.state_path)
        updater.apply(
            [
                parsed(
                    "2026-09-03",
                    "secundaria",
                    [
                        assignment("VIZCAINO SANCHIS, GEMMA", "3A1", "03010442", 1),
                        assignment("DURAN GIL, TANIA", "6A2", "03011458", 1),
                    ],
                    statuses=[
                        status("VIZCAINO SANCHIS, GEMMA", "3A1", 1, "A"),
                        status("MARTINEZ GUIJARRO, SALVADOR", "3A1", 2, "D"),
                        status("MARTINEZ MARTINEZ, DAVID", "3A1", 3, "N"),
                        status("DURAN GIL, TANIA", "6A2", 1, "A"),
                    ],
                )
            ],
            "curso",
        )
        updater.save()

        data = self.load_positions()
        self.assertEqual(data["reference_stage"], "adjudicacion_continua")
        self.assertEqual(data["reference_date"], "2026-09-03")
        self.assertEqual(data["people"][0][2][0][3:5], [1, 1])
        self.assertEqual(data["people"][0][2][0][8], "A")
        self.assertEqual(data["people"][1][2][0][3:5], [2, 2])
        self.assertEqual(data["people"][1][2][0][8], "D")
        self.assertEqual(data["people"][2][2][0][3:5], [3, 2])
        self.assertEqual(data["people"][2][2][0][8], "N")
        tania = next(person for person in data["people"] if person[1] == "DURAN GIL, TANIA")
        self.assertEqual(tania[2][0][0], "6A2")
        self.assertEqual(tania[2][0][3], 1)
        self.assertEqual(tania[2][0][8], "A")
        self.assertEqual(tania[2][0][9][:5], ["C", "2026-09-03", "vacante", "C", "03011458"])

    def test_cross_specialty_duplicate_uses_the_non_awarded_row(self) -> None:
        updater = PositionContextUpdater(self.positions_path, self.state_path)
        updater.apply(
            [
                parsed(
                    "2026-09-03",
                    "secundaria",
                    [],
                    statuses=[
                        status("VIZCAINO SANCHIS, GEMMA", "3A1", 1, "A"),
                        status("VIZCAINO SANCHIS, GEMMA", "3A1", 2, "N"),
                    ],
                )
            ],
            "curso",
        )
        updater.save()

        data = self.load_positions()
        self.assertEqual(data["people"][0][2][0][3], 2)
        self.assertEqual(data["people"][0][2][0][8], "N")
        self.assertEqual(
            data["continuous_snapshot"]["secondary_cross_specialty_duplicates_ignored"],
            1,
        )

    def test_legacy_province_state_is_migrated_without_losing_rows(self) -> None:
        legacy_fields = [
            "body",
            "specialty_code",
            "person_index",
            "position_index",
            "after_order",
            "initial_order",
            "center_code",
            "province_index",
            "published_date",
            "mode",
            "placement_type",
            "candidate_name",
            "source_url",
            "source_sha256",
        ]
        legacy_row = [
            "secundaria",
            "3A1",
            0,
            0,
            4,
            6,
            "03010442",
            0,
            "2026-07-15",
            "inicio",
            "vacante",
            "VIZCAINO SANCHIS, GEMMA",
            "https://example.test/start.pdf",
            "sha-start",
        ]
        self.state_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "academic_year": "2026-2027",
                    "assignment_fields": legacy_fields,
                    "assignments": [legacy_row],
                    "sources": [],
                    "skipped": {},
                }
            ),
            encoding="utf-8",
        )

        updater = PositionContextUpdater(self.positions_path, self.state_path)

        self.assertTrue(updater.enabled)
        self.assertEqual(updater.state["schema_version"], 3)
        self.assertEqual(updater.state["assignments"][0][:14], legacy_row)
        self.assertEqual(
            updater.state["assignments"][0][14:],
            [None, None, None, None, None, None],
        )


if __name__ == "__main__":
    unittest.main()
