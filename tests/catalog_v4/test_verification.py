from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Callable

from scripts.catalog_v4 import VerificationError, build_catalog, verify_publication, write_result


class VerificationTests(unittest.TestCase):
    def build(self, root: Path) -> None:
        result = build_catalog(
            [
                {
                    "source_id": "x", "vendor": "X", "source_product_id": "p", "source_variant_id": "v-3.5",
                    "name": "X THCA Flower", "variant": "3.5g", "url": "https://x.example/products/x?variant=v-3.5",
                    "availability": "in_stock", "price": 20,
                },
                {
                    "source_id": "x", "vendor": "X", "source_product_id": "p", "source_variant_id": "v-7",
                    "name": "X THCA Flower", "variant": "7g", "url": "https://x.example/products/x?variant=v-7",
                    "availability": "in_stock", "price": 36,
                },
            ],
            generated_at="2026-01-01T00:00:00Z",
            detail_shards=1,
        )
        write_result(result, root)

    def rewrite_detail(self, root: Path, mutate: Callable[[dict], None]) -> None:
        manifest_path = root / "catalog-v4" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = manifest["product_detail_shards"][0]
        declared = str(entry["path"]).replace("\\", "/")
        if declared.startswith("data/"):
            declared = declared[5:]
        detail_path = root / declared
        payload = json.loads(detail_path.read_text(encoding="utf-8"))
        mutate(payload)
        detail_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        entry["sha256"] = hashlib.sha256(detail_path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def test_valid_builder_output_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build(root)
            result = verify_publication(root)
            self.assertTrue(result["verified"])
            self.assertEqual(result["variants"], 2)

    def test_hash_tampering_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build(root)
            index = root / "catalog-v4" / "index.json"
            index.write_text(index.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(VerificationError, "hash mismatch"):
                verify_publication(root)

    def test_generation_mismatch_fails_even_with_updated_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build(root)
            index_path = root / "catalog-v4" / "index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["generation_id"] = "0" * 32
            index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest_path = root / "catalog-v4" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["compact_index"]["sha256"] = hashlib.sha256(index_path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(VerificationError, "schema/generation mismatch"):
                verify_publication(root)

    def test_missing_detail_variant_fails_with_updated_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build(root)
            self.rewrite_detail(root, lambda payload: payload["products"][0].update(
                variants=payload["products"][0]["variants"][:-1]
            ))
            with self.assertRaisesRegex(VerificationError, "variant identity mismatch"):
                verify_publication(root)

    def test_extra_or_renamed_detail_variant_fails_with_updated_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build(root)

            def mutate(payload: dict) -> None:
                replacement = dict(payload["products"][0]["variants"][0])
                replacement["variant_id"] = "unexpected-detail-variant"
                payload["products"][0]["variants"].append(replacement)

            self.rewrite_detail(root, mutate)
            with self.assertRaisesRegex(VerificationError, "variant identity mismatch"):
                verify_publication(root)

    def test_detail_variant_weight_mismatch_fails_with_updated_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build(root)
            self.rewrite_detail(
                root,
                lambda payload: payload["products"][0]["variants"][0].__setitem__("grams", 99),
            )
            with self.assertRaisesRegex(VerificationError, "variant weight mismatch"):
                verify_publication(root)

    def test_detail_variant_url_mismatch_fails_with_updated_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build(root)
            self.rewrite_detail(
                root,
                lambda payload: payload["products"][0]["variants"][0].__setitem__(
                    "variant_url", "https://x.example/products/wrong?variant=wrong"
                ),
            )
            with self.assertRaisesRegex(VerificationError, "variant URL mismatch"):
                verify_publication(root)

    def test_expansion_only_detail_changes_remain_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build(root)
            self.rewrite_detail(
                root,
                lambda payload: payload["products"][0].__setitem__(
                    "image_url", "https://cdn.example/new-product-image.jpg"
                ),
            )
            self.assertTrue(verify_publication(root)["verified"])


if __name__ == "__main__":
    unittest.main()
