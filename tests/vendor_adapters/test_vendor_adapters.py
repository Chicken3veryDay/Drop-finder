from __future__ import annotations

import unittest

from scripts.vendor_adapters.annotate import annotate_products
from scripts.vendor_adapters.discovery import discover_json_documents
from scripts.vendor_adapters.mapping import map_documents


class SharedDocumentAssociationTests(unittest.TestCase):
    SOURCE_URL = "https://shop.example/api/products"
    ALLOWED_HOSTS = {"shop.example", "cdn.example.com"}
    OBSERVED_AT = "2026-07-16T00:00:00Z"

    def _discover(self, payload):
        return discover_json_documents(
            payload,
            vendor_id="vendor",
            source_url=self.SOURCE_URL,
            allowed_hosts=self.ALLOWED_HOSTS,
            observed_at=self.OBSERVED_AT,
        )

    def test_shared_url_preserves_distinct_associations_through_annotation(self):
        payload = [
            {
                "product_id": "p1",
                "variant_id": "v-7g",
                "batch_id": "B1",
                "title": "Blue Dream 7g COA",
                "coa_url": "https://cdn.example.com/blue-dream.pdf?utm_source=first",
            },
            {
                "product_id": "p2",
                "variant_id": "v-14g",
                "batch_id": "B2",
                "title": "Blue Dream 14g COA",
                "coa_url": "https://cdn.example.com/blue-dream.pdf?utm_source=second",
            },
        ]

        candidates = self._discover(payload)
        reversed_candidates = self._discover(list(reversed(payload)))

        self.assertEqual(len(candidates), 2)
        self.assertEqual(
            {(item.product_id, item.variant_id, item.batch_id) for item in candidates},
            {("p1", "v-7g", "B1"), ("p2", "v-14g", "B2")},
        )
        self.assertEqual(
            {item.url for item in candidates},
            {"https://cdn.example.com/blue-dream.pdf"},
        )
        self.assertEqual(len({item.document_id for item in candidates}), 2)
        self.assertEqual(
            [item.document_id for item in candidates],
            [item.document_id for item in reversed_candidates],
        )

        products = [
            {
                "id": "p1",
                "source_id": "vendor",
                "name": "Blue Dream 7g",
                "variant_id": "v-7g",
                "batch_id": "B1",
                "grams": 7,
            },
            {
                "id": "p2",
                "source_id": "vendor",
                "name": "Blue Dream 14g",
                "variant_id": "v-14g",
                "batch_id": "B2",
                "grams": 14,
            },
        ]
        expected_ids = {item.product_id: item.document_id for item in candidates}

        decisions = {item.product_id: item for item in map_documents(products, candidates)}
        self.assertEqual(decisions["p1"].document_id, expected_ids["p1"])
        self.assertEqual(decisions["p2"].document_id, expected_ids["p2"])
        self.assertFalse(decisions["p1"].ambiguous)
        self.assertFalse(decisions["p2"].ambiguous)

        annotated = {item["id"]: item for item in annotate_products(products, candidates, [])}
        self.assertEqual(annotated["p1"]["lab_evidence"]["document_id"], expected_ids["p1"])
        self.assertEqual(annotated["p2"]["lab_evidence"]["document_id"], expected_ids["p2"])

    def test_exact_association_duplicates_still_collapse_after_canonicalization(self):
        association = {
            "product_id": "p1",
            "variant_id": "v-7g",
            "batch_id": "B1",
            "title": "Blue Dream 7g COA",
            "coa_url": "https://cdn.example.com/blue-dream.pdf?utm_source=first",
        }
        duplicate = {
            **association,
            "coa_url": "https://cdn.example.com/blue-dream.pdf?utm_source=duplicate",
        }

        candidates = self._discover([association, duplicate])

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].url, "https://cdn.example.com/blue-dream.pdf")
        self.assertEqual(candidates[0].product_id, "p1")
        self.assertEqual(candidates[0].variant_id, "v-7g")
        self.assertEqual(candidates[0].batch_id, "B1")


if __name__ == "__main__":
    unittest.main()
