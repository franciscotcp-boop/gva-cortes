from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import os
import re
import socket
import ssl
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from offered_positions import (
    DATASET,
    ITEM_FIELDS,
    UPDATE_MODE,
    build_payload,
    compact_text,
    load_center_names,
    load_specialties,
    parse_pdf,
)


PAGE_URL = (
    "https://ceice.gva.es/es/web/rrhh-educacion/"
    "convocatoria-y-peticion-telematica"
)
DEFAULT_OUTPUT = Path("data/puestos_ofertados.json")
DEFAULT_SPECIALTIES = Path("data/posiciones_bolsa.json")
DEFAULT_CENTERS = Path("data/adjudicaciones.json")
MADRID = ZoneInfo("Europe/Madrid")


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

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
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
                {
                    "url": self._href.split("#", 1)[0],
                    "text": compact_text(" ".join(self._text)),
                }
            )
            self._href = None
            self._text = []


def normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.casefold()).strip()


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
                "User-Agent": (
                    "AdjudicApp/1.0 "
                    "(+https://github.com/franciscotcp-boop/gva-cortes)"
                ),
                "Accept": (
                    "text/html,application/pdf,application/octet-stream;"
                    "q=0.9,*/*;q=0.5"
                ),
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

    raise SourceAccessError(
        f"Conselleria no responde tras {attempts} intentos: {url}: {last_error}"
    )


def extract_links(page_html: bytes, page_url: str) -> list[dict[str, str]]:
    parser = LinkParser(page_url)
    parser.feed(page_html.decode("utf-8", errors="replace"))
    seen: set[str] = set()
    links: list[dict[str, str]] = []
    for link in parser.links:
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        links.append(link)
    return links


def candidate_filename(link: dict[str, str]) -> str:
    path = urllib.parse.unquote(urllib.parse.urlparse(link.get("url", "")).path)
    return Path(path).name or "puestos_ofertados.pdf"


def is_offered_positions_pdf(link: dict[str, str]) -> bool:
    url = urllib.parse.unquote(link.get("url", ""))
    if ".pdf" not in url.casefold():
        return False
    filename = normalized(candidate_filename(link))
    combined = normalized(f"{filename} {link.get('text', '')}")
    if re.search(r"(?:^|[^a-z0-9])pue[^a-z0-9]+prov(?:[^a-z0-9]|$)", filename):
        return True
    if "puestos" in combined and any(
        word in combined for word in ("ofertados", "ofertats", "oferts")
    ):
        return True
    return "llocs" in combined and any(
        word in combined for word in ("ofertats", "oferits", "oferts")
    )


def offered_position_links(page_html: bytes, page_url: str) -> list[dict[str, str]]:
    return [
        link
        for link in extract_links(page_html, page_url)
        if is_offered_positions_pdf(link)
    ]


def _valid_date(year: int, month: int, day: int) -> date | None:
    if year < 2000 or year > 3000:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def document_date_hint(link: dict[str, str]) -> date | None:
    value = f"{candidate_filename(link)} {link.get('text', '')}"
    patterns = (
        (r"(?<!\d)(\d{4})[-_./](\d{1,2})[-_./](\d{1,2})(?!\d)", False),
        (r"(?<!\d)(\d{1,2})[-_./](\d{1,2})[-_./](\d{4})(?!\d)", True),
    )
    for pattern, day_first in patterns:
        match = re.search(pattern, value)
        if not match:
            continue
        first, second, third = (int(part) for part in match.groups())
        if day_first:
            result = _valid_date(third, second, first)
        else:
            result = _valid_date(first, second, third)
        if result:
            return result

    compact_match = re.search(
        r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)",
        candidate_filename(link),
    )
    if compact_match:
        year, month, day = (int(part) for part in compact_match.groups())
        return _valid_date(2000 + year, month, day)
    return None


def academic_year_for_check(value: date) -> str:
    if value.month >= 9 or (value.month == 7 and value.day > 1) or value.month == 8:
        first_year = value.year
    else:
        first_year = value.year - 1
    return f"{first_year}-{first_year + 1}"


def academic_year_for_document(value: date) -> str:
    return academic_year_for_check(value)


def is_correction(link: dict[str, str]) -> bool:
    value = normalized(f"{candidate_filename(link)} {link.get('text', '')}")
    return "correccion" in value or "correccio" in value


def links_for_latest_target_document(
    links: list[dict[str, str]], target_year: str
) -> list[dict[str, str]]:
    indexed = list(enumerate(links))
    hinted = [
        (index, link, hint)
        for index, link in indexed
        if (hint := document_date_hint(link))
        and academic_year_for_document(hint) == target_year
    ]
    if hinted:
        newest_date = max(hint for _, _, hint in hinted)
        newest = [entry for entry in hinted if entry[2] == newest_date]
        if any(is_correction(link) for _, link, _ in newest):
            newest = [entry for entry in newest if is_correction(entry[1])]
        return [
            link
            for _, link, _ in sorted(
                newest,
                key=lambda entry: entry[0],
            )
        ]

    return [link for _, link in indexed if document_date_hint(link) is None]


def parse_iso_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def load_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SourceValidationError(f"JSON existente no legible: {path}: {error}") from error
    if payload and payload.get("dataset") != DATASET:
        raise SourceValidationError(f"Dataset inesperado en {path}")
    return payload


def validate_payload(payload: dict, target_year: str) -> None:
    if payload.get("dataset") != DATASET or payload.get("update_mode") != UPDATE_MODE:
        raise SourceValidationError("El PDF no ha producido el dataset esperado")
    if payload.get("academic_year") != target_year:
        raise SourceValidationError(
            f"El PDF pertenece a {payload.get('academic_year')}, no a {target_year}"
        )
    if payload.get("status") != "published":
        raise SourceValidationError("El estado del PDF procesado no es published")
    if not parse_iso_date(payload.get("publication_date")):
        raise SourceValidationError("El PDF no contiene una fecha oficial valida")
    if payload.get("item_fields") != ITEM_FIELDS:
        raise SourceValidationError("El formato de puestos ha cambiado")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise SourceValidationError("El PDF no contiene puestos ofertados")
    if any(not isinstance(item, list) or len(item) != len(ITEM_FIELDS) for item in items):
        raise SourceValidationError("Hay filas de puestos incompletas")
    orders = [item[0] for item in items]
    if len(orders) != len(set(orders)):
        raise SourceValidationError("Hay numeros de puesto duplicados")
    if any(not re.fullmatch(r"\d{8}", str(item[5])) for item in items):
        raise SourceValidationError("Hay codigos de centro no validos")
    if any(item[12] not in {"vacante", "sub_indeterminada", "sub_determinada"} for item in items):
        raise SourceValidationError("Hay tipos de puesto no reconocidos")


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False, dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        ) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def empty_payload(specialties: list[dict], academic_year: str) -> dict:
    return build_payload(
        specialties=specialties,
        academic_year=academic_year,
        status="awaiting_first_continuous_adjudication",
        publication_date=None,
        source=None,
        items=[],
    )


def parse_downloaded_pdf(
    content: bytes,
    link: dict[str, str],
    page_url: str,
    specialties: list[dict],
    center_names: dict[str, str],
) -> dict:
    if not content.lstrip().startswith(b"%PDF-"):
        raise SourceValidationError(
            f"El enlace no ha devuelto un PDF: {link.get('url', '')}"
        )
    suffix = Path(candidate_filename(link)).suffix or ".pdf"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=suffix) as handle:
            handle.write(content)
            temporary = Path(handle.name)
        payload = parse_pdf(temporary, specialties, center_names)
    except Exception as error:
        if isinstance(error, SourceValidationError):
            raise
        raise SourceValidationError(
            f"No se ha podido validar {candidate_filename(link)}: {error}"
        ) from error
    finally:
        if temporary and temporary.exists():
            temporary.unlink()

    publication_date = parse_iso_date(payload.get("publication_date"))
    if not publication_date:
        raise SourceValidationError("No se ha reconocido la fecha del PDF")
    payload["academic_year"] = academic_year_for_document(publication_date)
    payload["source"] = {
        "page_url": page_url,
        "url": link.get("url", ""),
        "filename": candidate_filename(link),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    if link.get("text"):
        payload["source"]["link_text"] = compact_text(link["text"])
    return payload


def should_publish(existing: dict, payload: dict) -> bool:
    existing_source = existing.get("source") if isinstance(existing.get("source"), dict) else {}
    new_source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    if existing_source.get("sha256") == new_source.get("sha256"):
        return False
    existing_date = parse_iso_date(existing.get("publication_date"))
    new_date = parse_iso_date(payload.get("publication_date"))
    if existing.get("academic_year") == payload.get("academic_year"):
        if existing_date and new_date and new_date < existing_date:
            return False
    return True


def update_from_page(
    *,
    page_url: str,
    output: Path,
    specialties_path: Path,
    centers_path: Path,
    target_year: str,
    fetch: Callable[[str], bytes] = http_get,
) -> dict:
    specialties = load_specialties(specialties_path)
    center_names = load_center_names(centers_path)
    existing = load_existing(output)
    page_html = fetch(page_url)
    links = offered_position_links(page_html, page_url)
    candidates = links_for_latest_target_document(links, target_year)
    errors: list[str] = []

    for link in candidates:
        try:
            payload = parse_downloaded_pdf(
                fetch(link["url"]), link, page_url, specialties, center_names
            )
            if payload.get("academic_year") != target_year:
                hint = document_date_hint(link)
                if hint and academic_year_for_document(hint) == target_year:
                    errors.append(
                        f"La fecha interna de {candidate_filename(link)} no coincide con su enlace"
                    )
                continue
            validate_payload(payload, target_year)
        except SourceValidationError as error:
            errors.append(str(error))
            continue

        if should_publish(existing, payload):
            atomic_write_json(output, payload)
            return {
                "result": "updated",
                "target_year": target_year,
                "publication_date": payload["publication_date"],
                "items": len(payload["items"]),
                "source": payload["source"]["url"],
            }
        return {
            "result": "unchanged",
            "target_year": target_year,
            "publication_date": payload["publication_date"],
            "items": len(payload["items"]),
            "source": payload["source"]["url"],
        }

    target_hints = [
        hint
        for link in links
        if (hint := document_date_hint(link))
        and academic_year_for_document(hint) == target_year
    ]
    if candidates and (target_hints or errors):
        raise SourceValidationError(
            "No se ha podido procesar el PDF mas reciente de puestos ofertados: "
            + " | ".join(errors or ["documento no valido"])
        )

    if existing.get("academic_year") != target_year or existing.get("dataset") != DATASET:
        payload = empty_payload(specialties, target_year)
        atomic_write_json(output, payload)
        result = "new_academic_year_without_offers"
    else:
        result = "no_current_document"
    return {
        "result": result,
        "target_year": target_year,
        "publication_date": None,
        "items": 0,
        "source": None,
    }


def valid_academic_year(value: str) -> bool:
    match = re.fullmatch(r"(\d{4})-(\d{4})", value)
    return bool(
        match
        and 2000 <= int(match.group(1)) < 3000
        and int(match.group(2)) == int(match.group(1)) + 1
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Actualiza exclusivamente la instantanea de puestos ofertados de "
            "las adjudicaciones continuas."
        )
    )
    parser.add_argument("--page-url", default=PAGE_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--specialties", type=Path, default=DEFAULT_SPECIALTIES)
    parser.add_argument("--centers", type=Path, default=DEFAULT_CENTERS)
    parser.add_argument("--school-year", default="")
    parser.add_argument("--now", help="Fecha ISO opcional para pruebas")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    current_date = (
        date.fromisoformat(args.now)
        if args.now
        else datetime.now(MADRID).date()
    )
    target_year = args.school_year or academic_year_for_check(current_date)
    if not valid_academic_year(target_year):
        raise ValueError("El curso debe tener el formato 2026-2027")
    result = update_from_page(
        page_url=args.page_url,
        output=args.output,
        specialties_path=args.specialties,
        centers_path=args.centers,
        target_year=target_year,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
