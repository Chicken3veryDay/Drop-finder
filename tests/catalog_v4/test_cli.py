from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.catalog_v4.cli import strict_flower_products

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

    def test_legacy_title_recovers_first_valid_weight_evidence(self) -> None:
        admitted, excluded = strict_flower_products([
            {
                "primary_type": "cannabis_flower",
                "grams": 28.3495,
                "source_weight_label": "28.3495g",
                "source_title": "THCa Flower - Sherb Tang - 28 Grams",
                "variant": "Default Title",
            },
            {
                "primary_type": "cannabis_flower",
                "grams": 28.0,
                "source_weight_label": "28.3495g",
                "source_title": "Bacio Gelato THCA Bulk Flower 1 Pound",
                "variant": "1 Pound",
            },
            {
                "primary_type": "cannabis_flower",
                "grams": 7.0,
                "source_title": "Apples and Bananas THCA Bulk Flower 1/4 Pound",
                "variant": "1/4 Pound",
            },
        ])
        self.assertEqual(excluded, 0)
        self.assertEqual(admitted[0]["grams"], 28.0)
        self.assertEqual(admitted[0]["source_weight_label"], "28 Grams")
        self.assertEqual(admitted[1]["grams"], 448.0)
        self.assertEqual(admitted[1]["source_weight_label"], "1 Pound")
        self.assertEqual(admitted[2]["grams"], 112.0)
        self.assertEqual(admitted[2]["source_weight_label"], "1/4 Pound")

    def test_legacy_title_does_not_authenticate_tier_potency_or_arbitrary_conflicts(self) -> None:
        admitted, excluded = strict_flower_products([
            {
                "primary_type": "cannabis_flower",
                "grams": 28.3495,
                "source_title": "ADL | THCa Flower | Tier 1",
                "variant": "",
            },
            {
                "primary_type": "cannabis_flower",
                "grams": 28.3495,
                "source_title": "Blue Dream THCA 24.1%",
                "variant": "",
            },
            {
                "primary_type": "cannabis_flower",
                "grams": 28.0,
                "source_title": "Blue Dream Quarter oz",
                "variant": "Quarter oz",
            },
        ])
        self.assertEqual(excluded, 0)
        self.assertNotIn("source_weight_label", admitted[0])
        self.assertNotIn("source_weight_label", admitted[1])
        self.assertNotIn("source_weight_label", admitted[2])


if __name__ == "__main__":
    unittest.main()
