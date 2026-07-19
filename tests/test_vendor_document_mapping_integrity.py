from __future__ import annotations

import unittest

from scripts.vendor_adapters.annotate import annotate_products
from scripts.vendor_adapters.discovery import discover_html_documents, discover_json_documents
from scripts.vendor_adapters.mapping import map_documents
from scripts.vendor_adapters.models import DocumentCandidate, ParsedLabRecord


class StructuredDiscoveryIntegrityTests(unittest.TestCase):
    def discover(self, payload):
        return discover_json_documents(
            payload,
            vendor_id="example",
            source_url="https://shop.example/api/products",
            allowed_hosts={"shop.example", "cdn.example.com"},
            observed_at="2026-07-19T00:00:00Z",
        )

    def test_nested_document_inherits_nearest_product_variant_batch_and_kind_context(self) -> None:
        rows = self.discover({
            "product_id": "p1",
            "variant_id": "v7",
            "batch_id": "B1",
            "title": "Blue Dream",
            "documents": [
                {"type": "COA", "url": "https://cdn.example.com/a.pdf"},
                {"variant_id": "v14", "batch_id": "B2", "url": "https://cdn.example.com/b.pdf"},
            ],
        })

        self.assertEqual(len(rows), 2)
        by_url = {row.url: row for row in rows}
        first = by_url["https://cdn.example.com/a.pdf"]
        self.assertEqual((first.product_id, first.variant_id, first.batch_id), ("p1", "v7", "B1"))
        self.assertEqual(first.document_kind, "coa")
        self.assertEqual(first.source_path, "$.documents[0].url")
        second = by_url["https://cdn.example.com/b.pdf"]
        self.assertEqual((second.product_id, second.variant_id, second.batch_id), ("p1", "v14", "B2"))
        self.assertEqual(second.source_path, "$.documents[1].url")

    def test_nested_siblings_do_not_leak_identity_and_unrelated_urls_remain_excluded(self) -> None:
        rows = self.discover({
            "products": [
                {
                    "product_id": "p1",
                    "variant_id": "v1",
                    "title": "Alpha",
                    "documents": [{"type": "COA", "url": "https://cdn.example.com/alpha.pdf"}],
                },
                {
                    "product_id": "p2",
                    "variant_id": "v2",
                    "title": "Beta",
                    "image": {"url": "https://cdn.example.com/beta.jpg"},
                    "links": [{"url": "https://shop.example/products/beta"}],
                },
            ],
        })
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0].product_id, rows[0].variant_id), ("p1", "v1"))

    def test_storefront_url_does_not_compete_with_explicit_coa_url(self) -> None:
        rows = self.discover({
            "product_id": "p1",
            "title": "Blue Dream",
            "url": "https://shop.example/products/blue-dream",
            "image_url": "https://cdn.example.com/blue-dream.jpg",
            "api_url": "https://shop.example/api/products/p1",
            "coa_url": "https://cdn.example.com/blue-dream-coa.pdf",
        })
        self.assertEqual([(row.document_kind, row.url) for row in rows], [
            ("coa", "https://cdn.example.com/blue-dream-coa.pdf"),
        ])
        decisions = map_documents(
            [{"id": "p1", "source_id": "example", "name": "Blue Dream"}],
            rows,
        )
        self.assertEqual(len(decisions), 1)
        self.assertFalse(decisions[0].ambiguous)

    def test_html_discovery_recovers_sparse_anchor_identity_from_filename(self) -> None:
        rows = discover_html_documents(
            '<a href="https://cdn.example.com/Stuffed_Cherry_Potency_1600x.webp"></a>',
            vendor_id="example",
            page_url="https://shop.example/pages/coas",
            allowed_hosts={"cdn.example.com", "shop.example"},
            observed_at="2026-07-19T00:00:00Z",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].title, "Stuffed Cherry Potency")
        self.assertEqual(rows[0].document_kind, "coa")
        self.assertEqual(rows[0].source_path, "html_anchor:1")


class MappingAndAnnotationIntegrityTests(unittest.TestCase):
    def parsed(self, candidate: DocumentCandidate, thca: float) -> ParsedLabRecord:
        return ParsedLabRecord(
            document_id=candidate.document_id,
            vendor_id=candidate.vendor_id,
            source_url=candidate.url,
            document_kind=candidate.document_kind,
            parse_status="parsed",
            parser_id="fixture",
            cannabinoids={"thca": thca},
        )

    def test_reused_product_ids_remain_vendor_scoped(self) -> None:
        products = [
            {"id": "123", "source_id": "vendor_a", "name": "Alpha THCA Flower"},
            {"id": "123", "source_id": "vendor_b", "name": "Beta THCA Flower"},
        ]
        candidates = [
            DocumentCandidate("vendor_a", "https://a.example/alpha.pdf", "coa", product_id="123"),
            DocumentCandidate("vendor_b", "https://b.example/beta.pdf", "coa", product_id="123"),
        ]
        records = [self.parsed(candidates[0], 21.0), self.parsed(candidates[1], 31.0)]

        for product_order in (products, list(reversed(products))):
            annotated = annotate_products(product_order, list(reversed(candidates)), list(reversed(records)))
            by_vendor = {row["source_id"]: row for row in annotated}
            self.assertEqual(by_vendor["vendor_a"]["lab_evidence"]["source_url"], candidates[0].url)
            self.assertEqual(by_vendor["vendor_a"]["lab_evidence"]["cannabinoids"]["thca"], 21.0)
            self.assertEqual(by_vendor["vendor_b"]["lab_evidence"]["source_url"], candidates[1].url)
            self.assertEqual(by_vendor["vendor_b"]["lab_evidence"]["cannabinoids"]["thca"], 31.0)

    def test_same_vendor_duplicate_product_ids_remain_variant_scoped(self) -> None:
        products = [
            {"id": "123", "source_id": "vendor_a", "variant_id": "v7", "variant": "7g", "grams": 7, "name": "Alpha 7g"},
            {"id": "123", "source_id": "vendor_a", "variant_id": "v14", "variant": "14g", "grams": 14, "name": "Alpha 14g"},
        ]
        candidates = [
            DocumentCandidate("vendor_a", "https://a.example/7g.pdf", "coa", product_id="123", variant_id="v7", weight_grams=7),
            DocumentCandidate("vendor_a", "https://a.example/14g.pdf", "coa", product_id="123", variant_id="v14", weight_grams=14),
        ]
        annotated = annotate_products(products, candidates, [])
        by_variant = {row["variant_id"]: row for row in annotated}
        self.assertEqual(by_variant["v7"]["lab_evidence"]["source_url"], candidates[0].url)
        self.assertEqual(by_variant["v14"]["lab_evidence"]["source_url"], candidates[1].url)

    def test_coa_and_terpene_reports_survive_independently(self) -> None:
        product = {"id": "p1", "source_id": "example", "name": "Blue Dream"}
        candidates = [
            DocumentCandidate("example", "https://cdn.example.com/blue-coa.pdf", "coa", product_id="p1"),
            DocumentCandidate("example", "https://cdn.example.com/blue-terpenes.pdf", "terpene_report", product_id="p1"),
        ]
        records = [self.parsed(candidates[0], 27.0), self.parsed(candidates[1], 0.0)]
        decisions = map_documents([product], candidates)
        self.assertEqual({row.document_kind for row in decisions}, {"coa", "terpene_report"})
        self.assertTrue(all(not row.ambiguous for row in decisions))

        annotated = annotate_products([product], candidates, records)[0]
        self.assertEqual({row["document_kind"] for row in annotated["lab_documents"]}, {"coa", "terpene_report"})
        self.assertEqual({row["kind"] for row in annotated["documents"]}, {"coa", "terpene"})
        self.assertEqual(annotated["lab_evidence"]["document_kind"], "coa")

    def test_ambiguity_is_isolated_within_each_document_kind(self) -> None:
        product = {"id": "p1", "source_id": "example", "name": "Blue Dream"}
        candidates = [
            DocumentCandidate("example", "https://cdn.example.com/a-coa.pdf", "coa", product_id="p1"),
            DocumentCandidate("example", "https://cdn.example.com/b-coa.pdf", "coa", product_id="p1"),
            DocumentCandidate("example", "https://cdn.example.com/terpenes.pdf", "terpene_report", product_id="p1"),
        ]
        annotated = annotate_products([product], candidates, [self.parsed(candidates[2], 0.0)])[0]
        self.assertEqual([row["document_kind"] for row in annotated["lab_documents"]], ["terpene_report"])
        self.assertEqual(annotated["lab_mapping_diagnostics"], [{
            "document_kind": "coa",
            "mapping_scope": "product",
            "mapping_score": 85,
            "reason": "ambiguous_equal_score",
        }])


if __name__ == "__main__":
    unittest.main()
