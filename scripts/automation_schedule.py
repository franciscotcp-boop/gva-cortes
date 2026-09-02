from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


MADRID = ZoneInfo("Europe/Madrid")
ALL_MODES = (
    "inicio",
    "curso",
    "posiciones",
    "acreditaciones",
    "puestos",
    "dificil",
    "limpieza_puestos",
)
START_HOURS = frozenset({9, 12, 15, 18, 21})
POSITION_HOURS = frozenset({9, 11, 13, 15, 17, 19})
ACCREDITATION_HOURS = frozenset({12, 14, 16, 18, 20})
OFFER_HOURS = frozenset({9, 11, 13, 15, 17, 19, 20})
DIFFICULT_HOURS = frozenset({9, 11, 13, 15, 17, 19, 21, 23})
BROAD_SCHEDULE = "20 7-23 * * *"
OFFER_CEST_SCHEDULE = "7 7,9,11,13,15,17,18 * 1-7,9-12 1,3"
OFFER_CET_SCHEDULE = "8 8,10,12,14,16,18,19 * 1-7,9-12 1,3"


def scheduled_modes(value: datetime) -> tuple[str, ...]:
    """Return the checks due at this exact Madrid local hour."""

    current = value.astimezone(MADRID)
    month = current.month
    weekday = current.isoweekday()
    hour = current.hour
    modes: list[str] = []

    # Inicio de curso: julio y agosto, de lunes a sabado.
    if month in {7, 8} and weekday != 7 and hour in START_HOURS:
        modes.append("inicio")

    # Adjudicaciones continuas: martes y jueves, de septiembre a junio.
    if month not in {7, 8} and weekday in {2, 4} and hour in START_HOURS:
        modes.append("curso")

    # Listas de participantes: todos los dias de junio y julio.
    if month in {6, 7} and hour in POSITION_HOURS:
        modes.append("posiciones")

    # Acreditaciones: viernes, de septiembre a julio. Agosto queda excluido.
    if month != 8 and weekday == 5 and hour in ACCREDITATION_HOURS:
        modes.append("acreditaciones")

    # Puestos ofertados: lunes y miercoles, de septiembre al 1 de julio.
    offers_in_season = month in {9, 10, 11, 12, 1, 2, 3, 4, 5, 6} or (
        month == 7 and current.day == 1
    )
    if offers_in_season and weekday in {1, 3} and hour in OFFER_HOURS:
        modes.append("puestos")

    # Difícil cobertura: viernes de septiembre a junio, hasta las 23:20.
    if month not in {7, 8} and weekday == 5 and hour in DIFFICULT_HOURS:
        modes.append("dificil")

    # Las ofertas de difícil cobertura caducan al terminar el viernes.
    if month not in {7, 8} and weekday == 6 and hour == 0:
        modes.append("limpieza_puestos")

    return tuple(modes)


def scheduled_event_modes(
    value: datetime, schedule_expression: str = ""
) -> tuple[str, ...]:
    """Resolve a cron event without depending on GitHub's actual start hour."""

    expression = schedule_expression.strip()
    if expression in {OFFER_CEST_SCHEDULE, OFFER_CET_SCHEDULE}:
        current = value.astimezone(MADRID)
        expected_offset_hours = 2 if expression == OFFER_CEST_SCHEDULE else 1
        offset = current.utcoffset()
        offset_hours = int(offset.total_seconds() // 3600) if offset else 0
        month = current.month
        offers_in_season = month in {9, 10, 11, 12, 1, 2, 3, 4, 5, 6} or (
            month == 7 and current.day == 1
        )
        if (
            offset_hours == expected_offset_hours
            and offers_in_season
            and current.isoweekday() in {1, 3}
        ):
            return ("puestos",)
        return ()

    modes = scheduled_modes(value)
    if expression == BROAD_SCHEDULE:
        return tuple(mode for mode in modes if mode != "puestos")
    return modes


def selected_modes(
    force: str, value: datetime, schedule_expression: str = ""
) -> tuple[str, ...]:
    if force == "all":
        return ALL_MODES
    if force in ALL_MODES:
        return (force,)
    return scheduled_event_modes(value, schedule_expression)


def explicit_modes(value: str) -> tuple[str, ...]:
    requested = tuple(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))
    invalid = [mode for mode in requested if mode not in ALL_MODES]
    if invalid:
        raise ValueError(f"Modos de recuperacion no validos: {', '.join(invalid)}")
    return tuple(mode for mode in ALL_MODES if mode in requested)


def write_github_output(path: Path, modes: tuple[str, ...]) -> None:
    selected = set(modes)
    lines = [
        f"run={'true' if modes else 'false'}",
        f"modes={','.join(modes)}",
    ]
    lines.extend(
        f"{mode}={'true' if mode in selected else 'false'}" for mode in ALL_MODES
    )
    with path.open("a", encoding="utf-8") as output:
        output.write("\n".join(lines) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        choices=("auto",) + ALL_MODES + ("all",),
        default="auto",
    )
    parser.add_argument(
        "--now",
        help="Instante ISO opcional para pruebas; por defecto usa la hora actual.",
    )
    parser.add_argument(
        "--modes",
        default="",
        help="Lista interna separada por comas usada por el vigilante al recuperar una ejecucion.",
    )
    parser.add_argument(
        "--schedule-expression",
        default="",
        help="Expresion cron que origino la ejecucion programada.",
    )
    parser.add_argument("--github-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(MADRID)
    if now.tzinfo is None:
        now = now.replace(tzinfo=MADRID)
    modes = (
        explicit_modes(args.modes)
        if args.modes
        else selected_modes(args.force, now, args.schedule_expression)
    )
    output_path = args.github_output
    if output_path is None and os.environ.get("GITHUB_OUTPUT"):
        output_path = Path(os.environ["GITHUB_OUTPUT"])
    if output_path:
        write_github_output(output_path, modes)
    print(",".join(modes) if modes else "sin_comprobacion")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
