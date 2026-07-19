from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.catalog_v4 import build_catalog, select_active_variant, verify_publication, write_result

FIXTURE = Path(__file__).parent / "fixtures" / "legacy_rows.json"


def read_json_bytes(data: bytes) -> dict:
    return json.loads(data.decode("utf-8"))


class CatalogBuilderTests(unittest.TestCase):
    def load_rows(self) -> tuple[list[dict], str]:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        return payload["products"], payload["generated_at"]

    def test_grouping_stock_filtering_and_pricing(self) -> None:
        rows, stamp = self.load_rows()
        result = build_catalog(rows, generated_at=stamp, detail_shards=4)
        index = read_json_bytes(result.files["catalog-v4/index.json"])
        self.assertEqual(result.product_count, 3)
        self.assertEqual(result.variant_count, 4)
        self.assertEqual({p["strain_name"] for p in index["products"]}, {"Blue Dream", "Northern Lights", "Gelato"})
        self.assertTrue(all(v["in_stock"] is True for p in index["products"] for v in p["variants"]))
        blue = next(p for p in index["products"] if p["strain_name"] == "Blue Dream")
        self.assertEqual(len(blue["variants"]), 2)
        self.assertEqual(blue["total_thc_display_percent"], 22)
        self.assertEqual(blue["rating"], 4.7)
        first = next(v for v in blue["variants"] if float(v["grams"]) == 3.5)
        self.assertEqual(first["current_price"], 35.0)
        self.assertEqual(first["original_price"], 40.0)
        self.assertEqual(first["discount_percent"], 12.5)
        self.assertAlmostEqual(first["price_per_gram"], 10.0, places=4)
        self.assertEqual(blue["default_variant_id"], select_active_variant(blue["variants"])["variant_id"])
        reasons = result.rejections["reason_counts"]
        self.assertEqual(reasons["out_of_stock_variant"], 1)
        self.assertEqual(reasons["unknown_stock_variant"], 1)

    def test_duplicate_weight_resolution_prefers_fresher_more_complete(self) -> None:
        rows, stamp = self.load_rows()
        result = build_catalog(rows, generated_at=stamp, detail_shards=2)
        index = read_json_bytes(result.files["catalog-v4/index.json"])
        gelato = next(p for p in index["products"] if p["strain_name"] == "Gelato")
        self.assertEqual(len(gelato["variants"]), 1)
        self.assertEqual(gelato["variants"][0]["current_price"], 29.0)
        shard = gelato["detail_shard"]
        detail = read_json_bytes(result.files[f"catalog-v4/details/{shard:03d}.json"])
        product = next(p for p in detail["products"] if p["product_id"] == gelato["product_id"])
        resolutions = product["provenance"]["duplicate_resolutions"]
        self.assertTrue(any(r["method"] == "duplicate_weight_completeness_then_freshness" for r in resolutions))

    def test_total_thc_methods_and_impossible_values(self) -> None:
        base = {
            "source_id": "x", "vendor": "X", "source_product_id": "p", "source_variant_id": "v",
            "name": "Test THCA Flower 3.5g", "variant": "3.5g", "url": "https://x.example/products/test?variant=v",
            "availability": "in_stock", "price": 20,
        }
        full = build_catalog([{**base, "thca": 25, "delta9_thc": 0.2}], generated_at="2026-01-01T00:00:00Z", detail_shards=1)
        detail = read_json_bytes(full.files["catalog-v4/details/000.json"])["products"][0]
        self.assertEqual(detail["total_thc"]["method"], "delta9_plus_thca_times_0_877")
        self.assertAlmostEqual(detail["total_thc"]["calculated_percent"], 22.125, places=4)
        estimated = build_catalog([{**base, "thca": 25}], generated_at="2026-01-01T00:00:00Z", detail_shards=1)
        detail = read_json_bytes(estimated.files["catalog-v4/details/000.json"])["products"][0]
        self.assertEqual(detail["total_thc"]["method"], "thca_only_estimate")
        missing = build_catalog([{**base, "thca": 150}], generated_at="2026-01-01T00:00:00Z", detail_shards=1)
        detail = read_json_bytes(missing.files["catalog-v4/details/000.json"])["products"][0]
        self.assertEqual(detail["total_thc"]["method"], "unavailable")
        self.assertIsNone(detail["total_thc"]["display_percent"])

    def test_documents_vendor_profiles_and_variant_mapping(self) -> None:
        row = {
            "source_id": "vendor", "vendor": "Vendor", "source_product_id": "p", "source_variant_id": "v-7",
            "name": "Document THCA Flower 7g", "variant": "7g", "url": "https://vendor.example/products/doc?variant=v-7",
            "availability": "in_stock", "price": 50,
            "documents": [
                {"kind": "coa", "scope": "variant", "source_variant_id": "v-7", "url": "https://lab.example/coa.pdf", "mime_type": "application/pdf"},
                {"kind": "coa", "scope": "weight", "grams": 14, "url": "https://lab.example/wrong.pdf"},
                {"kind": "terpene", "scope": "weight", "grams": 7, "url": "https://lab.example/terpenes.pdf"},
                {"kind": "coa", "url": "javascript:alert(1)"},
            ],
        }
        profiles = {"vendors": [{"vendor_id": "vendor", "vendor_name": "Vendor", "favicon_url": "https://vendor.example/favicon.ico", "age_gate_classification": "self_attestation_21_plus"}]}
        result = build_catalog([row], generated_at="2026-01-01T00:00:00Z", vendor_profiles=profiles, detail_shards=1)
        detail = read_json_bytes(result.files["catalog-v4/details/000.json"])["products"][0]
        documents = detail["variants"][0]["documents"]
        self.assertEqual({d["kind"] for d in documents}, {"coa", "terpene"})
        self.assertEqual(len(documents), 2)
        vendors = read_json_bytes(result.files["catalog-v4/vendors.json"])
        self.assertEqual(vendors["vendors"][0]["age_gate_classification"], "self_attestation_21_plus")
        self.assertEqual(vendors["vendors"][0]["profile_status"], "supplied")

    def test_stable_ids_and_deterministic_output(self) -> None:
        rows, stamp = self.load_rows()
        first = build_catalog(rows, generated_at=stamp, detail_shards=4)
        second = build_catalog(list(reversed(rows)), generated_at=stamp, detail_shards=4)
        self.assertEqual(first.generation_id, second.generation_id)
        self.assertEqual(first.files, second.files)
        changed = [dict(row) for row in rows]
        changed[0]["price"] = 34
        third = build_catalog(changed, generated_at=stamp, detail_shards=4)
        first_index = read_json_bytes(first.files["catalog-v4/index.json"])
        third_index = read_json_bytes(third.files["catalog-v4/index.json"])
        self.assertEqual(
            {p["product_id"] for p in first_index["products"]},
            {p["product_id"] for p in third_index["products"]},
        )
        self.assertNotEqual(first.generation_id, third.generation_id)

    def test_duplicate_product_url_conflict_uses_source_authority(self) -> None:
        base = {
            "source_id": "vendor", "vendor": "Vendor", "name": "Conflict THCA Flower 3.5g",
            "variant": "3.5g", "url": "https://vendor.example/products/conflict",
            "availability": "in_stock", "price": 25,
        }
        rows = [
            {**base, "source_product_id": "authoritative", "source_variant_id": "v1", "effects": ["Calm"]},
            {**base, "source_variant_id": "v2", "rating": 4.5, "review_count": 10},
        ]
        result = build_catalog(rows, generated_at="2026-01-01T00:00:00Z", detail_shards=1)
        self.assertEqual(result.product_count, 1)
        detail = read_json_bytes(result.files["catalog-v4/details/000.json"])["products"][0]
        resolution = detail["provenance"]["product_url_conflict_resolution"]
        self.assertEqual(resolution["method"], "source_authority_then_variant_coverage_then_completeness_then_freshness")
        self.assertEqual(len(resolution["discarded_product_ids"]), 1)

    def test_duplicate_product_url_reconciliation_preserves_unique_weights_and_documents(self) -> None:
        url = "https://vendor.example/products/blue-dream"
        rows = [
            {
                "source_id": "vendor", "vendor": "Vendor", "source_product_id": "123", "source_variant_id": "v-35",
                "name": "Blue Dream THCA Flower | 3.5g", "variant": "3.5g", "url": url,
                "availability": "in_stock", "price": 25,
                "documents": [{"kind": "coa", "scope": "variant", "source_variant_id": "v-35", "url": "https://lab.example/35.pdf"}],
            },
            {
                "source_id": "vendor", "vendor": "Vendor", "source_variant_id": "v-7",
                "name": "Blue Dream THCA Flower | 7g", "variant": "7g", "url": url,
                "availability": "in_stock", "price": 40,
                "documents": [{"kind": "coa", "scope": "variant", "source_variant_id": "v-7", "url": "https://lab.example/7.pdf"}],
            },
        ]
        result = build_catalog(rows, generated_at="2026-01-01T00:00:00Z", detail_shards=1)
        self.assertEqual(result.product_count, 1)
        self.assertEqual(result.variant_count, 2)
        index_product = read_json_bytes(result.files["catalog-v4/index.json"])["products"][0]
        self.assertEqual({float(variant["grams"]) for variant in index_product["variants"]}, {3.5, 7.0})
        detail = read_json_bytes(result.files["catalog-v4/details/000.json"])["products"][0]
        self.assertEqual(detail["provenance"]["identity"]["method"], "source_product_identity")
        self.assertEqual(
            {document["public_url"] for variant in detail["variants"] for document in variant["documents"]},
            {"https://lab.example/35.pdf", "https://lab.example/7.pdf"},
        )
        self.assertTrue(all(
            document["product_id"] == detail["product_id"]
            for variant in detail["variants"]
            for document in variant["documents"]
        ))
        resolution = detail["provenance"]["product_url_conflict_resolution"]
        self.assertEqual(resolution["candidate_variant_count"], 2)
        self.assertEqual(resolution["retained_variant_count"], 2)
        self.assertEqual(resolution["discarded_variant_count"], 0)

    def test_duplicate_product_url_reconciliation_does_not_restore_rejected_stock(self) -> None:
        url = "https://vendor.example/products/blue-dream"
        rows = [
            {
                "source_id": "vendor", "vendor": "Vendor", "source_product_id": "123", "source_variant_id": "v-35",
                "name": "Blue Dream THCA Flower | 3.5g", "variant": "3.5g", "url": url,
                "availability": "in_stock", "price": 25,
            },
            {
                "source_id": "vendor", "vendor": "Vendor", "source_variant_id": "v-7",
                "name": "Blue Dream THCA Flower | 7g", "variant": "7g", "url": url,
                "availability": "out_of_stock", "price": 40,
            },
        ]
        result = build_catalog(rows, generated_at="2026-01-01T00:00:00Z", detail_shards=1)
        self.assertEqual(result.product_count, 1)
        self.assertEqual(result.variant_count, 1)
        index_product = read_json_bytes(result.files["catalog-v4/index.json"])["products"][0]
        self.assertEqual([float(variant["grams"]) for variant in index_product["variants"]], [3.5])
        self.assertEqual(result.rejections["reason_counts"]["out_of_stock_variant"], 1)

    def test_write_and_verify_publication(self) -> None:
        rows, stamp = self.load_rows()
        result = build_catalog(rows, generated_at=stamp, detail_shards=4)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_result(result, root)
            verification = verify_publication(root)
            self.assertTrue(verification["verified"])
            self.assertEqual(verification["products"], result.product_count)
            self.assertEqual(verification["variants"], result.variant_count)


if __name__ == "__main__":
    unittest.main()
