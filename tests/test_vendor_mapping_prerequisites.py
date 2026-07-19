from __future__ import annotations

import unittest

from scripts.vendor_adapters.annotate import annotate_products
from scripts.vendor_adapters.mapping import map_documents, score_candidate
from scripts.vendor_adapters.models import DocumentCandidate


class MappingPrerequisiteTests(unittest.TestCase):
    def setUp(self):
        self.products = [
            {"id": "blue", "source_id": "example", "name": "Blue Dream 7g", "grams": 7},
            {"id": "purple", "source_id": "example", "name": "Purple Haze 7g", "grams": 7},
            {"id": "orange", "source_id": "example", "name": "Orange Cookies 14g", "grams": 14},
        ]

    def test_weight_only_report_remains_unlinked(self):
        candidate = DocumentCandidate(
            vendor_id="example",
            url="https://cdn.example.com/unscoped-7g-report.pdf",
            document_kind="coa",
            weight_grams=7,
        )
        for product in self.products[:2]:
            decision = score_candidate(product, candidate)
            self.assertEqual(decision.scope, "unmatched")
            self.assertEqual(decision.reasons, ("product identity insufficient",))
        self.assertEqual(map_documents(self.products, [candidate]), [])
        annotated = annotate_products(self.products, [candidate], [])
        self.assertTrue(all(row["lab_evidence"]["mapping_scope"] == "unmatched" for row in annotated))

    def test_product_id_allows_weight_to_refine_the_scope(self):
        candidate = DocumentCandidate(
            vendor_id="example",
            url="https://cdn.example.com/blue-7g-report.pdf",
            document_kind="coa",
            product_id="blue",
            weight_grams=7,
        )
        decision = score_candidate(self.products[0], candidate)
        self.assertEqual(decision.scope, "weight")
        self.assertIn("exact product id", decision.reasons)
        self.assertIn("exact normalized weight", decision.reasons)
        selected = map_documents(self.products, [candidate])
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].product_id, "blue")

    def test_batch_and_variant_without_product_identity_are_also_unlinked(self):
        product = {
            "id": "blue",
            "source_id": "example",
            "name": "Blue Dream",
            "variant_id": "v7",
            "batch_id": "B1",
            "grams": 7,
        }
        for candidate in (
            DocumentCandidate("example", "https://cdn.example.com/batch.pdf", "coa", batch_id="B1"),
            DocumentCandidate("example", "https://cdn.example.com/variant.pdf", "coa", variant_id="v7"),
            DocumentCandidate("example", "https://cdn.example.com/combined.pdf", "coa", variant_id="v7", batch_id="B1", weight_grams=7),
        ):
            with self.subTest(candidate=candidate.url):
                decision = score_candidate(product, candidate)
                self.assertEqual(decision.scope, "unmatched")
                self.assertEqual(decision.reasons, ("product identity insufficient",))

    def test_normalized_product_name_can_establish_then_refine(self):
        candidate = DocumentCandidate(
            vendor_id="example",
            url="https://cdn.example.com/blue-name.pdf",
            document_kind="coa",
            title="Blue Dream",
            weight_grams=7,
        )
        product = {"id": "blue", "source_id": "example", "name": "Blue Dream", "grams": 7}
        decision = score_candidate(product, candidate)
        self.assertEqual(decision.scope, "weight")
        self.assertIn("normalized product-name match", decision.reasons)


if __name__ == "__main__":
    unittest.main()
