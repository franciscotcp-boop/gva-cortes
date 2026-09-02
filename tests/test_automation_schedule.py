from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from automation_schedule import (
    ACCREDITATION_CEST_SCHEDULE,
    ACCREDITATION_CET_SCHEDULE,
    ALL_MODES,
    BROAD_SCHEDULE,
    CLEANUP_CEST_SCHEDULE,
    CLEANUP_CET_SCHEDULE,
    COURSE_CEST_SCHEDULE,
    COURSE_CET_SCHEDULE,
    DIFFICULT_CEST_SCHEDULE,
    DIFFICULT_CET_SCHEDULE,
    MADRID,
    OFFER_CEST_SCHEDULE,
    OFFER_CET_SCHEDULE,
    POSITION_CEST_SCHEDULE,
    START_CEST_SCHEDULE,
    explicit_modes,
    scheduled_event_modes,
    scheduled_modes,
    selected_modes,
)


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

    def test_offered_positions_include_a_closing_check_at_20(self) -> None:
        self.assertEqual(
            scheduled_modes(local("2026-09-02T20:00:00")),
            ("puestos",),
        )

    def test_dedicated_offer_schedule_survives_a_delayed_start(self) -> None:
        self.assertEqual(
            scheduled_event_modes(
                local("2026-09-02T18:34:00"), OFFER_CEST_SCHEDULE
            ),
            ("puestos",),
        )
        self.assertNotIn(
            "puestos",
            scheduled_event_modes(
                local("2026-09-02T19:20:00"), BROAD_SCHEDULE
            ),
        )

    def test_every_source_schedule_survives_a_delayed_start(self) -> None:
        delayed_summer = local("2026-07-21T10:47:00")
        delayed_winter = local("2026-12-03T10:47:00")
        delayed_autumn = local("2026-09-04T13:47:00")
        delayed_cleanup = local("2026-09-05T02:10:00")

        self.assertEqual(
            scheduled_event_modes(delayed_summer, START_CEST_SCHEDULE),
            ("inicio",),
        )
        self.assertEqual(
            scheduled_event_modes(delayed_summer, POSITION_CEST_SCHEDULE),
            ("posiciones",),
        )
        self.assertEqual(
            scheduled_event_modes(delayed_winter, COURSE_CET_SCHEDULE),
            ("curso",),
        )
        self.assertEqual(
            scheduled_event_modes(delayed_autumn, ACCREDITATION_CEST_SCHEDULE),
            ("acreditaciones",),
        )
        self.assertEqual(
            scheduled_event_modes(delayed_autumn, DIFFICULT_CEST_SCHEDULE),
            ("dificil",),
        )
        self.assertEqual(
            scheduled_event_modes(delayed_cleanup, CLEANUP_CEST_SCHEDULE),
            ("limpieza_puestos",),
        )

    def test_course_schedule_covers_tomorrow_and_both_time_zones(self) -> None:
        self.assertEqual(
            scheduled_event_modes(
                local("2026-09-03T10:58:00"), COURSE_CEST_SCHEDULE
            ),
            ("curso",),
        )
        self.assertEqual(
            scheduled_event_modes(
                local("2026-12-03T10:58:00"), COURSE_CET_SCHEDULE
            ),
            ("curso",),
        )
        self.assertEqual(
            scheduled_event_modes(
                local("2026-12-03T10:58:00"), COURSE_CEST_SCHEDULE
            ),
            (),
        )

    def test_all_cet_variants_are_selected_in_winter(self) -> None:
        winter = local("2026-12-04T16:45:00")
        self.assertEqual(
            scheduled_event_modes(winter, ACCREDITATION_CET_SCHEDULE),
            ("acreditaciones",),
        )
        self.assertEqual(
            scheduled_event_modes(winter, DIFFICULT_CET_SCHEDULE),
            ("dificil",),
        )
        self.assertEqual(
            scheduled_event_modes(
                local("2026-12-05T01:45:00"), CLEANUP_CET_SCHEDULE
            ),
            ("limpieza_puestos",),
        )

    def test_dedicated_offer_schedule_respects_madrid_dst(self) -> None:
        self.assertEqual(
            scheduled_event_modes(
                local("2026-12-02T20:45:00"), OFFER_CET_SCHEDULE
            ),
            ("puestos",),
        )
        self.assertEqual(
            scheduled_event_modes(
                local("2026-12-02T20:45:00"), OFFER_CEST_SCHEDULE
            ),
            (),
        )

    def test_offered_positions_include_only_the_first_day_of_july(self) -> None:
        self.assertEqual(
            scheduled_modes(local("2026-07-01T09:00:00")),
            ("inicio", "posiciones", "puestos"),
        )
        self.assertNotIn("puestos", scheduled_modes(local("2026-07-08T09:00:00")))

    def test_difficult_coverage_runs_friday_until_2320(self) -> None:
        self.assertEqual(
            scheduled_modes(local("2026-09-04T23:20:00")),
            ("dificil",),
        )
        self.assertNotIn(
            "dificil", scheduled_modes(local("2026-09-05T23:20:00"))
        )
        self.assertNotIn(
            "dificil", scheduled_modes(local("2027-07-02T11:20:00"))
        )

    def test_difficult_coverage_is_cleaned_at_the_start_of_saturday(self) -> None:
        self.assertEqual(
            scheduled_modes(local("2026-09-05T00:20:00")),
            ("limpieza_puestos",),
        )

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
