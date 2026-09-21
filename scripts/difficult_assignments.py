"""Independent difficult-coverage awards; lottery order is never a pool rank."""
import argparse
from collections import defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from position_context import MASTER_PROFILE_ALIASES, normalized_name


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
        profile_code = winner["specialty_code"]
        if offer["body"] == "maestros" and profile_code in {"151", "152"} and len(matches) == 1:
            registered = {str(entry[0]) for entry in matches[0][2]}
            alias = MASTER_PROFILE_ALIASES[profile_code]
            if profile_code not in registered and alias in registered:
                profile_code = alias
        awards.append({
            "id": f"{publication_date}:{slot}", "official_name": name,
            "display_name": (given.strip() + " " + surnames).title(),
            "gender": matches[0][5] if len(matches) == 1 else "u",
            "identity_status": "ambiguous" if len(matches) > 1 else "unique" if matches else "not_in_pool",
            "body": offer["body"], "specialty_code": profile_code,
            "offered_specialty_code": winner["specialty_code"],
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


def _pool_identity(person):
    return sorted([[str(entry[0]), entry[1]] for entry in person[2]], key=lambda pair: pair[0])


def _people_by_name(positions):
    by_name = defaultdict(list)
    for person in positions.get("people", []):
        by_name[normalized_name(person[1])].append(person)
    return by_name


def _award_people(positions, award, by_name=None):
    if by_name is None:
        by_name = _people_by_name(positions)
    matches = by_name.get(normalized_name(award["official_name"]), [])
    if isinstance(award.get("pool_identity"), list):
        identity = sorted(award["pool_identity"], key=lambda pair: pair[0])
        matches = [person for person in matches if _pool_identity(person) == identity]
    return matches


def _apply_confirmed_profile_resolutions(positions, ledger):
    """Apply scoped owner decisions, preserving pool ranks and assignment history."""
    by_name = _people_by_name(positions)
    for award in ledger.get("awards", []):
        resolution = award.get("profile_resolution")
        if not resolution:
            continue
        if resolution.get("confirmed_by") != "project_owner":
            raise ValueError("Profile resolution requires explicit owner confirmation")
        if resolution.get("separate_homonym"):
            if award.get("pool_identity") != []:
                raise ValueError("A separate unranked homonym must have an empty pool identity")
            if not _award_people(positions, award, by_name):
                person = [award["display_name"], award["official_name"], [], award["body"], None, award["gender"]]
                positions.setdefault("people", []).append(person)
                by_name[normalized_name(award["official_name"])].append(person)
        matches = _award_people(positions, award, by_name)
        if len(matches) != 1:
            raise ValueError("Confirmed profile resolution no longer identifies one person")
        # Only the exact, confirmed ended assignment is cleared. Future awards survive.
        for ended in resolution.get("superseded_ordinary_assignments", []):
            for entry in matches[0][2]:
                if (len(entry) > 9 and entry[8] == "A" and str(entry[0]) == ended["specialty_code"]
                        and entry[9] == ended["detail"]):
                    entry[8], entry[9] = "N", None


def attach_ledger(positions, ledger):
    """Attach the extension and explicit profile resolutions; never change ranks or cuts."""
    if ledger.get("status") != "definitive" or any(a.get("provisional") is not False for a in ledger.get("awards", [])):
        raise ValueError("Only verified released awards may be attached")
    if ledger.get("academic_year", "").replace("-", "/") == positions.get("academic_year", "").replace("-", "/"):
        _apply_confirmed_profile_resolutions(positions, ledger)
        positions["difficult_assignments"] = ledger
        labels = ledger.get("specialties", [])
        if labels:
            catalog = positions.setdefault("specialties", [])
            known = {str(item["code"]) for item in catalog}
            awarded = {str(award["specialty_code"]) for award in ledger.get("awards", [])}
            for item in labels:
                code = str(item.get("code", ""))
                if code in awarded and code not in known and item.get("es") and item.get("va"):
                    catalog.append(dict(item))
                    known.add(code)
    else:
        positions.pop("difficult_assignments", None)
    return positions


def make_directory_review_ledger(reviews, offers, positions, assignment_date, source_sha, source_name, specialty_labels=()):
    """Publish reviewed directory cross-references, never the provisional arrows.

    The legacy client value 'definitive' means released rather than a claim that
    the candidate PDF is a definitive resolution. Keep the actual evidence basis.
    """
    winners = []
    evidence_by_slot = {}
    identities = set()
    people = defaultdict(list)
    for person in positions.get("people", []):
        people[normalized_name(person[1])].append(person)
    for review in reviews:
        winner = review["winner"]
        evidence = review["evidence"]
        if review.get("decision") != "verified_center_match":
            raise ValueError("Unreviewed directory match")
        identity = normalized_name(winner["candidate_name"])
        matches = people[identity]
        if len(matches) > 1:
            raise ValueError("Directory evidence alone cannot resolve pool homonyms")
        if any(len(entry) > 8 and entry[8] == "A" for person in matches for entry in person[2]):
            raise ValueError("Official PDF assignments take priority over directory inferences")
        if identity in identities:
            raise ValueError("A directory center alone cannot resolve multiple posts for one person")
        identities.add(identity)
        if normalized_name(evidence.get("official_name")) != identity:
            raise ValueError("Directory identity differs from candidate")
        if str(evidence.get("center_code")) != str(winner["center_code"]):
            raise ValueError("Directory center differs from offered center")
        if evidence.get("exact_name_results") != 1 or not evidence.get("checked_at"):
            raise ValueError("Ambiguous or undated directory evidence")
        for field in ("search_url", "department_url"):
            url = urlparse(str(evidence.get(field, "")))
            if url.scheme != "https" or url.hostname != "sede.gva.es":
                raise ValueError("Evidence must refer to the official directory")
        if review.get("competing_assignment") or review.get("multiple_possible_posts") or review.get("later_post_evidence"):
            raise ValueError("Conflicting assignment requires separate manual confirmation")
        winners.append(winner)
        evidence_by_slot[str(winner["slot_id"])] = evidence
    ledger = make_ledger(winners, offers, positions, assignment_date, source_sha, source_name)
    ledger["verification_basis"] = "reviewed_directory_cross_reference"
    ledger["source"]["document_type"] = "provisional_candidate_list"
    ledger["source"]["is_definitive_resolution"] = False
    ledger["source"]["directory_url"] = "https://sede.gva.es/va/cercador-persones"
    awarded_codes = {award["specialty_code"] for award in ledger["awards"]}
    ledger["specialties"] = [dict(item) for item in specialty_labels if str(item["code"]) in awarded_codes]
    for award in ledger["awards"]:
        award["verification"] = {**evidence_by_slot[award["slot_id"]],
                                 "assignment_inference": "ordered_candidate_and_current_workplace_match",
                                 "is_definitive_resolution": False}
    return ledger


def preserve_ledger(positions, data_directory):
    path = Path(data_directory) / "difficult_assignments.json"
    if path.exists():
        ledger = json.loads(path.read_text(encoding="utf-8"))
        if ledger.get("academic_year", "").replace("-", "/") != positions.get("academic_year", "").replace("-", "/"):
            positions.pop("difficult_assignments", None)
            return
        _apply_confirmed_profile_resolutions(positions, ledger)
        # Official assignments supersede emergency directory evidence, regardless of PDF date.
        by_name = _people_by_name(positions)
        ledger["awards"] = [award for award in ledger.get("awards", [])
                            if not (award.get("verification", {}).get("assignment_inference") and
                                    any(len(entry) > 8 and entry[8] == "A"
                                        for person in _award_people(positions, award, by_name) for entry in person[2]))]
        attach_ledger(positions, ledger)


def merge_ledger(previous, incoming):
    """Replace a corrected day's results, retaining definitive assignments on other days."""
    if not previous or previous.get("academic_year") != incoming.get("academic_year"):
        return incoming
    new_date = incoming["source"]["date"]
    if incoming.get("verification_basis") == "reviewed_directory_cross_reference":
        incoming_names = {normalized_name(award["official_name"]) for award in incoming["awards"]}
        official = [award for award in previous["awards"]
                    if not award.get("verification", {}).get("assignment_inference")]
        if any(award["date"] == new_date or normalized_name(award["official_name"]) in incoming_names
               for award in official):
            raise ValueError("Official PDF difficult-coverage awards take priority over directory inferences")
    retained = [a for a in previous["awards"] if a["date"] != new_date]
    sources = {s["date"]: s for s in previous.get("sources", [previous["source"]])}
    sources[new_date] = incoming["source"]
    labels = {str(item["code"]): item for item in previous.get("specialties", [])}
    labels.update({str(item["code"]): item for item in incoming.get("specialties", [])})
    return {**incoming, "sources": list(sources.values()), "awards": retained + incoming["awards"],
            "specialties": list(labels.values())}


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
