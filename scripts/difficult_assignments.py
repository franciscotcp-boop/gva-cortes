"""Independent difficult-coverage awards; lottery order is never a pool rank."""
import argparse
from collections import defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
import re

from position_context import normalized_name


def parse_page(text, page_number):
    headers = list(re.finditer(r"(\d{6})\s+(\d{8})PUESTO\s*:", text))
    specialties = list(re.finditer(r"^([0-9][0-9A-Z]{2})\s*(?=[A-Z])(.+)$", text, re.M))
    awards = []
    for line in re.finditer(r"^.*-->.*$", text, re.M):
        prior_headers = [h for h in headers if h.start() < line.start()]
        prior_specialties = [s for s in specialties if s.start() < line.start()]
        if not prior_headers or not prior_specialties:
            raise ValueError(f"Winner without preceding header on page {page_number}")
        slot, center = prior_headers[-1].groups()
        match = re.search(r"-->\s*(.+?)(\d+)\s+(.+?)(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}:\d{2}(.+)", line.group())
        if not match:
            raise ValueError(f"Unreadable arrow on page {page_number}")
        surnames, _, given, _, tail = match.groups()
        assigned = re.search(r"(?<!\d)(\d{6})(?!\d)", tail)
        if not assigned or assigned.group(1) != slot:
            raise ValueError(f"Assigned slot differs from header on page {page_number}")
        awards.append({"page": page_number, "slot_id": slot, "center_code": center,
                       "specialty_code": prior_specialties[-1].group(1),
                       "candidate_name": surnames.strip() + ", " + given.strip()})
    return awards


def make_ledger(winners, offers, positions, publication_date, source_sha, source_name, provisional=False):
    if provisional:
        raise ValueError("Provisional assignments must not change personal profiles")
    day = date.fromisoformat(publication_date)
    year = day.year if day.month >= 7 else day.year - 1
    by_name = defaultdict(list)
    for person in positions["people"]:
        by_name[normalized_name(person[1])].append(person)
    offer_map = {str(row["slot_id"]): row for row in offers}
    awards, seen = [], set()
    for winner in winners:
        slot = str(winner["slot_id"])
        if slot in seen:
            raise ValueError(f"Duplicate winner for slot {slot}")
        seen.add(slot)
        offer = offer_map[slot]
        if (str(offer["center_code"]), str(offer["specialty_code"])) != (winner["center_code"], winner["specialty_code"]):
            raise ValueError(f"Offer/header mismatch for {slot}")
        name = winner["candidate_name"]
        matches = by_name[normalized_name(name)]
        surnames, given = name.split(",", 1)
        awards.append({
            "id": f"{publication_date}:{slot}", "official_name": name,
            "display_name": (given.strip() + " " + surnames).title(),
            "gender": matches[0][5] if len(matches) == 1 else "u",
            "identity_status": "ambiguous" if len(matches) > 1 else "unique" if matches else "not_in_pool",
            "body": offer["body"], "specialty_code": winner["specialty_code"],
            "slot_id": slot, "date": publication_date, "provisional": provisional,
            "source_page": winner["page"],
            "source_sha256": source_sha,
            "detail": ["D", publication_date, offer["placement_type"], offer["hours"] if offer["hours"] is not None else "C",
                       winner["center_code"], offer["english_requirement"], offer["itinerant"],
                       offer["center_name_pdf"], offer["municipality"], offer["observations"]],
        })
    return {"schema_version": 1, "status": "definitive", "academic_year": f"{year}/{year + 1}",
            "source": {"file": source_name, "sha256": source_sha, "date": publication_date},
            "awards": awards}


def attach_ledger(positions, ledger):
    """Only append an optional extension. No ranks, statuses, cuts or notification stamps change."""
    if ledger.get("status") != "definitive" or any(a.get("provisional") is not False for a in ledger.get("awards", [])):
        raise ValueError("Only verified definitive awards may be attached")
    if ledger.get("academic_year", "").replace("-", "/") == positions.get("academic_year", "").replace("-", "/"):
        positions["difficult_assignments"] = ledger
    else:
        positions.pop("difficult_assignments", None)
    return positions


def preserve_ledger(positions, data_directory):
    path = Path(data_directory) / "difficult_assignments.json"
    if path.exists():
        attach_ledger(positions, json.loads(path.read_text(encoding="utf-8")))


def merge_ledger(previous, incoming):
    """Replace a corrected day's results, retaining definitive assignments on other days."""
    if not previous or previous.get("academic_year") != incoming.get("academic_year"):
        return incoming
    new_date = incoming["source"]["date"]
    retained = [a for a in previous["awards"] if a["date"] != new_date]
    sources = {s["date"]: s for s in previous.get("sources", [previous["source"]])}
    sources[new_date] = incoming["source"]
    return {**incoming, "sources": list(sources.values()), "awards": retained + incoming["awards"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--offers", type=Path, required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--confirmed-final", action="store_true", help="Required after checking the definitive source and its layout")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    if not args.confirmed_final:
        raise ValueError("Review the definitive document before using --confirmed-final")
    from pypdf import PdfReader
    reader = PdfReader(args.pdf)
    first = reader.pages[0].extract_text()
    if "PROVISIONALMENTE" in first.upper() or "DEFINITIV" not in first.upper():
        raise ValueError("Not a recognized definitive result document; nothing will be imported")
    winners = []
    for number, page in enumerate(reader.pages, 1):
        winners.extend(parse_page(page.extract_text(), number))
    if not winners:
        raise ValueError("No arrow-marked winners")
    offered = json.loads(args.offers.read_text(encoding="utf-8"))
    offers = [dict(zip(offered["item_fields"], row)) for row in offered["items"]]
    positions_path = args.data_dir / "posiciones_bolsa.json"
    positions = json.loads(positions_path.read_text(encoding="utf-8"))
    ledger = make_ledger(winners, offers, positions, args.date,
                         hashlib.sha256(args.pdf.read_bytes()).hexdigest(), args.pdf.name)
    if ledger["academic_year"] != positions["academic_year"].replace("-", "/"):
        raise ValueError("The definitive document belongs to another academic year")
    genders_path = args.data_dir / "gender_first_name_map.json"
    genders = json.loads(genders_path.read_text(encoding="utf-8")) if genders_path.exists() else {}
    for award in ledger["awards"]:
        if award["gender"] == "u":
            for token in normalized_name(award["official_name"].split(",", 1)[1]).split():
                if genders.get(token) in {"m", "f"}:
                    award["gender"] = genders[token]
                    break
    from update_source_data import save_json_atomic
    ledger_path = args.data_dir / "difficult_assignments.json"
    previous = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else None
    ledger = merge_ledger(previous, ledger)
    attach_ledger(positions, ledger)
    save_json_atomic(ledger_path, ledger)
    save_json_atomic(positions_path, attach_ledger(positions, ledger))
    print(json.dumps({"awards": len(winners), "unresolved": sum(a["identity_status"] == "ambiguous" for a in ledger["awards"])}))


if __name__ == "__main__":
    main()
