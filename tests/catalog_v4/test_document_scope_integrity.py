from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.catalog_v4 import VerificationError, build_catalog, verify_publication, write_result
from scripts.catalog_v4.documents import normalize_documents


class DocumentScopeIntegrityTests(unittest.TestCase):
    def targets(self) -> list[dict[str, object]]:
        return [
            {
                "variant_id": "normalized-v7",
                "source_variant_id": "source-v7",
                "grams": 7.0,
                "batch": "B1",
                "lot": "L1",
            },
            {
                "variant_id": "normalized-v14",
                "source_variant_id": "source-v14",
                "grams": 14.0,
                "batch": "B2",
                "lot": "L2",
            },
        ]

    def documents(self) -> list[dict[str, object]]:
        return [
            {"document_id": "variant-v7", "url": "https://lab.example/v7.pdf", "kind": "coa", "scope": "variant", "variant_id": "source-v7"},
            {"document_id": "variant-missing", "url": "https://lab.example/variant-missing.pdf", "kind": "coa", "scope": "variant"},
            {"document_id": "weight-7", "url": "https://lab.example/7g.pdf", "kind": "coa", "scope": "weight", "grams": 7.0},
            {"document_id": "weight-missing", "url": "https://lab.example/weight-missing.pdf", "kind": "coa", "scope": "weight"},
            {"document_id": "batch-b1", "url": "https://lab.example/b1.pdf", "kind": "coa", "scope": "batch", "batch": "B1"},
            {"document_id": "batch-missing", "url": "https://lab.example/batch-missing.pdf", "kind": "coa", "scope": "batch"},
            {"document_id": "product-wide", "url": "https://lab.example/product.pdf", "kind": "coa", "scope": "product"},
            {"document_id": "invalid-scope", "url": "https://lab.example/invalid.pdf", "kind": "coa", "scope": "surprise"},
        ]

    def test_narrow_scopes_require_present_matching_identity(self) -> None:
        mapped: dict[str, set[str]] = {}
        rejected: list[dict[str, object]] = []
        for target in self.targets():
            rows = normalize_documents(
                self.documents(),
                product_id="product-1",
                vendor_id="vendor-1",
                variant_id=str(target["variant_id"]),
                source_variant_id=str(target["source_variant_id"]),
                grams=float(target["grams"]),
                batch=str(target["batch"]),
                lot=str(target["lot"]),
                rejections=rejected,
            )
            mapped[str(target["variant_id"])] = {str(row["document_id"]) for row in rows}
            for row in rows:
                if row["scope"] in {"variant", "weight", "batch"}:
                    self.assertEqual(row["variant_id"], target["variant_id"])

        self.assertEqual(
            mapped["normalized-v7"],
            {"variant-v7", "weight-7", "batch-b1", "product-wide"},
        )
        self.assertEqual(mapped["normalized-v14"], {"product-wide"})
        reasons = {str(row["reason"]) for row in rejected}
        self.assertTrue({
            "document_variant_identity_missing",
            "document_variant_identity_mismatch",
            "document_weight_identity_missing",
            "document_weight_identity_mismatch",
            "document_batch_identity_missing",
            "document_batch_identity_mismatch",
            "document_invalid_scope",
        }.issubset(reasons))

    def build(self):
        records = [
            {
                "source_id": "vendor-1",
                "vendor": "Vendor One",
                "source_product_id": "product-source",
                "source_variant_id": "source-v7",
                "name": "Blue Dream THCA Flower 7g",
                "variant": "7g",
                "url": "https://shop.example/products/blue-dream?variant=v7",
                "availability": "in_stock",
                "price": 35,
                "batch": "B1",
            },
            {
                "source_id": "vendor-1",
                "vendor": "Vendor One",
                "source_product_id": "product-source",
                "source_variant_id": "source-v14",
                "name": "Blue Dream THCA Flower 14g",
                "variant": "14g",
                "url": "https://shop.example/products/blue-dream?variant=v14",
                "availability": "in_stock",
                "price": 60,
                "batch": "B2",
            },
        ]
        documents = [
            {
                "vendor_id": "vendor-1",
                "source_product_id": "product-source",
                "document_id": "batch-b1",
                "url": "https://lab.example/b1.pdf",
                "kind": "coa",
                "scope": "batch",
                "batch": "B1",
            },
            {
                "vendor_id": "vendor-1",
                "source_product_id": "product-source",
                "document_id": "variant-missing",
                "url": "https://lab.example/missing.pdf",
                "kind": "coa",
                "scope": "variant",
            },
        ]
        return build_catalog(records, document_records=documents, generated_at="2026-07-19T00:00:00Z", detail_shards=2)

    def test_builder_attaches_batch_evidence_only_to_matching_variant_and_records_rejection(self) -> None:
        result = self.build()
        product = next(
            row
            for path, blob in result.files.items()
            if path.startswith("catalog-v4/details/")
            for row in json.loads(blob)["products"]
        )
        by_weight = {float(row["grams"]): row for row in product["variants"]}
        self.assertEqual([row["document_id"] for row in by_weight[7.0]["documents"]], ["batch-b1"])
        self.assertEqual(by_weight[14.0]["documents"], [])
        self.assertGreaterEqual(result.rejections["reason_counts"].get("document_variant_identity_missing", 0), 1)
        self.assertGreaterEqual(result.rejections["reason_counts"].get("document_batch_identity_mismatch", 0), 1)

    def test_publication_verifier_rejects_corrupted_narrow_scope_association(self) -> None:
        result = self.build()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_result(result, root)
            verify_publication(root)

            manifest_path = root / "catalog-v4" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            target_entry = None
            target_payload = None
            target_variant = None
            for entry in manifest["product_detail_shards"]:
                path = root / entry["path"].removeprefix("data/")
                payload = json.loads(path.read_text(encoding="utf-8"))
                for product in payload["products"]:
                    for variant in product["variants"]:
                        if variant["documents"]:
                            target_entry = entry
                            target_payload = payload
                            target_variant = variant
                            break
            self.assertIsNotNone(target_entry)
            self.assertIsNotNone(target_payload)
            self.assertIsNotNone(target_variant)
            target_variant["batch"] = "B2"
            detail_path = root / target_entry["path"].removeprefix("data/")
            encoded = (json.dumps(target_payload, indent=2, sort_keys=True, ensure_ascii=False, separators=(",", ": ")) + "\n").encode("utf-8")
            detail_path.write_bytes(encoded)
            target_entry["sha256"] = hashlib.sha256(encoded).hexdigest()
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False, separators=(",", ": ")) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(VerificationError, "document batch identity mismatch"):
                verify_publication(root)


if __name__ == "__main__":
    unittest.main()
