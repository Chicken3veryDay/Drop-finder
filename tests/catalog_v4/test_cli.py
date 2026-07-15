from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "legacy_rows.json"


class CliTests(unittest.TestCase):
    def test_cli_build_and_verify(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = [
                sys.executable, "-m", "scripts.catalog_v4.cli",
                "--input", str(FIXTURE),
                "--output", str(root),
                "--detail-shards", "4",
            ]
            completed = subprocess.run(command, cwd=Path(__file__).parents[2], text=True, capture_output=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn('"verified": true', completed.stdout)
            verified = subprocess.run(
                [sys.executable, "-m", "scripts.catalog_v4.cli", "--input", str(FIXTURE), "--output", str(root), "--verify-only"],
                cwd=Path(__file__).parents[2], text=True, capture_output=True, check=False,
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertIn('"products": 3', verified.stdout)


if __name__ == "__main__":
    unittest.main()
