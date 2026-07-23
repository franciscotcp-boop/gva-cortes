from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from automation_schedule import ALL_MODES, MADRID, explicit_modes, scheduled_modes, selected_modes


def local(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=MADRID)


class AutomationScheduleTests(unittest.TestCase):
    def test_july_monday_combines_start_and_positions(self) -> None:
        self.assertEqual(
            scheduled_modes(local("2026-07-20T09:00:00")),
            ("inicio", "posiciones"),
        )
        self.assertEqual(
            scheduled_modes(local("2026-07-20T11:00:00")),
            ("posiciones",),
        )

    def test_start_check_skips_sunday_but_positions_does_not(self) -> None:
        self.assertEqual(
            scheduled_modes(local("2026-07-19T09:00:00")),
            ("posiciones",),
        )

    def test_continuous_checks_run_only_tuesday_and_thursday(self) -> None:
        self.assertEqual(
            scheduled_modes(local("2026-09-08T12:00:00")),
            ("curso",),
        )
        self.assertEqual(scheduled_modes(local("2026-09-09T12:00:00")), ())

    def test_accreditations_run_on_friday_but_never_in_august(self) -> None:
        self.assertEqual(
            scheduled_modes(local("2026-09-04T14:00:00")),
            ("acreditaciones",),
        )
        self.assertEqual(scheduled_modes(local("2026-08-07T14:00:00")), ())

    def test_june_overlap_is_expected(self) -> None:
        self.assertEqual(
            scheduled_modes(local("2027-06-03T15:00:00")),
            ("curso", "posiciones"),
        )

    def test_offered_positions_run_monday_and_wednesday_in_the_season(self) -> None:
        self.assertEqual(
            scheduled_modes(local("2026-09-02T11:00:00")),
            ("puestos",),
        )
        self.assertNotIn("puestos", scheduled_modes(local("2026-09-03T11:00:00")))

    def test_offered_positions_include_only_the_first_day_of_july(self) -> None:
        self.assertEqual(
            scheduled_modes(local("2026-07-01T09:00:00")),
            ("inicio", "posiciones", "puestos"),
        )
        self.assertNotIn("puestos", scheduled_modes(local("2026-07-08T09:00:00")))

    def test_force_modes_are_independent_from_calendar(self) -> None:
        moment = local("2026-08-02T03:00:00")
        self.assertEqual(selected_modes("all", moment), ALL_MODES)
        self.assertEqual(selected_modes("acreditaciones", moment), ("acreditaciones",))
        self.assertEqual(selected_modes("puestos", moment), ("puestos",))

    def test_recovery_modes_are_validated_and_keep_canonical_order(self) -> None:
        self.assertEqual(
            explicit_modes("posiciones,inicio,posiciones"),
            ("inicio", "posiciones"),
        )
        with self.assertRaises(ValueError):
            explicit_modes("inicio,desconocido")


if __name__ == "__main__":
    unittest.main()
