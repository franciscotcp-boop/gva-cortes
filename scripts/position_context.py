from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


MASTER_SPECIALTY_CODES = frozenset({
    "120",
    "121",
    "122",
    "123",
    "124",
    "126",
    "127",
    "128",
    "151",
    "152",
    "153",
})
PROVINCE_INDEX = {"03": 0, "46": 1, "12": 2}
PROVINCES = ("alicante", "valencia", "castellon")
STATE_SCHEMA_VERSION = 1
ASSIGNMENT_FIELDS = [
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


def normalized_name(value: object) -> str:
    text = str(value or "").upper().replace("Mª", " MARIA ").replace("M.ª", " MARIA ")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact_name(value: object) -> str:
    return normalized_name(value).replace(" ", "")


def normalized_academic_year(value: object) -> str | None:
    match = re.fullmatch(r"\s*(\d{4})\s*[-/]\s*(\d{4})\s*", str(value or ""))
    if not match:
        return None
    first, second = (int(part) for part in match.groups())
    if second != first + 1:
        return None
    return f"{first}-{second}"


def academic_year_for_date(value: object) -> str | None:
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(value or ""))
    if not match:
        return None
    year, month, _day = (int(part) for part in match.groups())
    start = year if month >= 7 else year - 1
    return f"{start}-{start + 1}"


def province_index(center_code: object) -> int | None:
    return PROVINCE_INDEX.get(str(center_code or "")[:2])


def body_for_profile(source: object, specialty_code: object) -> str:
    code = str(specialty_code or "")
    if code in MASTER_SPECIALTY_CODES and str(source or "") in {"maestros", "mixto"}:
        return "maestros"
    return "secundaria"


def profile_orders(person: list, position: list) -> tuple[int | None, int | None]:
    code = str(position[0])
    if body_for_profile(person[3] if len(person) > 3 else "", code) == "maestros":
        general = person[4] if len(person) > 4 and isinstance(person[4], list) else []
        initial = general[0] if general else None
        after = general[1] if len(general) > 1 else None
    else:
        initial = position[1]
        after = position[3] if len(position) > 3 else None

    def integer(value: object) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    return integer(initial), integer(after)


def empty_state(academic_year: str) -> dict:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "academic_year": academic_year,
        "updated_at": None,
        "assignment_fields": list(ASSIGNMENT_FIELDS),
        "assignments": [],
        "sources": [],
        "skipped": {},
    }


class PositionContextUpdater:
    """Maintain province counters without changing the cut database."""

    def __init__(self, positions_path: Path, state_path: Path) -> None:
        self.positions_path = Path(positions_path)
        self.state_path = Path(state_path)
        self.enabled = self.positions_path.exists()
        self.dirty = False
        self.positions: dict = {}
        self.state: dict = {}
        self.profile_refs: list[dict] = []
        self.by_identity_code: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.by_compact_code: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.by_code: dict[str, list[dict]] = defaultdict(list)
        if not self.enabled:
            print(f"Posiciones: omitido; no existe {self.positions_path}")
            return

        self.positions = json.loads(self.positions_path.read_text(encoding="utf-8"))
        positions_year = normalized_academic_year(self.positions.get("academic_year"))
        if positions_year is None or int(self.positions.get("schema_version") or 0) < 7:
            print("Posiciones: omitido; el JSON no tiene un curso o esquema compatible")
            self.enabled = False
            return

        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
        else:
            self.state = empty_state(positions_year)
        if self.state.get("assignment_fields") != ASSIGNMENT_FIELDS:
            print("Posiciones: omitido; el estado provincial tiene un formato incompatible")
            self.enabled = False
            return
        if normalized_academic_year(self.state.get("academic_year")) != positions_year:
            print("Posiciones: estado de otro curso; se esperara al PDF de inicio correspondiente")

        self._build_profile_index()

    def _build_profile_index(self) -> None:
        for person_index, person in enumerate(self.positions.get("people", [])):
            if not isinstance(person, list) or len(person) < 4 or not isinstance(person[2], list):
                continue
            official_name = str(person[1] or "")
            identity = normalized_name(official_name)
            compact = compact_name(official_name)
            for position_index, position in enumerate(person[2]):
                if not isinstance(position, list) or len(position) < 2:
                    continue
                code = str(position[0])
                initial_order, after_order = profile_orders(person, position)
                if initial_order is None:
                    continue
                ref = {
                    "person_index": person_index,
                    "position_index": position_index,
                    "body": body_for_profile(person[3], code),
                    "specialty_code": code,
                    "initial_order": initial_order,
                    "after_order": after_order,
                    "official_name": official_name,
                }
                self.profile_refs.append(ref)
                self.by_identity_code[(identity, code)].append(ref)
                self.by_compact_code[(compact, code)].append(ref)
                self.by_code[code].append(ref)

    def _rows_as_dicts(self) -> list[dict]:
        return [
            dict(zip(ASSIGNMENT_FIELDS, row))
            for row in self.state.get("assignments", [])
            if isinstance(row, list) and len(row) == len(ASSIGNMENT_FIELDS)
        ]

    def _choose_profile(self, assignment: object, mode: str, existing_rows: list[dict]) -> dict | None:
        code = str(getattr(assignment, "specialty_code", "") or "")
        candidate = str(getattr(assignment, "candidate_name", "") or "")
        body = str(getattr(assignment, "body", "") or "")
        candidates = [
            ref
            for ref in self.by_identity_code.get((normalized_name(candidate), code), [])
            if ref["body"] == body
        ]
        if not candidates:
            candidates = [
                ref
                for ref in self.by_compact_code.get((compact_name(candidate), code), [])
                if ref["body"] == body
            ]
        cut = int(getattr(assignment, "cut", 0) or 0)
        exact = [ref for ref in candidates if ref["after_order"] == cut]
        if len(exact) == 1:
            return exact[0]

        if mode == "inicio":
            rank_match = [
                ref
                for ref in self.by_code.get(code, [])
                if ref["body"] == body and ref["after_order"] == cut
            ]
            if len(rank_match) == 1:
                return rank_match[0]
            without_after = [ref for ref in candidates if ref["after_order"] is None]
            if len(without_after) == 1:
                return without_after[0]
            return None

        if len(candidates) == 1:
            return candidates[0]

        if mode == "curso" and candidates:
            previous = {
                (int(row["person_index"]), int(row["position_index"]))
                for row in existing_rows
                if row["specialty_code"] == code
                and normalized_name(row["candidate_name"]) == normalized_name(candidate)
            }
            repeated = [
                ref
                for ref in candidates
                if (ref["person_index"], ref["position_index"]) in previous
            ]
            if len(repeated) == 1:
                return repeated[0]
        return None

    def _resolve_pdf(self, parsed: object, mode: str, existing_rows: list[dict]) -> tuple[list[dict], dict[str, int]]:
        resolved: list[dict] = []
        skipped: defaultdict[str, int] = defaultdict(int)
        seen: set[tuple] = set()
        for assignment in getattr(parsed, "assignments", []):
            code = str(getattr(assignment, "specialty_code", "") or "")
            if not code:
                skipped["without_specialty"] += 1
                continue
            body = str(getattr(assignment, "body", "") or "")
            candidate = str(getattr(assignment, "candidate_name", "") or "")
            province = province_index(getattr(assignment, "center_code", ""))
            if province is None:
                skipped["unknown_province"] += 1
                continue
            profile = self._choose_profile(assignment, mode, existing_rows)
            if profile is None:
                if mode != "inicio":
                    skipped["without_unique_profile"] += 1
                    continue
                person_index = -1
                position_index = -1
                after_order = int(getattr(assignment, "cut", 0) or 0)
                initial_order = None
                key = ("initial_unresolved", body, code, after_order, normalized_name(candidate))
                skipped["initial_position_without_profile"] += 1
            else:
                person_index = profile["person_index"]
                position_index = profile["position_index"]
                after_order = (
                    int(getattr(assignment, "cut", 0) or 0)
                    if mode == "inicio"
                    else profile["after_order"]
                )
                initial_order = profile["initial_order"]
                key = ("profile", person_index, position_index)
            if key in seen:
                skipped["duplicate_assignment"] += 1
                continue
            seen.add(key)
            resolved.append({
                "body": profile["body"] if profile is not None else body,
                "specialty_code": code,
                "person_index": person_index,
                "position_index": position_index,
                "after_order": after_order,
                "initial_order": initial_order,
                "center_code": str(getattr(assignment, "center_code", "") or ""),
                "province_index": province,
                "published_date": str(getattr(parsed, "published_date", "") or ""),
                "mode": mode,
                "placement_type": str(getattr(assignment, "placement_type", "") or ""),
                "candidate_name": candidate,
                "source_url": str(getattr(parsed, "url", "") or ""),
                "source_sha256": str(getattr(parsed, "sha256", "") or ""),
            })
        return resolved, dict(skipped)

    def apply(self, parsed_items: Iterable[object], mode: str) -> bool:
        if not self.enabled:
            return False
        changed = False
        positions_year = normalized_academic_year(self.positions.get("academic_year"))
        for parsed in sorted(
            parsed_items,
            key=lambda item: (str(getattr(item, "published_date", "") or ""), str(getattr(item, "body", "") or "")),
        ):
            published_date = getattr(parsed, "published_date", None)
            pdf_year = academic_year_for_date(published_date)
            if pdf_year is None or pdf_year != positions_year:
                print(
                    "Posiciones: PDF omitido para evitar mezclar cursos "
                    f"({published_date or 'sin fecha'} frente a {positions_year})"
                )
                continue

            state_year = normalized_academic_year(self.state.get("academic_year"))
            if state_year != positions_year:
                if mode != "inicio":
                    print("Posiciones: adjudicacion continua omitida hasta inicializar el curso")
                    continue
                self.state = empty_state(positions_year)

            existing = self._rows_as_dicts()
            resolved, skipped = self._resolve_pdf(parsed, mode, existing)
            body = str(getattr(parsed, "body", "") or "")
            if mode == "inicio":
                existing = [row for row in existing if row["body"] != body]

            def assignment_key(row: dict) -> tuple:
                person_index = int(row["person_index"])
                position_index = int(row["position_index"])
                if person_index >= 0 and position_index >= 0:
                    return ("profile", person_index, position_index)
                return (
                    "initial_unresolved",
                    row["body"],
                    row["specialty_code"],
                    int(row["after_order"]),
                    normalized_name(row["candidate_name"]),
                )

            by_profile = {assignment_key(row): row for row in existing}
            for row in resolved:
                key = assignment_key(row)
                previous = by_profile.get(key)
                if (
                    mode == "curso"
                    and previous is not None
                    and str(previous.get("published_date") or "") > str(row.get("published_date") or "")
                ):
                    continue
                by_profile[key] = row
            merged = sorted(
                by_profile.values(),
                key=lambda row: (
                    row["specialty_code"],
                    int(row["after_order"]) if row["after_order"] is not None else 10**9,
                    int(row["initial_order"]) if row["initial_order"] is not None else 10**9,
                    int(row["person_index"]),
                    int(row["position_index"]),
                ),
            )
            new_rows = [[row[field] for field in ASSIGNMENT_FIELDS] for row in merged]
            if new_rows != self.state.get("assignments", []):
                self.state["assignments"] = new_rows
                changed = True

            source = {
                "mode": mode,
                "body": body,
                "published_date": published_date,
                "url": str(getattr(parsed, "url", "") or ""),
                "sha256": str(getattr(parsed, "sha256", "") or ""),
                "parsed_assignments": len(getattr(parsed, "assignments", [])),
                "resolved_assignments": len(resolved),
            }
            sources = [
                item
                for item in self.state.get("sources", [])
                if not (
                    item.get("mode") == mode
                    and item.get("body") == body
                    and item.get("sha256") == source["sha256"]
                )
            ]
            sources.append(source)
            self.state["sources"] = sorted(
                sources,
                key=lambda item: (
                    str(item.get("published_date") or ""),
                    str(item.get("mode") or ""),
                    str(item.get("body") or ""),
                ),
            )
            for reason, count in skipped.items():
                self.state.setdefault("skipped", {})[f"{mode}:{body}:{reason}"] = count
            self.state["updated_at"] = max(
                str(self.state.get("updated_at") or ""),
                str(published_date or ""),
            ) or None
            changed = True

        if changed:
            self._recalculate()
            self.dirty = True
        return changed

    def _recalculate(self) -> None:
        events_by_code: dict[str, list[dict]] = defaultdict(list)
        for row in self._rows_as_dicts():
            events_by_code[str(row["specialty_code"])].append(row)
        refs_by_code: dict[str, list[dict]] = defaultdict(list)
        for ref in self.profile_refs:
            refs_by_code[ref["specialty_code"]].append(ref)

        def assign_counts(code_refs: list[dict], code_events: list[dict], order_field: str) -> None:
            events = sorted(
                (event for event in code_events if event.get(order_field) is not None),
                key=lambda item: (int(item[order_field]), int(item["person_index"])),
            )
            refs = sorted(
                (ref for ref in code_refs if ref.get(order_field) is not None),
                key=lambda item: (int(item[order_field]), int(item["person_index"])),
            )
            counts = [0, 0, 0]
            event_index = 0
            for ref in refs:
                while event_index < len(events) and int(events[event_index][order_field]) < int(ref[order_field]):
                    counts[int(events[event_index]["province_index"])] += 1
                    event_index += 1
                position = self.positions["people"][ref["person_index"]][2][ref["position_index"]]
                while len(position) < 8:
                    position.append(None)
                previous = position[7] if isinstance(position[7], list) else []
                future_same_position = previous[3] if len(previous) > 3 else None
                future_previous_course = previous[4] if len(previous) > 4 else None
                position[7] = [*counts, future_same_position, future_previous_course]

        for code, refs in refs_by_code.items():
            events = events_by_code.get(code, [])
            with_after = [ref for ref in refs if ref["after_order"] is not None]
            without_after = [ref for ref in refs if ref["after_order"] is None]
            assign_counts(with_after, events, "after_order")
            assign_counts(without_after, events, "initial_order")

        metadata = self.positions.setdefault("additional_information", {})
        metadata["version"] = max(2, int(metadata.get("version") or 0))
        metadata["body_scope"] = ["maestros", "otros"]
        metadata["province_order"] = list(PROVINCES)
        metadata["source_stage"] = "acumulativo_inicio_y_durante_curso"
        metadata["source_date"] = self.state.get("updated_at")
        metadata["calculation"] = (
            "Se cuenta una sola adjudicacion acumulativa por persona y especialidad. "
            "La especialidad adjudicada debe ser la misma que la tarjeta consultada; "
            "en Otros Cuerpos tambien debe coincidir con el encabezado del PDF. "
            "Las adjudicaciones posteriores sustituyen la provincia anterior de esa persona."
        )
        metadata.setdefault("future_history_available", False)
        self.positions["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def save(self) -> bool:
        if not self.enabled or not self.dirty:
            return False
        self.positions_path.write_text(
            json.dumps(self.positions, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self.state, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return True
