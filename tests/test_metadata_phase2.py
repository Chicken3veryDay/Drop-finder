from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from scripts import cloud_scan, product_detail_reliability
from scripts.catalog_v4 import build_catalog


ROUTE = ("html", "https://example.test/products/example-flower", "product_detail")


class MetadataPhaseTwoTests(unittest.TestCase):
    def test_product_detail_extracts_target_scoped_potency_rating_lineage_environment_and_coa(self) -> None:
        payload = """
        <html><head>
          <meta property="og:title" content="Cap Junkie THCA Flower 28g">
          <meta property="product:price:amount" content="90">
          <meta property="product:availability" content="instock">
        </head><body>
          <section id="product-cap-junkie-thca-flower">
            <h1>Cap Junkie THCA Flower</h1>
            <p>Strain Type: Hybrid</p>
            <p>Grow Method: Indoor</p>
            <p>THCA Content: 28.81%</p>
            <div data-average-rating="4.8" data-review-count="73"></div>
            <a href="https://cdn.example.test/labs/cap-junkie-coa.pdf">COA Download</a>
          </section>
        </body></html>
        """
        rows = cloud_scan.html_detail(
            payload,
            "fixture",
            "Fixture",
            ROUTE,
            "https://example.test/products/cap-junkie-thca-flower",
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["thca"], 28.81)
        self.assertEqual(row["rating"], 4.8)
        self.assertEqual(row["review_count"], 73)
        self.assertEqual(row["strain_type"], "Hybrid")
        self.assertEqual(row["grow_environment"], "Indoor")
        self.assertEqual(len(row["documents"]), 1)
        self.assertEqual(row["documents"][0]["kind"], "coa")
        self.assertEqual(row["documents"][0]["scope"], "product")

    def test_description_effects_are_conservative_and_negation_aware(self) -> None:
        row = cloud_scan.record(
            "fixture",
            "Fixture",
            ROUTE,
            "Clementine THCA Flower 3.5g",
            "https://example.test/products/clementine",
            (
                "Effects of Clementine include uplifting energy, creativity, focus, and gentle physical relaxation. "
                "It is clear-headed without sedation."
            ),
            35,
            "in stock",
        )
        result = build_catalog([row], generated_at="2026-07-23T00:00:00Z", detail_shards=1)
        detail = json.loads(result.files["catalog-v4/details/000.json"])["products"][0]
        self.assertIn("Uplifted", detail["effects"])
        self.assertIn("Energetic", detail["effects"])
        self.assertIn("Creative", detail["effects"])
        self.assertIn("Focused", detail["effects"])
        self.assertIn("Relaxed", detail["effects"])
        self.assertNotIn("Sedating", detail["effects"])
        self.assertEqual(detail["effects_provenance"]["source"], "conservative_text")

    def test_plain_jane_listing_card_maps_lineage_and_thca_by_product_url(self) -> None:
        payload = """
        <product-card>
          <a href="/products/orange-cookies">Orange Cookies</a>
          <span aria-label="Strain family: Sativa">Sativa</span>
          <span aria-label="Batch-reported THCA: 31.2 percent">THCA 31.2%</span>
          <span class="product-card__rating-badge-value">4.7</span>
        </product-card>
        """
        worker = SimpleNamespace(core=cloud_scan)
        metadata = product_detail_reliability._listing_metadata_from_html(
            worker,
            payload,
            "https://plainjane.com/",
        )
        record = metadata["https://plainjane.com/products/orange-cookies"]
        self.assertEqual(record["strain_type"].lower(), "sativa")
        self.assertEqual(record["thca"], 31.2)
        self.assertNotIn("rating", record, "a score without a review count must not publish")

    def test_gold_canna_listing_card_maps_badges(self) -> None:
        payload = """
        <div class="bs-card">
          <a href="/products/cap-junkie-thca-bulk-flower-exotic-indoor" class="bs-title">Cap Junkie</a>
          <span class="bs-badge-strain strain-bg-hybrid">HYBRID</span>
          <span class="bs-badge-thc">THCA 28.81%</span>
        </div>
        """
        worker = SimpleNamespace(core=cloud_scan)
        metadata = product_detail_reliability._listing_metadata_from_html(
            worker,
            payload,
            "https://goldcanna.com/collections/thca-bulk",
        )
        record = metadata["https://goldcanna.com/products/cap-junkie-thca-bulk-flower-exotic-indoor"]
        self.assertEqual(record["strain_type"].lower(), "hybrid")
        self.assertEqual(record["thca"], 28.81)

    def test_detail_merge_preserves_existing_fields_and_adds_documents(self) -> None:
        product = {
            "source_id": "fixture",
            "url": "https://example.test/products/flower?variant=1",
            "rating": 4.9,
            "review_count": 10,
            "documents": [],
        }
        detail = {
            "rating": 4.0,
            "review_count": 100,
            "thca": 25.5,
            "strain_type": "hybrid",
            "documents": [{"url": "https://example.test/coa.pdf", "kind": "coa", "scope": "product"}],
        }
        merged, changed = product_detail_reliability._merge_detail_metadata(
            product,
            detail,
            "https://example.test/products/flower",
        )
        self.assertEqual((merged["rating"], merged["review_count"]), (4.9, 10))
        self.assertEqual(merged["thca"], 25.5)
        self.assertEqual(merged["strain_type"], "hybrid")
        self.assertEqual(len(merged["documents"]), 1)
        self.assertGreaterEqual(changed, 3)


if __name__ == "__main__":
    unittest.main()
