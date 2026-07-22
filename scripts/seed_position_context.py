from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from position_context import MASTER_SPECIALTY_CODES, PositionContextUpdater, empty_state, normalized_academic_year


def load_cache(path: Path) -> tuple[list[dict], str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("records")
    if not isinstance(records, list) or data.get("issues"):
        raise ValueError(f"Cache de adjudicaciones no valido: {path}")
    return records, str(data.get("sha256") or "")


def parsed_pdf(
    records: list[dict],
    body: str,
    published_date: str,
    url: str,
    sha256: str,
) -> SimpleNamespace:
    expected_master = body == "maestros"
    assignments = []
    for record in records:
        code = str(record.get("specialty_code") or "")
        if (code in MASTER_SPECIALTY_CODES) != expected_master:
            continue
        assignments.append(
            SimpleNamespace(
                cut=int(record["cut"]),
                candidate_name=str(record.get("candidate") or ""),
                center_code=str(record.get("center_code") or ""),
                specialty_code=code,
                body=body,
                placement_type=str(record.get("placement_type") or ""),
            )
        )
    return SimpleNamespace(
        url=url,
        sha256=sha256,
        body=body,
        published_date=published_date,
        assignments=assignments,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--positions", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--masters-cache", type=Path, required=True)
    parser.add_argument("--secondary-cache", type=Path, required=True)
    parser.add_argument("--date", required=True, help="Fecha oficial en formato AAAA-MM-DD")
    parser.add_argument("--masters-url", default="")
    parser.add_argument("--secondary-url", default="")
    args = parser.parse_args()

    positions = json.loads(args.positions.read_text(encoding="utf-8"))
    academic_year = normalized_academic_year(positions.get("academic_year"))
    if academic_year is None:
        raise ValueError("El JSON de posiciones no tiene un curso academico valido")

    master_records, master_sha = load_cache(args.masters_cache)
    secondary_records, secondary_sha = load_cache(args.secondary_cache)

    updater = PositionContextUpdater(args.positions, args.state)
    if not updater.enabled:
        raise RuntimeError("No se pudo inicializar el actualizador provincial")
    updater.state = empty_state(academic_year)
    updater.apply(
        [
            parsed_pdf(
                master_records,
                "maestros",
                args.date,
                args.masters_url,
                master_sha,
            ),
            parsed_pdf(
                secondary_records,
                "secundaria",
                args.date,
                args.secondary_url,
                secondary_sha,
            ),
        ],
        "inicio",
    )
    if not updater.save():
        raise RuntimeError("No se genero el estado provincial")
    print(
        f"Estado provincial creado: {len(updater.state['assignments'])} adjudicaciones "
        f"para {academic_year}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
