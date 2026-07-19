from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Callable

from scripts.catalog_v4 import VerificationError, build_catalog, verify_publication, write_result


class ConsumerContractVerificationTests(unittest.TestCase):
    def build(self, root: Path) -> None:
        result = build_catalog(
            [
                {
                    "source_id": "vendor-x",
                    "vendor": "Vendor X",
                    "source_product_id": "product-x",
                    "source_variant_id": "variant-3.5",
                    "name": "Blue Dream THCA Flower",
                    "variant": "3.5g",
                    "url": "https://vendor.example/products/blue-dream?variant=variant-3.5",
                    "availability": "in_stock",
                    "price": 20,
                },
                {
                    "source_id": "vendor-x",
                    "vendor": "Vendor X",
                    "source_product_id": "product-x",
                    "source_variant_id": "variant-7",
                    "name": "Blue Dream THCA Flower",
                    "variant": "7g",
                    "url": "https://vendor.example/products/blue-dream?variant=variant-7",
                    "availability": "in_stock",
                    "price": 36,
                },
            ],
            generated_at="2026-07-19T12:00:00Z",
            detail_shards=1,
        )
        write_result(result, root)

    def rewrite_index(self, root: Path, mutate: Callable[[dict], None]) -> None:
        index_path = root / "catalog-v4" / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        mutate(index)
        index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest_path = root / "catalog-v4" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["compact_index"]["sha256"] = hashlib.sha256(index_path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def assert_index_rejected(self, mutate: Callable[[dict], None], pattern: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build(root)
            self.rewrite_index(root, mutate)
            with self.assertRaisesRegex(VerificationError, pattern):
                verify_publication(root)

    def test_missing_or_blank_product_identity_fields_fail(self) -> None:
        cases = (
            ("vendor_id", "missing vendor id"),
            ("vendor_name", "missing vendor name"),
            ("strain_name", "missing strain name"),
        )
        for field, pattern in cases:
            with self.subTest(field=field, form="missing"):
                self.assert_index_rejected(
                    lambda index, field=field: index["products"][0].pop(field, None),
                    pattern,
                )
            with self.subTest(field=field, form="blank"):
                self.assert_index_rejected(
                    lambda index, field=field: index["products"][0].__setitem__(field, "  "),
                    pattern,
                )

    def test_variant_requires_https_navigation_url(self) -> None:
        for value in ("", "not-a-url", "http://vendor.example/product"):
            with self.subTest(value=value):
                self.assert_index_rejected(
                    lambda index, value=value: index["products"][0]["variants"][0].__setitem__(
                        "product_url", value
                    ),
                    "invalid variant URL",
                )

    def test_one_invalid_variant_rejects_the_whole_product(self) -> None:
        self.assert_index_rejected(
            lambda index: index["products"][0]["variants"][1].pop("product_url", None),
            "invalid variant URL",
        )

    def test_default_variant_must_remain_consumer_valid(self) -> None:
        def mutate(index: dict) -> None:
            product = index["products"][0]
            default_id = product["default_variant_id"]
            variant = next(row for row in product["variants"] if row["variant_id"] == default_id)
            variant["product_url"] = ""

        self.assert_index_rejected(mutate, "invalid variant URL")

    def test_valid_builder_output_still_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build(root)
            result = verify_publication(root)
            self.assertTrue(result["verified"])
            self.assertEqual(result["products"], 1)
            self.assertEqual(result["variants"], 2)


if __name__ == "__main__":
    unittest.main()
