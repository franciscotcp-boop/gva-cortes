from __future__ import annotations

import argparse
import csv
import hashlib
import html.parser
import io
import json
import math
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
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pdfplumber

from position_context import PositionContextUpdater


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "adjudicaciones.json"
CENTER_OVERRIDES_PATH = ROOT / "data" / "center_overrides.json"
CENTER_WEB_OVERRIDES_PATH = ROOT / "data" / "center_web_overrides.json"
POSITIONS_PATH = ROOT / "data" / "posiciones_bolsa.json"
POSITION_CONTEXT_STATE_PATH = ROOT / "data" / "position_context_state.json"
TZ = ZoneInfo("Europe/Madrid")

START_PAGE_URL = "https://ceice.gva.es/es/web/rrhh-educacion/adjudicacion3"
COURSE_PAGE_URL = "https://ceice.gva.es/es/web/rrhh-educacion/resolucion"
CENTERS_CSV_URL = "https://terramapas.icv.gva.es/12_Centros_wfs?request=GetFeature&service=WFS&version=2.0.0&typename=CentrosDocentesRegimen&outputformat=csv"


def env_positive_seconds(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


HTTP_TIMEOUT_SECONDS = env_positive_seconds("HTTP_TIMEOUT_SECONDS", 120)
SOURCE_RETRY_WINDOW_SECONDS = env_positive_seconds("SOURCE_RETRY_WINDOW_SECONDS", 1800)
SOURCE_RETRY_TIMEOUT_SECONDS = env_positive_seconds("SOURCE_RETRY_TIMEOUT_SECONDS", 600)
SOURCE_RETRY_DELAY_SECONDS = env_positive_seconds("SOURCE_RETRY_DELAY_SECONDS", 30)
RETRYABLE_HTTP_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

CENTER_FORMAT = [
    "codigo",
    "nombre",
    "tipoES",
    "tipoVA",
    "regimen",
    "direccion",
    "cp",
    "telefono",
    "email",
    "web",
    "webVA",
    "municipio",
    "comarca",
    "provincia",
    "lat",
    "lon",
]

CUT_FORMAT = [
    "codigoCentro",
    "codigoEspecialidad",
    "numeroCorte",
    "nombreEspecialidad",
    "nombreCentro",
    "municipio",
    "cuerpo",
    "tipoPlaza",
    "origen",
    "requisitoIngles",
    "itinerante",
    "posicionEspecialidad",
]

SCHEMA_VERSION = 7
SECONDARY_MATCH_POLICY_VERSION = 5
CUT_POLICY = {
    "version": 8,
    "rule": "En Otros Cuerpos solo computa una adjudicacion cuando la especialidad del encabezado coincide con la especialidad de la plaza adjudicada junto al docente. En Maestros se identifica el requisito de ingles exclusivamente por / ING. en el bloque de la plaza adjudicada. La itinerancia se toma exclusivamente del mismo bloque adjudicado. En Maestros se conserva la posicion general y se incorpora por separado la posicion posterior a la adjudicacion dentro de la especialidad.",
    "maestros": "Se conserva la especialidad de la plaza adjudicada y se marcan requisitoIngles e itinerante solo cuando esa misma adjudicacion contiene / ING. o Itinerante.",
    "master_positions": "numeroCorte es la posicion posterior a la adjudicacion en la bolsa general de Maestros; posicionEspecialidad es la posicion posterior a la misma adjudicacion dentro de la especialidad.",
    "secundaria_y_otros": "Se exige que el codigo del encabezado y el codigo de la plaza adjudicada sean iguales; las filas de especialidades compatibles distintas no generan corte.",
    "independent_extractors": ["pdfplumber", "pypdf"],
}

# Solo estas especialidades pertenecen al cuerpo de Maestros. Los PDF pueden
# repetir una misma plaza en listas de cuerpos distintos; el corte valido es el
# de la lista correspondiente al cuerpo titular de la especialidad.
MAESTRO_SPECIALTY_CODES = frozenset({
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

MASTER_SPECIALTY_POSITION_ALIASES = {
    "151": "126",
    "152": "127",
    "153": "128",
}

MASTER_CUT_POSITION_POLICY = {
    "version": 1,
    "general_field": "master_general_positions.position_after_adjudication",
    "specialty_field": "positions.position_after_adjudication",
    "specialty_aliases": MASTER_SPECIALTY_POSITION_ALIASES,
    "source": "data/posiciones_bolsa.json",
    "previous_course_policy": "No se mezclan posiciones de especialidad del curso nuevo con adjudicaciones continuas pertenecientes al curso anterior.",
}

VACANCY_TOTALS_POLICY = {
    "version": 1,
    "inicio": "Se sustituye por el recuento completo de los PDF mas recientes de inicio de curso de cada cuerpo.",
    "curso": "Se acumulan unicamente las vacantes de cada PDF de adjudicacion continua desde la primera adjudicacion del curso, sin contar dos veces el mismo PDF.",
}

DEFAULT_DATA = {
    "schema_version": SCHEMA_VERSION,
    "generated_at": None,
    "timezone": "Europe/Madrid",
    "sources": {
        "centers": CENTERS_CSV_URL,
        "inicio": START_PAGE_URL,
        "curso": COURSE_PAGE_URL,
    },
    "center_format": CENTER_FORMAT,
    "cut_format": CUT_FORMAT,
    "cut_policy": CUT_POLICY,
    "master_cut_position_policy": MASTER_CUT_POSITION_POLICY,
    "vacancy_totals_policy": VACANCY_TOTALS_POLICY,
    "vacancy_totals": {
        "schema_version": 1,
        "definition_es": "Numero de adjudicaciones con tipo de plaza vacante por especialidad. Excluye sustituciones determinadas e indeterminadas e incluye cualquier jornada e itinerancia.",
        "definition_va": "Nombre d'adjudicacions amb tipus de placa vacant per especialitat. Exclou substitucions determinades i indeterminades i inclou qualsevol jornada i itinerancia.",
        "inicio": None,
        "curso": None,
    },
    "centers": [],
    "cuts": {
        "inicio": {
            "school_year": None,
            "start_year": None,
            "updated_at": None,
            "rows": [],
            "pdfs": {},
        },
        "curso": {
            "school_year": None,
            "updated_at": None,
            "rows": [],
            "pdfs": [],
        },
    },
    "processed_pdfs": {},
}


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
        attrs_dict = {k.lower(): v for k, v in attrs}
        href = attrs_dict.get("href")
        if href:
            self._href = urllib.parse.urljoin(self.base_url, href)
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append({"url": self._href, "text": " ".join(self._text).strip()})
            self._href = None
            self._text = []


@dataclass
class Adjudication:
    cut: int
    candidate_name: str
    center_code: str
    specialty_code: str
    specialty_name: str
    center_name: str
    locality: str
    body: str
    placement_type: str
    english_requirement: bool
    workload: int | str
    itinerant: bool


@dataclass
class ParsedPdf:
    url: str
    sha256: str
    body: str
    published_date: str | None
    rows: list[list]
    assignments: list[Adjudication] = field(default_factory=list)


def now_local() -> datetime:
    return datetime.now(TZ)


def norm(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text.lower()).strip()


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def owning_body_for_specialty(code: str) -> str:
    return "maestros" if str(code) in MAESTRO_SPECIALTY_CODES else "secundaria"


def smart_title(value: str) -> str:
    value = clean(value)
    if not value:
        return ""
    titled = value.lower().title()
    for old, new in {
        "Ceip": "CEIP",
        "Cep": "CEP",
        "Cee": "CEE",
        "Cra": "CRA",
        "Ies": "IES",
        "Cipfp": "CIPFP",
        "Cfpa": "CFPA",
        "Fpa": "FPA",
        "Eoi": "EOI",
        "Ei": "EI",
        "Fp": "FP",
        "Pub.": "Púb.",
    }.items():
        titled = re.sub(rf"\b{re.escape(old)}\b", new, titled)
    for old, new in {"De": "de", "Del": "del", "Dels": "dels", "I": "i", "Y": "y"}.items():
        titled = re.sub(rf"\b{old}\b", new, titled)
    for article in ("la", "el", "los", "las"):
        titled = re.sub(rf"^{article}\b", article.capitalize(), titled)
    titled = re.sub(
        r"^(CEIP|CEP|CEE|CRA|IES|CIPFP|CFPA|FPA|EOI|EI)\s+(la|el|los|las)\b",
        lambda m: m.group(1) + " " + m.group(2).capitalize(),
        titled,
    )
    titled = re.sub(r"\bD'([A-ZÀ-Ú])", lambda m: "d'" + m.group(1).lower(), titled)
    titled = re.sub(r"\bL'([a-zà-ú])", lambda m: "L'" + m.group(1).upper(), titled)
    titled = titled.replace("Col·Legi", "Col·legi").replace("1Er", "1er")
    for old, new in {"Ii": "II", "Iii": "III", "Iv": "IV", "Vi": "VI", "Vii": "VII", "Viii": "VIII", "Ix": "IX", "Xi": "XI", "Xii": "XII"}.items():
        titled = re.sub(rf"\b{old}\b", new, titled)
    titled = re.sub(
        r"\b(Jaume|Jaime|Joan|Juan|Alfons|Alfonso|Carles|Carlos|Enric|Enrique|Lluís|Luis)\s+i\b",
        lambda m: m.group(1) + " I",
        titled,
        flags=re.I,
    )
    return titled


def display_place(value: str) -> str:
    value = clean(value)
    match = re.match(r"^(.+?)\s+\((EL|LA|LOS|LAS|ELS|LES|L'|L’)\)$", value, re.I)
    if match:
        article = {"EL": "El", "LA": "La", "LOS": "Los", "LAS": "Las", "ELS": "Els", "LES": "Les", "L'": "L'", "L’": "L'"}.get(match.group(2).upper(), match.group(2))
        place = smart_title(match.group(1))
        return f"{article}{place[:1].upper() + place[1:]}" if article == "L'" else f"{article} {place}"
    return smart_title(value)


def blank_zero(value: str) -> str:
    value = clean(value)
    return "" if value == "0" else value


def http_get(url: str, *, timeout_seconds: float = HTTP_TIMEOUT_SECONDS) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; adjudicaciones-cv-updater/1.0)",
            "Accept": "*/*",
        },
    )
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, context=context, timeout=max(1, timeout_seconds)) as response:
        return response.read()


def is_retryable_http_error(error: Exception) -> bool:
    if isinstance(error, urllib.error.HTTPError):
        return error.code in RETRYABLE_HTTP_STATUS
    return isinstance(
        error,
        (urllib.error.URLError, TimeoutError, ConnectionError, socket.timeout, ssl.SSLError),
    )


def resilient_http_get(
    url: str,
    *,
    retry_window_seconds: float = SOURCE_RETRY_WINDOW_SECONDS,
    initial_timeout_seconds: float = HTTP_TIMEOUT_SECONDS,
    retry_timeout_seconds: float = SOURCE_RETRY_TIMEOUT_SECONDS,
    retry_delay_seconds: float = SOURCE_RETRY_DELAY_SECONDS,
    request_fn=None,
    sleep_fn=time.sleep,
    monotonic_fn=time.monotonic,
) -> bytes:
    request_fn = request_fn or http_get
    deadline = monotonic_fn() + max(0, retry_window_seconds)
    attempt = 1

    while True:
        remaining = deadline - monotonic_fn()
        requested_timeout = initial_timeout_seconds if attempt == 1 else retry_timeout_seconds
        timeout_seconds = requested_timeout
        if retry_window_seconds > 0:
            timeout_seconds = min(requested_timeout, max(1, remaining))

        try:
            return request_fn(url, timeout_seconds=timeout_seconds)
        except Exception as error:
            remaining = deadline - monotonic_fn()
            if (
                not is_retryable_http_error(error)
                or retry_window_seconds <= 0
                or remaining <= 0
            ):
                raise

            delay = min(retry_delay_seconds, remaining)
            print(
                f"WARNING: {url} no responde "
                f"(intento {attempt}: {error}). Nuevo intento en {delay:.0f} segundos.",
                file=sys.stderr,
                flush=True,
            )
            if delay > 0:
                sleep_fn(delay)
            attempt += 1


def load_data() -> dict:
    if DATA_PATH.exists():
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    else:
        data = json.loads(json.dumps(DEFAULT_DATA))
    for key, value in DEFAULT_DATA.items():
        data.setdefault(key, value)
    data.setdefault("cuts", {}).setdefault("inicio", DEFAULT_DATA["cuts"]["inicio"].copy())
    data.setdefault("cuts", {}).setdefault("curso", DEFAULT_DATA["cuts"]["curso"].copy())
    data.setdefault("processed_pdfs", {})
    data.setdefault("master_cut_position_policy", MASTER_CUT_POSITION_POLICY)
    data.setdefault("vacancy_totals_policy", VACANCY_TOTALS_POLICY)
    data.setdefault("vacancy_totals", json.loads(json.dumps(DEFAULT_DATA["vacancy_totals"])))
    return data


def save_data(data: dict) -> None:
    data["generated_at"] = now_local().isoformat(timespec="seconds")
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=False) + "\n", encoding="utf-8")


def is_start_window(dt: datetime) -> bool:
    return dt.month in (7, 8)


def is_course_window(dt: datetime) -> bool:
    return dt.month in (1, 2, 3, 4, 5, 6, 9, 10, 11, 12) and dt.weekday() in (1, 3)


def school_year_for_date(date_text: str | None, fallback: datetime) -> str:
    if date_text:
        dt = datetime.strptime(date_text, "%Y-%m-%d")
        year = dt.year if dt.month >= 7 else dt.year - 1
    else:
        year = fallback.year if fallback.month >= 7 else fallback.year - 1
    return f"{year}-{year + 1}"


def start_year_from_school_year(value: object) -> int | None:
    match = re.fullmatch(r"(\d{4})-(\d{4})", clean(str(value or "")))
    if not match:
        return None
    start_year, end_year = (int(part) for part in match.groups())
    if end_year != start_year + 1:
        return None
    return start_year


def normalized_school_year(value: object) -> str | None:
    match = re.fullmatch(r"\s*(\d{4})\s*[-/]\s*(\d{4})\s*", str(value or ""))
    if not match:
        return None
    start_year, end_year = (int(part) for part in match.groups())
    if end_year != start_year + 1:
        return None
    return f"{start_year}-{end_year}"


def positive_integer(value: object) -> int | None:
    try:
        number = int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return number if number is not None and number > 0 else None


def metadata_field_index(fields: object, name: str, fallback: int) -> int:
    if isinstance(fields, list) and name in fields:
        return fields.index(name)
    return fallback


class MasterCutPositionIndex:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.enabled = False
        self.academic_year: str | None = None
        self.by_general_specialty: dict[tuple[int, str], int] = {}
        if not self.path.exists():
            print(f"Posiciones de corte de Maestros: omitidas; no existe {self.path}")
            return

        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.academic_year = normalized_school_year(data.get("academic_year"))
        if self.academic_year is None:
            print("Posiciones de corte de Maestros: omitidas; curso no valido")
            return

        person_fields = data.get("person_fields")
        position_fields = data.get("position_fields")
        general_fields = data.get("master_general_position_fields")
        person_positions_index = metadata_field_index(person_fields, "positions", 2)
        person_source_index = metadata_field_index(person_fields, "source", 3)
        person_general_index = metadata_field_index(person_fields, "master_general_positions", 4)
        specialty_code_index = metadata_field_index(position_fields, "specialty_code", 0)
        specialty_after_index = metadata_field_index(position_fields, "position_after_adjudication", 3)
        general_after_index = metadata_field_index(general_fields, "position_after_adjudication", 1)

        for person in data.get("people", []):
            if not isinstance(person, list):
                continue
            source = str(person[person_source_index] or "") if len(person) > person_source_index else ""
            if source not in {"maestros", "mixto"}:
                continue
            general = person[person_general_index] if len(person) > person_general_index else None
            positions = person[person_positions_index] if len(person) > person_positions_index else None
            if not isinstance(general, list) or len(general) <= general_after_index or not isinstance(positions, list):
                continue
            general_after = positive_integer(general[general_after_index])
            if general_after is None:
                continue
            for position in positions:
                if not isinstance(position, list) or len(position) <= max(specialty_code_index, specialty_after_index):
                    continue
                code = str(position[specialty_code_index] or "")
                specialty_after = positive_integer(position[specialty_after_index])
                if specialty_after is None:
                    continue
                key = (general_after, code)
                previous = self.by_general_specialty.get(key)
                if previous is not None and previous != specialty_after:
                    raise RuntimeError(
                        "Posiciones de corte de Maestros ambiguas para "
                        f"posicion general {general_after} y especialidad {code}"
                    )
                self.by_general_specialty[key] = specialty_after
        self.enabled = bool(self.by_general_specialty)

    def resolve(self, general_position: object, specialty_code: object, school_year: object) -> int | None:
        if not self.enabled or normalized_school_year(school_year) != self.academic_year:
            return None
        general = positive_integer(general_position)
        if general is None:
            return None
        code = str(specialty_code or "")
        lookup_code = MASTER_SPECIALTY_POSITION_ALIASES.get(code, code)
        return self.by_general_specialty.get((general, lookup_code))


def ensure_period_metadata(data: dict) -> bool:
    inicio = data.setdefault("cuts", {}).setdefault("inicio", {})
    expected = start_year_from_school_year(inicio.get("school_year"))
    if "start_year" in inicio and inicio.get("start_year") == expected:
        return False
    inicio["start_year"] = expected
    return True


def extract_pdf_links(page_url: str) -> list[dict[str, str]]:
    parser = LinkParser(page_url)
    parser.feed(resilient_http_get(page_url).decode("utf-8", errors="replace"))
    seen: set[str] = set()
    links: list[dict[str, str]] = []
    for link in parser.links:
        url = link["url"].split("#", 1)[0]
        if ".pdf" not in url.lower() or url in seen:
            continue
        if not looks_like_adjudication_list(link):
            continue
        seen.add(url)
        links.append({"url": url, "text": link.get("text", "")})
    return links


def looks_like_adjudication_list(link: dict[str, str]) -> bool:
    url = link.get("url", "")
    filename = urllib.parse.unquote(url.rsplit("/", 1)[-1])
    combined = norm(f"{link.get('text', '')} {filename} {url}")
    if re.search(r"\b(listado|lista|llistat|llista|listat)s?\b", combined):
        return True
    return bool(re.search(r"(^|[^a-z])lis([^a-z]|$)", combined))


def center_prefix(row: dict[str, str]) -> str:
    generic = norm(row.get("dgenerica_cas", ""))
    if "colegio de educacion infantil y primaria" in generic:
        return "CEIP"
    if "colegio de educacion primaria" in generic:
        return "CEP"
    if "instituto de educacion secundaria" in generic:
        return "IES"
    if "centro de educacion especial" in generic:
        return "CEE"
    if "colegio rural agrupado" in generic:
        return "CRA"
    return ""


def has_visible_prefix(name: str) -> bool:
    return bool(re.match(r"^(CEIP|CEP|CEE|CRA|IES|CIPFP|CFPA|FPA|EOI|EI|CENTR[EO]|COL[E·]GI|COLEGIO|ESCOLA|ESCUELA|CONSERVATORI|CONSERVATORIO|SECCI[ÓO]N|SECCI[ÓO]|AULARIO)\b", name, re.I))


def center_name(row: dict[str, str]) -> str:
    free = clean(row.get("dlibre", ""))
    if free:
        prefix = center_prefix(row)
        if prefix and not has_visible_prefix(free):
            free = f"{prefix} {free}"
        return smart_title(free)
    return smart_title(" ".join(part for part in (row.get("dgenerica_cas", ""), row.get("despecifica", "")) if part))


def load_center_overrides(path: Path | None = None) -> list[list]:
    target = path or CENTER_OVERRIDES_PATH
    if not target.exists():
        return []

    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("center_format") != CENTER_FORMAT:
        raise ValueError(f"Formato de centros no valido en {target}")

    rows = payload.get("centers")
    if not isinstance(rows, list):
        raise ValueError(f"Lista de centros no valida en {target}")

    result: list[list] = []
    seen: set[str] = set()
    for raw in rows:
        if not isinstance(raw, list) or len(raw) != len(CENTER_FORMAT):
            raise ValueError(f"Ficha manual de centro no valida en {target}")
        row = list(raw)
        code = str(row[0]).strip()
        if not code or code in seen:
            raise ValueError(f"Codigo de centro manual vacio o duplicado: {code!r}")
        if not all(isinstance(row[index], (int, float)) and math.isfinite(row[index]) for index in (14, 15)):
            raise ValueError(f"Coordenadas manuales no validas para {code}")
        seen.add(code)
        result.append(row)
    return result


def merge_center_overrides(centers: list[list], overrides: list[list] | None = None) -> list[list]:
    merged = [list(center) for center in centers]
    positions = {str(center[0]): index for index, center in enumerate(merged)}
    for override in load_center_overrides() if overrides is None else overrides:
        code = str(override[0])
        if code in positions:
            merged[positions[code]] = list(override)
        else:
            positions[code] = len(merged)
            merged.append(list(override))
    merged.sort(key=lambda row: (norm(row[11]), norm(row[1]), str(row[0])))
    return merged


def load_center_web_overrides(path: Path | None = None) -> dict[str, str | None]:
    target = path or CENTER_WEB_OVERRIDES_PATH
    if not target.exists():
        return {}

    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError(f"Formato de webs manuales no valido en {target}")

    websites = payload.get("websites")
    blocked = payload.get("blocked")
    if not isinstance(websites, dict) or not isinstance(blocked, dict):
        raise ValueError(f"Lista de webs manuales no valida en {target}")

    result: dict[str, str | None] = {}
    for raw_code, raw_url in websites.items():
        code = str(raw_code).strip()
        url = str(raw_url).strip() if isinstance(raw_url, str) else ""
        parsed = urllib.parse.urlparse(url)
        if (
            not re.fullmatch(r"\d{8}", code)
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
        ):
            raise ValueError(f"Web manual no valida para {code!r}: {raw_url!r}")
        result[code] = url

    for raw_code, reason in blocked.items():
        code = str(raw_code).strip()
        if (
            not re.fullmatch(r"\d{8}", code)
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            raise ValueError(f"Bloqueo de web no valido para {code!r}")
        if code in result:
            raise ValueError(f"Codigo con web y bloqueo simultaneos: {code}")
        result[code] = None
    return result


def merge_center_web_overrides(
    centers: list[list],
    overrides: dict[str, str | None] | None = None,
) -> list[list]:
    merged = [list(center) for center in centers]
    positions = {str(center[0]): index for index, center in enumerate(merged)}
    entries = load_center_web_overrides() if overrides is None else overrides
    for code, url in entries.items():
        position = positions.get(str(code))
        if position is None:
            continue
        merged[position][9] = url or ""
        if url is None:
            merged[position][10] = ""
    return merged


def centers_by_code(centers: list[list]) -> dict[str, dict[str, str]]:
    return {
        str(center[0]): {
            "code": str(center[0]),
            "name": center[1],
            "municipality": center[11],
            "province": center[13],
            "lat": center[14],
            "lon": center[15],
        }
        for center in centers
    }


def load_centers(existing: list[list]) -> tuple[list[list], dict[str, dict[str, str]]]:
    try:
        raw = http_get(CENTERS_CSV_URL).decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"WARNING: no se ha podido refrescar la guia de centros: {exc}", file=sys.stderr)
        centers = merge_center_web_overrides(merge_center_overrides(existing))
        return centers, centers_by_code(centers)

    centers: list[list] = []
    for row in csv.DictReader(io.StringIO(raw)):
        code = clean(row.get("codcen", ""))
        if not code:
            continue
        status = clean(row.get("cod_estado", "")).upper()
        if status not in {"A", "L"}:
            continue
        province = clean(row.get("provincia", "")) or {"03": "Alacant/Alicante", "12": "Castelló/Castellón", "46": "València/Valencia"}.get(code[:2], "")
        locality = clean(row.get("localidad_oficial" if status == "L" else "noms_mun", "")) or clean(row.get("noms_mun", "")) or clean(row.get("localidad_oficial", ""))
        item = {
            "code": code,
            "name": center_name(row),
            "typeEs": smart_title(row.get("dgenerica_cas", "")),
            "typeVa": smart_title(row.get("dgenerica_val", "")),
            "regime": smart_title(row.get("regimen", "")),
            "address": clean(row.get("direccion", "")),
            "postal": clean(row.get("codpos", "")),
            "phone": blank_zero(row.get("telef", "")),
            "email": clean(row.get("mail", "")),
            "web": blank_zero(row.get("web", "")),
            "webVa": "",
            "municipality": display_place(locality),
            "comarca": clean(row.get("comarca", "")),
            "province": province,
            "lat": float(row["latitud"]) if row.get("latitud") else None,
            "lon": float(row["longitud"]) if row.get("longitud") else None,
        }
        centers.append([
            item["code"],
            item["name"],
            item["typeEs"],
            item["typeVa"],
            item["regime"],
            item["address"],
            item["postal"],
            item["phone"],
            item["email"],
            item["web"],
            item["webVa"],
            item["municipality"],
            item["comarca"],
            item["province"],
            item["lat"],
            item["lon"],
        ])
    centers = merge_center_web_overrides(merge_center_overrides(centers))
    return centers, centers_by_code(centers)


CANDIDATE_RE = re.compile(r"^(\d{1,5})(?:\s*/\s*\d{1,5})?\s+(?!\s*/)[^,]+,\s+.+")
CENTER_RE = re.compile(r"^\d{5,7}\s+(.+)\((\d{8})\)(.+)$")
SPECIALTY_RE = re.compile(r"^([0-9A-Z]{3})\s*/\s*(.+)$")
PAGE_SPECIALTY_PREFIX_RE = re.compile(r"^([0-9A-Z]{3})\s+(.+)$")
PAGE_SPECIALTY_SUFFIX_RE = re.compile(r"^(.+?)\s*([0-9A-Z]{3})$")


def parse_date_from_text(text: str) -> str | None:
    match = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", text)
    if not match:
        return None
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


def classify_body(text: str) -> str | None:
    normalized = norm(text)
    if "mestres / maestros" in normalized:
        return "maestros"
    if "altres cossos / otros cuerpos" in normalized:
        return "secundaria"
    return None


def secondary_page_specialty(text: str) -> tuple[str, str] | None:
    """Read the offered specialty from an Otros Cuerpos page header."""
    lines = [clean(line) for line in text.splitlines() if clean(line)]
    marker = next(
        (index for index, line in enumerate(lines) if "altres cossos / otros cuerpos" in norm(line)),
        None,
    )
    if marker is None:
        return None

    # The visual "219 TECNOLOGIA" header is extracted in reverse order by
    # some PDF engines, so both representations are accepted.
    for line in lines[marker + 1 : marker + 7]:
        if "/" in line:
            continue
        suffix = PAGE_SPECIALTY_SUFFIX_RE.match(line)
        if suffix and any(character.isdigit() for character in suffix.group(2)):
            return suffix.group(2), clean(suffix.group(1))
        prefix = PAGE_SPECIALTY_PREFIX_RE.match(line)
        if (
            prefix
            and any(character.isdigit() for character in prefix.group(1))
        ):
            return prefix.group(1), clean(prefix.group(2))
    return None


def detect_placement_type(block: list[str]) -> str:
    normalized = norm(" ".join(block))
    if "substitucio indeterminada" in normalized or "sustitucion indeterminada" in normalized:
        return "sub_indeterminada"
    if "substitucio determinada" in normalized or "sustitucion determinada" in normalized:
        return "sub_determinada"
    if re.search(r"\b(vacant|vacante)\b", normalized):
        return "vacante"
    return ""


def detect_english_requirement(block: list[str], body: str) -> bool:
    if body != "maestros":
        return False
    normalized = norm(" ".join(block))
    return bool(re.search(r"(?:^|\s)/\s*ing\.?(?=\s|\d|$)", normalized))


def detect_workload(block: list[str]) -> int | str:
    normalized = norm(" ".join(block))
    match = re.search(r"\b(\d{1,2})\s*(?:horas?|hores?)\b", normalized)
    if match:
        return int(match.group(1))
    if "jornada completa" in normalized:
        return "C"
    return "C"


def detect_itinerant(block: list[str]) -> bool:
    return bool(re.search(r"\bitinerant(?:e)?\b", norm(" ".join(block))))


def candidate_name_from_line(line: str, match_cut: re.Match[str]) -> str:
    value = clean(line[match_cut.end() :])
    value = re.split(
        r"(?:Petici.n\s*:|Voluntaria\b|Obligat.ria\b|PREFER.NCIA\b)",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return clean(value)


def parse_block(
    block: list[str],
    body: str,
    page_specialty: tuple[str, str] | None = None,
) -> Adjudication | None:
    if not block or not any("Adjudicat" in line for line in block):
        return None
    match_cut = re.match(r"^(\d{1,5})(?:\s*/\s*\d{1,5})?\s+", block[0])
    if not match_cut:
        return None
    center_match = None
    specialty_match = None
    for line in block[1:]:
        center_match = center_match or CENTER_RE.match(line)
        specialty_match = specialty_match or SPECIALTY_RE.match(line)
    if not center_match:
        return None
    if body == "secundaria":
        if page_specialty is None or specialty_match is None:
            return None
        assigned_specialty_code = specialty_match.group(1)
        if assigned_specialty_code != page_specialty[0]:
            return None
        # The row only belongs to this cut when the candidate-pool header and
        # the specialty of the awarded position identify the same specialty.
        specialty_code, specialty_name = page_specialty
    elif specialty_match:
        specialty_code = specialty_match.group(1)
        specialty_name = clean(specialty_match.group(2))
    else:
        return None
    return Adjudication(
        cut=int(match_cut.group(1)),
        candidate_name=candidate_name_from_line(block[0], match_cut),
        center_code=center_match.group(2),
        specialty_code=specialty_code,
        specialty_name=specialty_name,
        center_name=clean(center_match.group(3)),
        locality=clean(center_match.group(1)),
        body=body,
        placement_type=detect_placement_type(block),
        english_requirement=detect_english_requirement(block, body),
        workload=detect_workload(block),
        itinerant=detect_itinerant(block),
    )


def parse_pdf(
    url: str,
    pdf_bytes: bytes,
    centers_by_code: dict[str, dict[str, str]],
    master_positions: MasterCutPositionIndex | None = None,
    mode: str | None = None,
) -> ParsedPdf | None:
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    rows: list[Adjudication] = []
    body: str | None = None
    published_date: str | None = None

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        preview = "\n".join((page.extract_text(x_tolerance=1, y_tolerance=3) or "") for page in pdf.pages[:3])
        body = classify_body(preview)
        published_date = parse_date_from_text(preview)
        if body is None:
            return None

        total_pages = len(pdf.pages)
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
            page_specialty = secondary_page_specialty(text) if body == "secundaria" else None
            if body == "secundaria" and page_specialty is None:
                raise ValueError(f"No se pudo leer la especialidad del encabezado en la pagina {page_number}")

            current: list[str] = []
            for raw_line in text.splitlines():
                line = clean(raw_line)
                if not line:
                    continue
                if CANDIDATE_RE.match(line):
                    parsed = parse_block(current, body, page_specialty)
                    if parsed:
                        rows.append(parsed)
                    current = [line]
                elif current:
                    current.append(line)
            parsed = parse_block(current, body, page_specialty)
            if parsed:
                rows.append(parsed)
            if page_number % 250 == 0 or page_number == total_pages:
                print(
                    f"{body}: procesadas {page_number}/{total_pages} paginas "
                    f"({len(rows)} adjudicaciones validas)",
                    flush=True,
                )

    valid_rows = [row for row in rows if owning_body_for_specialty(row.specialty_code) == body]
    best: OrderedDict[tuple[str, str], Adjudication] = OrderedDict()
    for row in valid_rows:
        key = (row.center_code, row.specialty_code)
        old = best.get(key)
        if old is None or row.cut > old.cut:
            best[key] = row

    output: list[list] = []
    parsed_school_year = school_year_for_date(published_date, now_local())
    for row in best.values():
        center = centers_by_code.get(row.center_code)
        specialty_position = None
        if row.body == "maestros" and mode == "inicio" and master_positions is not None:
            specialty_position = master_positions.resolve(
                row.cut,
                row.specialty_code,
                parsed_school_year,
            )
        output.append([
            row.center_code,
            row.specialty_code,
            row.cut,
            row.specialty_name,
            center["name"] if center else smart_title(row.center_name),
            center["municipality"] if center else display_place(row.locality),
            row.body,
            row.placement_type,
            row.english_requirement,
            row.itinerant,
            specialty_position,
        ])

    assignments: list[Adjudication] = []
    seen_assignments: set[tuple[str, str, int, str]] = set()
    for row in valid_rows:
        key = (norm(row.candidate_name), row.specialty_code, row.cut, row.center_code)
        if key in seen_assignments:
            continue
        seen_assignments.add(key)
        assignments.append(row)

    return ParsedPdf(
        url=url,
        sha256=sha,
        body=body,
        published_date=published_date,
        rows=output,
        assignments=assignments,
    )


def pdf_already_processed(data: dict, parsed: ParsedPdf) -> bool:
    current = data["processed_pdfs"].get(parsed.url)
    return bool(current and current.get("sha256") == parsed.sha256)


def url_already_seen(data: dict, url: str) -> bool:
    return url in data.get("processed_pdfs", {})


def mark_processed(data: dict, parsed: ParsedPdf, mode: str) -> None:
    data["processed_pdfs"][parsed.url] = {
        "sha256": parsed.sha256,
        "mode": mode,
        "body": parsed.body,
        "published_date": parsed.published_date,
        "rows": len(parsed.rows),
        "processed_at": now_local().isoformat(timespec="seconds"),
    }


def mark_ignored(data: dict, url: str, sha256: str | None, mode: str, reason: str, body: str | None = None, published_date: str | None = None) -> None:
    data["processed_pdfs"][url] = {
        "sha256": sha256,
        "mode": f"{mode}:ignored",
        "body": body,
        "published_date": published_date,
        "rows": 0,
        "reason": reason,
        "processed_at": now_local().isoformat(timespec="seconds"),
    }


def row_key(row: list) -> str:
    body = row[6] if len(row) > 6 else ""
    return f"{row[0]}|{row[1]}|{body}"


def row_english_requirement(row: list) -> bool:
    if len(row) >= 9 and row[8] in {"inicio", "curso"}:
        return len(row) >= 10 and row[9] is True
    if len(row) >= 9 and isinstance(row[8], bool):
        return row[8]
    return False


def row_itinerant(row: list) -> bool:
    if len(row) >= 9 and row[8] in {"inicio", "curso"}:
        return len(row) >= 11 and row[10] is True
    if len(row) >= 10 and isinstance(row[9], bool):
        return row[9]
    return False


def row_specialty_position(row: list) -> int | None:
    if len(row) >= 9 and row[8] in {"inicio", "curso"}:
        return positive_integer(row[11]) if len(row) >= 12 else None
    return positive_integer(row[10]) if len(row) >= 11 else None


def row_with_origin(row: list, origin: str) -> list:
    if len(row) >= 8 and row[7] not in {"inicio", "curso"}:
        base = row[:8]
    else:
        base = (row[:7] if len(row) >= 7 else row + [""] * (7 - len(row))) + [""]
    return base + [
        origin,
        row_english_requirement(row),
        row_itinerant(row),
        row_specialty_position(row),
    ]


def row_origin(row: list, default: str) -> str:
    if len(row) >= 9 and row[8] in {"inicio", "curso"}:
        return row[8]
    if len(row) >= 8 and row[7] in {"inicio", "curso"}:
        return row[7]
    return default


def ensure_cut_schema(data: dict) -> bool:
    changed = False
    for mode in ("inicio", "curso"):
        period = data.setdefault("cuts", {}).setdefault(mode, {})
        rows = period.setdefault("rows", [])
        normalized = [row_with_origin(row, row_origin(row, "inicio")) for row in rows]
        if normalized != rows:
            period["rows"] = normalized
            changed = True
    if data.get("schema_version") != SCHEMA_VERSION:
        data["schema_version"] = SCHEMA_VERSION
        changed = True
    if data.get("cut_format") != CUT_FORMAT:
        data["cut_format"] = CUT_FORMAT
        changed = True
    return changed


def enrich_master_cut_positions(data: dict, positions: MasterCutPositionIndex | None) -> bool:
    if positions is None or not positions.enabled:
        return False
    inicio = data.setdefault("cuts", {}).setdefault("inicio", {})
    school_year = normalized_school_year(inicio.get("school_year"))
    if school_year is None or school_year != positions.academic_year:
        return False

    changed = False
    start_values: dict[str, int] = {}
    start_rows: list[list] = []
    unresolved = 0
    for raw in inicio.setdefault("rows", []):
        row = row_with_origin(raw, row_origin(raw, "inicio"))
        value = None
        if len(row) >= 7 and str(row[6]) == "maestros":
            value = positions.resolve(row[2], row[1], school_year)
            if value is None:
                unresolved += 1
            else:
                start_values[row_key(row)] = value
        if row[11] != value:
            row[11] = value
            changed = True
        start_rows.append(row)
    if unresolved:
        print(
            "WARNING: faltan posiciones por especialidad para "
            f"{unresolved} cortes de inicio de Maestros",
            file=sys.stderr,
        )
    if start_rows != inicio.get("rows"):
        inicio["rows"] = start_rows
        changed = True

    curso = data.setdefault("cuts", {}).setdefault("curso", {})
    course_rows: list[list] = []
    for raw in curso.setdefault("rows", []):
        origin = row_origin(raw, "inicio")
        row = row_with_origin(raw, origin)
        value = None
        if len(row) >= 7 and str(row[6]) == "maestros" and origin == "inicio":
            value = start_values.get(row_key(row))
        if row[11] != value:
            row[11] = value
            changed = True
        course_rows.append(row)
    if course_rows != curso.get("rows"):
        curso["rows"] = course_rows
        changed = True
    return changed


def latest_secondary_course_url(data: dict) -> str | None:
    items = [
        item
        for item in data.get("cuts", {}).get("curso", {}).get("pdfs", [])
        if item.get("body") == "secundaria" and item.get("url")
    ]
    if not items:
        return None
    return max(items, key=lambda item: (item.get("published_date") or "", item.get("url") or ""))["url"]


def secondary_start_url(data: dict) -> str | None:
    item = data.get("cuts", {}).get("inicio", {}).get("pdfs", {}).get("secundaria", {})
    return item.get("url")


def update_secondary_metadata(data: dict, parsed: ParsedPdf, mode: str) -> None:
    if mode == "inicio":
        data["cuts"]["inicio"].setdefault("pdfs", {})["secundaria"] = {
            "url": parsed.url,
            "sha256": parsed.sha256,
            "published_date": parsed.published_date,
            "rows": len(parsed.rows),
        }
    else:
        history = data["cuts"]["curso"].setdefault("pdfs", [])
        current = next((item for item in history if item.get("body") == "secundaria"), None)
        replacement = {
            "url": parsed.url,
            "sha256": parsed.sha256,
            "body": "secundaria",
            "published_date": parsed.published_date,
            "rows": len(parsed.rows),
        }
        if current is None:
            history.append(replacement)
        else:
            current.update(replacement)

    data.setdefault("processed_pdfs", {})[parsed.url] = {
        "sha256": parsed.sha256,
        "mode": mode,
        "body": "secundaria",
        "published_date": parsed.published_date,
        "rows": len(parsed.rows),
        "parser_policy": "encabezado_y_especialidad_adjudicada_coincidentes",
        "processed_at": now_local().isoformat(timespec="seconds"),
    }


def migrate_secondary_header_policy(data: dict, centers_by_code: dict[str, dict[str, str]]) -> bool:
    current_policy_version = int(data.get("cut_policy", {}).get("version") or 0)
    if current_policy_version >= SECONDARY_MATCH_POLICY_VERSION:
        return False

    inicio = data.get("cuts", {}).get("inicio", {})
    if not inicio.get("rows"):
        data["schema_version"] = SCHEMA_VERSION
        data["cut_policy"] = CUT_POLICY
        return True

    start_url = secondary_start_url(data)
    if not start_url:
        raise RuntimeError("No se puede migrar secundaria: falta el PDF de inicio")
    parsed_start = parse_pdf(start_url, http_get(start_url), centers_by_code)
    if parsed_start is None or parsed_start.body != "secundaria" or not parsed_start.rows:
        raise RuntimeError("No se puede migrar secundaria: PDF de inicio no valido")

    maestro_start = [
        row_with_origin(row, "inicio")
        for row in inicio.get("rows", [])
        if len(row) >= 7 and row[6] == "maestros"
    ]
    secondary_start = [row_with_origin(row, "inicio") for row in parsed_start.rows]
    new_start = sorted(
        maestro_start + secondary_start,
        key=lambda row: (str(row[1]), int(row[2]), str(row[0])),
    )
    inicio["rows"] = new_start
    update_secondary_metadata(data, parsed_start, "inicio")

    curso = data.get("cuts", {}).get("curso", {})
    maestro_course = [
        row_with_origin(row, "curso")
        for row in curso.get("rows", [])
        if len(row) >= 7 and row[6] == "maestros" and row_origin(row, "inicio") == "curso"
    ]
    secondary_course: list[list] = []
    course_url = latest_secondary_course_url(data)
    if course_url:
        parsed_course = parse_pdf(course_url, http_get(course_url), centers_by_code)
        if parsed_course is None or parsed_course.body != "secundaria":
            raise RuntimeError("No se puede migrar secundaria: PDF de durante el curso no valido")
        secondary_course = [row_with_origin(row, "curso") for row in parsed_course.rows]
        update_secondary_metadata(data, parsed_course, "curso")

    cumulative = {row_key(row): row_with_origin(row, "inicio") for row in new_start}
    for row in maestro_course + secondary_course:
        cumulative[row_key(row)] = row
    curso["rows"] = sorted(
        cumulative.values(),
        key=lambda row: (str(row[1]), int(row[2]), str(row[0])),
    )

    data["schema_version"] = SCHEMA_VERSION
    data["cut_policy"] = CUT_POLICY
    print(
        "Migracion por coincidencia de especialidades completada: "
        f"inicio_secundaria={len(parsed_start.rows)} "
        f"curso_secundaria={len(secondary_course)}"
    )
    return True


def assignment_belongs_to_pdf_body(assignment: Adjudication, body: str) -> bool:
    is_master_specialty = str(assignment.specialty_code) in MAESTRO_SPECIALTY_CODES
    return is_master_specialty if body == "maestros" else not is_master_specialty


def vacancy_counts_for_pdf(parsed: ParsedPdf) -> tuple[Counter[str], int, int]:
    all_vacancies = [
        assignment
        for assignment in parsed.assignments
        if assignment.placement_type == "vacante"
    ]
    owned_vacancies = [
        assignment
        for assignment in all_vacancies
        if assignment_belongs_to_pdf_body(assignment, parsed.body)
    ]
    counts = Counter(str(assignment.specialty_code) for assignment in owned_vacancies)
    return counts, len(all_vacancies), len(owned_vacancies)


def ordered_counts(counts: Counter[str] | dict[str, int]) -> dict[str, int]:
    return {str(code): int(counts[code]) for code in sorted(counts)}


def vacancy_document_summary(parsed: ParsedPdf) -> dict:
    counts, pdf_vacancy_total, owned_total = vacancy_counts_for_pdf(parsed)
    return {
        "url": parsed.url,
        "pdf_sha256": parsed.sha256,
        "body": parsed.body,
        "published_date": parsed.published_date,
        "source_records": len(parsed.assignments),
        "pdf_vacancy_total": pdf_vacancy_total,
        "excluded_other_body_vacancies": pdf_vacancy_total - owned_total,
        "total": owned_total,
        "counts": ordered_counts(counts),
    }


def aggregate_vacancy_documents(documents: list[dict]) -> tuple[dict[str, int], dict[str, dict], int]:
    total_counts: Counter[str] = Counter()
    body_counts: dict[str, Counter[str]] = {
        "maestros": Counter(),
        "secundaria": Counter(),
    }
    body_totals = {"maestros": 0, "secundaria": 0}
    for document in documents:
        body = str(document.get("body") or "")
        counts = Counter({str(code): int(value) for code, value in (document.get("counts") or {}).items()})
        total_counts.update(counts)
        if body in body_counts:
            body_counts[body].update(counts)
            body_totals[body] += sum(counts.values())
    bodies = {
        body: {
            "total": body_totals[body],
            "counts": ordered_counts(body_counts[body]),
        }
        for body in ("maestros", "secundaria")
        if body_totals[body] or body_counts[body]
    }
    return ordered_counts(total_counts), bodies, sum(total_counts.values())


def apply_vacancy_totals_inicio(data: dict, parsed_items: list[ParsedPdf]) -> bool:
    if not parsed_items:
        return False
    latest_by_body: dict[str, ParsedPdf] = {}
    for parsed in parsed_items:
        old = latest_by_body.get(parsed.body)
        if old is None or (parsed.published_date or "") >= (old.published_date or ""):
            latest_by_body[parsed.body] = parsed

    newest = max(latest_by_body.values(), key=lambda item: item.published_date or "")
    school_year = school_year_for_date(newest.published_date, now_local())
    vacancy_totals = data.setdefault("vacancy_totals", json.loads(json.dumps(DEFAULT_DATA["vacancy_totals"])))
    current = vacancy_totals.get("inicio")
    if not isinstance(current, dict) or current.get("school_year") != school_year:
        current = {
            "school_year": school_year,
            "start_year": start_year_from_school_year(school_year),
            "updated_at": None,
            "total": 0,
            "counts": {},
            "bodies": {},
        }
        vacancy_totals["inicio"] = current
        vacancy_totals["curso"] = None

    bodies = current.setdefault("bodies", {})
    for body, parsed in latest_by_body.items():
        document = vacancy_document_summary(parsed)
        bodies[body] = {
            key: value
            for key, value in document.items()
            if key not in {"url", "body"}
        }

    body_documents = [
        {"body": body, **summary}
        for body, summary in bodies.items()
        if isinstance(summary, dict)
    ]
    counts, aggregated_bodies, total = aggregate_vacancy_documents(body_documents)
    for body, summary in aggregated_bodies.items():
        if body in bodies:
            summary.update({
                key: value
                for key, value in bodies[body].items()
                if key not in {"counts", "total"}
            })
            aggregated_bodies[body] = summary
    dates = [
        str(summary.get("published_date") or "")
        for summary in bodies.values()
        if isinstance(summary, dict) and summary.get("published_date")
    ]
    current.update({
        "school_year": school_year,
        "start_year": start_year_from_school_year(school_year),
        "updated_at": max(dates) if dates else None,
        "total": total,
        "counts": counts,
        "bodies": aggregated_bodies,
    })
    return True


def apply_vacancy_totals_curso(data: dict, parsed_items: list[ParsedPdf]) -> bool:
    if not parsed_items:
        return False
    newest = max(parsed_items, key=lambda item: item.published_date or "")
    school_year = school_year_for_date(newest.published_date, now_local())
    vacancy_totals = data.setdefault("vacancy_totals", json.loads(json.dumps(DEFAULT_DATA["vacancy_totals"])))
    current = vacancy_totals.get("curso")
    if not isinstance(current, dict) or current.get("school_year") != school_year:
        current = {
            "school_year": school_year,
            "first_date": None,
            "updated_at": None,
            "total": 0,
            "counts": {},
            "bodies": {},
            "documents": {},
        }
        vacancy_totals["curso"] = current

    documents = current.setdefault("documents", {})
    changed = False
    for parsed in parsed_items:
        if any(
            item.get("pdf_sha256") == parsed.sha256 and url != parsed.url
            for url, item in documents.items()
        ):
            continue
        document = vacancy_document_summary(parsed)
        if documents.get(parsed.url) != document:
            documents[parsed.url] = document
            changed = True

    if not changed:
        return False
    document_list = [item for item in documents.values() if isinstance(item, dict)]
    counts, bodies, total = aggregate_vacancy_documents(document_list)
    dates = sorted(
        str(item.get("published_date"))
        for item in document_list
        if item.get("published_date")
    )
    current.update({
        "school_year": school_year,
        "first_date": dates[0] if dates else None,
        "updated_at": dates[-1] if dates else None,
        "total": total,
        "counts": counts,
        "bodies": bodies,
        "documents": documents,
    })
    return True


def apply_inicio(data: dict, parsed_items: list[ParsedPdf]) -> bool:
    changed = False
    latest_by_body: dict[str, ParsedPdf] = {}
    for item in parsed_items:
        old = latest_by_body.get(item.body)
        if old is None or (item.published_date or "") >= (old.published_date or ""):
            latest_by_body[item.body] = item

    for body, parsed in latest_by_body.items():
        school_year = school_year_for_date(parsed.published_date, now_local())
        inicio = data["cuts"]["inicio"]
        if inicio.get("school_year") != school_year:
            inicio.update({
                "school_year": school_year,
                "start_year": start_year_from_school_year(school_year),
                "updated_at": parsed.published_date,
                "rows": [],
                "pdfs": {},
            })
            data["cuts"]["curso"].update({"school_year": school_year, "updated_at": parsed.published_date, "rows": [], "pdfs": []})
            changed = True
        existing = [row for row in inicio.get("rows", []) if len(row) < 7 or row[6] != body]
        inicio["rows"] = sorted(existing + [row_with_origin(row, "inicio") for row in parsed.rows], key=lambda r: (str(r[1]), int(r[2]), str(r[0])))
        inicio["updated_at"] = max(inicio.get("updated_at") or "", parsed.published_date or "") or None
        inicio.setdefault("pdfs", {})[body] = {
            "url": parsed.url,
            "sha256": parsed.sha256,
            "published_date": parsed.published_date,
            "rows": len(parsed.rows),
        }
        curso = data["cuts"]["curso"]
        if curso.get("school_year") == school_year and not curso.get("pdfs"):
            curso["updated_at"] = inicio["updated_at"]
            curso["rows"] = [row_with_origin(row, "inicio") for row in inicio["rows"]]
        mark_processed(data, parsed, "inicio")
        changed = True
    return changed


def apply_curso(data: dict, parsed_items: list[ParsedPdf]) -> bool:
    if not parsed_items:
        return False
    parsed_items.sort(key=lambda item: (item.published_date or "", item.body, item.url))
    curso = data["cuts"]["curso"]
    current_year = school_year_for_date(parsed_items[-1].published_date, now_local())
    inicio = data["cuts"]["inicio"]
    if curso.get("school_year") != current_year:
        curso.update({"school_year": current_year, "updated_at": None, "rows": [], "pdfs": []})
    seed_rows = curso.get("rows") or (inicio.get("rows", []) if inicio.get("school_year") == current_year else [])
    rows_by_key = {row_key(row): row_with_origin(row, row_origin(row, "inicio")) for row in seed_rows}
    changed = False

    for parsed in parsed_items:
        for row in parsed.rows:
            rows_by_key[row_key(row)] = row_with_origin(row, "curso")
        curso["updated_at"] = max(curso.get("updated_at") or "", parsed.published_date or "") or None
        pdf_item = {
            "url": parsed.url,
            "sha256": parsed.sha256,
            "body": parsed.body,
            "published_date": parsed.published_date,
            "rows": len(parsed.rows),
        }
        history = curso.setdefault("pdfs", [])
        if not any(item.get("sha256") == parsed.sha256 for item in history):
            history.append(pdf_item)
        mark_processed(data, parsed, "curso")
        changed = True

    curso["school_year"] = current_year
    curso["rows"] = sorted(rows_by_key.values(), key=lambda r: (str(r[1]), int(r[2]), str(r[0])))
    return changed


def link_points_outside_target_year(link: dict[str, str], target_school_year: str | None) -> bool:
    if not target_school_year:
        return False
    start_year, end_year = [int(part) for part in target_school_year.split("-", 1)]
    allowed = {start_year, end_year}
    url = urllib.parse.unquote(link.get("url", ""))
    filename = url.rsplit("/", 1)[-1]
    combined = f"{link.get('text', '')} {filename} {url}"
    full_years = {int(match) for match in re.findall(r"(?<!\d)(20\d{2})(?!\d)", combined)}
    if full_years and full_years.isdisjoint(allowed):
        return True
    match = re.match(r"^(\d{2})(\d{2})(\d{2})", filename)
    if match:
        inferred_year = 2000 + int(match.group(1))
        if inferred_year not in allowed:
            return True
    return False


def run_mode(
    data: dict,
    mode: str,
    centers_by_code: dict[str, dict[str, str]],
    target_school_year: str | None,
    position_context: PositionContextUpdater | None = None,
    master_positions: MasterCutPositionIndex | None = None,
) -> bool:
    page_url = START_PAGE_URL if mode == "inicio" else COURSE_PAGE_URL
    links = extract_pdf_links(page_url)
    print(f"{mode}: encontrados {len(links)} enlaces PDF")
    parsed_items: list[ParsedPdf] = []
    changed = False
    for link in links:
        if url_already_seen(data, link["url"]):
            continue
        if link_points_outside_target_year(link, target_school_year):
            mark_ignored(data, link["url"], None, mode, f"fuera del curso {target_school_year}")
            changed = True
            continue
        try:
            pdf_bytes = http_get(link["url"])
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            parsed = parse_pdf(
                link["url"],
                pdf_bytes,
                centers_by_code,
                master_positions,
                mode,
            )
            if parsed is None:
                print(f"{mode}: omitido PDF no clasificable {link['url']}")
                mark_ignored(data, link["url"], sha256, mode, "pdf no clasificable")
                changed = True
                continue
            if target_school_year and parsed.published_date:
                parsed_year = school_year_for_date(parsed.published_date, now_local())
                if parsed_year != target_school_year:
                    print(f"{mode}: omitido PDF de otro curso ({parsed_year}) {link['url']}")
                    mark_ignored(data, link["url"], parsed.sha256, mode, f"fuera del curso {target_school_year}", parsed.body, parsed.published_date)
                    changed = True
                    continue
            if pdf_already_processed(data, parsed):
                continue
            parsed_items.append(parsed)
            print(f"{mode}: nuevo PDF {parsed.body} {parsed.published_date or 'sin fecha'} {link['url']} filas={len(parsed.rows)}")
        except Exception as exc:
            print(f"WARNING: no se pudo procesar {link['url']}: {exc}", file=sys.stderr)
    if mode == "inicio":
        result = apply_inicio(data, parsed_items) or changed
        result = apply_vacancy_totals_inicio(data, parsed_items) or result
    else:
        result = apply_curso(data, parsed_items) or changed
        result = apply_vacancy_totals_curso(data, parsed_items) or result
    if position_context is not None and parsed_items:
        position_context.apply(parsed_items, mode)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", choices=["inicio", "curso", "all"], help="Ejecuta una comprobacion aunque no toque por calendario.")
    parser.add_argument("--data", default=str(DATA_PATH), help="Ruta del JSON de datos.")
    parser.add_argument("--positions", default=str(POSITIONS_PATH), help="Ruta del JSON de posiciones.")
    parser.add_argument(
        "--position-context-state",
        default=str(POSITION_CONTEXT_STATE_PATH),
        help="Ruta del estado acumulativo usado para la informacion provincial.",
    )
    parser.add_argument(
        "--skip-position-context",
        action="store_true",
        help="Actualiza solo los cortes y omite la informacion provincial.",
    )
    parser.add_argument("--school-year", help="Curso escolar objetivo, por ejemplo 2025-2026. Por defecto usa el curso activo en Europe/Madrid.")
    parser.add_argument("--include-old", action="store_true", help="Permite procesar PDFs de otros cursos. Usar solo para reconstrucciones controladas.")
    return parser.parse_args()


def main() -> int:
    global DATA_PATH
    args = parse_args()
    DATA_PATH = Path(args.data)

    dt = now_local()
    modes: list[str] = []
    if args.force in ("inicio", "all") or (args.force is None and is_start_window(dt)):
        modes.append("inicio")
    if args.force in ("curso", "all") or (args.force is None and is_course_window(dt)):
        modes.append("curso")

    if not modes:
        print(f"Sin comprobacion programada para {dt.isoformat(timespec='seconds')}")
        return 0

    data = load_data()
    data["centers"], centers_by_code = load_centers(data.get("centers", []))
    position_context = None
    if not args.skip_position_context:
        position_context = PositionContextUpdater(
            Path(args.positions),
            Path(args.position_context_state),
        )
    master_positions = MasterCutPositionIndex(Path(args.positions))
    target_school_year = None if args.include_old else (args.school_year or school_year_for_date(None, dt))
    changed = migrate_secondary_header_policy(data, centers_by_code)
    changed = ensure_cut_schema(data) or changed
    changed = enrich_master_cut_positions(data, master_positions) or changed
    policy_changed = data.get("cut_policy") != CUT_POLICY
    if policy_changed:
        data["cut_policy"] = CUT_POLICY
    vacancy_policy_changed = data.get("vacancy_totals_policy") != VACANCY_TOTALS_POLICY
    if vacancy_policy_changed:
        data["vacancy_totals_policy"] = VACANCY_TOTALS_POLICY
    master_position_policy_changed = data.get("master_cut_position_policy") != MASTER_CUT_POSITION_POLICY
    if master_position_policy_changed:
        data["master_cut_position_policy"] = MASTER_CUT_POSITION_POLICY
    changed = changed or policy_changed or vacancy_policy_changed or master_position_policy_changed
    for mode in modes:
        changed = run_mode(
            data,
            mode,
            centers_by_code,
            target_school_year,
            position_context,
            master_positions,
        ) or changed
    changed = enrich_master_cut_positions(data, master_positions) or changed
    changed = ensure_period_metadata(data) or changed

    save_data(data)
    position_context_changed = bool(position_context and position_context.save())
    print("JSON actualizado" if changed else "Sin cambios de adjudicaciones")
    if position_context_changed:
        print("Informacion provincial de posiciones actualizada")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
