from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pdfplumber


MASTER_FLAGS = ("INF", "PRI", "ING", "FRA", "EF", "PT", "AL", "MUS")
MASTER_SPECIALTIES = {
    "INF": ("120", "Educación Infantil", "Educació Infantil"),
    "ING": ("121", "Lengua Extranjera: Inglés", "Llengua Estrangera: Anglés"),
    "FRA": ("122", "Lengua Extranjera: Francés", "Llengua Estrangera: Francés"),
    "EF": ("123", "Educación Física", "Educació Física"),
    "MUS": ("124", "Música", "Música"),
    "AL": ("126", "Audición y Lenguaje", "Audició i Llenguatge"),
    "PT": ("127", "Pedagogía Terapéutica", "Pedagogia Terapèutica"),
    "PRI": ("128", "Educación Primaria", "Educació Primària"),
}
FPA_PRIMARY = ("153", "FPA Primaria", "FPA Primària")
EXTRA_SPECIALTY_NAMES = {
    "2A5": {"es": "Máquinas, Servicios y Producción", "va": "Màquines, Serveis i Producció"},
    "2A7": {"es": "Oficina de Proyectos de Fabricación Mecánica", "va": "Oficina de Projectes de Fabricació Mecànica"},
    "402": {"es": "Árabe", "va": "Àrab"},
    "407": {"es": "Euskera", "va": "Euskera"},
    "410": {"es": "Griego", "va": "Grec"},
    "415": {"es": "Portugués", "va": "Portugués"},
    "416": {"es": "Rumano", "va": "Romanés"},
    "507": {"es": "Caracterización", "va": "Caracterització"},
    "5A3": {"es": "Historia de la Música", "va": "Història de la Música"},
    "5A4": {"es": "Pedagogía", "va": "Pedagogia"},
    "5A5": {"es": "Improvisación y Acompañamiento", "va": "Improvisació i Acompanyament"},
    "5A9": {"es": "Lengua Alemana", "va": "Llengua Alemanya"},
    "5B0": {"es": "Lengua Francesa", "va": "Llengua Francesa"},
    "5B2": {"es": "Lengua Italiana", "va": "Llengua Italiana"},
    "5C1": {"es": "Contrabajo de Jazz", "va": "Contrabaix de Jazz"},
    "5D0": {"es": "Bajo Eléctrico", "va": "Baix Elèctric"},
    "5D2": {"es": "Instrumentos de Viento de Jazz", "va": "Instruments de Vent de Jazz"},
    "5D3": {"es": "Instrumentos Históricos de Cuerda Frotada", "va": "Instruments Històrics de Corda Fregada"},
    "5D5": {"es": "Instrumentos Históricos de Viento", "va": "Instruments Històrics de Vent"},
    "5D6": {"es": "Teclados/Piano Jazz", "va": "Teclats/Piano Jazz"},
    "5D7": {"es": "Escena Lírica", "va": "Escena Lírica"},
    "5DB": {"es": "Instrumentos de Viento de Jazz: Trombón", "va": "Instruments de Vent de Jazz: Trombó"},
    "5DD": {"es": "Instrumentos Históricos de Cuerda Frotada: Violín Barroco", "va": "Instruments Històrics de Corda Fregada: Violí Barroc"},
    "5DF": {"es": "Instrumentos Históricos de Cuerda Frotada: Violonchelo Barroco", "va": "Instruments Històrics de Corda Fregada: Violoncel Barroc"},
    "5DG": {"es": "Instrumentos Históricos de Viento: Oboe Barroco", "va": "Instruments Històrics de Vent: Oboè Barroc"},
    "5DH": {"es": "Instrumentos Históricos de Viento: Traverso", "va": "Instruments Històrics de Vent: Traverso"},
    "5E0": {"es": "Contrabajo", "va": "Contrabaix"},
    "5E2": {"es": "Fagot", "va": "Fagot"},
    "5E3": {"es": "Flauta Travesera", "va": "Flauta Travessera"},
    "5E4": {"es": "Guitarra", "va": "Guitarra"},
    "5E7": {"es": "Oboe", "va": "Oboè"},
    "5F0": {"es": "Piano", "va": "Piano"},
    "5F1": {"es": "Saxofón", "va": "Saxòfon"},
    "5F2": {"es": "Trompa", "va": "Trompa"},
    "5F3": {"es": "Trompeta", "va": "Trompeta"},
    "5F4": {"es": "Tuba", "va": "Tuba"},
    "5F5": {"es": "Viola", "va": "Viola"},
    "5F6": {"es": "Violín", "va": "Violí"},
    "5F7": {"es": "Violonchelo", "va": "Violoncel"},
    "5F8": {"es": "Producción y Gestión de Música y Artes Escénicas", "va": "Producció i Gestió de Música i Arts Escèniques"},
    "5G1": {"es": "Ciencias de la Salud Aplicadas a la Danza", "va": "Ciències de la Salut Aplicades a la Dansa"},
    "5G5": {"es": "Trombón", "va": "Trombó"},
    "5G6": {"es": "Arpa", "va": "Arpa"},
    "5G7": {"es": "Órgano", "va": "Orgue"},
    "5G8": {"es": "Dirección de Coro", "va": "Direcció de Cor"},
    "5H4": {"es": "Análisis y Práctica del Repertorio de Danza Contemporánea", "va": "Anàlisi i Pràctica del Repertori de Dansa Contemporània"},
    "5K8": {"es": "Composición Coreográfica", "va": "Composició Coreogràfica"},
    "5L6": {"es": "Dramaturgia y Escritura Dramática", "va": "Dramatúrgia i Escriptura Dramàtica"},
    "5L8": {"es": "Estética e Historia del Arte", "va": "Estètica i Història de l'Art"},
    "5M3": {"es": "Interpretación en el Teatro de Texto", "va": "Interpretació en el Teatre de Text"},
    "5N6": {"es": "Iluminación", "va": "Il·luminació"},
    "6A1": {"es": "Arpa", "va": "Arpa"},
    "6A6": {"es": "Coro", "va": "Cor"},
    "6A7": {"es": "Fagot", "va": "Fagot"},
    "6B6": {"es": "Instrumentos de Cuerda Pulsada del Renacimiento y Barroco", "va": "Instruments de Corda Polsada del Renaixement i Barroc"},
    "6B7": {"es": "Instrumentos de Púa", "va": "Instruments de Pua"},
    "6B8": {"es": "Oboe", "va": "Oboè"},
    "6B9": {"es": "Órgano", "va": "Orgue"},
    "6C0": {"es": "Orquesta", "va": "Orquestra"},
    "6C3": {"es": "Saxofón", "va": "Saxòfon"},
    "6C5": {"es": "Trombón", "va": "Trombó"},
    "6C6": {"es": "Trompa", "va": "Trompa"},
    "6D0": {"es": "Viola de Gamba", "va": "Viola de Gamba"},
    "6D2": {"es": "Violonchelo", "va": "Violoncel"},
    "6E1": {"es": "Danza Aplicada al Arte Dramático", "va": "Dansa Aplicada a l'Art Dramàtic"},
    "6E6": {"es": "Espacio Escénico", "va": "Espai Escènic"},
    "6F3": {"es": "Literatura Dramática", "va": "Literatura Dramàtica"},
    "6G2": {"es": "Dulzaina", "va": "Dolçaina"},
    "6G6": {"es": "Cante Flamenco", "va": "Cant Flamenc"},
    "6H1": {"es": "Caracterización", "va": "Caracterització"},
    "6H2": {"es": "Acrobacia Aplicada al Arte Dramático", "va": "Acrobàcia Aplicada a l'Art Dramàtic"},
    "6H5": {"es": "Esgrima Aplicada al Arte Dramático", "va": "Esgrima Aplicada a l'Art Dramàtic"},
    "6H6": {"es": "Estética e Historia del Arte", "va": "Estètica i Història de l'Art"},
    "6H7": {"es": "Indumentaria", "va": "Indumentària"},
    "6J5": {"es": "Producción y Gestión Teatral", "va": "Producció i Gestió Teatral"},
    "7B6": {"es": "Joyería y Orfebrería", "va": "Joieria i Orfebreria"},
    "8A9": {"es": "Moldes y Reproducciones", "va": "Motles i Reproduccions"},
    "8B1": {"es": "Talla en Piedra y Madera", "va": "Talla en Pedra i Fusta"},
    "8B3": {"es": "Técnicas de Grabado y Estampación", "va": "Tècniques de Gravat i Estampació"},
    "8B9": {"es": "Técnicas Textiles", "va": "Tècniques Tèxtils"},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def semantic_lines(page: pdfplumber.page.Page) -> list[tuple[float, str]]:
    """Rebuild lines in PDF content order so overlapping columns stay separable."""
    grouped: dict[float, list[str]] = defaultdict(list)
    for char in page.chars:
        grouped[round(float(char["top"]), 1)].append(char["text"])
    return [(top, "".join(chars).strip()) for top, chars in sorted(grouped.items())]


def clean_pdf_text(value: str) -> str:
    return value.translate(str.maketrans({"Ŕ": "À", "Č": "È", "Ň": "Ò", "Ů": "Ú"}))


def clean_official_name(value: str) -> str:
    value = clean_pdf_text(value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s+,", ",", value)
    return value


def display_name(official_name: str) -> str:
    if "," in official_name:
        surnames, given_names = official_name.split(",", 1)
        value = f"{given_names.strip()} {surnames.strip()}"
    else:
        value = official_name
    value = value.title()
    value = re.sub(r"\bMª\b", "Mª", value, flags=re.IGNORECASE)
    return value


def normalize_name(value: str) -> str:
    value = value.upper().replace("Mª", " MARIA ").replace("M.ª", " MARIA ")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def token_key(value: str) -> str:
    return " ".join(sorted(normalize_name(value).split()))


def identity_key(value: str) -> str:
    return normalize_name(value)


def parse_specialty_map(js_path: Path | None) -> dict[str, dict[str, str]]:
    if not js_path:
        return {}
    source = js_path.read_text(encoding="utf-8")
    start = source.index("const SPECIALTY_NAME_MAP = {")
    end = source.index("\n};", start)
    block = source[start:end]
    pattern = re.compile(
        r'"([0-9A-Z]+)"\s*:\s*\{\s*es:\s*"([^"]+)",\s*va:\s*"([^"]+)"\s*\}'
    )
    return {code: {"es": es, "va": va} for code, es, va in pattern.findall(block)}


def parse_masters(pdf_path: Path) -> tuple[list[dict], dict[str, int], list[str]]:
    rows: list[dict] = []
    counters = Counter()
    errors: list[str] = []
    expected_global = 1

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            page_rows = 0
            for _, line in semantic_lines(page):
                match = re.match(r"^(\d+)(.+?)(?:AMB|SENSE)\s*SERVEIS(.*)$", line)
                if not match:
                    continue
                global_position = int(match.group(1))
                official = clean_official_name(match.group(2))
                tail = match.group(3)
                flags = [flag for flag in MASTER_FLAGS if flag in tail]
                if global_position != expected_global:
                    errors.append(
                        f"Maestros página {page_number}: esperado {expected_global}, "
                        f"encontrado {global_position} ({official})"
                    )
                    expected_global = global_position
                expected_global += 1
                page_rows += 1
                positions: list[tuple[str, int]] = []
                for flag in flags:
                    counters[flag] += 1
                    code = MASTER_SPECIALTIES[flag][0]
                    positions.append((code, counters[flag]))
                    if flag == "PRI":
                        positions.append((FPA_PRIMARY[0], counters[flag]))
                if not flags:
                    errors.append(
                        f"Maestros página {page_number}, posición {global_position}: sin habilitaciones"
                    )
                rows.append(
                    {
                        "official_name": official,
                        "display_name": display_name(official),
                        "global_position": global_position,
                        "positions": positions,
                        "page": page_number,
                    }
                )
            if page_rows == 0:
                errors.append(f"Maestros página {page_number}: no se extrajo ninguna fila")

    return rows, dict(counters), errors


def parse_secondary(pdf_path: Path) -> tuple[list[dict], dict[str, str], list[str]]:
    rows: list[dict] = []
    specialties: dict[str, str] = {}
    errors: list[str] = []
    last_position: dict[str, int] = {}
    page_specialties: dict[int, str] = {}

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            lines = semantic_lines(page)
            header_matches = []
            for top, line in lines:
                match = re.match(r"^\(([0-9A-Z]{3})\)\s*(.+)$", line)
                if match:
                    code = match.group(1)
                    name = clean_pdf_text(re.sub(r"\s+", " ", match.group(2)).strip())
                    specialties.setdefault(code, name)
                    if specialties[code] != name:
                        errors.append(
                            f"Secundaria: nombre incoherente para {code}: "
                            f"{specialties[code]!r} / {name!r}"
                        )
                    header_matches.append((top, code))
            if not header_matches:
                errors.append(f"Secundaria página {page_number}: sin encabezado de especialidad")
                continue
            if len({code for _, code in header_matches}) > 1:
                errors.append(
                    f"Secundaria página {page_number}: varios encabezados "
                    f"{sorted({code for _, code in header_matches})}"
                )
            current_code = header_matches[-1][1]
            page_specialties[page_number] = current_code
            page_rows = 0
            for _, line in lines:
                match = re.match(r"^(\d+)(.+?)(?:AMB|SENSE)\s*SERVEIS", line)
                if not match:
                    continue
                position = int(match.group(1))
                official = clean_official_name(match.group(2))
                expected = last_position.get(current_code, 0) + 1
                if position != expected:
                    errors.append(
                        f"Secundaria {current_code}, página {page_number}: esperado {expected}, "
                        f"encontrado {position} ({official})"
                    )
                last_position[current_code] = position
                page_rows += 1
                rows.append(
                    {
                        "official_name": official,
                        "display_name": display_name(official),
                        "specialty_code": current_code,
                        "position": position,
                        "page": page_number,
                    }
                )
            if page_rows == 0:
                errors.append(f"Secundaria página {page_number}: no se extrajo ninguna fila")

    return rows, specialties, errors


def merge_people(master_rows: Iterable[dict], secondary_rows: Iterable[dict]) -> tuple[list, list[str]]:
    master_profiles: dict[str, list[dict]] = defaultdict(list)
    secondary_by_name: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    errors: list[str] = []

    for row in master_rows:
        person = {
            "display_name": row["display_name"],
            "official_name": row["official_name"],
            "positions": {},
            "source": "maestros",
        }
        for code, position in row["positions"]:
            person["positions"][code] = position
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
            }
            for _ in range(profile_count)
        ]
        for code, rows in by_specialty.items():
            for index, row in enumerate(sorted(rows, key=lambda item: item["position"])):
                profiles[index]["positions"][code] = row["position"]
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
            [[code, position] for code, position in sorted(person["positions"].items())],
            person["source"],
        ]
        for person in people
    ]
    compact.sort(key=lambda person: normalize_name(person[0]))
    return compact, errors


def build_specialties(
    secondary: dict[str, str], existing_map: dict[str, dict[str, str]]
) -> tuple[list[dict], list[str]]:
    records: dict[str, dict] = {}
    for _, (code, es, va) in MASTER_SPECIALTIES.items():
        records[code] = {"code": code, "es": es, "va": va, "body": "maestros"}
    records[FPA_PRIMARY[0]] = {
        "code": FPA_PRIMARY[0],
        "es": FPA_PRIMARY[1],
        "va": FPA_PRIMARY[2],
        "body": "maestros",
    }

    unknown: list[str] = []
    for code, raw_name in secondary.items():
        mapped = existing_map.get(code) or EXTRA_SPECIALTY_NAMES.get(code)
        if mapped:
            es = mapped["es"]
            va = mapped["va"]
        else:
            va = raw_name.title()
            es = va
            unknown.append(f"{code}: {raw_name}")
        records[code] = {"code": code, "es": es, "va": va, "body": "otros"}

    return [records[code] for code in sorted(records)], unknown


def verify_examples(people: list) -> list[str]:
    errors: list[str] = []
    by_key: dict[str, list[dict[str, int]]] = defaultdict(list)
    for person in people:
        by_key[identity_key(person[1])].append(dict(person[2]))
    checks = {
        "MARQUET SOLDEVILA, ROSA MARIA": {"120": 1, "128": 1, "153": 1},
        "ONRUBIA BERGES, ROSA MARIA": {"128": 25, "123": 1, "127": 13, "126": 4},
        "PEREZ VIDAL, ANGEL MIGUEL": {"3A1": 5},
    }
    for name, expected in checks.items():
        profiles = by_key.get(identity_key(name), [])
        if not profiles:
            errors.append(f"No se encontró el ejemplo de control: {name}")
            continue
        if not any(all(profile.get(code) == position for code, position in expected.items()) for profile in profiles):
            errors.append(f"El ejemplo {name} no coincide con {expected}; encontrado {profiles}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--masters", type=Path, required=True)
    parser.add_argument("--secondary", type=Path, required=True)
    parser.add_argument("--specialty-js", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    master_rows, master_counts, master_errors = parse_masters(args.masters)
    secondary_rows, secondary_specialties, secondary_errors = parse_secondary(args.secondary)
    people, merge_errors = merge_people(master_rows, secondary_rows)
    specialties, unknown_specialties = build_specialties(
        secondary_specialties, parse_specialty_map(args.specialty_js)
    )
    example_errors = verify_examples(people)
    errors = master_errors + secondary_errors + merge_errors + example_errors

    duplicate_same_specialty = []
    seen_secondary: dict[tuple[str, str], tuple[int, int]] = {}
    for row in secondary_rows:
        key = (identity_key(row["official_name"]), row["specialty_code"])
        if key in seen_secondary:
            duplicate_same_specialty.append(
                {
                    "name": row["official_name"],
                    "specialty": row["specialty_code"],
                    "first": seen_secondary[key],
                    "second": (row["position"], row["page"]),
                }
            )
        else:
            seen_secondary[key] = (row["position"], row["page"])

    dataset = {
        "schema_version": 1,
        "dataset": "posiciones_bolsa",
        "academic_year": "2026/2027",
        "status": "provisional",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "sources": [
            {
                "body": "maestros",
                "filename": args.masters.name,
                "sha256": sha256(args.masters),
                "pages": 395,
            },
            {
                "body": "otros",
                "filename": args.secondary.name,
                "sha256": sha256(args.secondary),
                "pages": 1513,
            },
        ],
        "specialties": specialties,
        "person_fields": ["display_name", "official_name", "positions", "source"],
        "position_fields": ["specialty_code", "position"],
        "people": people,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(dataset, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    report = {
        "master_rows": len(master_rows),
        "master_last_global_position": master_rows[-1]["global_position"] if master_rows else 0,
        "master_specialty_counts": master_counts,
        "secondary_rows": len(secondary_rows),
        "secondary_specialties": len(secondary_specialties),
        "secondary_max_positions": dict(
            sorted(Counter({row["specialty_code"]: row["position"] for row in secondary_rows}).items())
        ),
        "unique_people": len(people),
        "unknown_specialties": unknown_specialties,
        "duplicate_same_specialty": duplicate_same_specialty,
        "errors": errors,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "master_rows": report["master_rows"],
                "secondary_rows": report["secondary_rows"],
                "secondary_specialties": report["secondary_specialties"],
                "unique_people": report["unique_people"],
                "unknown_specialties": len(unknown_specialties),
                "duplicate_same_specialty": len(duplicate_same_specialty),
                "errors": len(errors),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
