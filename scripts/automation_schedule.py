from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


MADRID = ZoneInfo("Europe/Madrid")
ALL_MODES = ("inicio", "curso", "posiciones", "acreditaciones")
START_HOURS = frozenset({9, 12, 15, 18, 21})
POSITION_HOURS = frozenset({9, 11, 13, 15, 17, 19})
ACCREDITATION_HOURS = frozenset({12, 14, 16, 18, 20})


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

    return tuple(modes)


def selected_modes(force: str, value: datetime) -> tuple[str, ...]:
    if force == "all":
        return ALL_MODES
    if force in ALL_MODES:
        return (force,)
    return scheduled_modes(value)


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
    parser.add_argument("--github-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(MADRID)
    if now.tzinfo is None:
        now = now.replace(tzinfo=MADRID)
    modes = explicit_modes(args.modes) if args.modes else selected_modes(args.force, now)
    output_path = args.github_output
    if output_path is None and os.environ.get("GITHUB_OUTPUT"):
        output_path = Path(os.environ["GITHUB_OUTPUT"])
    if output_path:
        write_github_output(output_path, modes)
    print(",".join(modes) if modes else "sin_comprobacion")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
