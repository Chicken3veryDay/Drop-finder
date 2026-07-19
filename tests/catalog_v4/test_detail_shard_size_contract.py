from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.catalog_v4 import VerificationError, build_catalog, verify_publication, write_result

DETAIL_LIMIT = 2 * 1024 * 1024


def record(name: str, source_product_id: str, evidence_bytes: int) -> dict:
    return {
        "source_id": "vendor-x",
        "vendor": "Vendor X",
        "source_product_id": source_product_id,
        "source_variant_id": f"{source_product_id}-3.5",
        "name": f"{name} THCA Flower",
        "variant": "3.5g",
        "url": f"https://vendor.example/products/{source_product_id}?variant=3.5",
        "availability": "in_stock",
        "price": 25,
        "classification_evidence": {"blob": "x" * evidence_bytes},
    }


class DetailShardSizeContractTests(unittest.TestCase):
    def test_large_products_split_before_crossing_browser_limit(self) -> None:
        result = build_catalog(
            [
                record("Blue Dream", "blue-dream", 1_150_000),
                record("Green Dream", "green-dream", 1_150_000),
            ],
            generated_at="2026-07-19T12:00:00Z",
            detail_shards=1,
        )
        entries = result.manifest["product_detail_shards"]
        self.assertGreaterEqual(len(entries), 2)
        self.assertEqual(sum(entry["product_count"] for entry in entries), 2)
        for entry in entries:
            relative = entry["path"].removeprefix("data/")
            payload = result.files[relative]
            self.assertEqual(entry["bytes"], len(payload))
            self.assertLessEqual(len(payload), DETAIL_LIMIT)

    def test_single_oversized_product_fails_with_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, r"single detail product .* exceeds"):
            build_catalog(
                [record("Huge Dream", "huge-dream", DETAIL_LIMIT + 100_000)],
                generated_at="2026-07-19T12:00:00Z",
                detail_shards=1,
            )

    def test_manifest_records_exact_bytes_for_every_declared_artifact(self) -> None:
        result = build_catalog(
            [record("Blue Dream", "blue-dream", 0)],
            generated_at="2026-07-19T12:00:00Z",
            detail_shards=1,
        )
        for key in ("compact_index", "vendor_profiles", "rejections"):
            descriptor = result.manifest[key]
            relative = descriptor["path"].removeprefix("data/")
            self.assertEqual(descriptor["bytes"], len(result.files[relative]))
        for descriptor in result.manifest["product_detail_shards"]:
            relative = descriptor["path"].removeprefix("data/")
            self.assertEqual(descriptor["bytes"], len(result.files[relative]))

    def test_verifier_rejects_declared_byte_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_result(
                build_catalog(
                    [record("Blue Dream", "blue-dream", 0)],
                    generated_at="2026-07-19T12:00:00Z",
                    detail_shards=1,
                ),
                root,
            )
            manifest_path = root / "catalog-v4" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["product_detail_shards"][0]["bytes"] += 1
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(VerificationError, "detail shard byte count mismatch"):
                verify_publication(root)

    def test_verifier_rejects_hash_consistent_oversized_detail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_result(
                build_catalog(
                    [record("Blue Dream", "blue-dream", 0)],
                    generated_at="2026-07-19T12:00:00Z",
                    detail_shards=1,
                ),
                root,
            )
            manifest_path = root / "catalog-v4" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            descriptor = manifest["product_detail_shards"][0]
            detail_path = root / descriptor["path"].removeprefix("data/")
            payload = detail_path.read_bytes()
            oversized = payload + b" " * (DETAIL_LIMIT - len(payload) + 1)
            detail_path.write_bytes(oversized)
            descriptor["bytes"] = len(oversized)
            descriptor["sha256"] = hashlib.sha256(oversized).hexdigest()
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(VerificationError, "detail shard exceeds browser byte limit"):
                verify_publication(root)

    def test_current_publication_remains_within_shared_limits(self) -> None:
        result = verify_publication(Path("cloud_pages/data"))
        self.assertTrue(result["verified"])


if __name__ == "__main__":
    unittest.main()
