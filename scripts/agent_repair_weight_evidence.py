from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one patch target in {path}, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "scripts/catalog_v4/normalization.py",
    '''    # Direct numeric values are not self-authenticating package-weight
    # evidence. Require a source label with an explicit unit or recognized
    # weight term, then require that evidence to agree with the normalized
    # numeric value. This prevents inherited Tier/count/potency numbers and
    # unitless legacy grams from producing shopper-visible price-per-gram data.
    if direct is not None:
        snapped = _snap_commercial_weight(direct)
        if label_weight is None or label_weight != snapped:
            return None, source_label
        return label_weight, supplied_label
''',
    '''    # A dedicated numeric grams field is an established structured-adapter
    # contract and remains valid when no competing textual label is supplied.
    # When a label is supplied, however, it must contain explicit weight
    # evidence and agree with the numeric field. This rejects inherited
    # Tier/count/potency numbers and unitless legacy labels without discarding
    # trusted structured grams or the CLI's conservative title recovery.
    if direct is not None:
        snapped = _snap_commercial_weight(direct)
        if not supplied_label:
            return snapped, source_label
        if label_weight is None or label_weight != snapped:
            return None, source_label
        return label_weight, supplied_label
''',
)

replace_once(
    "tests/catalog_v4/test_normalization.py",
    '''    def test_weight_normalization_rejects_unitless_numeric_evidence(self) -> None:
        for value, label in ((28.3495, None), ("28.3495", None), (28.3495, "28.3495"), (7, "Tier 7")):
            with self.subTest(value=value, label=label):
                grams, _ = normalize_weight(value, label)
                self.assertIsNone(grams)
''',
    '''    def test_weight_normalization_preserves_structured_numeric_grams_without_competing_label(self) -> None:
        for value in (28.3495, "28.3495"):
            with self.subTest(value=value):
                grams, source_label = normalize_weight(value)
                self.assertEqual(grams, Decimal("28"))
                self.assertEqual(source_label, "28.3495")

    def test_weight_normalization_rejects_unitless_or_non_weight_supplied_labels(self) -> None:
        for value, label in ((28.3495, "28.3495"), (7, "Tier 7")):
            with self.subTest(value=value, label=label):
                grams, _ = normalize_weight(value, label)
                self.assertIsNone(grams)
''',
)

replace_once(
    "tests/catalog_v4/test_weight_evidence.py",
    '''    def test_matching_explicit_weight_evidence_remains_publishable(self) -> None:
''',
    '''    def test_structured_numeric_grams_without_competing_label_remain_publishable(self) -> None:
        result = build_catalog(
            [row(
                source_product_id="structured-product",
                source_variant_id="structured-variant",
                name="Blue Dream THCA Flower",
                variant="",
                grams=3.5,
            )],
            generated_at="2026-07-16T00:00:00Z",
            detail_shards=1,
        )
        index = read_json_bytes(result.files["catalog-v4/index.json"])
        variant = index["products"][0]["variants"][0]
        self.assertEqual(variant["grams"], 3.5)
        self.assertEqual(variant["source_weight_label"], "3.5")
        self.assertAlmostEqual(variant["price_per_gram"], 9.9971, places=4)

    def test_matching_explicit_weight_evidence_remains_publishable(self) -> None:
''',
)

replace_once(
    "tests/catalog_v4/test_cli.py",
    '''import subprocess
import sys
import tempfile
import unittest
''',
    '''import subprocess
import sys
import tempfile
import unittest

from scripts.catalog_v4 import build_catalog
from scripts.catalog_v4.cli import strict_flower_products
''',
)

replace_once(
    "tests/catalog_v4/test_cli.py",
    '''class CliTests(unittest.TestCase):
    def test_cli_build_and_verify(self) -> None:
''',
    '''class CliTests(unittest.TestCase):
    def test_source_title_weight_recovery_remains_publishable(self) -> None:
        prepared, excluded = strict_flower_products([{
            "source_id": "structured",
            "vendor": "Structured Vendor",
            "source_product_id": "blue-dream",
            "source_variant_id": "blue-dream-3-5",
            "name": "Blue Dream THCA Flower 3.5g",
            "url": "https://structured.example/products/blue-dream",
            "availability": "in_stock",
            "price": 35,
        }])
        self.assertEqual(excluded, 0)
        self.assertEqual(prepared[0]["grams"], 3.5)

        result = build_catalog(
            prepared,
            generated_at="2026-07-16T00:00:00Z",
            detail_shards=1,
        )
        self.assertEqual(result.product_count, 1)
        self.assertEqual(result.variant_count, 1)

    def test_cli_build_and_verify(self) -> None:
''',
)
