from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import html.parser
import io
import json
import os
import re
import socket
import ssl
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import pdfplumber
from pypdf import PdfReader

from build_bolsa_dataset import (
    FPA_PRIMARY,
    MASTER_FLAGS,
    MASTER_SPECIALTIES,
    build_specialties,
    clean_official_name,
    display_name,
    identity_key,
    normalize_name,
)
from build_bolsa_dataset_v5 import merge_people_v4
from update_adjudicaciones import (
    Adjudication,
    classify_body,
    clean,
    detect_english_requirement,
    detect_itinerant,
    detect_placement_type,
    detect_workload,
    parse_date_from_text,
    secondary_page_specialty,
)


PARTICIPANTS_URL = "https://ceice.gva.es/es/web/rrhh-educacion/participantes2"
ACCREDITATIONS_URL = "https://ceice.gva.es/es/web/rrhh-educacion/listados-definitivos"
DEFAULT_POSITIONS_PATH = Path("data/posiciones_bolsa.json")
DEFAULT_CUTS_PATH = Path("data/adjudicaciones.json")
DEFAULT_ACCREDITATIONS_PATH = Path("data/english_accreditations.json.gz")
DEFAULT_STATE_PATH = Path("data/source_monitor_state.json")
DEFAULT_GENDER_PATH = Path("data/gender_first_name_map.json")
ENGLISH_TARGET_CODES = ("120", "123", "124", "126", "127", "128", "153")
MASTER_CODES = frozenset({"120", "121", "122", "123", "124", "126", "127", "128", "151", "152", "153"})
PROVINCES = ("alicante", "valencia", "castellon")
PROVINCE_BY_PREFIX = {"03": 0, "46": 1, "12": 2}
VALID_LEVELS = {"B2": 2, "C1": 3, "C2": 4}
POSITION_FIELDS = [
    "specialty_code",
    "position_at_course_start",
    "position_without_deactivated",
    "position_after_adjudication",
    "position_after_adjudication_without_deactivated",
    "position_reference",
    "english_requirement_position",
    "additional_information",
    "adjudication_status",
    "adjudication_detail",
]
DETAIL_FIELDS = [
    "stage",
    "date",
    "placement_type",
    "workload",
    "center_code",
    "english_requirement",
    "itinerant",
    "center_name",
    "municipality",
]


class SourceAccessError(RuntimeError):
    pass


class SourceValidationError(RuntimeError):
    pass


class LinkParser(html.parser.HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[dict[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = urllib.parse.urljoin(self.base_url, href)
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append(
                {"url": self._href, "text": clean(" ".join(self._text))}
            )
            self._href = None
            self._text = []


def normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", text.lower()).strip()


def canonical_url(value: str) -> str:
    return value.split("#", 1)[0]


def positive_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def http_get(url: str) -> bytes:
    timeout = positive_float("SOURCE_HTTP_TIMEOUT_SECONDS", 90)
    attempts = int(positive_float("SOURCE_HTTP_ATTEMPTS", 3))
    delay = positive_float("SOURCE_HTTP_RETRY_DELAY_SECONDS", 20)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "AdjudicApp/1.0 (+https://github.com/franciscotcp-boop/gva-cortes)",
                "Accept": "text/html,application/pdf,application/octet-stream;q=0.9,*/*;q=0.5",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            socket.timeout,
            ssl.SSLError,
        ) as error:
            last_error = error
            if attempt < attempts:
                print(
                    f"WARNING: intento {attempt}/{attempts} fallido para {url}: {error}",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(delay * attempt)
    raise SourceAccessError(f"Conselleria no responde tras {attempts} intentos: {url}: {last_error}")


def extract_links(page_url: str) -> list[dict[str, str]]:
    parser = LinkParser(page_url)
    parser.feed(http_get(page_url).decode("utf-8", errors="replace"))
    seen: set[str] = set()
    output: list[dict[str, str]] = []
    for link in parser.links:
        url = canonical_url(link["url"])
        if url in seen:
            continue
        seen.add(url)
        output.append({"url": url, "text": link.get("text", "")})
    return output


def is_pdf_link(link: dict[str, str]) -> bool:
    return ".pdf" in urllib.parse.unquote(link.get("url", "")).lower()


def position_document(link: dict[str, str]) -> tuple[str, int] | None:
    url = urllib.parse.unquote(link.get("url", ""))
    combined = normalized(f"{link.get('text', '')} {url}")
    filename = normalized(url.rsplit("/", 1)[-1])
    looks_like_list = bool(
        re.search(r"par[^a-z0-9]*pro[^a-z0-9]*int[^a-z0-9]*lis", filename)
        or ("listado provisional" in combined and "bolsa" in combined)
        or ("llista provisional" in combined and "bors" in combined)
    )
    if not is_pdf_link(link) or not looks_like_list:
        return None
    if re.search(r"(?:^|[_\W])mae(?:[_\W]|$)", filename) or "cos de mestres" in combined or "cuerpo de maestros" in combined:
        body = "maestros"
    elif re.search(r"(?:^|[_\W])sec(?:[_\W]|$)", filename) or "altres cossos" in combined or "otros cuerpos" in combined:
        body = "secundaria"
    else:
        return None
    year_match = re.search(r"ini[_\W]?(20\d{2})", combined)
    if not year_match:
        course_match = re.search(r"(20\d{2})\s*[/_-]\s*(20\d{2})", combined)
        if not course_match:
            return None
        year = int(course_match.group(1))
    else:
        year = int(year_match.group(1))
    return body, year


def select_position_pair(
    links: Iterable[dict[str, str]], target_year: int | None = None
) -> tuple[int, dict[str, dict[str, str]]] | None:
    grouped: dict[int, dict[str, dict[str, str]]] = defaultdict(dict)
    for link in links:
        classification = position_document(link)
        if classification:
            body, year = classification
            grouped[year][body] = link
    years = [year for year, bodies in grouped.items() if {"maestros", "secundaria"} <= set(bodies)]
    if target_year is not None:
        years = [year for year in years if year == target_year]
    if not years:
        return None
    year = max(years)
    return year, grouped[year]


def pdf_text_pages(pdf_bytes: bytes) -> tuple[list[str], int]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return pages, len(reader.pages)


def parse_master_position_list(pdf_bytes: bytes) -> tuple[list[dict], dict[str, int], int]:
    pages, page_count = pdf_text_pages(pdf_bytes)
    rows: list[dict] = []
    counters: Counter[str] = Counter()
    expected = 1
    row_pattern = re.compile(r"^(\d+)\s*(.+?)\s*(?:AMB|SENSE)\s+SERVEIS(.*)$")
    for page_number, text in enumerate(pages, 1):
        for raw_line in text.splitlines():
            line = clean(raw_line)
            match = row_pattern.match(line)
            if not match:
                continue
            position = int(match.group(1))
            if position != expected:
                raise SourceValidationError(
                    f"Lista de Maestros incompleta: se esperaba {expected} y aparece {position} en la pagina {page_number}"
                )
            expected += 1
            official = clean_official_name(match.group(2))
            tail = match.group(3)
            flags = [flag for flag in MASTER_FLAGS if re.search(rf"\b{flag}\b", tail)]
            if not flags:
                raise SourceValidationError(f"Maestros {position} sin especialidad: {official}")
            positions: list[tuple[str, int]] = []
            for flag in flags:
                counters[flag] += 1
                code = MASTER_SPECIALTIES[flag][0]
                positions.append((code, counters[flag]))
                if flag == "PRI":
                    positions.append((FPA_PRIMARY[0], counters[flag]))
            rows.append(
                {
                    "official_name": official,
                    "display_name": display_name(official),
                    "global_position": position,
                    "positions": positions,
                    "page": page_number,
                }
            )
    if len(rows) < 1000:
        raise SourceValidationError(f"Lista de Maestros demasiado corta: {len(rows)} filas")
    return rows, dict(counters), page_count


def secondary_header(text: str) -> tuple[str, str] | None:
    for raw_line in text.splitlines():
        line = clean(raw_line)
        match = re.search(r"\(([0-9A-Z]{3})\)\s*(.+)$", line)
        if match:
            return match.group(1), clean(match.group(2))
    return None


def parse_secondary_position_list(
    pdf_bytes: bytes,
) -> tuple[list[dict], dict[str, str], int]:
    pages, page_count = pdf_text_pages(pdf_bytes)
    rows: list[dict] = []
    specialties: dict[str, str] = {}
    last: dict[str, int] = {}
    row_pattern = re.compile(r"^(\d+)\s*(.+?)\s*(?:AMB|SENSE)\s+SERVEIS(.*)$")
    for page_number, text in enumerate(pages, 1):
        header = secondary_header(text)
        if not header:
            continue
        code, specialty_name = header
        specialties.setdefault(code, specialty_name)
        for raw_line in text.splitlines():
            line = clean(raw_line)
            match = row_pattern.match(line)
            if not match:
                continue
            position = int(match.group(1))
            expected = last.get(code, 0) + 1
            if position != expected:
                raise SourceValidationError(
                    f"Lista de Secundaria {code} incompleta: se esperaba {expected} y aparece {position} en la pagina {page_number}"
                )
            last[code] = position
            rows.append(
                {
                    "official_name": clean_official_name(match.group(2)),
                    "display_name": display_name(clean_official_name(match.group(2))),
                    "specialty_code": code,
                    "position": position,
                    "disabled_habilitation": "(*)" in match.group(3),
                    "page": page_number,
                }
            )
    if len(rows) < 1000 or len(specialties) < 20:
        raise SourceValidationError(
            f"Lista de Secundaria demasiado corta: {len(rows)} filas y {len(specialties)} especialidades"
        )
    return rows, specialties, page_count


@dataclass
class AwardPdf:
    body: str
    published_date: str | None
    pages: int
    statuses: list[dict]
    assignments: list[Adjudication]


def block_status(block: list[str]) -> str:
    text = normalized(" ".join(block))
    if "desactivat" in text or "desactivado" in text or "desactivada" in text:
        return "D"
    if "ha participat" in text or "ha participado" in text:
        return "P"
    if re.search(r"\bno\s+adjudicat", text) or re.search(r"\bno\s+adjudicad", text):
        return "N"
    if re.search(r"\badjudicat\b", text) or re.search(r"\badjudicad[oa]\b", text):
        return "A"
    return "N"


def detection_block(block: list[str]) -> list[str]:
    """Restore separators that pypdf can omit between adjacent labels."""

    return [
        re.sub(
            r"(?i)(vacant(?:e)?)(itinerant(?:e)?)",
            r"\1 \2",
            item,
        )
        for item in block
    ]


def parse_award_pdf(pdf_bytes: bytes) -> AwardPdf:
    pages, page_count = pdf_text_pages(pdf_bytes)
    preview = "\n".join(pages[:3])
    body = classify_body(preview)
    if body is None:
        raise SourceValidationError("El PDF de adjudicacion no identifica el cuerpo docente")
    published_date = parse_date_from_text(preview)
    statuses: list[dict] = []
    assignments: list[Adjudication] = []
    # pypdf sometimes joins the printed position and surname ("13501CABEDO...").
    cut_line_pattern = re.compile(r"^(\d{1,5})(?:\s*/\s*\d{1,5})?\s*(.*)$")
    center_pattern = re.compile(r"^(.+?)\((\d{8})\)(.+)$")
    specialty_pattern = re.compile(r"^([0-9A-Z]{3})\s*/\s*(.+)$")
    status_words = {
        "D": ("desactivat", "desactivado", "desactivada"),
        "N": (
            "no adjudicat",
            "no adjudicado",
            "no adjudicada",
            "no ha participat",
            "no ha participado",
        ),
        "P": ("ha participat", "ha participado"),
        "A": ("adjudicat", "adjudicado", "adjudicada"),
    }

    def status_code(line: str) -> str | None:
        value = normalized(line)
        for code, words in status_words.items():
            if any(value == word or value.startswith(word + " ") for word in words):
                return code
        return None

    for page_number, text in enumerate(pages, 1):
        page_specialty = secondary_page_specialty(text) if body == "secundaria" else None
        if body == "secundaria" and page_specialty is None:
            continue
        lines = [clean(line) for line in text.splitlines() if clean(line)]
        previous_status = -1
        for index, line in enumerate(lines):
            status = status_code(line)
            if status is None:
                continue
            segment = lines[previous_status + 1 : index]
            previous_status = index
            cut_index = None
            cut = None
            inline_name = ""
            for segment_index, candidate in enumerate(segment):
                match = cut_line_pattern.match(candidate)
                if not match:
                    continue
                # Exclude dates and page counters while accepting rows such as 9/1 NAME.
                if candidate.count("/") > 1:
                    continue
                cut_index = segment_index
                cut = int(match.group(1))
                inline_name = clean(match.group(2) or "")
                break
            if cut is None or cut_index is None:
                continue
            official = inline_name if "," in inline_name else ""
            if not official:
                for candidate in reversed(segment[cut_index + 1 :]):
                    if "," not in candidate:
                        continue
                    official = re.split(
                        r"(?:Petici.n\s*:|Voluntaria\b|Obligat.ria\b|PREFER.NCIA\b)",
                        candidate,
                        maxsplit=1,
                        flags=re.IGNORECASE,
                    )[0]
                    official = clean(official)
                    break
            if not official:
                continue
            statuses.append(
                {
                    "official_name": official,
                    "identity": identity_key(official),
                    "specialty_code": page_specialty[0] if page_specialty else None,
                    "printed_position": cut,
                    "deactivated": status == "D",
                    "raw_status": status,
                    "page": page_number,
                }
            )
            if status != "A":
                continue
            center_match = next((center_pattern.match(item) for item in segment if center_pattern.match(item)), None)
            specialty_match = next((specialty_pattern.match(item) for item in segment if specialty_pattern.match(item)), None)
            if center_match is None or specialty_match is None:
                continue
            assigned_code = specialty_match.group(1)
            if body == "secundaria":
                if page_specialty is None or assigned_code != page_specialty[0]:
                    continue
                specialty_code, specialty_name = page_specialty
            else:
                specialty_code, specialty_name = assigned_code, clean(specialty_match.group(2))
            detection_segment = detection_block(segment)
            assignments.append(
                Adjudication(
                    cut=cut,
                    candidate_name=official,
                    center_code=center_match.group(2),
                    specialty_code=specialty_code,
                    specialty_name=specialty_name,
                    center_name=clean(center_match.group(3)),
                    locality=clean(center_match.group(1)),
                    body=body,
                    placement_type=detect_placement_type(detection_segment),
                    english_requirement=detect_english_requirement(detection_segment, body),
                    workload=detect_workload(detection_segment),
                    itinerant=detect_itinerant(detection_segment),
                )
            )
    if len(statuses) < 1000:
        raise SourceValidationError(
            f"PDF de adjudicacion {body} incompleto: solo {len(statuses)} estados"
        )
    return AwardPdf(body, published_date, page_count, statuses, assignments)


def attach_statuses(
    master_rows: list[dict],
    secondary_rows: list[dict],
    master_award: AwardPdf | None,
    secondary_award: AwardPdf | None,
) -> None:
    if master_award:
        by_name: dict[str, deque[dict]] = defaultdict(deque)
        by_compact_name: dict[str, deque[dict]] = defaultdict(deque)
        used_master_statuses: set[int] = set()
        for record in sorted(master_award.statuses, key=lambda item: item["printed_position"]):
            by_name[record["identity"]].append(record)
            by_compact_name[record["identity"].replace(" ", "")].append(record)
        for row in master_rows:
            queue = by_name.get(identity_key(row["official_name"]))
            while queue and id(queue[0]) in used_master_statuses:
                queue.popleft()
            if not queue:
                queue = by_compact_name.get(identity_key(row["official_name"]).replace(" ", ""))
                while queue and id(queue[0]) in used_master_statuses:
                    queue.popleft()
            if queue:
                record = queue.popleft()
                used_master_statuses.add(id(record))
                row["adjudication_position"] = record["printed_position"]
                row["adjudication_deactivated"] = record["deactivated"]
                row["raw_status"] = record["raw_status"]

    post_counts: Counter[str] = Counter()
    post_active: Counter[str] = Counter()
    for row in sorted(
        (item for item in master_rows if item.get("adjudication_position") is not None),
        key=lambda item: int(item["adjudication_position"]),
    ):
        row["post_positions"] = {}
        row["post_active_positions"] = {}
        for code, _position in row["positions"]:
            post_counts[code] += 1
            row["post_positions"][code] = post_counts[code]
            row["post_active_positions"][code] = post_active[code] + 1
            if not row.get("adjudication_deactivated"):
                post_active[code] += 1

    initial_active: Counter[str] = Counter()
    for row in master_rows:
        enhanced = []
        for code, initial in row["positions"]:
            post_without = row.get("post_active_positions", {}).get(code)
            compatible = post_without if post_without is not None else initial_active[code] + 1
            enhanced.append(
                (
                    code,
                    initial,
                    compatible,
                    row.get("post_positions", {}).get(code),
                    post_without,
                )
            )
            if not row.get("adjudication_deactivated"):
                initial_active[code] += 1
        row["enhanced_positions"] = enhanced
        row["master_general_positions"] = (
            row["global_position"],
            row.get("adjudication_position"),
        )

    if secondary_award:
        by_key: dict[tuple[str, str], deque[dict]] = defaultdict(deque)
        by_compact_key: dict[tuple[str, str], deque[dict]] = defaultdict(deque)
        used_secondary_statuses: set[int] = set()
        for record in sorted(
            secondary_award.statuses,
            key=lambda item: (str(item.get("specialty_code") or ""), int(item["printed_position"])),
        ):
            code = str(record.get("specialty_code") or "")
            if code:
                by_key[(code, record["identity"])].append(record)
                by_compact_key[(code, record["identity"].replace(" ", ""))].append(record)
        for row in secondary_rows:
            key = (row["specialty_code"], identity_key(row["official_name"]))
            queue = by_key.get(key)
            while queue and id(queue[0]) in used_secondary_statuses:
                queue.popleft()
            if not queue:
                compact_key = (row["specialty_code"], key[1].replace(" ", ""))
                queue = by_compact_key.get(compact_key)
                while queue and id(queue[0]) in used_secondary_statuses:
                    queue.popleft()
            if queue:
                record = queue.popleft()
                used_secondary_statuses.add(id(record))
                row["adjudication_position"] = record["printed_position"]
                row["adjudication_deactivated"] = record["deactivated"]
                row["raw_status"] = record["raw_status"]

    post_active_secondary: Counter[str] = Counter()
    ordered_secondary = sorted(
        (row for row in secondary_rows if row.get("adjudication_position") is not None),
        key=lambda row: (row["specialty_code"], int(row["adjudication_position"])),
    )
    for row in ordered_secondary:
        code = row["specialty_code"]
        row["post_without_deactivated"] = post_active_secondary[code] + 1
        if not row.get("adjudication_deactivated"):
            post_active_secondary[code] += 1

    initial_active_secondary: Counter[str] = Counter()
    for row in secondary_rows:
        code = row["specialty_code"]
        row["effective_position"] = row["position"]
        row["post_adjudication_position"] = row.get("adjudication_position")
        post_without = row.get("post_without_deactivated")
        row["without_deactivated"] = (
            post_without if post_without is not None else initial_active_secondary[code] + 1
        )
        disabled = (
            bool(row.get("adjudication_deactivated"))
            if row.get("adjudication_position") is not None
            else bool(row.get("disabled_habilitation"))
        )
        if not disabled:
            initial_active_secondary[code] += 1


def prior_person_maps(data: dict) -> tuple[dict[str, str], dict[str, str]]:
    display: dict[str, str] = {}
    gender: dict[str, str] = {}
    for person in data.get("people", []):
        if not isinstance(person, list) or len(person) < 2:
            continue
        key = identity_key(person[1])
        display.setdefault(key, str(person[0]))
        if len(person) > 5 and person[5] in {"m", "f", "u"}:
            gender.setdefault(key, person[5])
    return display, gender


def infer_gender(official_name: str, gender_map: dict[str, str], previous: str | None) -> str:
    if previous in {"m", "f"}:
        return previous
    given = official_name.split(",", 1)[1] if "," in official_name else official_name
    given = re.sub(r"^M[ªA]\b", "MARIA", given, flags=re.IGNORECASE)
    for token in given.split():
        key = re.sub(r"[^A-Z]", "", normalized(token).upper())
        value = gender_map.get(key)
        if value in {"m", "f"}:
            return value
    return "u"


def add_english_positions(data: dict, accredited_names: set[str]) -> dict[str, int]:
    state: dict[int, tuple[dict[str, list], bool, bool]] = {}
    for person_index, person in enumerate(data["people"]):
        positions = {str(position[0]): position for position in person[2]}
        is_master = isinstance(person[4], list)
        if is_master:
            state[person_index] = (
                positions,
                "121" in positions,
                identity_key(person[1]) in accredited_names,
            )
    totals: dict[str, int] = {}
    for code in ENGLISH_TARGET_CODES:
        ordered = []
        for person_index, (positions, has_121, accredited) in state.items():
            position = positions.get(code)
            if not position or len(position) < 4 or position[3] is None:
                continue
            ordered.append((int(position[3]), person_index, has_121, accredited))
        ordered.sort()
        rank = 0
        for _order, person_index, has_121, accredited in ordered:
            contribution = int(has_121) + int(accredited)
            if not contribution:
                continue
            rank += contribution
            state[person_index][0][code][6] = rank
        totals[code] = rank
    return totals


def center_lookup(cuts: dict) -> dict[str, tuple[str, str]]:
    output = {}
    for row in cuts.get("centers", []):
        if isinstance(row, list) and len(row) >= 12:
            output[str(row[0])] = (str(row[1]), str(row[11]))
    return output


def assignment_key(assignment: Adjudication) -> tuple[str, str, int]:
    return assignment.body, assignment.specialty_code, int(assignment.cut)


def enrich_status_details_and_context(
    data: dict,
    master_rows: list[dict],
    secondary_rows: list[dict],
    assignments: list[Adjudication],
    published_date: str | None,
    centers: dict[str, tuple[str, str]],
) -> None:
    assignment_map = {assignment_key(item): item for item in assignments}
    master_status = {
        (identity_key(row["official_name"]), row.get("adjudication_position")): row.get("raw_status", "N")
        for row in master_rows
        if row.get("adjudication_position") is not None
    }
    secondary_status = {
        (row["specialty_code"], identity_key(row["official_name"]), row.get("adjudication_position")): row.get("raw_status", "N")
        for row in secondary_rows
        if row.get("adjudication_position") is not None
    }
    secondary_disabled = {
        (row["specialty_code"], identity_key(row["official_name"]), row["position"])
        for row in secondary_rows
        if row.get("disabled_habilitation")
    }
    award_events: dict[str, list[tuple[int, int]]] = defaultdict(list)

    for person in data["people"]:
        identity = identity_key(person[1])
        for position in person[2]:
            code = str(position[0])
            is_master = isinstance(person[4], list) and code in MASTER_CODES
            cut = person[4][1] if is_master and person[4] else position[3]
            assignment_body = "maestros" if is_master else "secundaria"
            assignment = (
                assignment_map.get((assignment_body, code, int(cut)))
                if cut is not None
                else None
            )
            if not is_master and (code, identity, int(position[1])) in secondary_disabled:
                status = "H"
            elif assignment:
                status = "A"
            elif is_master:
                raw_status = master_status.get((identity, cut), "N")
                status = "N" if raw_status == "A" else raw_status
            else:
                raw_status = secondary_status.get((code, identity, cut), "N")
                status = "N" if raw_status == "A" else raw_status
            position[8] = status if status in {"A", "N", "P", "D", "H"} else "N"
            if assignment:
                center_name, municipality = centers.get(
                    assignment.center_code,
                    (assignment.center_name, assignment.locality),
                )
                position[9] = [
                    "I",
                    published_date,
                    assignment.placement_type,
                    assignment.workload,
                    assignment.center_code,
                    bool(assignment.english_requirement),
                    bool(assignment.itinerant),
                    center_name,
                    municipality,
                ]
                order = position[3] if position[3] is not None else position[1]
                province = PROVINCE_BY_PREFIX.get(assignment.center_code[:2])
                if province is not None:
                    award_events[code].append((int(order), province))

    for events in award_events.values():
        events.sort()
    for person in data["people"]:
        for position in person[2]:
            code = str(position[0])
            order = position[3] if position[3] is not None else position[1]
            counts = [0, 0, 0]
            for event_order, province in award_events.get(code, []):
                if event_order >= int(order):
                    break
                counts[province] += 1
            position[7] = counts + [None, None]


def last_awarded_rows(data: dict) -> dict:
    fields = [
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
        "english_requirement",
        "last_vacancy_english_requirement",
        "last_non_english_vacancy_position",
        "last_non_english_vacancy_display_name",
        "last_non_english_vacancy_official_name",
    ]
    records: dict[str, list[tuple[int, list, list]]] = defaultdict(list)
    for person in data["people"]:
        for position in person[2]:
            if position[8] == "A" and position[9]:
                order = position[3] if position[3] is not None else position[1]
                records[str(position[0])].append((int(order), person, position))
    rows = []
    for code, items in sorted(records.items()):
        items.sort(key=lambda item: item[0])
        last = items[-1]
        vacancies = [item for item in items if item[2][9][2] == "vacante"]
        non_english = [item for item in vacancies if not item[2][9][5]]
        vacancy = vacancies[-1] if vacancies else None
        plain = non_english[-1] if non_english else None
        body = "maestros" if code in MASTER_CODES and isinstance(last[1][4], list) else "otros"
        rows.append(
            [
                code,
                body,
                last[0],
                last[2][9][2],
                last[1][0],
                last[1][1],
                vacancy[0] if vacancy else None,
                vacancy[1][0] if vacancy else "",
                vacancy[1][1] if vacancy else "",
                "inicio_curso",
                data.get("reference_date"),
                bool(last[2][9][5]),
                bool(vacancy and vacancy[2][9][5]),
                plain[0] if plain else None,
                plain[1][0] if plain else "",
                plain[1][1] if plain else "",
            ]
        )
    return {
        "fields": fields,
        "rows": rows,
        "source_stage": "inicio_curso",
        "source_date": data.get("reference_date"),
        "secondary_rule": "Solo cuenta cuando coinciden la especialidad del encabezado y la plaza adjudicada",
        "masters_rule": "Se selecciona la mayor posicion adjudicada de cada especialidad",
        "masters_english_requirement_rule": "La marca procede del literal / ING. del bloque adjudicado",
    }


def accreditation_names(payload: dict) -> set[str]:
    return {
        identity_key(row.get("official_name", ""))
        for row in payload.get("records", [])
        if row.get("official_name")
    }


def build_positions_dataset(
    previous: dict,
    cuts: dict,
    accreditations: dict,
    master_pdf: bytes,
    secondary_pdf: bytes,
    year: int,
    sources: dict[str, dict[str, str]],
    master_award_pdf: bytes | None = None,
    secondary_award_pdf: bytes | None = None,
) -> dict:
    master_rows, master_counts, master_pages = parse_master_position_list(master_pdf)
    secondary_rows, secondary_names, secondary_pages = parse_secondary_position_list(secondary_pdf)
    master_award = parse_award_pdf(master_award_pdf) if master_award_pdf else None
    secondary_award = parse_award_pdf(secondary_award_pdf) if secondary_award_pdf else None
    attach_statuses(master_rows, secondary_rows, master_award, secondary_award)
    people = merge_people_v4(master_rows, secondary_rows)
    previous_display, previous_gender = prior_person_maps(previous)
    gender_map = load_json(DEFAULT_GENDER_PATH, {})
    for person in people:
        key = identity_key(person[1])
        if key in previous_display:
            person[0] = previous_display[key]
        for position in person[2]:
            while len(position) < 10:
                position.append(None)
            position[5] = None
            position[6] = None
            position[7] = [0, 0, 0, None, None]
            position[8] = "N"
            position[9] = None
        person.append(infer_gender(person[1], gender_map, previous_gender.get(key)))

    existing_map = {
        str(item.get("code")): {"es": item.get("es", ""), "va": item.get("va", "")}
        for item in previous.get("specialties", [])
    }
    specialties, unknown_specialties = build_specialties(secondary_names, existing_map)
    if unknown_specialties:
        print(f"WARNING: {len(unknown_specialties)} especialidades nuevas sin traduccion previa", file=sys.stderr)
    academic_year = f"{year}/{year + 1}"
    published_date = None
    assignments: list[Adjudication] = []
    award_sources = []
    if master_award and secondary_award:
        published_date = master_award.published_date or secondary_award.published_date
        assignments = master_award.assignments + secondary_award.assignments
        award_sources = [
            {
                "role": "deactivation_status",
                "body": "maestros",
                "sha256": hashlib.sha256(master_award_pdf or b"").hexdigest(),
                "pages": master_award.pages,
            },
            {
                "role": "deactivation_status",
                "body": "otros",
                "sha256": hashlib.sha256(secondary_award_pdf or b"").hexdigest(),
                "pages": secondary_award.pages,
            },
        ]
    if not published_date:
        published_date = date.today().isoformat()

    dataset = {
        "schema_version": 9,
        "dataset": "posiciones_bolsa",
        "academic_year": academic_year,
        "status": "listado",
        "reference_stage": "inicio_curso",
        "reference_date": published_date,
        "position_reference": {"kind": "listado", "academic_year": academic_year, "date": published_date},
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "sources": [
            {
                "role": "position_list",
                "body": "maestros",
                "filename": urllib.parse.unquote(sources["maestros"]["url"].rsplit("/", 1)[-1]),
                "url": sources["maestros"]["url"],
                "sha256": hashlib.sha256(master_pdf).hexdigest(),
                "pages": master_pages,
            },
            {
                "role": "position_list",
                "body": "otros",
                "filename": urllib.parse.unquote(sources["secundaria"]["url"].rsplit("/", 1)[-1]),
                "url": sources["secundaria"]["url"],
                "sha256": hashlib.sha256(secondary_pdf).hexdigest(),
                "pages": secondary_pages,
            },
            *award_sources,
        ],
        "calculation": copy.deepcopy(previous.get("calculation", {})),
        "specialties": specialties,
        "last_awarded_by_specialty": {"fields": [], "rows": []},
        "person_fields": ["display_name", "official_name", "positions", "source", "master_general_positions", "gender"],
        "master_general_position_fields": ["position_at_course_start", "position_after_adjudication"],
        "position_fields": list(POSITION_FIELDS),
        "people": people,
    }
    totals = add_english_positions(dataset, accreditation_names(accreditations))
    enrich_status_details_and_context(
        dataset,
        master_rows,
        secondary_rows,
        assignments,
        published_date,
        center_lookup(cuts),
    )
    dataset["last_awarded_by_specialty"] = last_awarded_rows(dataset)
    dataset["english_requirement"] = {
        "body": "maestros",
        "excluded_specialty": "121",
        "eligible_specialties": list(ENGLISH_TARGET_CODES),
        "calculation": "En el orden vigente se acumula una entrada por habilitacion 121 y otra por acreditacion B2/C1/C2",
        "accreditation_records": len(accreditations.get("records", [])),
        "accreditation_unique_names": len(accreditation_names(accreditations)),
        "credential_entries_by_specialty": totals,
        "accreditation_updated_at": accreditations.get("updated_at"),
    }
    dataset["additional_information"] = {
        "version": 1,
        "body_scope": ["maestros", "otros"],
        "source_stage": "inicio_curso",
        "source_date": published_date,
        "province_order": list(PROVINCES),
        "position_context_fields": [
            "ahead_current_alicante",
            "ahead_current_valencia",
            "ahead_current_castellon",
            "previous_course_same_position",
            "ahead_previous_course",
        ],
        "previous_course_same_position_fields": ["municipality", "placement_type", "date"],
        "ahead_previous_course_fields": ["alicante", "valencia", "castellon", "not_worked"],
        "calculation": "Cuenta las adjudicaciones de la misma especialidad situadas por delante y las agrupa por provincia",
        "future_history_available": False,
    }
    dataset["adjudication_status"] = {
        "source_stage": "inicio_curso",
        "source_date": published_date,
        "codes": {
            "A": "adjudicado en esta especialidad",
            "N": "no adjudicado en esta especialidad",
            "P": "ha participado",
            "D": "desactivado",
            "H": "habilitacion desactivada para esta especialidad",
        },
        "gender_codes": {"m": "masculino", "f": "femenino", "u": "no determinado"},
        "secondary_award_rule": "Solo se marca adjudicado cuando coinciden el encabezado y la especialidad real de la plaza",
    }
    dataset["adjudication_detail_fields"] = list(DETAIL_FIELDS)
    dataset["adjudication_detail"] = {
        "stage_codes": {"I": "inicio_curso", "C": "adjudicacion_continua"},
        "full_workload_code": "C",
        "current_stage": "inicio_curso",
        "current_date": published_date,
        "future_continuous_ready": True,
    }
    if len(people) < 10000 or sum(len(person[2]) for person in people) < 20000:
        raise SourceValidationError("La nueva base de posiciones no supera los controles minimos")
    return dataset


def normalize_table_header(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", normalized(value))


def rows_from_accreditation_table(
    table: list[list[object]], province: str, source: dict[str, str]
) -> list[dict]:
    if not table:
        return []
    header_index = next(
        (
            index
            for index, row in enumerate(table)
            if any("apellido1" in normalize_table_header(cell) for cell in row)
            and any("nombre" in normalize_table_header(cell) for cell in row)
        ),
        None,
    )
    if header_index is None:
        return []
    header = [normalize_table_header(cell) for cell in table[header_index]]

    def find(names: tuple[str, ...]) -> int | None:
        for index, value in enumerate(header):
            if any(name in value for name in names):
                return index
        return None

    surname1 = find(("apellido1", "cognom1"))
    surname2 = find(("apellido2", "cognom2"))
    given = find(("nombre", "nom"))
    language = find(("idioma", "llengua"))
    level = find(("nivel", "nivell"))
    exclusion = find(("motivos", "motius", "exclusion"))
    if None in {surname1, given, language, level}:
        return []
    output = []
    for raw in table[header_index + 1 :]:
        row = [clean(str(cell or "").replace("\n", " ")) for cell in raw]
        if max(surname1, given, language, level) >= len(row):
            continue
        language_value = normalized(row[language])
        level_value = re.sub(r"[^A-Z0-9]", "", row[level].upper())
        if not ("angles" in language_value or "ingles" in language_value or "english" in language_value):
            continue
        if level_value not in VALID_LEVELS:
            continue
        if exclusion is not None and exclusion < len(row) and row[exclusion].strip():
            continue
        surnames = clean(" ".join(part for part in (row[surname1], row[surname2] if surname2 is not None and surname2 < len(row) else "") if part))
        name = row[given]
        if not surnames or not name:
            continue
        official = clean_official_name(f"{surnames}, {name}")
        output.append(
            {
                "official_name": official,
                "display_name": display_name(official),
                "level": level_value,
                "province": province,
                "date": source.get("date"),
                "academic_year": source.get("academic_year"),
                "source_url": source.get("url"),
            }
        )
    return output


def parse_accreditation_pdf(
    pdf_bytes: bytes, province: str, source: dict[str, str]
) -> list[dict]:
    records: list[dict] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                records.extend(rows_from_accreditation_table(table, province, source))
    unique = {}
    for record in records:
        key = (identity_key(record["official_name"]), record["level"])
        unique[key] = record
    return list(unique.values())


def source_date(link: dict[str, str]) -> str | None:
    combined = urllib.parse.unquote(f"{link.get('text', '')} {link.get('url', '')}")
    match = re.search(r"(?<!\d)(20\d{2})[-_/](\d{2})[-_/](\d{2})(?!\d)", combined)
    if match:
        return "-".join(match.groups())
    match = re.search(r"(?<!\d)(\d{2})[-_/](\d{2})[-_/](20\d{2})(?!\d)", combined)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"
    return None


def academic_year_for(value: date) -> str:
    start = value.year if value.month >= 8 else value.year - 1
    return f"{start}-{start + 1}"


def allowed_accreditation_years(today: date) -> set[str]:
    current = academic_year_for(today)
    years = {current}
    if today.month in {6, 7}:
        years.add(f"{today.year}-{today.year + 1}")
    return years


def folder_allowed(link: dict[str, str], years: set[str]) -> bool:
    text = normalized(f"{link.get('text', '')} {urllib.parse.unquote(link.get('url', ''))}")
    found = re.findall(r"20\d{2}\s*[-/]\s*20\d{2}", text)
    if not found:
        return True
    normalized_years = {re.sub(r"\s*[-/]\s*", "-", value) for value in found}
    return bool(normalized_years & years)


def crawl_accreditation_links(today: date, max_pages: int = 30) -> list[dict[str, str]]:
    years = allowed_accreditation_years(today)
    pending = deque([(ACCREDITATIONS_URL, "")])
    visited: set[str] = set()
    pdfs: list[dict[str, str]] = []
    while pending and len(visited) < max_pages:
        page_url, inherited_province = pending.popleft()
        if page_url in visited:
            continue
        visited.add(page_url)
        for link in extract_links(page_url):
            text = normalized(link.get("text", ""))
            province = inherited_province
            if "alacant" in text or "alicante" in text:
                province = "Alicante"
            elif "castello" in text or "castellon" in text:
                province = "Castellon"
            elif "valencia" in text or "valencia" in normalized(urllib.parse.unquote(link["url"])):
                province = "Valencia"
            if "/folder/" in link["url"] and folder_allowed(link, years):
                pending.append((link["url"], province))
            elif is_pdf_link(link) and province:
                date_value = source_date(link)
                year_value = academic_year_for(date.fromisoformat(date_value)) if date_value else None
                if year_value in years:
                    pdfs.append({**link, "province": province, "date": date_value, "academic_year": year_value})
    return pdfs


def is_correction(link: dict[str, str]) -> bool:
    value = normalized(f"{link.get('text', '')} {urllib.parse.unquote(link.get('url', ''))}")
    return "correccion" in value or "correccio" in value or "errors" in value


def preferred_accreditation_links(links: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for link in links:
        grouped[(str(link.get("province")), str(link.get("date")))].append(link)
    selected = []
    for group in grouped.values():
        group.sort(key=lambda item: (is_correction(item), item.get("url", "")))
        selected.append(group[-1])
    return selected


def merge_accreditations(payload: dict, new_records: list[dict], documents: list[dict]) -> bool:
    by_name = {identity_key(row["official_name"]): row for row in payload.get("records", [])}
    changed = False
    for record in new_records:
        key = identity_key(record["official_name"])
        current = by_name.get(key)
        source = {
            "source_url": record.get("source_url"),
            "date": record.get("date"),
            "province": record.get("province"),
            "academic_year": record.get("academic_year"),
            "level": record.get("level"),
        }
        if current is None:
            current = {
                "official_name": record["official_name"],
                "display_name": record["display_name"],
                "highest_level": record["level"],
                "levels": [record["level"]],
                "provinces": [record["province"]],
                "first_date": record.get("date"),
                "latest_date": record.get("date"),
                "sources": [source],
            }
            by_name[key] = current
            changed = True
            continue
        levels = set(current.get("levels", [])) | {record["level"]}
        provinces = set(current.get("provinces", [])) | {record["province"]}
        sources = current.setdefault("sources", [])
        if not any(item.get("source_url") == source["source_url"] for item in sources):
            sources.append(source)
            changed = True
        highest = max(levels, key=lambda value: VALID_LEVELS.get(value, 0))
        dates = [value for value in (current.get("first_date"), current.get("latest_date"), record.get("date")) if value]
        updates = {
            "highest_level": highest,
            "levels": sorted(levels, key=lambda value: VALID_LEVELS.get(value, 0)),
            "provinces": sorted(provinces),
            "first_date": min(dates) if dates else None,
            "latest_date": max(dates) if dates else None,
        }
        for field, value in updates.items():
            if current.get(field) != value:
                current[field] = value
                changed = True
    processed = {item.get("url"): item for item in payload.get("processed_documents", [])}
    for document in documents:
        if processed.get(document["url"]) != document:
            processed[document["url"]] = document
            changed = True
    if changed:
        payload["records"] = sorted(by_name.values(), key=lambda row: normalize_name(row["official_name"]))
        payload["processed_documents"] = sorted(processed.values(), key=lambda row: (str(row.get("date") or ""), str(row.get("province") or ""), str(row.get("url") or "")))
        payload["updated_at"] = max((record.get("date") or "" for record in new_records), default=date.today().isoformat())
    return changed


def recalculate_english_positions(positions: dict, accreditations: dict) -> bool:
    before = [
        position[6] if len(position) > 6 else None
        for person in positions.get("people", [])
        for position in person[2]
    ]
    for person in positions.get("people", []):
        for position in person[2]:
            while len(position) <= 6:
                position.append(None)
            position[6] = None
    totals = add_english_positions(positions, accreditation_names(accreditations))
    after = [position[6] for person in positions.get("people", []) for position in person[2]]
    positions.setdefault("english_requirement", {}).update(
        {
            "accreditation_records": len(accreditations.get("records", [])),
            "accreditation_unique_names": len(accreditation_names(accreditations)),
            "credential_entries_by_specialty": totals,
            "accreditation_updated_at": accreditations.get("updated_at"),
        }
    )
    if before != after:
        positions["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return True
    return False


def load_json(path: Path, default: object | None = None):
    if not path.exists():
        if default is not None:
            return copy.deepcopy(default)
        raise FileNotFoundError(path)
    if path.name.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as source:
            return json.load(source)
    return json.loads(path.read_text(encoding="utf-8"))


def save_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if path.name.endswith(".gz"):
        with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=9) as target:
            target.write(serialized)
        with gzip.open(temporary, "rt", encoding="utf-8") as source:
            json.load(source)
    else:
        temporary.write_text(serialized, encoding="utf-8")
        json.loads(temporary.read_text(encoding="utf-8"))
    temporary.replace(path)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def current_start_pdfs(cuts: dict, year: int) -> dict[str, dict] | None:
    section = cuts.get("cuts", {}).get("inicio", {})
    if int(section.get("start_year") or 0) != year:
        return None
    pdfs = section.get("pdfs", {})
    if not isinstance(pdfs, dict) or not pdfs.get("maestros") or not pdfs.get("secundaria"):
        return None
    return pdfs


def run_positions(
    positions_path: Path,
    cuts_path: Path,
    accreditations_path: Path,
    state_path: Path,
    target_year: int | None,
) -> bool:
    links = extract_links(PARTICIPANTS_URL)
    pair = select_position_pair(links, target_year)
    if pair is None:
        print("posiciones: todavia no hay una pareja completa de PDFs")
        return False
    year, documents = pair
    master_pdf = http_get(documents["maestros"]["url"])
    secondary_pdf = http_get(documents["secundaria"]["url"])
    fingerprints = {"maestros": sha256(master_pdf), "secundaria": sha256(secondary_pdf)}
    previous = load_json(positions_path)
    current_sources = {
        ("secundaria" if row.get("body") == "otros" else row.get("body")): row.get("sha256")
        for row in previous.get("sources", [])
        if row.get("role") == "position_list"
    }
    cuts = load_json(cuts_path)
    start_meta = current_start_pdfs(cuts, year)
    state = load_json(state_path, {"schema_version": 1, "position_lists": {}, "checks": {}})
    start_fingerprints = {
        body: meta.get("sha256") for body, meta in (start_meta or {}).items()
    }
    previous_state = state.get("position_lists", {}).get(str(year), {})
    if fingerprints == current_sources and previous_state.get("start_pdfs") == start_fingerprints:
        print("posiciones: PDFs ya publicados con los mismos SHA-256")
        return False
    master_award_pdf = http_get(start_meta["maestros"]["url"]) if start_meta else None
    secondary_award_pdf = http_get(start_meta["secundaria"]["url"]) if start_meta else None
    accreditations = load_json(accreditations_path)
    candidate = build_positions_dataset(
        previous,
        cuts,
        accreditations,
        master_pdf,
        secondary_pdf,
        year,
        documents,
        master_award_pdf,
        secondary_award_pdf,
    )
    save_json_atomic(positions_path, candidate)
    state.setdefault("position_lists", {})[str(year)] = {
        "academic_year": f"{year}-{year + 1}",
        "documents": {
            body: {"url": documents[body]["url"], "sha256": fingerprints[body]}
            for body in ("maestros", "secundaria")
        },
        "start_pdfs": start_fingerprints,
        "published_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    state.setdefault("checks", {})["posiciones"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    save_json_atomic(state_path, state)
    print(f"posiciones: publicado Listado {year}/{year + 1} con {len(candidate['people'])} personas")
    return True


def run_accreditations(
    positions_path: Path,
    accreditations_path: Path,
    state_path: Path,
    today: date,
) -> bool:
    payload = load_json(accreditations_path)
    processed_urls = {item.get("url") for item in payload.get("processed_documents", [])}
    links = preferred_accreditation_links(crawl_accreditation_links(today))
    fresh = [link for link in links if link.get("url") not in processed_urls]
    if not fresh:
        print("acreditaciones: no hay PDFs nuevos")
        return False
    records: list[dict] = []
    documents: list[dict] = []
    for link in fresh:
        pdf_bytes = http_get(link["url"])
        parsed = parse_accreditation_pdf(pdf_bytes, link["province"], link)
        if not parsed:
            raise SourceValidationError(
                f"No se extrajo ninguna acreditacion inglesa B2/C1/C2 de {link['url']}"
            )
        records.extend(parsed)
        documents.append(
            {
                "url": link["url"],
                "sha256": sha256(pdf_bytes),
                "date": link.get("date"),
                "province": link.get("province"),
                "academic_year": link.get("academic_year"),
                "correction": is_correction(link),
                "records": len(parsed),
            }
        )
    changed = merge_accreditations(payload, records, documents)
    positions = load_json(positions_path)
    positions_changed = recalculate_english_positions(positions, payload)
    if changed:
        save_json_atomic(accreditations_path, payload)
    if positions_changed:
        save_json_atomic(positions_path, positions)
    state = load_json(state_path, {"schema_version": 1, "position_lists": {}, "checks": {}})
    state.setdefault("checks", {})["acreditaciones"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    save_json_atomic(state_path, state)
    print(
        f"acreditaciones: {len(documents)} documentos, {len(records)} filas y {len(payload['records'])} personas acumuladas"
    )
    return changed or positions_changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", choices=("posiciones", "acreditaciones", "all"), required=True)
    parser.add_argument("--positions", type=Path, default=DEFAULT_POSITIONS_PATH)
    parser.add_argument("--cuts", type=Path, default=DEFAULT_CUTS_PATH)
    parser.add_argument("--accreditations", type=Path, default=DEFAULT_ACCREDITATIONS_PATH)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--target-year", type=int)
    parser.add_argument("--today", type=date.fromisoformat)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    modes = ("posiciones", "acreditaciones") if args.force == "all" else (args.force,)
    if "posiciones" in modes:
        run_positions(
            args.positions,
            args.cuts,
            args.accreditations,
            args.state,
            args.target_year,
        )
    if "acreditaciones" in modes:
        run_accreditations(
            args.positions,
            args.accreditations,
            args.state,
            args.today or date.today(),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
