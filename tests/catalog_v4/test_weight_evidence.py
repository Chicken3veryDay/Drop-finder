from __future__ import annotations

import json
import unittest

from scripts.catalog_v4 import build_catalog


def read_json_bytes(data: bytes) -> dict:
    return json.loads(data.decode("utf-8"))


def row(**overrides: object) -> dict:
    base = {
        "source_id": "legacy",
        "vendor": "Legacy Vendor",
        "source_product_id": "tier-product",
        "source_variant_id": "tier-variant",
        "name": "ADL | THCa Flower | Tier 1",
        "variant": "Tier 1",
        "url": "https://legacy.example/products/adl-tier-1",
        "availability": "in_stock",
        "price": 34.99,
    }
    base.update(overrides)
    return base


class WeightEvidenceTests(unittest.TestCase):
    def test_unitless_legacy_grams_do_not_enter_catalog_or_price_per_gram(self) -> None:
        result = build_catalog(
            [row(grams=28.3495, source_weight_label="28.3495")],
            generated_at="2026-07-16T00:00:00Z",
            detail_shards=1,
        )
        index = read_json_bytes(result.files["catalog-v4/index.json"])
        self.assertEqual(index["products"], [])
        self.assertEqual(result.variant_count, 0)
        self.assertEqual(result.rejections["reason_counts"]["invalid_or_missing_weight"], 1)

    def test_structured_numeric_grams_without_competing_label_remain_publishable(self) -> None:
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
        result = build_catalog(
            [row(grams=28.3495, source_weight_label="1 oz", variant="1 oz")],
            generated_at="2026-07-16T00:00:00Z",
            detail_shards=1,
        )
        index = read_json_bytes(result.files["catalog-v4/index.json"])
        variant = index["products"][0]["variants"][0]
        self.assertEqual(variant["grams"], 28.0)
        self.assertEqual(variant["source_weight_label"], "1 oz")
        self.assertAlmostEqual(variant["price_per_gram"], 1.2496, places=4)

    def test_conflicting_numeric_and_text_weight_is_rejected(self) -> None:
        result = build_catalog(
            [row(grams=28.3495, source_weight_label="Quarter oz", variant="Quarter oz")],
            generated_at="2026-07-16T00:00:00Z",
            detail_shards=1,
        )
        self.assertEqual(result.product_count, 0)
        self.assertEqual(result.rejections["reason_counts"]["invalid_or_missing_weight"], 1)


if __name__ == "__main__":
    unittest.main()
