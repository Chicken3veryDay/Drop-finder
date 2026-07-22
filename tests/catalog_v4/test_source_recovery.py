from __future__ import annotations

import copy
import unittest

from scripts import route_repair, source_recovery


class PriceCore:
    @staticmethod
    def num(value):
        try:
            parsed = float(str(value).replace("$", "").replace(",", "").strip())
        except (TypeError, ValueError):
            return None
        return parsed if 0 < parsed < 100000 else None


class RouteCore:
    def __init__(self):
        self.SOURCES = [
            (
                "bay_smokes",
                "Bay Smokes",
                [("html", "https://baysmokes.com/collections/thca-flower", "thca_flower")],
            ),
            (
                "wnc_cbd",
                "WNC CBD",
                [("html", "https://wnc-cbd.com/thca-flower/", "thca_flower")],
            ),
        ]


class RouteWorker:
    def __init__(self):
        self.core = RouteCore()
        self.FALLBACK_HTML_ROUTES = {}
        self.PRODUCT_PATHS = ("/product/", "/products/")


class SitemapCore:
    def __init__(self):
        self.responses = {
            "https://wnc-cbd.com/product-sitemap.xml": (
                """
                <urlset>
                  <url><loc>https://wnc-cbd.com/products/thca-blue-dream-flower.html</loc></url>
                  <url><loc>https://other.example/products/thca-external-flower.html</loc></url>
                  <url><loc>https://wnc-cbd.com/blog/thca-flower-guide</loc></url>
                </urlset>
                """,
                "application/xml",
                200,
            ),
            "https://wnc-cbd.com/products/thca-blue-dream-flower.html": (
                "<html><div class='price'>Now: $34.99 - $194.99</div></html>",
                "text/html",
                200,
            ),
        }

    def fetch(self, target):
        return self.responses[target]

    @staticmethod
    def html_detail(_payload, source_id, vendor, _route, target):
        return [{
            "source_id": source_id,
            "vendor": vendor,
            "name": "Blue Dream THCA Flower",
            "url": target,
            "variant": "",
            "price": 34.99,
            "primary_type": "cannabis_flower",
            "classification_evidence": {
                "primary_type": "cannabis_flower",
                "evidence_source": "product_detail_metadata",
            },
        }]

    @staticmethod
    def dedupe(rows):
        by_url = {row["url"]: row for row in rows}
        return list(by_url.values())


class SitemapWorker:
    def __init__(self):
        self.core = SitemapCore()

    @staticmethod
    def path_text(target):
        return target.replace("-", " ").replace("_", " ")

    @staticmethod
    def has_product_evidence(value):
        value = str(value).casefold()
        return "thca" in value and "flower" in value


class SourceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self._routes = copy.deepcopy(route_repair.ROUTE_REPAIRS)
        self._fallbacks = copy.deepcopy(route_repair.FALLBACK_REPAIRS)

    def tearDown(self):
        route_repair.ROUTE_REPAIRS.clear()
        route_repair.ROUTE_REPAIRS.update(self._routes)
        route_repair.FALLBACK_REPAIRS.clear()
        route_repair.FALLBACK_REPAIRS.update(self._fallbacks)

    def test_strict_gate_discards_only_rows_the_existing_gate_rejects(self):
        products = [
            {
                "url": "https://example.test/products/valid",
                "primary_type": "cannabis_flower",
                "classification_evidence": {
                    "primary_type": "cannabis_flower",
                    "evidence_source": "product_detail_metadata",
                },
            },
            {
                "url": "https://example.test/products/mismatch",
                "primary_type": "cannabis_vape",
                "classification_evidence": {
                    "primary_type": "cannabis_flower",
                    "evidence_source": "storefront_record",
                },
            },
            {
                "url": "https://example.test/products/card-only",
                "primary_type": "cannabis_flower",
                "classification_evidence": {
                    "primary_type": "cannabis_flower",
                    "evidence_source": "product_card_title_or_url",
                },
            },
        ]

        def original_gate(rows):
            self.assertEqual(len(rows), 1)
            return True, [], {"products": len(rows)}

        admitted, reasons, quality = source_recovery.filter_for_strict_gate(original_gate, products)
        self.assertTrue(admitted)
        self.assertEqual(reasons, [])
        self.assertEqual(len(products), 1)
        self.assertEqual(quality["admission_rejections"], 2)
        self.assertEqual(quality["admission_rejection_reasons"], {
            "classification_type_mismatch": 1,
            "unverified_listing_card_evidence": 1,
        })

    def test_product_detail_price_recovery_is_bounded_to_price_markup(self):
        woo = """
        <div class="summary entry-summary">
          <p class="price"><span class="woocommerce-Price-amount amount"><bdi>$29.99</bdi></span></p>
        </div>
        """
        wnc = """
        <div class="price-section price-section--withoutTax">
          <span class="price price--withoutTax">Now: $34.99 - $194.99</span>
        </div>
        """
        unrelated = "<p>Free shipping over $50.00</p>"
        self.assertEqual(source_recovery.extract_first_party_price(PriceCore, woo), 29.99)
        self.assertEqual(source_recovery.extract_first_party_price(PriceCore, wnc), 34.99)
        self.assertIsNone(source_recovery.extract_first_party_price(PriceCore, unrelated))

    def test_json_price_minor_units_are_normalized_only_with_framework_evidence(self):
        woo_minor = '<script>{"currency_minor_unit":2,"price":"2900"}</script>'
        shopify_theme = '<script>Shopify.theme={};{"price":3750,"price_min":3750}</script>'
        ordinary_dollars = '<script>{"price":1600}</script>'
        explicit_decimal = '<script>{"price":"37.50"}</script>'
        self.assertEqual(source_recovery.extract_first_party_price(PriceCore, woo_minor), 29.0)
        self.assertEqual(source_recovery.extract_first_party_price(PriceCore, shopify_theme), 37.5)
        self.assertEqual(source_recovery.extract_first_party_price(PriceCore, ordinary_dollars), 1600.0)
        self.assertEqual(source_recovery.extract_first_party_price(PriceCore, explicit_decimal), 37.5)

    def test_route_overrides_remove_known_dead_paths(self):
        worker = RouteWorker()
        source_recovery.apply_route_overrides(worker)
        routes = {source_id: values for source_id, _vendor, values in worker.core.SOURCES}
        self.assertFalse(any(
            route[0] == "html" and "collections/thca-flower" in route[1]
            for route in routes["bay_smokes"]
        ))
        self.assertEqual(source_recovery.ROUTE_OVERRIDES["beleafer"][0][1], "https://beleafer.com/product-category/hemp-flower/")
        self.assertEqual(source_recovery.ROUTE_OVERRIDES["five_leaf_wellness"][0][1], "https://fiveleafwellness.com/product-category/top-shelf/")
        self.assertEqual(source_recovery.ROUTE_OVERRIDES["veteran_grown_hemp"][0][1], "https://www.veterangrownhemp.com/flower")
        self.assertEqual(source_recovery.ROUTE_OVERRIDES["wnc_cbd"][0][2], "sitemap")
        self.assertTrue(all("products.json" not in route[1] for route in source_recovery.ROUTE_OVERRIDES["snapdragon_hemp"]))
        self.assertIn("/product-page/", worker.PRODUCT_PATHS)

    def test_same_host_sitemap_discovers_current_product_details(self):
        worker = SitemapWorker()
        diagnostics = {}
        index = """
        <sitemapindex>
          <sitemap><loc>https://wnc-cbd.com/product-sitemap.xml</loc></sitemap>
          <sitemap><loc>https://other.example/external-sitemap.xml</loc></sitemap>
        </sitemapindex>
        """
        rows = source_recovery.sitemap_products(
            worker,
            index,
            "wnc_cbd",
            "WNC CBD",
            ("html", "https://wnc-cbd.com/xmlsitemap.php", "sitemap"),
            diagnostics,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["price"], 34.99)
        self.assertEqual(rows[0]["discovery_method"], "xml_sitemap_product_detail")
        self.assertEqual(diagnostics["sitemap_documents"], 2)
        self.assertEqual(diagnostics["sitemap_product_candidates"], 1)
        self.assertEqual(diagnostics["detail_failures"], 0)


if __name__ == "__main__":
    unittest.main()
