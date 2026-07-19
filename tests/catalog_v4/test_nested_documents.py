from __future__ import annotations

import json
import unittest

from scripts.catalog_v4 import build_catalog
from scripts.catalog_v4.builder import _flatten_records


def nested_product(*, empty_child_documents: bool = False) -> dict:
    child_documents = [] if empty_child_documents else [
        {
            "document_id": "v7-terp",
            "kind": "terpene",
            "scope": "variant",
            "source_variant_id": "v7",
            "url": "https://lab.example/v7.pdf",
        }
    ]
    return {
        "source_id": "vendor",
        "vendor": "Vendor",
        "source_product_id": "p1",
        "name": "Blue Dream THCA Flower",
        "url": "https://vendor.example/products/blue-dream",
        "documents": [
            {
                "document_id": "product-coa",
                "kind": "coa",
                "scope": "product",
                "url": "https://lab.example/product.pdf",
            }
        ],
        "variants": [
            {
                "source_variant_id": "v7",
                "variant": "7g",
                "availability": "in_stock",
                "price": 50,
                "url": "https://vendor.example/products/blue-dream?variant=v7",
                "documents": child_documents,
            },
            {
                "source_variant_id": "v14",
                "variant": "14g",
                "availability": "in_stock",
                "price": 85,
                "url": "https://vendor.example/products/blue-dream?variant=v14",
                "documents": [
                    {
                        "document_id": "v14-terp",
                        "kind": "terpene",
                        "scope": "variant",
                        "source_variant_id": "v14",
                        "url": "https://lab.example/v14.pdf",
                    }
                ],
            },
        ],
    }


class NestedDocumentMergeTests(unittest.TestCase):
    def test_flattening_adds_child_documents_without_erasing_parent(self):
        rows = _flatten_records([nested_product()])
        self.assertEqual(len(rows), 2)
        by_variant = {row["source_variant_id"]: row for row in rows}
        self.assertEqual(
            [document["document_id"] for document in by_variant["v7"]["documents"]],
            ["product-coa", "v7-terp"],
        )
        self.assertEqual(
            [document["document_id"] for document in by_variant["v14"]["documents"]],
            ["product-coa", "v14-terp"],
        )
        self.assertEqual(by_variant["v7"]["price"], 50)
        self.assertEqual(by_variant["v14"]["price"], 85)

    def test_empty_child_documents_do_not_silently_erase_parent_evidence(self):
        rows = _flatten_records([nested_product(empty_child_documents=True)])
        v7 = next(row for row in rows if row["source_variant_id"] == "v7")
        self.assertEqual([document["document_id"] for document in v7["documents"]], ["product-coa"])

    def test_catalog_detail_preserves_common_and_matching_narrow_documents(self):
        result = build_catalog(
            [nested_product()],
            generated_at="2026-07-19T00:00:00Z",
            detail_shards=1,
        )
        detail = json.loads(result.files["catalog-v4/details/000.json"])
        product = detail["products"][0]
        by_grams = {float(variant["grams"]): variant for variant in product["variants"]}
        self.assertEqual(
            {document["document_id"] for document in by_grams[7.0]["documents"]},
            {"product-coa", "v7-terp"},
        )
        self.assertEqual(
            {document["document_id"] for document in by_grams[14.0]["documents"]},
            {"product-coa", "v14-terp"},
        )
        self.assertTrue(all(
            len({document["document_id"] for document in variant["documents"]}) == len(variant["documents"])
            for variant in product["variants"]
        ))

    def test_duplicate_parent_child_document_identity_is_deduplicated_downstream(self):
        payload = nested_product()
        payload["variants"][0]["documents"].append({
            "document_id": "product-coa",
            "kind": "coa",
            "scope": "product",
            "url": "https://lab.example/product.pdf",
            "lab": "Example Lab",
        })
        result = build_catalog([payload], generated_at="2026-07-19T00:00:00Z", detail_shards=1)
        detail = json.loads(result.files["catalog-v4/details/000.json"])
        v7 = next(variant for variant in detail["products"][0]["variants"] if float(variant["grams"]) == 7.0)
        self.assertEqual([document["document_id"] for document in v7["documents"]].count("product-coa"), 1)


if __name__ == "__main__":
    unittest.main()
