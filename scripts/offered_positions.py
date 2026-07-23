from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pdfplumber


SCHEMA_VERSION = 1
DATASET = "puestos_ofertados"
UPDATE_MODE = "replace_latest_snapshot"
SLOT_X_MIN = 293.4
SLOT_X_MAX = 317.0
SPECIALTY_OVERRIDES = {
    "152": {
        "code": "152",
        "es": "Educación Especial: Pedagogía Terapéutica",
        "va": "Educació Especial: Pedagogia Terapèutica",
        "body": "maestros",
    },
    "294": {
        "code": "294",
        "es": "FPA Comunicación (Inglés)",
        "va": "FPA Comunicació (Anglés)",
        "body": "otros",
    },
}
ITEM_FIELDS = [
    "offer_order",
    "body",
    "specialty_code",
    "province",
    "municipality",
    "center_code",
    "center_name_pdf",
    "slot_id",
    "hours",
    "english_requirement",
    "itinerant",
    "observations",
    "placement_type",
]


def compact_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_date(raw: str) -> str:
    return datetime.strptime(raw, "%d/%m/%Y").date().isoformat()


def academic_year_for(date_iso: str) -> str:
    date = datetime.strptime(date_iso, "%Y-%m-%d").date()
    first_year = date.year if date.month >= 7 else date.year - 1
    return f"{first_year}-{first_year + 1}"


def normalize_body(raw: str) -> str:
    return (
        "maestros"
        if compact_text(raw).upper() in {"MAESTROS", "MESTRES"}
        else "otros"
    )


def normalize_province(raw: str) -> str:
    key = compact_text(raw).casefold()
    if key in {"alacant", "alicante"}:
        return "Alicante"
    if key in {"valència", "valencia"}:
        return "Valencia"
    if key in {"castelló", "castellón", "castello", "castellon"}:
        return "Castellón"
    return compact_text(raw)


def normalize_placement(raw: str) -> str:
    key = compact_text(raw).upper()
    if key in {"VACANTE", "VACANT"}:
        return "vacante"
    if "INDETERMINADA" in key:
        return "sub_indeterminada"
    if "DETERMINADA" in key:
        return "sub_determinada"
    raise ValueError(f"Tipo de puesto no reconocido: {raw!r}")


def parse_specialty(raw: str) -> tuple[str, str]:
    match = re.match(r"^([0-9A-Z]+)\s*-\s*(.+)$", compact_text(raw), re.IGNORECASE)
    if not match:
        raise ValueError(f"Especialidad no reconocida: {raw!r}")
    return match.group(1).upper(), match.group(2).strip()


def row_text(page: pdfplumber.page.Page, row: dict[str, Any], x0: float, x1: float) -> str:
    top = max(0, float(row["top"]) - 2.2)
    bottom = min(float(page.height), float(row["bottom"]) + 2.2)
    return compact_text(
        page.crop((x0, top, x1, bottom)).extract_text(x_tolerance=1, y_tolerance=2)
    )


def extract_slot_id(page: pdfplumber.page.Page, row: dict[str, Any]) -> str | None:
    """Read the six-digit slot id even when it overlaps a long center name."""
    top = max(0, float(row["top"]) - 2.2)
    bottom = min(float(page.height), float(row["bottom"]) + 2.2)
    # Keep the PDF content-stream order: the slot is drawn after the center
    # name, so its six digits are the final six digits in this narrow column.
    digit_chars = [
        char
        for char in page.chars
        if str(char.get("text", "")).isdigit()
        and top <= float(char["top"]) <= bottom
        and SLOT_X_MIN <= float(char["x0"]) <= SLOT_X_MAX
    ]
    slot_id = "".join(str(char["text"]) for char in digit_chars[-6:])
    return slot_id if re.fullmatch(r"\d{6}", slot_id) else None


def context_lines(page: pdfplumber.page.Page) -> list[dict[str, Any]]:
    return page.extract_text_lines(
        layout=False,
        strip=True,
        return_chars=False,
        x_tolerance=2,
        y_tolerance=3,
    )


def nearest_context(
    contexts: list[tuple[float, str]], row_top: float, label: str, page_number: int
) -> str:
    values = [value for top, value in contexts if top < row_top]
    if not values:
        raise ValueError(f"Falta {label} antes de una fila en la página {page_number}")
    return values[-1]


def parse_pdf(
    pdf_path: Path,
    specialties: list[dict[str, Any]],
    center_names: dict[str, str],
) -> dict[str, Any]:
    items: list[list[Any]] = []
    publication_date = ""
    specialty_by_code = {str(item["code"]): dict(item) for item in specialties}

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            page_text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            if not publication_date:
                date_match = re.search(
                    r"ADJUDICACI[ÓO]N DE PERSONAL DOCENTE INTERINO D[ÍI]A\s+(\d{2}/\d{2}/\d{4})",
                    page_text,
                    re.IGNORECASE,
                )
                if date_match:
                    publication_date = normalize_date(date_match.group(1))

            bodies: list[tuple[float, str]] = []
            page_specialties: list[tuple[float, str]] = []
            provinces: list[tuple[float, str]] = []
            for line in context_lines(page):
                text = compact_text(line.get("text"))
                top = float(line.get("top", 0))
                if text.startswith("CUERPO/COS:"):
                    bodies.append((top, text.split(":", 1)[1].strip()))
                elif text.startswith("ESPECIALIDAD/ESPECIALITAT:"):
                    page_specialties.append((top, text.split(":", 1)[1].strip()))
                elif text.startswith("PROVINCIA/PROVINCIA:"):
                    provinces.append((top, text.split(":", 1)[1].strip()))

            words = page.extract_words(x_tolerance=1, y_tolerance=2)
            row_numbers = [
                word
                for word in words
                if word["text"].isdigit()
                and float(word["x0"]) < 43
                and int(word["text"]) < 10000
                and float(word["top"]) < float(page.height) - 20
            ]

            seen_on_page: set[tuple[str, float]] = set()
            for row in row_numbers:
                row_marker = (row["text"], round(float(row["top"]), 1))
                if row_marker in seen_on_page:
                    continue
                seen_on_page.add(row_marker)

                center_cell = row_text(page, row, 43, 327)
                center_match = re.match(
                    r"^(.+?)\s+-\s+(\d{8})\s+-\s+(.+)$", center_cell
                )
                if not center_match:
                    continue

                municipality = center_match.group(1).strip()
                center_code = center_match.group(2)
                extracted_center_name = center_match.group(3).strip()
                slot_id = extract_slot_id(page, row)
                center_name_pdf = center_names.get(center_code, extracted_center_name)
                requirement = row_text(page, row, 327, 454)
                itinerary = row_text(page, row, 454, 618)
                placement_raw = row_text(page, row, 618, 840)

                body_raw = nearest_context(bodies, float(row["top"]), "cuerpo", page_number)
                specialty_raw = nearest_context(
                    page_specialties, float(row["top"]), "especialidad", page_number
                )
                province_raw = nearest_context(
                    provinces, float(row["top"]), "provincia", page_number
                )
                specialty_code, specialty_name = parse_specialty(specialty_raw)
                body = normalize_body(body_raw)
                specialty_by_code.setdefault(
                    specialty_code,
                    SPECIALTY_OVERRIDES.get(
                        specialty_code,
                        {
                        "code": specialty_code,
                        "es": specialty_name.title(),
                        "va": specialty_name.title(),
                        "body": body,
                        },
                    ),
                )

                requirement_without_english = re.sub(
                    r"\bING(?:L[ÉE]S)?\s*-?\s*B2\b",
                    " ",
                    requirement,
                    flags=re.IGNORECASE,
                )
                hours_match = re.search(
                    r"(?<![\w-])(\d{1,2}(?:[,.]\d+)?)(?![\w-])",
                    requirement_without_english,
                )
                hours = (
                    float(hours_match.group(1).replace(",", "."))
                    if hours_match
                    else None
                )
                english_requirement = bool(re.search(r"\bING(?:L[ÉE]S)?\s*-?\s*B2\b", requirement, re.IGNORECASE))
                itinerant_match = re.match(r"^(S[ÍI]|NO)\b\.?\s*(.*)$", itinerary, re.IGNORECASE)
                if not itinerant_match:
                    raise ValueError(
                        f"Itinerancia no reconocida en página {page_number}, puesto {row['text']}: {itinerary!r}"
                    )
                itinerant = itinerant_match.group(1).upper() in {"SI", "SÍ"}
                observations = itinerant_match.group(2).strip()

                items.append(
                    [
                        int(row["text"]),
                        body,
                        specialty_code,
                        normalize_province(province_raw),
                        municipality,
                        center_code,
                        center_name_pdf,
                        slot_id,
                        hours,
                        english_requirement,
                        itinerant,
                        observations,
                        normalize_placement(placement_raw),
                    ]
                )

    if not publication_date:
        raise ValueError("No se ha encontrado la fecha oficial de adjudicación")
    if not items:
        raise ValueError("No se ha extraído ningún puesto")

    order_values = [int(item[0]) for item in items]
    if len(order_values) != len(set(order_values)):
        raise ValueError("Hay números de puesto duplicados")

    specialties_sorted = sorted(
        specialty_by_code.values(),
        key=lambda item: (str(item.get("body", "")), str(item["code"])),
    )
    return build_payload(
        specialties=specialties_sorted,
        academic_year=academic_year_for(publication_date),
        status="published",
        publication_date=publication_date,
        source={
            "filename": pdf_path.name,
            "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        },
        items=sorted(items, key=lambda item: int(item[0])),
    )


def build_payload(
    *,
    specialties: list[dict[str, Any]],
    academic_year: str,
    status: str,
    publication_date: str | None,
    source: dict[str, Any] | None,
    items: list[list[Any]],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset": DATASET,
        "update_mode": UPDATE_MODE,
        "replacement_policy": "El PDF más reciente sustituye por completo el listado anterior.",
        "academic_year": academic_year,
        "status": status,
        "publication_date": publication_date,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "specialties": specialties,
        "item_fields": ITEM_FIELDS,
        "items": items,
    }


def load_specialties(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    specialties = payload.get("specialties")
    if not isinstance(specialties, list) or not specialties:
        raise ValueError(f"No hay catálogo de especialidades en {path}")
    by_code = {
        str(item["code"]): dict(item)
        for item in specialties
        if isinstance(item, dict) and item.get("code")
    }
    by_code.update({code: dict(item) for code, item in SPECIALTY_OVERRIDES.items()})
    return list(by_code.values())


def load_center_names(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    centers = payload.get("centers")
    if not isinstance(centers, list) or not centers:
        raise ValueError(f"No hay catálogo de centros en {path}")

    center_format = payload.get("center_format")
    if isinstance(center_format, list):
        try:
            code_index = center_format.index("codigo")
            name_index = center_format.index("nombre")
        except ValueError as error:
            raise ValueError(f"Formato de centros no reconocido en {path}") from error
        result = {
            str(row[code_index]): compact_text(row[name_index])
            for row in centers
            if isinstance(row, list)
            and len(row) > max(code_index, name_index)
            and compact_text(row[code_index])
            and compact_text(row[name_index])
        }
    else:
        result = {
            str(row.get("codigo") or row.get("code")): compact_text(
                row.get("nombre") or row.get("name")
            )
            for row in centers
            if isinstance(row, dict)
            and compact_text(row.get("codigo") or row.get("code"))
            and compact_text(row.get("nombre") or row.get("name"))
        }
    if not result:
        raise ValueError(f"No se han podido leer los centros de {path}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convierte el último PDF de puestos ofertados en una instantánea JSON."
    )
    parser.add_argument("--specialties", type=Path, required=True)
    parser.add_argument("--centers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pdf", type=Path)
    group.add_argument("--empty-year")
    args = parser.parse_args()

    specialties = load_specialties(args.specialties)
    center_names = load_center_names(args.centers)
    if args.pdf:
        payload = parse_pdf(args.pdf, specialties, center_names)
    else:
        if not re.fullmatch(r"\d{4}-\d{4}", args.empty_year):
            raise ValueError("El curso debe tener el formato 2026-2027")
        payload = build_payload(
            specialties=specialties,
            academic_year=args.empty_year,
            status="awaiting_first_continuous_adjudication",
            publication_date=None,
            source=None,
            items=[],
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "academic_year": payload["academic_year"],
                "status": payload["status"],
                "publication_date": payload["publication_date"],
                "specialties": len(payload["specialties"]),
                "items": len(payload["items"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
