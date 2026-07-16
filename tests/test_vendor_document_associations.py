from __future__ import annotations

import unittest

from scripts.vendor_adapters.discovery import discover_json_documents
from scripts.vendor_adapters.mapping import map_documents


class SharedDocumentAssociationTests(unittest.TestCase):
    def discover(self, payload):
        return discover_json_documents(
            payload,
            vendor_id="v",
            source_url="https://shop.example/api/products",
            allowed_hosts={"shop.example", "cdn.example.com"},
            observed_at="2026-07-16T00:00:00Z",
        )

    def test_shared_url_preserves_distinct_product_variant_batch_edges(self):
        payload = [
            {
                "product_id": "p1",
                "variant_id": "v-7g",
                "batch_id": "B1",
                "title": "Blue Dream COA",
                "coa_url": "https://cdn.example.com/blue-dream.pdf",
            },
            {
                "product_id": "p2",
                "variant_id": "v-14g",
                "batch_id": "B2",
                "title": "Blue Dream COA",
                "coa_url": "https://cdn.example.com/blue-dream.pdf",
            },
        ]

        rows = self.discover(payload)

        self.assertEqual(
            {(row.product_id, row.variant_id, row.batch_id) for row in rows},
            {("p1", "v-7g", "B1"), ("p2", "v-14g", "B2")},
        )
        decisions = map_documents(
            [
                {"id": "p1", "source_id": "v", "name": "Blue Dream", "variant_id": "v-7g", "batch_id": "B1"},
                {"id": "p2", "source_id": "v", "name": "Blue Dream", "variant_id": "v-14g", "batch_id": "B2"},
            ],
            rows,
        )
        self.assertEqual({decision.product_id for decision in decisions}, {"p1", "p2"})
        self.assertTrue(all(not decision.ambiguous for decision in decisions))

    def test_true_duplicate_association_remains_deduplicated_after_canonicalization(self):
        payload = [
            {
                "product_id": "p1",
                "variant_id": "v-7g",
                "batch_id": "B1",
                "title": "Blue Dream COA",
                "coa_url": "https://cdn.example.com/blue-dream.pdf?utm_source=first",
            },
            {
                "product_id": "p1",
                "variant_id": "v-7g",
                "batch_id": "B1",
                "title": "Blue Dream COA",
                "coa_url": "https://cdn.example.com/blue-dream.pdf?utm_source=second",
            },
        ]

        rows = self.discover(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].url, "https://cdn.example.com/blue-dream.pdf")


if __name__ == "__main__":
    unittest.main()
