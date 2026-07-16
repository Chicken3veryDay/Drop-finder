from __future__ import annotations

from pathlib import Path


def replace_exact(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one exact replacement, found {count}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def main() -> int:
    replace_exact(
        "scripts/catalog_v4/builder.py",
        '''            grams, source_weight_label = normalize_weight(
                raw.get("grams") if raw.get("grams") not in (None, "") else raw.get("weight_grams"),
                variant_label or raw.get("weight") or raw.get("size"),
            )''',
        '''            adapter_weight = raw.get("weight_grams")
            legacy_weight = raw.get("grams")
            weight_value = adapter_weight if adapter_weight not in (None, "") else legacy_weight
            weight_label = variant_label or raw.get("weight") or raw.get("size") or source_title
            grams, source_weight_label = normalize_weight(
                weight_value,
                weight_label,
                require_explicit_label=(
                    adapter_weight in (None, "") and legacy_weight not in (None, "")
                ),
            )''',
    )

    replace_exact(
        "tests/catalog_v4/test_normalization.py",
        '''    def test_weight_normalization(self) -> None:
        cases = {
            "3.5g": Decimal("3.5"),
            "1/8th oz": Decimal("3.5"),
            "Quarter oz": Decimal("7"),
            "half ounce": Decimal("14"),
            "one ounce": Decimal("28"),
            "two ounces": Decimal("56"),
        }
        for label, expected in cases.items():
            with self.subTest(label=label):
                self.assertEqual(normalize_weight(None, label)[0], expected)
        self.assertEqual(normalize_weight("7", "7 grams")[0], Decimal("7"))
        self.assertIsNone(normalize_weight(None, "family pack")[0])
        self.assertIsNone(normalize_weight(-1, "-1g")[0])''',
        '''    def test_weight_normalization(self) -> None:
        cases = {
            "3.5g": Decimal("3.5"),
            "1/8th oz": Decimal("3.5"),
            "Quarter oz": Decimal("7"),
            "half ounce": Decimal("14"),
            "one ounce": Decimal("28"),
            "two ounces": Decimal("56"),
        }
        for label, expected in cases.items():
            with self.subTest(label=label):
                self.assertEqual(normalize_weight(None, label)[0], expected)
        self.assertEqual(normalize_weight("7", "7 grams")[0], Decimal("7"))
        self.assertIsNone(normalize_weight(None, "family pack")[0])
        self.assertIsNone(normalize_weight(-1, "-1g")[0])
        for label in ("Quarter Pound", "quarter lb", "1/4 lb", "half pound"):
            with self.subTest(label=label):
                self.assertIsNone(normalize_weight(None, label)[0])

    def test_legacy_numeric_weight_requires_matching_source_evidence(self) -> None:
        self.assertIsNone(
            normalize_weight("28.3495", "Tier 1", require_explicit_label=True)[0]
        )
        self.assertIsNone(
            normalize_weight("56.699", "THCA 24.1%", require_explicit_label=True)[0]
        )
        self.assertIsNone(
            normalize_weight("28.3495", "7g", require_explicit_label=True)[0]
        )
        self.assertEqual(
            normalize_weight("28.3495", "1 oz", require_explicit_label=True)[0],
            Decimal("28"),
        )''',
    )

    replace_exact(
        "tests/catalog_v4/test_builder.py",
        '''    def test_write_and_verify_publication(self) -> None:''',
        '''    def test_legacy_numeric_weight_requires_explicit_source_evidence(self) -> None:
        base = {
            "source_id": "vendor",
            "vendor": "Vendor",
            "availability": "in_stock",
            "price": 30,
        }
        rows = [
            {
                **base,
                "source_product_id": "tier",
                "source_variant_id": "tier-v",
                "name": "Example THCA Flower | Tier 1",
                "url": "https://vendor.example/products/tier",
                "grams": 28.3495,
            },
            {
                **base,
                "source_product_id": "potency",
                "source_variant_id": "potency-v",
                "name": "Example THCA Flower 24.1%",
                "url": "https://vendor.example/products/potency",
                "grams": 28.3495,
            },
            {
                **base,
                "source_product_id": "explicit",
                "source_variant_id": "explicit-v",
                "name": "Explicit THCA Flower | 1 oz",
                "url": "https://vendor.example/products/explicit",
                "grams": 28.3495,
            },
            {
                **base,
                "source_product_id": "trusted",
                "source_variant_id": "trusted-v",
                "name": "Trusted THCA Flower",
                "url": "https://vendor.example/products/trusted",
                "weight_grams": 28,
            },
        ]
        result = build_catalog(
            rows,
            generated_at="2026-01-01T00:00:00Z",
            detail_shards=1,
        )
        index = read_json_bytes(result.files["catalog-v4/index.json"])
        self.assertEqual(result.product_count, 2)
        self.assertEqual(
            {product["strain_name"] for product in index["products"]},
            {"Explicit", "Trusted"},
        )
        self.assertEqual(result.rejections["reason_counts"]["invalid_or_missing_weight"], 2)

    def test_write_and_verify_publication(self) -> None:''',
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
