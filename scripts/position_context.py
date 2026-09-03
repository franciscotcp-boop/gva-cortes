from __future__ import annotations

import gzip
import json
import re
import unicodedata
from collections import defaultdict, deque
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
MASTER_PROFILE_ALIASES = {
    "151": "126",
    "152": "127",
    "153": "128",
}
MASTER_ENGLISH_TARGET_CODES = frozenset({"120", "123", "124", "126", "127", "128", "153"})
SECONDARY_ENGLISH_SPECIALTY_CODE = "211"
PROVINCE_INDEX = {"03": 0, "46": 1, "12": 2}
PROVINCES = ("alicante", "valencia", "castellon")
STATE_SCHEMA_VERSION = 3
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
    "workload",
    "english_requirement",
    "itinerant",
    "center_name",
    "locality",
    "observations",
]


def normalized_name(value: object) -> str:
    text = str(value or "").upper().replace("Mª", " MARIA ").replace("M.ª", " MARIA ")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact_name(value: object) -> str:
    return normalized_name(value).replace(" ", "")


def candidate_name(value: object) -> str:
    return re.sub(r"\(\s*esp\s*:\s*\d+\s*\)\s*$", "", str(value or ""), flags=re.I).strip()


def display_candidate_name(value: object) -> str:
    official = candidate_name(value)
    if "," in official:
        surnames, given = (part.strip() for part in official.split(",", 1))
        official = f"{given} {surnames}"
    return re.sub(r"\s+", " ", official.lower().title()).strip()


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


def migrate_state_format(state: dict) -> dict | None:
    fields = state.get("assignment_fields")
    rows = state.get("assignments")
    if not isinstance(fields, list) or not isinstance(rows, list):
        return None
    if fields == ASSIGNMENT_FIELDS:
        state["schema_version"] = STATE_SCHEMA_VERSION
        return state
    required = set(ASSIGNMENT_FIELDS[:13])
    if not required.issubset(set(fields)):
        return None
    migrated = []
    for raw in rows:
        if not isinstance(raw, list) or len(raw) != len(fields):
            continue
        item = dict(zip(fields, raw))
        migrated.append([item.get(field) for field in ASSIGNMENT_FIELDS])
    state["assignment_fields"] = list(ASSIGNMENT_FIELDS)
    state["assignments"] = migrated
    state["schema_version"] = STATE_SCHEMA_VERSION
    return state


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
        self.current_status_by_profile: dict[tuple[int, int], str] = {}
        self.current_assignment_profiles: set[tuple[int, int]] = set()
        self.current_snapshot_date: str | None = None
        self.current_master_people: set[int] = set()
        self.current_secondary_profiles: set[tuple[int, int]] = set()
        self.accredited_names: set[str] = set()
        self.gender_by_first_name: dict[str, str] = {}
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
        migrated_state = migrate_state_format(self.state)
        if migrated_state is None:
            print("Posiciones: omitido; el estado provincial tiene un formato incompatible")
            self.enabled = False
            return
        self.state = migrated_state
        if normalized_academic_year(self.state.get("academic_year")) != positions_year:
            print("Posiciones: estado de otro curso; se esperara al PDF de inicio correspondiente")

        self._load_supporting_data()
        self._build_profile_index()

    def _load_supporting_data(self) -> None:
        accreditation_path = self.positions_path.parent / "english_accreditations.json.gz"
        if accreditation_path.exists():
            try:
                with gzip.open(accreditation_path, "rt", encoding="utf-8") as handle:
                    payload = json.load(handle)
                self.accredited_names = {
                    normalized_name(record.get("official_name"))
                    for record in payload.get("records", [])
                    if isinstance(record, dict) and record.get("official_name")
                }
            except (OSError, json.JSONDecodeError):
                self.accredited_names = set()

        gender_path = self.positions_path.parent / "gender_first_name_map.json"
        if gender_path.exists():
            try:
                payload = json.loads(gender_path.read_text(encoding="utf-8"))
                self.gender_by_first_name = {
                    normalized_name(key): value
                    for key, value in payload.items()
                    if value in {"m", "f"}
                }
            except (OSError, json.JSONDecodeError):
                self.gender_by_first_name = {}

    def _build_profile_index(self) -> None:
        self.profile_refs = []
        self.by_identity_code = defaultdict(list)
        self.by_compact_code = defaultdict(list)
        self.by_code = defaultdict(list)
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
                if initial_order is None and after_order is None:
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

    @staticmethod
    def _status_value(record: object, name: str, default: object = None) -> object:
        if isinstance(record, dict):
            return record.get(name, default)
        return getattr(record, name, default)

    def _infer_gender(self, official_name: str) -> str:
        given = official_name.split(",", 1)[1] if "," in official_name else official_name
        given = re.sub(r"^M[ªA]\b", "MARIA", given.strip(), flags=re.I)
        for token in given.split():
            gender = self.gender_by_first_name.get(normalized_name(token))
            if gender in {"m", "f"}:
                return gender
        return "u"

    def _ensure_assignment_profiles(self, parsed_items: list[object]) -> bool:
        changed = False
        people_by_identity: dict[tuple[str, str], set[int]] = defaultdict(set)
        profile_keys: set[tuple[str, str, str]] = set()
        newly_created: dict[tuple[str, str], int] = {}
        for ref in self.profile_refs:
            identity = normalized_name(ref["official_name"])
            people_by_identity[(ref["body"], identity)].add(ref["person_index"])
            profile_keys.add((ref["body"], ref["specialty_code"], identity))

        # Continuous secondary lists may introduce new candidates or newly
        # enabled specialties that were absent from the annual list.
        for parsed in parsed_items:
            if str(getattr(parsed, "body", "") or "") != "secundaria":
                continue
            for record in getattr(parsed, "statuses", []):
                code = str(self._status_value(record, "specialty_code", "") or "")
                official = candidate_name(self._status_value(record, "candidate_name", ""))
                identity = normalized_name(official)
                key = ("secundaria", code, identity)
                if not code or not identity or key in profile_keys:
                    continue
                candidates = people_by_identity.get(("secundaria", identity), set())
                person_index = newly_created.get(("secundaria", identity))
                if person_index is None and len(candidates) == 1:
                    person_index = next(iter(candidates))
                if person_index is None:
                    person = [
                        display_candidate_name(official),
                        official,
                        [],
                        "otros",
                        None,
                        self._infer_gender(official),
                    ]
                    self.positions.setdefault("people", []).append(person)
                    person_index = len(self.positions["people"]) - 1
                    people_by_identity[("secundaria", identity)].add(person_index)
                    newly_created[("secundaria", identity)] = person_index
                person = self.positions["people"][person_index]
                person[2].append([
                    code,
                    None,
                    None,
                    int(self._status_value(record, "position", 0) or 0) or None,
                    None,
                    None,
                    None,
                    [0, 0, 0, None, None],
                    "N",
                    None,
                ])
                profile_keys.add(key)
                changed = True

        if changed:
            self._build_profile_index()

        for parsed in parsed_items:
            if not getattr(parsed, "statuses", None):
                continue
            body = str(getattr(parsed, "body", "") or "")
            statuses = list(getattr(parsed, "statuses", []))
            for assignment in getattr(parsed, "assignments", []):
                if self._choose_profile(assignment, "curso", []):
                    continue
                code = str(getattr(assignment, "specialty_code", "") or "")
                official = candidate_name(getattr(assignment, "candidate_name", ""))
                identity = normalized_name(official)
                status_position = None
                for record in statuses:
                    record_code = str(self._status_value(record, "specialty_code", "") or "")
                    record_name = candidate_name(self._status_value(record, "candidate_name", ""))
                    if normalized_name(record_name) != identity:
                        continue
                    if body == "secundaria" and record_code != code:
                        continue
                    status_position = int(self._status_value(record, "position", 0) or 0) or None
                    break

                matching_people = {
                    ref["person_index"]
                    for ref in self.profile_refs
                    if ref["body"] == body and normalized_name(ref["official_name"]) == identity
                }
                person_index = next(iter(matching_people)) if len(matching_people) == 1 else None
                if person_index is None:
                    source = "maestros" if body == "maestros" else "otros"
                    general = [None, int(getattr(assignment, "cut", 0) or 0)] if body == "maestros" else None
                    person = [
                        display_candidate_name(official),
                        official,
                        [],
                        source,
                        general,
                        self._infer_gender(official),
                    ]
                    self.positions.setdefault("people", []).append(person)
                    person_index = len(self.positions["people"]) - 1
                person = self.positions["people"][person_index]
                if any(str(position[0]) == code for position in person[2] if isinstance(position, list) and position):
                    continue
                after_order = status_position if body == "secundaria" else None
                person[2].append([
                    code,
                    None,
                    None,
                    after_order,
                    None,
                    None,
                    None,
                    [0, 0, 0, None, None],
                    "N",
                    None,
                ])
                changed = True
                self._build_profile_index()
        return changed

    @staticmethod
    def _take_unused(queue: deque[int] | None, used: set[int]) -> int | None:
        while queue and queue[0] in used:
            queue.popleft()
        if not queue:
            return None
        value = queue.popleft()
        used.add(value)
        return value

    def _sync_status_snapshots(self, parsed_items: list[object]) -> dict[str, int]:
        latest: dict[str, object] = {}
        for parsed in parsed_items:
            if not getattr(parsed, "statuses", None):
                continue
            body = str(getattr(parsed, "body", "") or "")
            previous = latest.get(body)
            if previous is None or str(getattr(parsed, "published_date", "") or "") >= str(
                getattr(previous, "published_date", "") or ""
            ):
                latest[body] = parsed

        report = {
            "master_statuses": 0,
            "master_matched": 0,
            "secondary_statuses": 0,
            "secondary_statuses_raw": 0,
            "secondary_cross_specialty_duplicates_ignored": 0,
            "secondary_matched": 0,
        }
        self.current_status_by_profile = {}
        self.current_master_people = set()
        self.current_secondary_profiles = set()
        snapshot_dates: list[str] = []

        master = latest.get("maestros")
        if master is not None:
            snapshot_dates.append(str(getattr(master, "published_date", "") or ""))
            people: list[tuple[int, int]] = []
            for person_index, person in enumerate(self.positions.get("people", [])):
                if not isinstance(person, list) or len(person) < 5 or not isinstance(person[2], list):
                    continue
                if not any(
                    body_for_profile(person[3], position[0]) == "maestros"
                    for position in person[2]
                    if isinstance(position, list) and position
                ):
                    continue
                general = person[4] if isinstance(person[4], list) else []
                old_order = general[1] if len(general) > 1 and general[1] is not None else (
                    general[0] if general else None
                )
                people.append((int(old_order) if old_order is not None else 10**9, person_index))
            people.sort()
            by_name: dict[str, deque[int]] = defaultdict(deque)
            by_compact: dict[str, deque[int]] = defaultdict(deque)
            for _old_order, person_index in people:
                official = self.positions["people"][person_index][1]
                by_name[normalized_name(official)].append(person_index)
                by_compact[compact_name(official)].append(person_index)

            matched_rows: list[tuple[int, int, str]] = []
            used: set[int] = set()
            statuses = sorted(
                getattr(master, "statuses", []),
                key=lambda item: int(self._status_value(item, "position", 0) or 0),
            )
            report["master_statuses"] = len(statuses)
            for record in statuses:
                name = candidate_name(self._status_value(record, "candidate_name", ""))
                person_index = self._take_unused(by_name.get(normalized_name(name)), used)
                if person_index is None:
                    person_index = self._take_unused(by_compact.get(compact_name(name)), used)
                if person_index is None:
                    continue
                order = int(self._status_value(record, "position", 0) or 0)
                status = str(self._status_value(record, "status", "N") or "N")
                person = self.positions["people"][person_index]
                if not isinstance(person[4], list):
                    person[4] = [None, order]
                else:
                    while len(person[4]) < 2:
                        person[4].append(None)
                    person[4][1] = order
                matched_rows.append((order, person_index, status))
                self.current_master_people.add(person_index)
            report["master_matched"] = len(matched_rows)
            if statuses and len(matched_rows) / len(statuses) < 0.95:
                raise RuntimeError(
                    "La lista continua de Maestros no coincide de forma segura con la bolsa: "
                    f"{len(matched_rows)}/{len(statuses)}"
                )

            all_counts: defaultdict[str, int] = defaultdict(int)
            active_counts: defaultdict[str, int] = defaultdict(int)
            for _order, person_index, status in sorted(matched_rows):
                person = self.positions["people"][person_index]
                for position_index, position in enumerate(person[2]):
                    if not isinstance(position, list) or not position:
                        continue
                    code = str(position[0])
                    if body_for_profile(person[3], code) != "maestros":
                        continue
                    while len(position) < 10:
                        position.append(None)
                    all_counts[code] += 1
                    position[3] = all_counts[code]
                    position[4] = active_counts[code] + 1
                    if status != "D":
                        active_counts[code] += 1
                    self.current_status_by_profile[(person_index, position_index)] = status

        secondary = latest.get("secundaria")
        if secondary is not None:
            snapshot_dates.append(str(getattr(secondary, "published_date", "") or ""))
            refs = sorted(
                (ref for ref in self.profile_refs if ref["body"] == "secundaria"),
                key=lambda ref: (
                    ref["specialty_code"],
                    ref["after_order"] if ref["after_order"] is not None else ref["initial_order"],
                    ref["person_index"],
                ),
            )
            by_name_code: dict[tuple[str, str], deque[int]] = defaultdict(deque)
            by_compact_code: dict[tuple[str, str], deque[int]] = defaultdict(deque)
            for ref_index, ref in enumerate(refs):
                key = (ref["specialty_code"], normalized_name(ref["official_name"]))
                by_name_code[key].append(ref_index)
                compact_key = (ref["specialty_code"], compact_name(ref["official_name"]))
                by_compact_code[compact_key].append(ref_index)

            raw_statuses = list(getattr(secondary, "statuses", []))
            grouped_statuses: dict[tuple[str, str], list[object]] = defaultdict(list)
            for record in raw_statuses:
                code = str(self._status_value(record, "specialty_code", "") or "")
                name = candidate_name(self._status_value(record, "candidate_name", ""))
                grouped_statuses[(code, normalized_name(name))].append(record)
            profile_counts = {
                key: len(queue)
                for key, queue in by_name_code.items()
            }
            valid_assignments = {
                (
                    str(getattr(assignment, "specialty_code", "") or ""),
                    normalized_name(candidate_name(getattr(assignment, "candidate_name", ""))),
                    int(getattr(assignment, "cut", 0) or 0),
                )
                for assignment in getattr(secondary, "assignments", [])
            }
            statuses: list[object] = []
            ignored_duplicates = 0
            for key, records in grouped_statuses.items():
                limit = max(1, profile_counts.get(key, 0))
                if len(records) <= limit:
                    statuses.extend(records)
                    continue
                exact_awards = [
                    record
                    for record in records
                    if (
                        key[0],
                        key[1],
                        int(self._status_value(record, "position", 0) or 0),
                    ) in valid_assignments
                ]
                non_awards = sorted(
                    (
                        record
                        for record in records
                        if str(self._status_value(record, "status", "N") or "N") != "A"
                    ),
                    key=lambda record: int(self._status_value(record, "position", 0) or 0),
                    reverse=True,
                )
                preferred: list[object] = []
                for record in [*exact_awards, *non_awards, *records]:
                    if record not in preferred:
                        preferred.append(record)
                statuses.extend(preferred[:limit])
                ignored_duplicates += len(records) - limit

            matched_rows: list[tuple[str, int, int, str]] = []
            used: set[int] = set()
            statuses = sorted(
                statuses,
                key=lambda item: (
                    str(self._status_value(item, "specialty_code", "") or ""),
                    int(self._status_value(item, "position", 0) or 0),
                ),
            )
            report["secondary_statuses_raw"] = len(raw_statuses)
            report["secondary_statuses"] = len(statuses)
            report["secondary_cross_specialty_duplicates_ignored"] = ignored_duplicates
            for record in statuses:
                code = str(self._status_value(record, "specialty_code", "") or "")
                name = candidate_name(self._status_value(record, "candidate_name", ""))
                ref_index = self._take_unused(by_name_code.get((code, normalized_name(name))), used)
                if ref_index is None:
                    ref_index = self._take_unused(by_compact_code.get((code, compact_name(name))), used)
                if ref_index is None:
                    continue
                ref = refs[ref_index]
                order = int(self._status_value(record, "position", 0) or 0)
                status = str(self._status_value(record, "status", "N") or "N")
                position = self.positions["people"][ref["person_index"]][2][ref["position_index"]]
                while len(position) < 10:
                    position.append(None)
                position[3] = order
                matched_rows.append((code, order, ref_index, status))
                profile_key = (ref["person_index"], ref["position_index"])
                self.current_secondary_profiles.add(profile_key)
                self.current_status_by_profile[profile_key] = status
            report["secondary_matched"] = len(matched_rows)
            if statuses and len(matched_rows) / len(statuses) < 0.95:
                raise RuntimeError(
                    "La lista continua de Secundaria no coincide de forma segura con la bolsa: "
                    f"{len(matched_rows)}/{len(statuses)}"
                )

            active_counts: defaultdict[str, int] = defaultdict(int)
            for code, _order, ref_index, status in sorted(matched_rows):
                ref = refs[ref_index]
                position = self.positions["people"][ref["person_index"]][2][ref["position_index"]]
                position[4] = active_counts[code] + 1
                if status != "D":
                    active_counts[code] += 1

        self.current_snapshot_date = max((date for date in snapshot_dates if date), default=None)
        if self.current_snapshot_date:
            self._sync_reference_metadata(latest, report)
            self._recalculate_current_english_positions(latest)
        return report

    def _sync_reference_metadata(self, latest: dict[str, object], report: dict[str, int]) -> None:
        academic_year = str(self.positions.get("academic_year") or "")
        self.positions["status"] = "adjudicacion_continua"
        self.positions["reference_stage"] = "adjudicacion_continua"
        self.positions["reference_date"] = self.current_snapshot_date
        self.positions["position_reference"] = {
            "kind": "adjudicacion_continua",
            "academic_year": academic_year,
            "date": self.current_snapshot_date,
        }
        details = self.positions.setdefault("adjudication_detail", {})
        details["current_stage"] = "adjudicacion_continua"
        details["current_date"] = self.current_snapshot_date
        details["future_continuous_ready"] = True
        status_metadata = self.positions.setdefault("adjudication_status", {})
        status_metadata["source_stage"] = "adjudicacion_continua"
        status_metadata["source_date"] = self.current_snapshot_date
        snapshot = self.positions.setdefault("continuous_snapshot", {})
        snapshot.update({
            "source_stage": "adjudicacion_continua",
            "source_date": self.current_snapshot_date,
            **report,
        })

        sources = list(self.positions.get("sources") or [])
        for body, parsed in latest.items():
            sha256 = str(getattr(parsed, "sha256", "") or "")
            source_url = str(getattr(parsed, "url", "") or "")
            filename_source = source_url.rsplit("#", 1)[-1] if "#" in source_url else source_url
            source = {
                "role": "continuous_adjudication",
                "body": "maestros" if body == "maestros" else "otros",
                "filename": filename_source.split("?")[0].rsplit("/", 1)[-1],
                "sha256": sha256,
                "date": str(getattr(parsed, "published_date", "") or ""),
                "statuses": len(getattr(parsed, "statuses", [])),
                "assignments": len(getattr(parsed, "assignments", [])),
            }
            sources = [
                item
                for item in sources
                if not (
                    isinstance(item, dict)
                    and item.get("role") == source["role"]
                    and item.get("body") == source["body"]
                    and item.get("sha256") == sha256
                )
            ]
            sources.append(source)
        self.positions["sources"] = sources
        self._update_last_awarded(latest.values())

    def _recalculate_current_english_positions(self, latest: dict[str, object]) -> None:
        metadata = self.positions.setdefault("english_requirement", {})
        master_totals: dict[str, int] = {}
        for code in MASTER_ENGLISH_TARGET_CODES:
            ordered: list[tuple[int, int, bool, bool]] = []
            for person_index in self.current_master_people:
                person = self.positions["people"][person_index]
                positions = {
                    str(position[0]): position
                    for position in person[2]
                    if isinstance(position, list) and position
                }
                position = positions.get(code)
                if position is None or position[3] is None:
                    continue
                while len(position) < 10:
                    position.append(None)
                has_english_specialty = "121" in positions
                accredited = normalized_name(person[1]) in self.accredited_names
                position[6] = None
                ordered.append((int(position[3]), person_index, has_english_specialty, accredited))
            ordered.sort()
            rank = 0
            for _order, person_index, has_english_specialty, accredited in ordered:
                contribution = int(has_english_specialty) + int(accredited)
                if not contribution:
                    continue
                rank += contribution
                position = next(
                    item
                    for item in self.positions["people"][person_index][2]
                    if str(item[0]) == code
                )
                position[6] = rank
            master_totals[code] = rank
        if master_totals:
            metadata["credential_entries_by_specialty"] = master_totals

        confirmed = {
            normalized_name(value)
            for value in metadata.get("secondary_assignment_confirmed_names", [])
            if value
        }
        targets = {
            str(code)
            for code in metadata.get("secondary_eligible_specialties", [])
            if str(code) != SECONDARY_ENGLISH_SPECIALTY_CODE
        }
        secondary = latest.get("secundaria")
        if secondary is not None:
            for assignment in getattr(secondary, "assignments", []):
                if getattr(assignment, "english_requirement", False) is not True:
                    continue
                code = str(getattr(assignment, "specialty_code", "") or "")
                if code and code != SECONDARY_ENGLISH_SPECIALTY_CODE:
                    targets.add(code)
                    confirmed.add(normalized_name(candidate_name(getattr(assignment, "candidate_name", ""))))

        secondary_totals: dict[str, int] = {}
        for code in sorted(targets):
            ordered: list[tuple[int, int, int]] = []
            for person_index, position_index in self.current_secondary_profiles:
                person = self.positions["people"][person_index]
                position = person[2][position_index]
                if str(position[0]) != code or position[3] is None:
                    continue
                while len(position) < 10:
                    position.append(None)
                position[6] = None
                has_english_specialty = any(
                    str(item[0]) == SECONDARY_ENGLISH_SPECIALTY_CODE
                    for item in person[2]
                    if isinstance(item, list) and item
                )
                eligible = (
                    has_english_specialty
                    or normalized_name(person[1]) in self.accredited_names
                    or normalized_name(person[1]) in confirmed
                )
                if eligible:
                    ordered.append((int(position[3]), person_index, position_index))
            ordered.sort()
            for rank, (_order, person_index, position_index) in enumerate(ordered, start=1):
                self.positions["people"][person_index][2][position_index][6] = rank
            secondary_totals[code] = len(ordered)
        if secondary_totals:
            metadata["secondary_credential_entries_by_specialty"] = secondary_totals
            metadata["secondary_eligible_specialties"] = sorted(targets)
            metadata["secondary_assignment_confirmed_names"] = sorted(confirmed)
            metadata["secondary_assignment_confirmed_count"] = len(confirmed)

    def _update_last_awarded(self, parsed_items: Iterable[object]) -> None:
        metadata = self.positions.get("last_awarded_by_specialty")
        if not isinstance(metadata, dict) or not isinstance(metadata.get("fields"), list):
            return
        fields = list(metadata["fields"])
        existing = {
            str(dict(zip(fields, row)).get("specialty_code") or ""): dict(zip(fields, row))
            for row in metadata.get("rows", [])
            if isinstance(row, list) and len(row) == len(fields)
        }
        assignments_by_code: dict[str, list[object]] = defaultdict(list)
        dates: list[str] = []
        for parsed in parsed_items:
            date = str(getattr(parsed, "published_date", "") or "")
            if date:
                dates.append(date)
            for assignment in getattr(parsed, "assignments", []):
                code = str(getattr(assignment, "specialty_code", "") or "")
                if code:
                    assignments_by_code[code].append(assignment)
        if not assignments_by_code:
            return
        source_date = max(dates) if dates else self.current_snapshot_date
        display_by_identity: dict[str, set[str]] = defaultdict(set)
        for person in self.positions.get("people", []):
            if isinstance(person, list) and len(person) > 1:
                display_by_identity[normalized_name(person[1])].add(str(person[0]))

        def display_for(assignment: object) -> str:
            identity = normalized_name(candidate_name(getattr(assignment, "candidate_name", "")))
            matches = display_by_identity.get(identity, set())
            if len(matches) == 1:
                return next(iter(matches))
            return display_candidate_name(getattr(assignment, "candidate_name", ""))

        for code, assignments in assignments_by_code.items():
            last = max(assignments, key=lambda item: int(getattr(item, "cut", 0) or 0))
            vacancies = [
                item for item in assignments if str(getattr(item, "placement_type", "") or "") == "vacante"
            ]
            non_english_vacancies = [
                item for item in vacancies if getattr(item, "english_requirement", False) is not True
            ]
            last_vacancy = max(vacancies, key=lambda item: int(getattr(item, "cut", 0) or 0)) if vacancies else None
            last_non_english = (
                max(non_english_vacancies, key=lambda item: int(getattr(item, "cut", 0) or 0))
                if non_english_vacancies
                else None
            )
            previous = existing.get(code, {})
            values = {
                "specialty_code": code,
                "body": "maestros" if str(getattr(last, "body", "") or "") == "maestros" else "otros",
                "position": int(getattr(last, "cut", 0) or 0),
                "placement_type": str(getattr(last, "placement_type", "") or ""),
                "display_name": display_for(last),
                "official_name": candidate_name(getattr(last, "candidate_name", "")),
                "last_vacancy_position": (
                    int(getattr(last_vacancy, "cut", 0) or 0)
                    if last_vacancy is not None
                    else previous.get("last_vacancy_position")
                ),
                "last_vacancy_display_name": (
                    display_for(last_vacancy)
                    if last_vacancy is not None
                    else previous.get("last_vacancy_display_name", "")
                ),
                "last_vacancy_official_name": (
                    candidate_name(getattr(last_vacancy, "candidate_name", ""))
                    if last_vacancy is not None
                    else previous.get("last_vacancy_official_name", "")
                ),
                "source_stage": "adjudicacion_continua",
                "source_date": source_date,
                "english_requirement": getattr(last, "english_requirement", False) is True,
                "last_vacancy_english_requirement": (
                    getattr(last_vacancy, "english_requirement", False) is True
                    if last_vacancy is not None
                    else previous.get("last_vacancy_english_requirement", False)
                ),
                "last_non_english_vacancy_position": (
                    int(getattr(last_non_english, "cut", 0) or 0)
                    if last_non_english is not None
                    else previous.get("last_non_english_vacancy_position")
                ),
                "last_non_english_vacancy_display_name": (
                    display_for(last_non_english)
                    if last_non_english is not None
                    else previous.get("last_non_english_vacancy_display_name", "")
                ),
                "last_non_english_vacancy_official_name": (
                    candidate_name(getattr(last_non_english, "candidate_name", ""))
                    if last_non_english is not None
                    else previous.get("last_non_english_vacancy_official_name", "")
                ),
            }
            existing[code] = values

        metadata["rows"] = [
            [values.get(field) for field in fields]
            for _code, values in sorted(existing.items())
        ]
        metadata["source_stage"] = "acumulativo_inicio_y_durante_curso"
        metadata["source_date"] = source_date

    def _choose_profile(self, assignment: object, mode: str, existing_rows: list[dict]) -> dict | None:
        code = str(getattr(assignment, "specialty_code", "") or "")
        candidate = candidate_name(getattr(assignment, "candidate_name", ""))
        body = str(getattr(assignment, "body", "") or "")
        lookup_codes = [code]
        alias = MASTER_PROFILE_ALIASES.get(code) if body == "maestros" else None
        if alias and alias not in lookup_codes:
            lookup_codes.append(alias)
        candidates = []
        for lookup_code in lookup_codes:
            candidates = [
                ref
                for ref in self.by_identity_code.get((normalized_name(candidate), lookup_code), [])
                if ref["body"] == body
            ]
            if not candidates:
                candidates = [
                    ref
                    for ref in self.by_compact_code.get((compact_name(candidate), lookup_code), [])
                    if ref["body"] == body
                ]
            if candidates:
                break
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

    def master_specialty_position(self, assignment: object) -> int | None:
        if str(getattr(assignment, "body", "") or "") != "maestros":
            return None
        profile = self._choose_profile(assignment, "curso", self._rows_as_dicts())
        if profile is None:
            return None
        position = self.positions["people"][profile["person_index"]][2][profile["position_index"]]
        try:
            return int(position[3]) if len(position) > 3 and position[3] is not None else None
        except (TypeError, ValueError):
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
                "specialty_code": profile["specialty_code"] if profile is not None else code,
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
                "workload": getattr(assignment, "workload", None),
                "english_requirement": getattr(assignment, "english_requirement", False) is True,
                "itinerant": getattr(assignment, "itinerant", False) is True,
                "center_name": str(getattr(assignment, "center_name", "") or ""),
                "locality": str(getattr(assignment, "locality", "") or ""),
                "observations": str(getattr(assignment, "observations", "") or ""),
            })
        return resolved, dict(skipped)

    def apply(self, parsed_items: Iterable[object], mode: str) -> bool:
        if not self.enabled:
            return False
        parsed_items = list(parsed_items)
        changed = False
        reset_bodies: set[str] = set()
        positions_year = normalized_academic_year(self.positions.get("academic_year"))
        snapshot_items = [
            parsed
            for parsed in parsed_items
            if academic_year_for_date(getattr(parsed, "published_date", None)) == positions_year
            and getattr(parsed, "statuses", None)
        ]
        if mode == "curso" and snapshot_items:
            changed = self._ensure_assignment_profiles(snapshot_items) or changed
            self._build_profile_index()
            report = self._sync_status_snapshots(snapshot_items)
            self._build_profile_index()
            if report["master_matched"] or report["secondary_matched"]:
                changed = True
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
            if mode == "curso" and str(published_date or "") == str(self.current_snapshot_date or ""):
                self.current_assignment_profiles.update(
                    (int(row["person_index"]), int(row["position_index"]))
                    for row in resolved
                    if int(row["person_index"]) >= 0 and int(row["position_index"]) >= 0
                )
            body = str(getattr(parsed, "body", "") or "")
            if mode == "inicio":
                existing = [row for row in existing if row["body"] != body]
                reset_bodies.add(body)

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
            self._sync_adjudication_details(reset_bodies)
            self.dirty = True
        return changed

    def _sync_adjudication_details(self, reset_bodies: set[str]) -> None:
        for ref in self.profile_refs:
            if ref["body"] not in reset_bodies:
                continue
            position = self.positions["people"][ref["person_index"]][2][ref["position_index"]]
            while len(position) < 10:
                position.append(None)
            if position[8] == "A":
                position[8] = "N"
            position[9] = None

        for (person_index, position_index), raw_status in self.current_status_by_profile.items():
            position = self.positions["people"][person_index][2][position_index]
            while len(position) < 10:
                position.append(None)
            position[8] = "N" if raw_status == "A" else raw_status
            position[9] = None

        for row in self._rows_as_dicts():
            person_index = int(row.get("person_index", -1))
            position_index = int(row.get("position_index", -1))
            workload = row.get("workload")
            if person_index < 0 or position_index < 0 or workload is None:
                continue
            profile_key = (person_index, position_index)
            if profile_key in self.current_status_by_profile:
                if profile_key not in self.current_assignment_profiles:
                    continue
                if str(row.get("published_date") or "") != str(self.current_snapshot_date or ""):
                    continue
            position = self.positions["people"][person_index][2][position_index]
            while len(position) < 10:
                position.append(None)
            position[8] = "A"
            position[9] = [
                "C" if row.get("mode") == "curso" else "I",
                str(row.get("published_date") or ""),
                str(row.get("placement_type") or ""),
                workload,
                str(row.get("center_code") or ""),
                row.get("english_requirement") is True,
                row.get("itinerant") is True,
                str(row.get("center_name") or ""),
                str(row.get("locality") or ""),
                str(row.get("observations") or ""),
            ]

        self.positions["schema_version"] = max(9, int(self.positions.get("schema_version") or 0))
        details = self.positions.setdefault("adjudication_details", {})
        details["version"] = max(2, int(details.get("version") or 0))
        details["position_index"] = 9
        details["fields"] = [
            "stage",
            "date",
            "placement_type",
            "workload",
            "center_code",
            "english_requirement",
            "itinerant",
            "center_name",
            "municipality",
            "observations",
        ]
        details["workload_full_time_code"] = "C"
        details["continuous_policy"] = "La adjudicacion mas reciente de la misma persona y especialidad sustituye el detalle anterior."

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
