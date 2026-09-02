from __future__ import annotations

import gzip
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path, *, compressed: bool = False) -> dict:
    opener = gzip.open if compressed else path.open
    if compressed:
        with opener(path, "rt", encoding="utf-8") as source:
            payload = json.load(source)
    else:
        with opener("r", encoding="utf-8") as source:
            payload = json.load(source)
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name}: la raiz debe ser un objeto JSON")
    return payload


def require_keys(name: str, payload: dict, keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise ValueError(f"{name}: faltan campos obligatorios: {', '.join(missing)}")


def validate_rows(name: str, rows: object, fields: object) -> int:
    if not isinstance(rows, list) or not isinstance(fields, list) or not fields:
        raise ValueError(f"{name}: filas o formato no validos")
    width = len(fields)
    invalid = next(
        (index for index, row in enumerate(rows) if not isinstance(row, list) or len(row) != width),
        None,
    )
    if invalid is not None:
        raise ValueError(f"{name}: fila {invalid} incompatible con su formato")
    return len(rows)


def validate_repository(root: Path = ROOT) -> dict[str, int]:
    data = root / "data"
    cuts = load_json(data / "adjudicaciones.json")
    positions = load_json(data / "posiciones_bolsa.json")
    context = load_json(data / "position_context_state.json")
    offers = load_json(data / "puestos_ofertados.json")
    monitor = load_json(data / "source_monitor_state.json")
    accreditations = load_json(
        data / "english_accreditations.json.gz", compressed=True
    )

    require_keys("adjudicaciones", cuts, ("schema_version", "centers", "cuts"))
    require_keys("posiciones", positions, ("schema_version", "people", "person_fields"))
    require_keys("contexto", context, ("schema_version", "assignments", "assignment_fields"))
    require_keys("puestos", offers, ("schema_version", "items", "item_fields"))
    require_keys("vigilancia", monitor, ("schema_version", "checks"))
    require_keys("acreditaciones", accreditations, ("schema_version", "records"))

    counts = {
        "centros": validate_rows(
            "adjudicaciones.centers", cuts["centers"], cuts.get("center_format")
        ),
        "cortes_inicio": validate_rows(
            "adjudicaciones.cuts.inicio",
            cuts["cuts"]["inicio"]["rows"],
            cuts.get("cut_format"),
        ),
        "cortes_curso": validate_rows(
            "adjudicaciones.cuts.curso",
            cuts["cuts"]["curso"]["rows"],
            cuts.get("cut_format"),
        ),
        "personas": validate_rows(
            "posiciones.people", positions["people"], positions["person_fields"]
        ),
        "adjudicaciones_contexto": validate_rows(
            "contexto.assignments", context["assignments"], context["assignment_fields"]
        ),
        "puestos": validate_rows(
            "puestos.items", offers["items"], offers["item_fields"]
        ),
    }

    records = accreditations["records"]
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError("acreditaciones.records: se esperaba una lista de objetos")
    counts["acreditaciones"] = len(records)
    return counts


def main() -> int:
    counts = validate_repository()
    summary = ", ".join(f"{name}={count}" for name, count in counts.items())
    print(f"Datos listos para publicar: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
