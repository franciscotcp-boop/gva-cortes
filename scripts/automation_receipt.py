from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import zipfile

from automation_schedule import explicit_modes

RECEIPT_FILE = "automation-check.json"


def build_receipt(modes: str, environment: dict[str, str], program_reviews: list[dict] | None = None) -> dict:
    selected = explicit_modes(modes)
    if not selected:
        raise ValueError("Cannot record a check without a selected source")
    return {
        "schema_version": 1,
        "run_id": int(environment["GITHUB_RUN_ID"]),
        "run_attempt": int(environment["GITHUB_RUN_ATTEMPT"]),
        "head_sha": environment["GITHUB_SHA"],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "modes": list(selected),
        "source_outcomes": {mode: environment.get(f"RESULT_{mode.upper()}", "skipped") for mode in selected},
        "validation_outcome": environment.get("RESULT_VALIDATION", "skipped"),
        "publication_outcome": environment.get("RESULT_PUBLICATION", "skipped"),
        "program_reviews": program_reviews or [],
    }


def load_program_reviews(environment: dict[str, str], path: Path) -> list[dict]:
    if not path.exists():
        return []
    report = json.loads(path.read_text(encoding="utf8"))
    if (
        report.get("schema_version") != 1
        or str(report.get("run_id")) != environment.get("GITHUB_RUN_ID")
        or str(report.get("run_attempt")) != environment.get("GITHUB_RUN_ATTEMPT")
    ):
        return []
    cases = report.get("cases")
    if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
        raise ValueError("Invalid program review report")
    return cases


def read_archive(content: bytes) -> dict:
    if len(content) > 1024 * 1024:
        raise ValueError("Receipt archive exceeds the size limit")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        info = archive.getinfo(RECEIPT_FILE)
        if info.file_size > 128 * 1024:
            raise ValueError("Receipt exceeds the size limit")
        value = json.loads(archive.read(info))
    if not isinstance(value, dict):
        raise ValueError("Invalid receipt object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modes", default="")
    parser.add_argument("--output", type=Path, default=Path(RECEIPT_FILE))
    parser.add_argument("--read-archive", action="store_true")
    args = parser.parse_args()
    if args.read_archive:
        print(json.dumps(read_archive(sys.stdin.buffer.read())))
    else:
        environment = dict(os.environ)
        reviews = load_program_reviews(environment, Path("program-review-pending.json"))
        args.output.write_text(json.dumps(build_receipt(args.modes, environment, reviews)), encoding="utf8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
