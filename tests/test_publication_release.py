from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.publication_release import (
    ReleaseGateError,
    build_receipt,
    evaluate_continuity,
    load_json,
    stamp_shard,
    verify_shards,
)


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
SHA_D = "d" * 40


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publication(root: Path, *, products: int, sources: int, v4_products: int, variants: int, generation: str) -> None:
    data = root / "data"
    rows = [{"id": f"p-{index}"} for index in range(products)]
    write_json(data / "catalog.json", {"product_count": products, "products": rows})
    write_json(
        data / "status.json",
        {
            "healthy_sources": sources,
            "enabled_sources": sources,
            "degraded_sources": 0,
        },
    )
    write_json(data / "runtime.json", {"zero_degraded_active_services": True})

    v4 = data / "catalog-v4"
    index = {
        "generation_id": generation,
        "product_count": v4_products,
        "in_stock_variant_count": variants,
        "products": [],
    }
    vendors = {"generation_id": generation, "vendors": []}
    rejections = {"generation_id": generation, "count": 0, "products": []}
    detail = {"generation_id": generation, "products": [{"id": f"v4-{i}"} for i in range(v4_products)]}
    write_json(v4 / "index.json", index)
    write_json(v4 / "vendors.json", vendors)
    write_json(v4 / "rejections.json", rejections)
    write_json(v4 / "details" / "000.json", detail)
    manifest = {
        "schema_version": "dropfinder-catalog-manifest-v4",
        "generation_id": generation,
        "generated_at": "2026-07-19T00:00:00+00:00",
        "product_count": v4_products,
        "in_stock_variant_count": variants,
        "compact_index": {
            "path": "data/catalog-v4/index.json",
            "sha256": sha256(v4 / "index.json"),
        },
        "vendor_profiles": {
            "path": "data/catalog-v4/vendors.json",
            "sha256": sha256(v4 / "vendors.json"),
        },
        "rejections": {
            "path": "data/catalog-v4/rejections.json",
            "sha256": sha256(v4 / "rejections.json"),
        },
        "product_detail_shards": [
            {
                "path": "data/catalog-v4/details/000.json",
                "product_count": v4_products,
                "sha256": sha256(v4 / "details" / "000.json"),
            }
        ],
    }
    write_json(v4 / "manifest.json", manifest)


class PublicationReleaseTests(unittest.TestCase):
    def test_shards_are_stamped_and_verified_against_one_source_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for shard in (0, 1):
                path = root / f"shard-{shard}.json"
                write_json(path, {"schema_version": "dropfinder-autonomous-shard-v1", "products": []})
                stamp_shard(path, SHA_A)
            result = verify_shards(root, SHA_A)
            self.assertEqual(result["source_commit"], SHA_A)
            self.assertEqual(result["shards"], [0, 1])

    def test_mixed_or_reused_shard_provenance_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "shard-0.json"
            second = root / "shard-1.json"
            write_json(first, {"schema_version": "dropfinder-autonomous-shard-v1"})
            write_json(second, {"schema_version": "dropfinder-autonomous-shard-v1"})
            stamp_shard(first, SHA_A)
            stamp_shard(second, SHA_B)
            with self.assertRaises(ReleaseGateError):
                verify_shards(root, SHA_A)
            with self.assertRaises(ReleaseGateError):
                stamp_shard(first, SHA_B)

    def test_normal_churn_passes_but_catastrophic_drop_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = root / "previous"
            normal = root / "normal"
            collapsed = root / "collapsed"
            publication(previous, products=270, sources=12, v4_products=100, variants=180, generation="previous")
            publication(normal, products=250, sources=11, v4_products=92, variants=160, generation="normal")
            publication(collapsed, products=25, sources=5, v4_products=10, variants=18, generation="collapsed")
            accepted = evaluate_continuity(previous, normal)
            self.assertEqual(accepted["status"], "accepted")
            with self.assertRaises(ReleaseGateError):
                evaluate_continuity(previous, collapsed)

    def test_audited_override_is_required_for_large_intentional_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = root / "previous"
            candidate = root / "candidate"
            publication(previous, products=270, sources=12, v4_products=100, variants=180, generation="previous")
            publication(candidate, products=100, sources=6, v4_products=40, variants=70, generation="candidate")
            with self.assertRaises(ReleaseGateError):
                evaluate_continuity(previous, candidate, override_reason="too short")
            result = evaluate_continuity(
                previous,
                candidate,
                override_reason="Retire documented unsupported sources in release 4",
            )
            self.assertEqual(result["status"], "accepted_override")
            self.assertTrue(result["override"]["used"])
            self.assertTrue(result["anomalies"])

    def test_receipt_covers_generation_hashes_provenance_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            publication(root, products=50, sources=8, v4_products=20, variants=31, generation="generation-1")
            continuity = evaluate_continuity(None, root)
            endpoint = {"status": "verified", "http_status": 200}
            receipt = build_receipt(
                root,
                source_commit=SHA_A,
                generated_commit=SHA_B,
                publication_commit=SHA_C,
                rollback_commit=SHA_D,
                workflow_name="DropFinder Autonomous Cloud",
                workflow_run_id="123",
                public_url="https://example.test/Drop-finder/",
                continuity=continuity,
                endpoint_verification=endpoint,
            )
            self.assertEqual(receipt["generation_id"], "generation-1")
            self.assertEqual(receipt["product_count"], 50)
            self.assertEqual(receipt["variant_count"], 31)
            self.assertEqual(receipt["rollback_commit"], SHA_D)
            self.assertIn("data/catalog-v4/manifest.json", receipt["catalog_v4_hashes"])

    def test_non_standard_json_constants_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text('{"value": NaN}', encoding="utf-8")
            with self.assertRaises(ReleaseGateError):
                load_json(path)


if __name__ == "__main__":
    unittest.main()
