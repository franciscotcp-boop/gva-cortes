from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_public_backups import validate_response, verify_url


def response(body: bytes, status: int = 200, cors: str = "*") -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = body
    result.headers["Content-Type"] = "application/json; charset=utf-8"
    result.headers["Access-Control-Allow-Origin"] = cors
    return result


class PublicBackupVerificationTests(unittest.TestCase):
    def setUp(self):
        self.data = {"schema_version": 1, "people": [["Example", 3]]}
        self.good = response(json.dumps(self.data).encode())

    def test_validates_complete_json_and_cors(self):
        self.assertTrue(validate_response(self.good, self.data)["matches"])

    def test_rejects_github_rate_limit_cached_as_http_200(self):
        with self.assertRaisesRegex(ValueError, "429 de GitHub"):
            validate_response(response(b"429: Too Many Requests\n"), self.data)

    def test_rejects_html_cached_as_json(self):
        with self.assertRaisesRegex(ValueError, "JSON valido"):
            validate_response(response(b"<html>Error</html>"), self.data)

    def test_rejects_outdated_json(self):
        with self.assertRaisesRegex(ValueError, "no coincide"):
            validate_response(self.good, {**self.data, "people": [["Example", 2]]})

    def test_rejects_http_error(self):
        with self.assertRaises(requests.HTTPError):
            validate_response(response(b"{}", status=404), self.data)

    def test_rejects_missing_cors(self):
        with self.assertRaisesRegex(ValueError, "CORS"):
            validate_response(response(self.good.content, cors=""), self.data)

    @patch("verify_public_backups.time.sleep")
    @patch("verify_public_backups.requests.get")
    def test_bounded_retry_recovers_without_changing_the_url(self, get, sleep):
        get.side_effect = [response(b"429: Too Many Requests"), self.good]
        url = "https://cdn.jsdelivr.net/gh/owner/repo@main/data/file.json"
        result = verify_url(url, self.data, attempts=2, timeout=90, delay=60)
        self.assertTrue(result["valid"])
        self.assertNotIn("error", result)
        self.assertEqual(get.call_count, 2)
        self.assertTrue(all(call.args[0] == url for call in get.call_args_list))
        sleep.assert_called_once_with(60)

    @patch("verify_public_backups.time.sleep")
    @patch("verify_public_backups.requests.get", side_effect=requests.Timeout("timeout"))
    def test_stops_after_the_requested_attempts(self, get, sleep):
        result = verify_url("https://example.test/data.json", self.data, attempts=2, timeout=90, delay=60)
        self.assertFalse(result["valid"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(get.call_count, 2)
        sleep.assert_called_once_with(60)


if __name__ == "__main__":
    unittest.main()
