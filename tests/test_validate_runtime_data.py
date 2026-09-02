from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_runtime_data import validate_repository, validate_rows


class RuntimeDataValidationTests(unittest.TestCase):
    def test_current_runtime_data_is_publishable(self) -> None:
        counts = validate_repository(ROOT)
        self.assertGreater(counts["centros"], 0)
        self.assertGreater(counts["personas"], 0)
        self.assertGreater(counts["puestos"], 0)

    def test_rejects_a_row_with_the_wrong_width(self) -> None:
        with self.assertRaisesRegex(ValueError, "fila 1"):
            validate_rows("ejemplo", [[1, 2], [3]], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
