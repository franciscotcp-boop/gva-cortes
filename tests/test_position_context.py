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


def assignment(name: str, code: str, center: str, cut: int, body: str = "secundaria") -> SimpleNamespace:
    return SimpleNamespace(
        candidate_name=name,
        specialty_code=code,
        center_code=center,
        cut=cut,
        body=body,
        placement_type="vacante",
    )


def parsed(date: str, body: str, assignments: list[SimpleNamespace], suffix: str = "1") -> SimpleNamespace:
    return SimpleNamespace(
        published_date=date,
        body=body,
        assignments=assignments,
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


if __name__ == "__main__":
    unittest.main()
