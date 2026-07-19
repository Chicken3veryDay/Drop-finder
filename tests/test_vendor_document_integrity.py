from __future__ import annotations

import unittest

from scripts.vendor_adapters.annotate import annotate_products
from scripts.vendor_adapters.discovery import discover_json_documents
from scripts.vendor_adapters.mapping import map_documents
from scripts.vendor_adapters.models import DocumentCandidate, ParsedLabRecord


SOURCE_URL = "https://shop.example/api/products"
HOSTS = {"shop.example", "cdn.example.com", "a.example", "b.example"}
OBSERVED = "2026-07-19T00:00:00Z"


def discover(payload):
    return discover_json_documents(
        payload,
        vendor_id="example",
        source_url=SOURCE_URL,
        allowed_hosts=HOSTS,
        observed_at=OBSERVED,
    )


class NestedStructuredDiscoveryTests(unittest.TestCase):
    def test_nested_document_inherits_nearest_product_variant_and_batch(self):
        rows = discover({
            "product_id": "p1",
            "variant_id": "v7",
            "batch_id": "B1",
            "title": "Blue Dream",
            "documents": [{"type": "COA", "url": "https://cdn.example.com/a.pdf"}],
        })
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row.product_id, row.variant_id, row.batch_id), ("p1", "v7", "B1"))
        self.assertEqual(row.document_kind, "coa")
        self.assertEqual(row.title, "Blue Dream")
        self.assertEqual(row.provenance.notes, "json_path:$.documents[0].url")

    def test_document_collection_context_discovers_url_only_child(self):
        rows = discover({
            "product_id": "p1",
            "variant_id": "v7",
            "title": "Blue Dream COA",
            "documents": [{"url": "https://cdn.example.com/a.pdf"}],
        })
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].product_id, "p1")
        self.assertEqual(rows[0].variant_id, "v7")
        self.assertEqual(rows[0].document_kind, "coa")

    def test_explicit_child_identity_overrides_parent_without_sibling_leakage(self):
        rows = discover({
            "product_id": "parent",
            "variant_id": "parent-v",
            "documents": [
                {"type": "COA", "product_id": "child-a", "variant_id": "a", "url": "https://cdn.example.com/a.pdf"},
                {"type": "COA", "product_id": "child-b", "variant_id": "b", "url": "https://cdn.example.com/b.pdf"},
            ],
        })
        self.assertEqual([(row.product_id, row.variant_id) for row in rows], [("child-a", "a"), ("child-b", "b")])

    def test_generic_storefront_url_is_not_promoted_by_sibling_coa(self):
        rows = discover({
            "product_id": "p1",
            "title": "Blue Dream",
            "url": "https://shop.example/products/blue-dream",
            "coa_url": "https://cdn.example.com/blue-dream-coa.pdf",
        })
        self.assertEqual([row.url for row in rows], ["https://cdn.example.com/blue-dream-coa.pdf"])

    def test_description_cue_does_not_promote_unrelated_generic_url(self):
        rows = discover({
            "product_id": "p1",
            "title": "Blue Dream",
            "description": "A COA is available on request",
            "url": "https://shop.example/products/blue-dream",
        })
        self.assertEqual(rows, [])


class VendorScopedMappingTests(unittest.TestCase):
    def test_reused_product_ids_keep_vendor_specific_evidence(self):
        products = [
            {"id": "123", "source_id": "vendor_a", "name": "Alpha THCA Flower"},
            {"id": "123", "source_id": "vendor_b", "name": "Beta THCA Flower"},
        ]
        candidates = [
            DocumentCandidate("vendor_a", "https://a.example/alpha.pdf", "coa", product_id="123"),
            DocumentCandidate("vendor_b", "https://b.example/beta.pdf", "coa", product_id="123"),
        ]
        parsed = [
            ParsedLabRecord(candidates[0].document_id, "vendor_a", candidates[0].url, "coa", "parsed", "test", cannabinoids={"thca": 21.0}),
            ParsedLabRecord(candidates[1].document_id, "vendor_b", candidates[1].url, "coa", "parsed", "test", cannabinoids={"thca": 31.0}),
        ]
        output = annotate_products(products, candidates, parsed)
        by_vendor = {row["source_id"]: row for row in output}
        self.assertEqual(by_vendor["vendor_a"]["lab_evidence"]["source_url"], "https://a.example/alpha.pdf")
        self.assertEqual(by_vendor["vendor_a"]["lab_evidence"]["cannabinoids"]["thca"], 21.0)
        self.assertEqual(by_vendor["vendor_b"]["lab_evidence"]["source_url"], "https://b.example/beta.pdf")
        self.assertEqual(by_vendor["vendor_b"]["lab_evidence"]["cannabinoids"]["thca"], 31.0)

    def test_ordering_does_not_change_cross_vendor_associations(self):
        products = [
            {"id": "123", "source_id": "vendor_a", "name": "Alpha"},
            {"id": "123", "source_id": "vendor_b", "name": "Beta"},
        ]
        candidates = [
            DocumentCandidate("vendor_a", "https://a.example/a.pdf", "coa", product_id="123"),
            DocumentCandidate("vendor_b", "https://b.example/b.pdf", "coa", product_id="123"),
        ]
        forward = annotate_products(products, candidates, [])
        reverse = annotate_products(list(reversed(products)), list(reversed(candidates)), [])
        self.assertEqual(
            {row["source_id"]: row["lab_evidence"]["source_url"] for row in forward},
            {row["source_id"]: row["lab_evidence"]["source_url"] for row in reverse},
        )


class IndependentEvidenceRoleTests(unittest.TestCase):
    def setUp(self):
        self.product = {"id": "p1", "source_id": "example", "name": "Blue Dream"}

    def test_exact_coa_and_terpene_reports_both_survive(self):
        candidates = [
            DocumentCandidate("example", "https://cdn.example.com/coa.pdf", "coa", product_id="p1"),
            DocumentCandidate("example", "https://cdn.example.com/terpenes.pdf", "terpene_report", product_id="p1"),
        ]
        decisions = map_documents([self.product], candidates)
        self.assertEqual([row.document_kind for row in decisions], ["coa", "terpene_report"])
        self.assertTrue(all(not row.ambiguous for row in decisions))
        annotated = annotate_products([self.product], candidates, [])[0]
        self.assertEqual(
            [row["document_kind"] for row in annotated["lab_evidence_records"]],
            ["coa", "terpene_report"],
        )
        self.assertEqual(annotated["lab_evidence"]["document_kind"], "coa")

    def test_ambiguous_coas_do_not_suppress_unique_terpene_report(self):
        candidates = [
            DocumentCandidate("example", "https://cdn.example.com/coa-a.pdf", "coa", product_id="p1"),
            DocumentCandidate("example", "https://cdn.example.com/coa-b.pdf", "coa", product_id="p1"),
            DocumentCandidate("example", "https://cdn.example.com/terpenes.pdf", "terpene_report", product_id="p1"),
        ]
        decisions = map_documents([self.product], candidates)
        by_kind = {row.document_kind: row for row in decisions}
        self.assertTrue(by_kind["coa"].ambiguous)
        self.assertFalse(by_kind["terpene_report"].ambiguous)
        annotated = annotate_products([self.product], candidates, [])[0]
        self.assertEqual([row["document_kind"] for row in annotated["lab_evidence_records"]], ["terpene_report"])
        self.assertEqual([row["document_kind"] for row in annotated["lab_evidence_ambiguities"]], ["coa"])


if __name__ == "__main__":
    unittest.main()
