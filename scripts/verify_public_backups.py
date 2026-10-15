"""Read-only verification of the exact public URLs used by shipped clients."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
FILES = ("adjudicaciones.json", "posiciones_bolsa.json")
SOURCES = {
    "primary": "https://raw.githubusercontent.com/franciscotcp-boop/gva-cortes/refs/heads/main/data/",
    "jsdelivr": "https://cdn.jsdelivr.net/gh/franciscotcp-boop/gva-cortes@main/data/",
}


def validate_response(response: requests.Response, expected: dict) -> dict:
    response.raise_for_status()
    # A CDN can cache an upstream error page with HTTP 200 and a JSON MIME type.
    if response.content.lstrip().startswith(b"429: Too Many Requests"):
        raise ValueError("El CDN sirve un aviso 429 de GitHub en lugar del JSON")
    try:
        actual = response.json()
    except ValueError as exc:
        raise ValueError("La respuesta HTTP no contiene un JSON valido") from exc
    if not isinstance(actual, dict) or actual != expected:
        raise ValueError("El JSON no coincide con la version local validada")
    if response.headers.get("Access-Control-Allow-Origin") != "*":
        raise ValueError("La respuesta no permite el acceso desde la web (CORS)")
    return {
        "bytes": len(response.content),
        "sha256": hashlib.sha256(response.content).hexdigest(),
        "matches": True,
    }


def verify_url(url: str, expected: dict, *, attempts: int, timeout: int, delay: int) -> dict:
    result = {"url": url, "valid": False}
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        result["attempts"] = attempt
        result.pop("status", None)
        try:
            with requests.get(
                url, timeout=(10, timeout),
                headers={"User-Agent": "AdjudicApp-backup-check (https://github.com/franciscotcp-boop/gva-cortes)"},
            ) as response:
                result["status"] = response.status_code
                result.update(validate_response(response, expected))
            result["valid"] = True
            result.pop("error", None)
            return result
        except (requests.RequestException, ValueError) as exc:
            result["error"] = str(exc)
        finally:
            result["seconds"] = round(time.monotonic() - started, 2)
        if attempt < attempts:
            time.sleep(delay)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--timeout", type=int, choices=range(10, 121), default=90)
    parser.add_argument("--retry-delay", type=int, choices=range(30, 301), default=60)
    args = parser.parse_args()
    expected = {name: json.loads((ROOT / "data" / name).read_text(encoding="utf-8")) for name in FILES}
    results = []
    for source, base in SOURCES.items():
        for name in FILES:
            result = verify_url(
                base + name, expected[name], attempts=args.attempts,
                timeout=args.timeout, delay=args.retry_delay,
            )
            result.update(source=source, file=name)
            results.append(result)
            print(json.dumps(result), flush=True)
    return 0 if all(result["valid"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
