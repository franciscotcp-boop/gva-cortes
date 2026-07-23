from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

import pdfplumber

from build_bolsa_dataset import (
    FPA_PRIMARY,
    MASTER_FLAGS,
    MASTER_SPECIALTIES,
    build_specialties,
    clean_official_name,
    display_name,
    identity_key,
    normalize_name,
    parse_masters,
    parse_specialty_map,
    semantic_lines,
    sha256,
)


LAST_AWARDED_FIELDS = [
    "specialty_code",
    "body",
    "position",
    "placement_type",
    "display_name",
    "official_name",
    "last_vacancy_position",
    "last_vacancy_display_name",
    "last_vacancy_official_name",
    "source_stage",
    "source_date",
]

VALID_PLACEMENT_TYPES = {"vacante", "sub_indeterminada", "sub_determinada"}


def parse_secondary_with_disabled_habilitations(
    pdf_path: Path,
) -> tuple[list[dict], dict[str, str], list[str], int]:
    rows: list[dict] = []
    specialties: dict[str, str] = {}
    errors: list[str] = []
    last_position: dict[str, int] = {}
    disabled_count = 0

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            lines = semantic_lines(page)
            headers: list[tuple[float, str]] = []
            for top, line in lines:
                match = re.match(r"^\(([0-9A-Z]{3})\)\s*(.+)$", line)
                if not match:
                    continue
                code = match.group(1)
                name = re.sub(r"\s+", " ", match.group(2)).strip()
                specialties.setdefault(code, name)
                if specialties[code] != name:
                    errors.append(
                        f"Secundaria: nombre incoherente para {code}: "
                        f"{specialties[code]!r} / {name!r}"
                    )
                headers.append((top, code))
            if not headers:
                errors.append(f"Secundaria página {page_number}: sin encabezado de especialidad")
                continue
            current_code = headers[-1][1]
            page_rows = 0
            for _, line in lines:
                match = re.match(r"^(\d+)(.+?)(?:AMB|SENSE)\s*SERVEIS(.*)$", line)
                if not match:
                    continue
                position = int(match.group(1))
                official = clean_official_name(match.group(2))
                expected = last_position.get(current_code, 0) + 1
                if position != expected:
                    errors.append(
                        f"Secundaria {current_code}, página {page_number}: esperado "
                        f"{expected}, encontrado {position} ({official})"
                    )
                last_position[current_code] = position
                disabled_habilitation = "(*)" in match.group(3)
                disabled_count += int(disabled_habilitation)
                rows.append(
                    {
                        "official_name": official,
                        "display_name": display_name(official),
                        "specialty_code": current_code,
                        "position": position,
                        "disabled_habilitation": disabled_habilitation,
                        "page": page_number,
                    }
                )
                page_rows += 1
            if page_rows == 0:
                errors.append(f"Secundaria página {page_number}: no se extrajo ninguna fila")

    return rows, specialties, errors, disabled_count


def known_name_lines(
    lines: list[tuple[float, str]], known_names: set[str]
) -> list[tuple[float, str, str]]:
    found: list[tuple[float, str, str]] = []
    for top, line in lines:
        if "," not in line:
            continue
        official = clean_official_name(
            re.sub(r"\s*\(\s*Esp:\s*\d+\s*\)\s*$", "", line)
        )
        key = identity_key(official)
        looks_like_name = bool(
            re.fullmatch(r"[A-ZÀ-ÖØ-ÞÑÇªº' .-]+,\s*[A-ZÀ-ÖØ-ÞÑÇªº' .-]+", official)
        )
        if key in known_names or (top >= 115 and looks_like_name):
            found.append((top, official, key))
    return found


def remove_specialty_header_records(
    records: list[dict], errors: list[str], specialty_names: dict[str, str]
) -> tuple[list[dict], list[str], int]:
    cleaned: list[dict] = []
    removed_names: set[str] = set()
    for record in records:
        code = str(record.get("specialty_code") or "")
        specialty_name = specialty_names.get(code)
        if specialty_name and identity_key(record["official_name"]) == identity_key(
            specialty_name
        ):
            removed_names.add(record["official_name"])
            continue
        cleaned.append(record)
    cleaned_errors = [
        error
        for error in errors
        if not any(name in error for name in removed_names)
    ]
    return cleaned, cleaned_errors, len(records) - len(cleaned)


def rank_in_block(block: list[tuple[float, str]], name_top: float) -> int | None:
    for top, line in block:
        if top < name_top - 0.5 or top > name_top + 4:
            continue
        match = re.fullmatch(r"(\d+)(?:/\d+)?", line.strip())
        if match:
            return int(match.group(1))
    return None


def parse_adjudication_statuses(
    pdf_path: Path,
    known_names: set[str],
    specialty_codes: set[str] | None = None,
) -> tuple[list[dict], list[str], int]:
    records: list[dict] = []
    errors: list[str] = []
    pages = 0

    with pdfplumber.open(pdf_path) as pdf:
        pages = len(pdf.pages)
        for page_number, page in enumerate(pdf.pages, 1):
            lines = semantic_lines(page)
            specialty_code: str | None = None
            if specialty_codes is not None:
                body_headers = [
                    line.strip()
                    for top, line in lines
                    if 80 <= top <= 95 and line.strip()
                ]
                if not body_headers:
                    # The last two pages are a body-less appendix that repeats
                    # assignments already present in the main sections.
                    continue
                header_codes = [
                    line.strip()
                    for top, line in lines
                    if top <= 112 and line.strip() in specialty_codes
                ]
                if not header_codes:
                    errors.append(
                        f"Adjudicación secundaria página {page_number}: sin código de especialidad"
                    )
                    continue
                specialty_code = header_codes[-1]

            people = known_name_lines(lines, known_names)
            if not people:
                errors.append(f"Adjudicación página {page_number}: sin filas reconocidas")
                continue
            for index, (top, official, key) in enumerate(people):
                next_top = people[index + 1][0] if index + 1 < len(people) else 10_000
                block = [(line_top, line) for line_top, line in lines if top <= line_top < next_top]
                rank = rank_in_block(block, top)
                if rank is None:
                    errors.append(
                        f"Adjudicación página {page_number}: sin posición para {official}"
                    )
                records.append(
                    {
                        "official_name": official,
                        "identity": key,
                        "specialty_code": specialty_code,
                        "printed_position": rank,
                        "deactivated": any("Desactivat" in line for _, line in block),
                        "page": page_number,
                    }
                )

    return records, errors, pages


def attach_master_statuses(master_rows: list[dict], records: list[dict]) -> tuple[int, list[str]]:
    candidates: dict[str, deque[int]] = defaultdict(deque)
    for index, row in enumerate(master_rows):
        candidates[identity_key(row["official_name"])].append(index)

    matched = 0
    errors: list[str] = []
    for record in records:
        queue = candidates.get(record["identity"])
        if not queue:
            errors.append(
                f"Maestros: no se encontró en el listado {record['official_name']} "
                f"(adjudicación página {record['page']})"
            )
            continue
        index = queue.popleft()
        row = master_rows[index]
        record["row_index"] = index
        row["adjudication_status_matched"] = True
        row["adjudication_deactivated"] = record["deactivated"]
        row["adjudication_position"] = record["printed_position"]
        matched += 1
    return matched, errors


def attach_secondary_statuses(
    secondary_rows: list[dict], records: list[dict]
) -> tuple[int, list[str]]:
    by_key: dict[tuple[str, str], deque[int]] = defaultdict(deque)
    for index, row in enumerate(secondary_rows):
        by_key[(row["specialty_code"], identity_key(row["official_name"]))].append(index)

    matched = 0
    matched_keys: set[tuple[str, str]] = set()
    unresolved: list[dict] = []
    errors: list[str] = []
    for record in records:
        code = str(record["specialty_code"] or "")
        record_key = (code, record["identity"])
        queue = by_key.get(record_key)
        if not queue:
            if record_key in matched_keys:
                # The final appendix repeats a small number of assignments already
                # listed in their body's main section.
                record["duplicate"] = True
                continue
            unresolved.append(record)
            continue
        index = queue.popleft()
        row = secondary_rows[index]
        record["row_index"] = index
        row["adjudication_status_matched"] = True
        row["adjudication_deactivated"] = record["deactivated"]
        row["adjudication_position"] = record["printed_position"]
        matched_keys.add(record_key)
        matched += 1

    def alias_score(left: str, right: str) -> float:
        left_key = identity_key(left)
        right_key = identity_key(right)
        if left_key.replace(" ", "") == right_key.replace(" ", ""):
            return 1.0
        if sorted(left_key.split()) == sorted(right_key.split()):
            return 1.0
        return SequenceMatcher(None, left_key, right_key).ratio()

    for record in unresolved:
        code = str(record["specialty_code"] or "")
        candidates: list[tuple[float, int, tuple[str, str]]] = []
        for candidate_key, queue in by_key.items():
            if candidate_key[0] != code:
                continue
            for index in queue:
                score = alias_score(
                    record["official_name"], secondary_rows[index]["official_name"]
                )
                candidates.append((score, index, candidate_key))
        candidates.sort(reverse=True)
        best_score = candidates[0][0] if candidates else 0.0
        second_score = candidates[1][0] if len(candidates) > 1 else 0.0
        if best_score >= 0.92 and best_score - second_score >= 0.05:
            _, index, candidate_key = candidates[0]
            by_key[candidate_key].remove(index)
            row = secondary_rows[index]
            record["row_index"] = index
            record["identity_alias_match"] = row["official_name"]
            record["identity_alias_score"] = round(best_score, 6)
            row["adjudication_status_matched"] = True
            row["adjudication_deactivated"] = record["deactivated"]
            row["adjudication_position"] = record["printed_position"]
            matched_keys.add((code, identity_key(row["official_name"])))
            matched += 1
            continue

        # A genuinely new candidate still affects every later position.
        record["unmatched_new_candidate"] = True
    return matched, errors


def build_last_awarded_by_specialty(
    cuts_path: Path,
    master_statuses: list[dict],
    secondary_statuses: list[dict],
    masters_adjudication_sha256: str,
    secondary_adjudication_sha256: str,
) -> tuple[dict, list[str]]:
    """Build the latest award and latest vacancy for every specialty.

    The cuts JSON already owns the audited adjudication parser. Its policy v5
    requires the secondary page header and the awarded-position specialty to
    match. Taking the largest cut across center maxima therefore yields the
    last valid award for each specialty without reintroducing compatible-body
    duplicates.
    """

    data = json.loads(cuts_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if int(data.get("schema_version", 0)) < 3:
        errors.append("El JSON de cortes no tiene un esquema compatible")
    if int(data.get("cut_policy", {}).get("version", 0)) < 5:
        errors.append(
            "El JSON de cortes no aplica la coincidencia entre encabezado y "
            "especialidad adjudicada"
        )

    start = data.get("cuts", {}).get("inicio", {})
    pdfs = start.get("pdfs", {})
    expected_hashes = {
        "maestros": masters_adjudication_sha256,
        "secundaria": secondary_adjudication_sha256,
    }
    for body, expected_sha in expected_hashes.items():
        actual_sha = str(pdfs.get(body, {}).get("sha256") or "")
        if actual_sha != expected_sha:
            errors.append(
                f"El PDF de {body} del JSON de cortes no coincide con el PDF "
                "usado para las posiciones"
            )

    format_names = [str(value) for value in data.get("cut_format", [])]
    required = {
        "codigoEspecialidad",
        "numeroCorte",
        "cuerpo",
        "tipoPlaza",
    }
    if not required.issubset(format_names):
        errors.append("El formato del JSON de cortes no contiene los campos requeridos")
        return {
            "fields": LAST_AWARDED_FIELDS,
            "rows": [],
            "source_stage": "inicio_curso",
            "source_date": start.get("updated_at"),
        }, errors
    field = {name: format_names.index(name) for name in required}

    best: dict[tuple[str, str], list] = {}
    best_vacancy: dict[tuple[str, str], list] = {}
    for row in start.get("rows", []):
        if not isinstance(row, list):
            continue
        body = str(row[field["cuerpo"]] or "")
        code = str(row[field["codigoEspecialidad"]] or "")
        placement = str(row[field["tipoPlaza"]] or "")
        try:
            position = int(row[field["numeroCorte"]])
        except (TypeError, ValueError):
            continue
        if body not in {"maestros", "secundaria"} or not code or position < 1:
            continue
        if placement not in VALID_PLACEMENT_TYPES:
            errors.append(
                f"Tipo de plaza no reconocido para {body} {code} posición {position}: "
                f"{placement!r}"
            )
            continue
        key = (body, code)
        if key not in best or position > int(best[key][field["numeroCorte"]]):
            best[key] = row
        if placement == "vacante" and (
            key not in best_vacancy
            or position > int(best_vacancy[key][field["numeroCorte"]])
        ):
            best_vacancy[key] = row

    master_names: dict[int, str] = {}
    for record in master_statuses:
        position = record.get("printed_position")
        if position is None:
            continue
        position = int(position)
        official = str(record.get("official_name") or "")
        old = master_names.get(position)
        if old and identity_key(old) != identity_key(official):
            errors.append(f"Posición general de maestros duplicada: {position}")
        master_names[position] = official

    secondary_names: dict[tuple[str, int], str] = {}
    for record in secondary_statuses:
        code = str(record.get("specialty_code") or "")
        position = record.get("printed_position")
        if not code or position is None or record.get("duplicate"):
            continue
        key = (code, int(position))
        official = str(record.get("official_name") or "")
        old = secondary_names.get(key)
        if old and identity_key(old) != identity_key(official):
            errors.append(f"Posición de secundaria duplicada: {code} {position}")
        secondary_names[key] = official

    def official_name(body: str, code: str, position: int) -> str:
        if body == "maestros":
            return master_names.get(position, "")
        return secondary_names.get((code, position), "")

    source_date = str(start.get("updated_at") or "")
    rows: list[list] = []
    for body, code in sorted(best, key=lambda item: (item[0], item[1])):
        row = best[(body, code)]
        position = int(row[field["numeroCorte"]])
        placement = str(row[field["tipoPlaza"]])
        official = official_name(body, code, position)
        if not official:
            errors.append(
                f"No se encontró el nombre del último adjudicado: {body} {code} {position}"
            )

        vacancy_row = best_vacancy.get((body, code))
        vacancy_position = (
            int(vacancy_row[field["numeroCorte"]]) if vacancy_row is not None else None
        )
        vacancy_official = (
            official_name(body, code, vacancy_position)
            if vacancy_position is not None
            else ""
        )
        if vacancy_position is not None and not vacancy_official:
            errors.append(
                f"No se encontró el nombre de la última vacante: "
                f"{body} {code} {vacancy_position}"
            )

        rows.append(
            [
                code,
                "maestros" if body == "maestros" else "otros",
                position,
                placement,
                display_name(official) if official else "",
                official,
                vacancy_position,
                display_name(vacancy_official) if vacancy_official else "",
                vacancy_official,
                "inicio_curso",
                source_date,
            ]
        )

    return {
        "fields": LAST_AWARDED_FIELDS,
        "rows": rows,
        "source_stage": "inicio_curso",
        "source_date": source_date,
        "secondary_rule": (
            "Sólo cuenta una fila cuando la especialidad del encabezado coincide "
            "con la especialidad de la plaza adjudicada junto al docente"
        ),
        "masters_rule": (
            "Se selecciona por especialidad la mayor posición general impresa "
            "entre las personas adjudicadas"
        ),
    }, errors


def calculate_master_positions(
    master_rows: list[dict], records: list[dict]
) -> tuple[
    dict[str, int],
    dict[str, int],
    dict[str, int],
    dict[str, int],
    list[str],
]:
    errors: list[str] = []
    post_counts: Counter[str] = Counter()
    post_active_counts: Counter[str] = Counter()
    matched_rows = sorted(
        (
            row
            for row in master_rows
            if row.get("adjudication_position") is not None
        ),
        key=lambda row: row["adjudication_position"],
    )
    printed_positions = [row["adjudication_position"] for row in matched_rows]
    if printed_positions != list(range(1, len(printed_positions) + 1)):
        errors.append(
            "Maestros: las posiciones generales posteriores a la adjudicacion "
            "no forman una secuencia completa"
        )

    for row in matched_rows:
        row_post_positions: dict[str, int] = {}
        row_post_without_deactivated: dict[str, int] = {}
        disabled = bool(row.get("adjudication_deactivated"))
        for code, _ in row["positions"]:
            post_counts[code] += 1
            row_post_positions[code] = post_counts[code]
            row_post_without_deactivated[code] = post_active_counts[code] + 1
            if not disabled:
                post_active_counts[code] += 1
        row["post_adjudication_positions"] = row_post_positions
        row["post_without_deactivated_positions"] = row_post_without_deactivated

    general_counts: Counter[str] = Counter()
    active_counts: Counter[str] = Counter()
    for row in master_rows:
        disabled = bool(row.get("adjudication_deactivated"))
        enhanced: list[tuple[str, int, int, int | None, int | None]] = []
        post_positions = row.get("post_adjudication_positions", {})
        post_without_deactivated = row.get(
            "post_without_deactivated_positions", {}
        )
        for code, general_position in row["positions"]:
            initial_without_deactivated = active_counts[code] + 1
            current_without_deactivated = post_without_deactivated.get(code)
            without_deactivated = (
                current_without_deactivated
                if current_without_deactivated is not None
                else initial_without_deactivated
            )
            enhanced.append(
                (
                    code,
                    general_position,
                    without_deactivated,
                    post_positions.get(code),
                    current_without_deactivated,
                )
            )
            general_counts[code] += 1
            if not disabled:
                active_counts[code] += 1
        row["enhanced_positions"] = enhanced
        row["master_general_positions"] = (
            row["global_position"],
            row.get("adjudication_position"),
        )
    return (
        dict(general_counts),
        dict(active_counts),
        dict(post_counts),
        dict(post_active_counts),
        errors,
    )


def calculate_secondary_positions(
    secondary_rows: list[dict], records: list[dict]
) -> tuple[
    dict[str, int],
    dict[str, int],
    dict[str, int],
    dict[str, int],
    list[str],
]:
    errors: list[str] = []
    post_positions_by_code: dict[str, list[int]] = defaultdict(list)
    for record in records:
        code = str(record.get("specialty_code") or "")
        position = record.get("printed_position")
        if code and position is not None and not record.get("duplicate"):
            post_positions_by_code[code].append(int(position))

    post_counts: dict[str, int] = {}
    for code, positions in post_positions_by_code.items():
        ordered = sorted(positions)
        if ordered != list(range(1, len(ordered) + 1)):
            errors.append(
                f"Secundaria {code}: las posiciones posteriores a la adjudicacion "
                "no forman una secuencia completa"
            )
        post_counts[code] = len(ordered)

    post_active_counts: Counter[str] = Counter()
    ordered_records = sorted(
        (
            record
            for record in records
            if record.get("specialty_code")
            and record.get("printed_position") is not None
            and not record.get("duplicate")
        ),
        key=lambda record: (
            str(record["specialty_code"]),
            int(record["printed_position"]),
        ),
    )
    for record in ordered_records:
        code = str(record["specialty_code"])
        current_without_deactivated = post_active_counts[code] + 1
        record["post_without_deactivated"] = current_without_deactivated
        row_index = record.get("row_index")
        if row_index is not None:
            secondary_rows[int(row_index)][
                "post_without_deactivated"
            ] = current_without_deactivated
        if not record["deactivated"]:
            post_active_counts[code] += 1

    general_counts: Counter[str] = Counter()
    active_counts: Counter[str] = Counter()
    for row in secondary_rows:
        code = row["specialty_code"]
        if row.get("adjudication_status_matched"):
            disabled = bool(row.get("adjudication_deactivated"))
        else:
            disabled = bool(row["disabled_habilitation"])
        row["effective_position"] = row["position"]
        row["post_adjudication_position"] = row.get("adjudication_position")
        initial_without_deactivated = active_counts[code] + 1
        current_without_deactivated = row.get("post_without_deactivated")
        row["without_deactivated"] = (
            current_without_deactivated
            if current_without_deactivated is not None
            else initial_without_deactivated
        )
        general_counts[code] += 1
        if not disabled:
            active_counts[code] += 1

    return (
        dict(general_counts),
        dict(active_counts),
        post_counts,
        dict(post_active_counts),
        errors,
    )


def merge_people_v4(
    master_rows: Iterable[dict], secondary_rows: Iterable[dict]
) -> list[list]:
    master_profiles: dict[str, list[dict]] = defaultdict(list)
    secondary_by_name: dict[str, dict[str, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for row in master_rows:
        person = {
            "display_name": row["display_name"],
            "official_name": row["official_name"],
            "positions": {},
            "source": "maestros",
            "master_general_positions": row["master_general_positions"],
        }
        for (
            code,
            start,
            without_deactivated,
            after_adjudication,
            after_without_deactivated,
        ) in row["enhanced_positions"]:
            person["positions"][code] = (
                start,
                without_deactivated,
                after_adjudication,
                after_without_deactivated,
            )
        master_profiles[identity_key(row["official_name"])].append(person)

    for row in secondary_rows:
        secondary_by_name[identity_key(row["official_name"])][row["specialty_code"]].append(row)

    secondary_profiles: dict[str, list[dict]] = defaultdict(list)
    for key, by_specialty in secondary_by_name.items():
        profile_count = max(len(rows) for rows in by_specialty.values())
        first_row = next(iter(by_specialty.values()))[0]
        profiles = [
            {
                "display_name": first_row["display_name"],
                "official_name": first_row["official_name"],
                "positions": {},
                "source": "otros",
                "master_general_positions": None,
            }
            for _ in range(profile_count)
        ]
        for code, rows in by_specialty.items():
            for index, row in enumerate(sorted(rows, key=lambda item: item["position"])):
                profiles[index]["positions"][code] = (
                    row["effective_position"],
                    row["without_deactivated"],
                    row["post_adjudication_position"],
                    row.get("post_without_deactivated"),
                )
        secondary_profiles[key] = profiles

    people: list[dict] = []
    for key in sorted(set(master_profiles) | set(secondary_profiles)):
        masters = master_profiles.get(key, [])
        secondary = secondary_profiles.get(key, [])
        if len(masters) == 1 and len(secondary) == 1:
            masters[0]["positions"].update(secondary[0]["positions"])
            masters[0]["source"] = "mixto"
            people.extend(masters)
        else:
            people.extend(masters)
            people.extend(secondary)

    compact = [
        [
            person["display_name"],
            person["official_name"],
            [
                [code, values[0], values[1], values[2], values[3]]
                for code, values in sorted(person["positions"].items())
            ],
            person["source"],
            (
                list(person["master_general_positions"])
                if person["master_general_positions"] is not None
                else None
            ),
        ]
        for person in people
    ]
    compact.sort(key=lambda person: normalize_name(person[0]))
    return compact


def profiles_for_name(
    people: list[list], official_name: str
) -> list[
    tuple[
        dict[str, tuple[int, int, int | None, int | None]],
        tuple[int, int | None] | None,
    ]
]:
    profiles: list[
        tuple[
            dict[str, tuple[int, int, int | None, int | None]],
            tuple[int, int | None] | None,
        ]
    ] = []
    wanted = identity_key(official_name)
    for person in people:
        if identity_key(person[1]) != wanted:
            continue
        positions = {
            str(code): (
                int(start),
                int(without),
                int(after) if after is not None else None,
                int(after_without) if after_without is not None else None,
            )
            for code, start, without, after, after_without in person[2]
        }
        general = (
            (
                int(person[4][0]),
                int(person[4][1]) if person[4][1] is not None else None,
            )
            if person[4] is not None
            else None
        )
        profiles.append((positions, general))
    return profiles


def validate_examples(people: list[list]) -> tuple[dict, list[str]]:
    checks = {
        "MARQUET SOLDEVILA, ROSA MARIA": ({"128": (1, 1, 1, 1)}, (1, 1)),
        "SOLDADO RIBES, LUISA ROSA": ({"128": (2, 1, 2, 1)}, (2, 2)),
        "MOTA FUENTES, FRANCISCA": ({"128": (3, 1, 3, 1)}, (3, 3)),
        "SOLANA VIGO, SAUL": (
            {"123": (681, 592, 673, 592), "128": (3424, 2856, 3394, 2856)},
            (4315, 4271),
        ),
        "MAYOR MAESO, MIGUEL": (
            {"123": (1139, 999, 1126, 999), "128": (6120, 5214, 6073, 5214)},
            (7708, 7639),
        ),
        "ANDRES SANCHEZ, SALVADOR": ({"3A1": (2, 1, 2, 1)}, None),
        "PEREZ VIDAL, ANGEL MIGUEL": ({"3A1": (5, 1, 3, 1)}, None),
        "VIZCAINO SANCHIS, GEMMA": ({"3A1": (6, 1, 4, 1)}, None),
        "VAELLO LLORET, PEDRO": ({"3A1": (120, 91, 111, 91)}, None),
    }
    found: dict[str, list] = {}
    errors: list[str] = []
    for name, (expected_positions, expected_general) in checks.items():
        profiles = profiles_for_name(people, name)
        found[name] = profiles
        if not any(
            all(positions.get(code) == values for code, values in expected_positions.items())
            and general == expected_general
            for positions, general in profiles
        ):
            errors.append(
                f"Ejemplo {name}: esperado {expected_positions}, {expected_general}; "
                f"encontrado {profiles}"
            )
    return found, errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--masters-list", type=Path, required=True)
    parser.add_argument("--secondary-list", type=Path, required=True)
    parser.add_argument("--masters-adjudication", type=Path, required=True)
    parser.add_argument("--secondary-adjudication", type=Path, required=True)
    parser.add_argument("--cuts-json", type=Path, required=True)
    parser.add_argument("--specialty-js", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--status-cache", type=Path)
    parser.add_argument("--academic-year", required=True)
    parser.add_argument(
        "--reference-stage",
        choices=("inicio_curso", "durante_curso", "adjudicacion_continua"),
        required=True,
    )
    parser.add_argument("--reference-date", required=True)
    args = parser.parse_args()

    year_match = re.fullmatch(r"(\d{4})/(\d{4})", args.academic_year)
    if not year_match or int(year_match.group(2)) != int(year_match.group(1)) + 1:
        parser.error("--academic-year debe tener el formato 2026/2027")
    try:
        datetime.strptime(args.reference_date, "%Y-%m-%d")
    except ValueError:
        parser.error("--reference-date debe ser una fecha valida con formato AAAA-MM-DD")

    master_rows, master_counts, master_errors = parse_masters(args.masters_list)
    secondary_rows, secondary_names, secondary_errors, secondary_starred = (
        parse_secondary_with_disabled_habilitations(args.secondary_list)
    )

    known_master_names = {identity_key(row["official_name"]) for row in master_rows}
    known_secondary_names = {identity_key(row["official_name"]) for row in secondary_rows}
    cache_key = {
        "parser_version": 4,
        "masters_list_sha256": sha256(args.masters_list),
        "secondary_list_sha256": sha256(args.secondary_list),
        "masters_sha256": sha256(args.masters_adjudication),
        "secondary_sha256": sha256(args.secondary_adjudication),
    }
    cached = None
    if args.status_cache and args.status_cache.exists():
        candidate = json.loads(args.status_cache.read_text(encoding="utf-8"))
        if candidate.get("key") == cache_key:
            cached = candidate
    if cached:
        master_statuses = cached["master_statuses"]
        master_status_errors = cached["master_status_errors"]
        master_adjudication_pages = cached["master_adjudication_pages"]
        secondary_statuses = cached["secondary_statuses"]
        secondary_status_errors = cached["secondary_status_errors"]
        secondary_adjudication_pages = cached["secondary_adjudication_pages"]
    else:
        master_statuses, master_status_errors, master_adjudication_pages = (
            parse_adjudication_statuses(args.masters_adjudication, known_master_names)
        )
        secondary_statuses, secondary_status_errors, secondary_adjudication_pages = (
            parse_adjudication_statuses(
                args.secondary_adjudication,
                known_secondary_names,
                set(secondary_names),
            )
        )
        if args.status_cache:
            args.status_cache.parent.mkdir(parents=True, exist_ok=True)
            args.status_cache.write_text(
                json.dumps(
                    {
                        "key": cache_key,
                        "master_statuses": master_statuses,
                        "master_status_errors": master_status_errors,
                        "master_adjudication_pages": master_adjudication_pages,
                        "secondary_statuses": secondary_statuses,
                        "secondary_status_errors": secondary_status_errors,
                        "secondary_adjudication_pages": secondary_adjudication_pages,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )

    (
        secondary_statuses,
        secondary_status_errors,
        secondary_header_records_ignored,
    ) = remove_specialty_header_records(
        secondary_statuses,
        secondary_status_errors,
        secondary_names,
    )

    matched_master, master_match_errors = attach_master_statuses(master_rows, master_statuses)
    matched_secondary, secondary_match_errors = attach_secondary_statuses(
        secondary_rows, secondary_statuses
    )
    (
        master_general_counts,
        master_active_counts,
        master_post_counts,
        master_post_active_counts,
        master_position_errors,
    ) = calculate_master_positions(master_rows, master_statuses)
    (
        secondary_general_counts,
        secondary_active_counts,
        secondary_post_counts,
        secondary_post_active_counts,
        current_position_errors,
    ) = (
        calculate_secondary_positions(secondary_rows, secondary_statuses)
    )
    people = merge_people_v4(master_rows, secondary_rows)
    specialties, unknown_specialties = build_specialties(
        secondary_names, parse_specialty_map(args.specialty_js)
    )
    examples, example_errors = validate_examples(people)
    last_awarded, last_awarded_errors = build_last_awarded_by_specialty(
        args.cuts_json,
        master_statuses,
        secondary_statuses,
        sha256(args.masters_adjudication),
        sha256(args.secondary_adjudication),
    )

    invariant_errors: list[str] = []
    position_records = 0
    for person in people:
        for (
            code,
            start,
            without_deactivated,
            after_adjudication,
            after_without_deactivated,
        ) in person[2]:
            position_records += 1
            if without_deactivated < 1:
                invariant_errors.append(
                    f"{person[1]} {code}: inicio={start}, "
                    f"sin_desactivados={without_deactivated}"
                )
            if after_adjudication is not None and after_adjudication < 1:
                invariant_errors.append(
                    f"{person[1]} {code}: posicion posterior invalida="
                    f"{after_adjudication}"
                )
            if after_adjudication is not None:
                if (
                    after_without_deactivated is None
                    or after_without_deactivated < 1
                    or after_without_deactivated > after_adjudication
                ):
                    invariant_errors.append(
                        f"{person[1]} {code}: posterior={after_adjudication}, "
                        f"posterior_sin_desactivados={after_without_deactivated}"
                    )
                elif without_deactivated != after_without_deactivated:
                    invariant_errors.append(
                        f"{person[1]} {code}: valor compatible={without_deactivated}, "
                        f"valor posterior={after_without_deactivated}"
                    )
            elif after_without_deactivated is not None:
                invariant_errors.append(
                    f"{person[1]} {code}: sin posicion posterior pero con "
                    f"posicion sin desactivados={after_without_deactivated}"
                )

    fatal_errors = (
        master_errors
        + secondary_errors
        + master_status_errors
        + secondary_status_errors
        + master_match_errors
        + secondary_match_errors
        + master_position_errors
        + current_position_errors
        + example_errors
        + last_awarded_errors
        + invariant_errors
    )

    position_reference_status = (
        "adjudicacion_continua"
        if args.reference_stage in {"durante_curso", "adjudicacion_continua"}
        else "listado"
    )

    dataset = {
        "schema_version": 5,
        "dataset": "posiciones_bolsa",
        "academic_year": args.academic_year,
        "status": position_reference_status,
        "reference_stage": args.reference_stage,
        "reference_date": args.reference_date,
        "position_reference": {
            "kind": position_reference_status,
            "academic_year": args.academic_year,
            "date": args.reference_date,
        },
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "sources": [
            {
                "role": "position_list",
                "body": "maestros",
                "filename": args.masters_list.name,
                "sha256": sha256(args.masters_list),
                "pages": max((row["page"] for row in master_rows), default=0),
            },
            {
                "role": "position_list",
                "body": "otros",
                "filename": args.secondary_list.name,
                "sha256": sha256(args.secondary_list),
                "pages": max((row["page"] for row in secondary_rows), default=0),
            },
            {
                "role": "deactivation_status",
                "body": "maestros",
                "filename": args.masters_adjudication.name,
                "sha256": sha256(args.masters_adjudication),
                "pages": master_adjudication_pages,
            },
            {
                "role": "deactivation_status",
                "body": "otros",
                "filename": args.secondary_adjudication.name,
                "sha256": sha256(args.secondary_adjudication),
                "pages": secondary_adjudication_pages,
            },
        ],
        "calculation": {
            "position_without_deactivated": (
                "Valor compatible: posición posterior sin desactivados cuando consta; "
                "si no consta tras la adjudicación, conserva el cálculo anual anterior"
            ),
            "position_after_adjudication_without_deactivated": (
                "1 + personas no marcadas como Desactivat situadas antes en el orden "
                "posterior a la adjudicación de la misma especialidad; Ha participat, "
                "No adjudicat y Adjudicat no se excluyen; la persona consultada siempre "
                "se cuenta aunque ella misma figure como Desactivat"
            ),
            "position_after_adjudication": (
                "Posición impresa tras la adjudicación en secundaria y otros cuerpos; "
                "en maestros se reconstruye por especialidad siguiendo el orden de la "
                "bolsa general posterior impresa en la adjudicación"
            ),
            "masters_general_positions": (
                "Posición general impresa en el listado anual y posición general "
                "impresa tras la adjudicación"
            ),
            "masters_rule": (
                "La bolsa general posterior impresa determina el nuevo orden; se excluye "
                "de cada especialidad a quien figura como Desactivat"
            ),
            "secondary_rule": (
                "Se recorre por separado cada especialidad en el PDF posterior y sólo "
                "se excluyen las filas cuyo estado es Desactivat"
            ),
            "last_awarded": (
                "Mayor posición adjudicada de cada especialidad; en secundaria y otros "
                "cuerpos sólo se acepta cuando coinciden la especialidad del encabezado "
                "y la especialidad de la plaza adjudicada"
            ),
            "last_vacancy": (
                "Mayor posición adjudicada como vacante dentro de la especialidad; "
                "se muestra cuando el último adjudicado obtuvo una sustitución"
            ),
        },
        "specialties": specialties,
        "last_awarded_by_specialty": last_awarded,
        "person_fields": [
            "display_name",
            "official_name",
            "positions",
            "source",
            "master_general_positions",
        ],
        "master_general_position_fields": [
            "position_at_course_start",
            "position_after_adjudication",
        ],
        "position_fields": [
            "specialty_code",
            "position_at_course_start",
            "position_without_deactivated",
            "position_after_adjudication",
            "position_after_adjudication_without_deactivated",
        ],
        "people": people,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(dataset, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    report = {
        "result": "ok" if not fatal_errors else "error",
        "master_rows": len(master_rows),
        "master_specialty_counts": master_counts,
        "master_adjudication_rows": len(master_statuses),
        "master_deactivated": sum(row["deactivated"] for row in master_statuses),
        "master_status_matches": matched_master,
        "master_unmatched_after_adjudication": len(master_rows) - matched_master,
        "master_general_counts": master_general_counts,
        "master_active_counts": master_active_counts,
        "master_post_adjudication_counts": master_post_counts,
        "master_post_active_counts": master_post_active_counts,
        "secondary_rows": len(secondary_rows),
        "secondary_specialties": len(secondary_names),
        "secondary_disabled_habilitations": secondary_starred,
        "secondary_adjudication_rows": len(secondary_statuses),
        "secondary_header_records_ignored": secondary_header_records_ignored,
        "secondary_deactivated": sum(row["deactivated"] for row in secondary_statuses),
        "secondary_status_matches": matched_secondary,
        "secondary_identity_alias_matches": sum(
            bool(row.get("identity_alias_match")) for row in secondary_statuses
        ),
        "secondary_new_candidates": sum(
            bool(row.get("unmatched_new_candidate")) for row in secondary_statuses
        ),
        "secondary_general_counts": secondary_general_counts,
        "secondary_active_counts": secondary_active_counts,
        "secondary_post_adjudication_counts": secondary_post_counts,
        "secondary_post_active_counts": secondary_post_active_counts,
        "last_awarded_specialties": len(last_awarded["rows"]),
        "last_awarded_controls": {
            row[0]: row
            for row in last_awarded["rows"]
            if row[0] in {"3A1", "128", "153"}
        },
        "people_profiles": len(people),
        "position_records": position_records,
        "unknown_specialties": unknown_specialties,
        "examples": examples,
        "errors": fatal_errors,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        key: report[key]
        for key in (
            "result",
            "master_rows",
            "master_adjudication_rows",
            "master_deactivated",
            "master_status_matches",
            "secondary_rows",
            "secondary_specialties",
            "secondary_disabled_habilitations",
            "secondary_adjudication_rows",
            "secondary_deactivated",
            "secondary_status_matches",
            "people_profiles",
            "position_records",
            "examples",
        )
    }, ensure_ascii=False, indent=2))
    if fatal_errors:
        print(json.dumps(fatal_errors[:50], ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
