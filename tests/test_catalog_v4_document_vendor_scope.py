from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.catalog_v4 import VerificationError, build_catalog, verify_publication, write_result


def product(vendor_id: str, vendor_name: str, title: str, url: str) -> dict[str, object]:
    return {
        "source_id": vendor_id,
        "vendor": vendor_name,
        "source_product_id": "42",
        "source_variant_id": f"{vendor_id}-3.5g",
        "source_title": title,
        "name": title,
        "variant": "3.5g",
        "in_stock": True,
        "grams": 3.5,
        "price": 24.0,
        "url": url,
    }


def detail_products(result) -> list[dict[str, object]]:
    products: list[dict[str, object]] = []
    for path, blob in result.files.items():
        if not path.startswith("catalog-v4/details/"):
            continue
        payload = json.loads(blob)
        products.extend(payload["products"])
    return products


class CatalogV4DocumentVendorScopeTests(unittest.TestCase):
    def records(self) -> list[dict[str, object]]:
        return [
            product("vendor-a", "Vendor A", "Alpha THCA Flower", "https://a.example/products/alpha"),
            product("vendor-b", "Vendor B", "Beta THCA Flower", "https://b.example/products/beta"),
        ]

    def document(self, **overrides) -> dict[str, object]:
        record: dict[str, object] = {
            "vendor_id": "vendor-a",
            "source_product_id": "42",
            "url": "https://a.example/labs/alpha-coa.pdf",
            "kind": "coa",
            "scope": "product",
        }
        record.update(overrides)
        return record

    def build(self, records=None, documents=None):
        return build_catalog(
            self.records() if records is None else records,
            document_records=[self.document()] if documents is None else documents,
            generated_at="2026-07-16T00:00:00Z",
            detail_shards=2,
        )

    def test_external_documents_are_scoped_by_vendor_and_retain_provenance(self):
        for records in (self.records(), list(reversed(self.records()))):
            result = self.build(records=records)
            by_vendor = {row["vendor_id"]: row for row in detail_products(result)}

            vendor_a_documents = by_vendor["vendor-a"]["variants"][0]["documents"]
            vendor_b_documents = by_vendor["vendor-b"]["variants"][0]["documents"]

            self.assertEqual(len(vendor_a_documents), 1)
            self.assertEqual(vendor_b_documents, [])
            self.assertEqual(vendor_a_documents[0]["vendor_id"], "vendor-a")
            self.assertEqual(vendor_a_documents[0]["product_id"], by_vendor["vendor-a"]["product_id"])
            self.assertEqual(
                vendor_a_documents[0]["public_url"],
                "https://a.example/labs/alpha-coa.pdf",
            )

    def test_missing_vendor_identity_is_quarantined_and_not_attached(self):
        result = self.build(documents=[self.document(vendor_id="")])

        self.assertEqual(
            result.rejections["reason_counts"].get("external_document_missing_vendor_identity"),
            1,
        )
        self.assertTrue(
            all(
                variant["documents"] == []
                for row in detail_products(result)
                for variant in row["variants"]
            )
        )

    def test_inline_document_with_explicit_mismatched_vendor_is_rejected(self):
        records = self.records()
        records[1] = {
            **records[1],
            "documents": [self.document()],
        }

        result = self.build(records=records, documents=[])
        by_vendor = {row["vendor_id"]: row for row in detail_products(result)}

        self.assertEqual(by_vendor["vendor-b"]["variants"][0]["documents"], [])

    def test_publication_verifier_rejects_document_vendor_mismatch(self):
        result = self.build()
        with tempfile.TemporaryDirectory(prefix="dropfinder-catalog-v4-") as directory:
            output_root = Path(directory)
            write_result(result, output_root)
            verify_publication(output_root)

            manifest_path = output_root / "catalog-v4" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            target_entry = None
            detail = None
            product_row = None
            for entry in manifest["product_detail_shards"]:
                candidate_path = output_root / entry["path"].removeprefix("data/")
                candidate_detail = json.loads(candidate_path.read_text(encoding="utf-8"))
                candidate_product = next(
                    (
                        row
                        for row in candidate_detail["products"]
                        if any(variant["documents"] for variant in row["variants"])
                    ),
                    None,
                )
                if candidate_product is not None:
                    target_entry = entry
                    detail = candidate_detail
                    product_row = candidate_product
                    break

            self.assertIsNotNone(target_entry)
            self.assertIsNotNone(detail)
            self.assertIsNotNone(product_row)
            detail_path = output_root / target_entry["path"].removeprefix("data/")
            product_row["variants"][0]["documents"][0]["vendor_id"] = "vendor-b"
            encoded = (json.dumps(detail, indent=2, sort_keys=True, ensure_ascii=False, separators=(",", ": ")) + "\n").encode("utf-8")
            detail_path.write_bytes(encoded)
            target_entry["sha256"] = hashlib.sha256(encoded).hexdigest()
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False, separators=(",", ": ")) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(VerificationError, "document vendor mismatch"):
                verify_publication(output_root)


if __name__ == "__main__":
    unittest.main()
