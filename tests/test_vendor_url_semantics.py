from __future__ import annotations

import json
import unittest

from scripts.vendor_adapters.discovery import discover_html_documents, discover_json_documents
from scripts.vendor_adapters.urls import canonicalize_url


class SemanticQueryParameterTests(unittest.TestCase):
    def test_generic_selectors_remain_distinct_and_sorted(self):
        expected = {
            "ref": (
                "https://lab.example/report?a=1&ref=batch-A&ref=batch-B",
                "https://lab.example/report?a=1&ref=batch-C",
            ),
            "source": (
                "https://lab.example/report?a=1&source=coa-123&source=coa-456",
                "https://lab.example/report?a=1&source=coa-789",
            ),
            "referrer": (
                "https://lab.example/report?a=1&referrer=product-A&referrer=product-B",
                "https://lab.example/report?a=1&referrer=product-C",
            ),
        }
        for key, (first_expected, second_expected) in expected.items():
            with self.subTest(key=key):
                first = canonicalize_url(
                    f"https://lab.example/report?{key}=batch-B&a=1&{key}=batch-A"
                    if key == "ref"
                    else f"https://lab.example/report?{key}=coa-456&a=1&{key}=coa-123"
                    if key == "source"
                    else f"https://lab.example/report?{key}=product-B&a=1&{key}=product-A",
                    allowed_hosts={"lab.example"},
                )
                second = canonicalize_url(
                    f"https://lab.example/report?a=1&{key}="
                    + ("batch-C" if key == "ref" else "coa-789" if key == "source" else "product-C"),
                    allowed_hosts={"lab.example"},
                )
                self.assertEqual(first, first_expected)
                self.assertEqual(second, second_expected)
                self.assertNotEqual(first, second)

    def test_campaign_parameters_are_still_removed(self):
        value = canonicalize_url(
            "https://lab.example/report?ref=batch-A&utm_source=email&gclid=abc&mc_cid=def&source=coa-1",
            allowed_hosts={"lab.example"},
        )
        self.assertEqual(value, "https://lab.example/report?ref=batch-A&source=coa-1")

    def test_html_discovery_preserves_semantic_selectors_but_deduplicates_campaign_variants(self):
        html = """
        <a href="/report.pdf?ref=batch-A&utm_source=email">Blue Dream COA batch 2024A</a>
        <a href="/report.pdf?ref=batch-A&utm_source=social">Blue Dream COA batch 2024A</a>
        <a href="/report.pdf?ref=batch-B">Northern Lights COA batch 2024B</a>
        """
        rows = discover_html_documents(
            html,
            vendor_id="vendor",
            page_url="https://lab.example/products",
            allowed_hosts={"lab.example"},
            observed_at="2026-07-18T00:00:00Z",
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {row.url for row in rows},
            {
                "https://lab.example/report.pdf?ref=batch-A",
                "https://lab.example/report.pdf?ref=batch-B",
            },
        )

    def test_json_discovery_preserves_distinct_source_selectors(self):
        payload = json.dumps([
            {"title": "Blue Dream COA", "coa_url": "/report?source=coa-123&utm_medium=api"},
            {"title": "Northern Lights COA", "coa_url": "/report?source=coa-456&utm_medium=api"},
        ])
        rows = discover_json_documents(
            payload,
            vendor_id="vendor",
            source_url="https://lab.example/api/products",
            allowed_hosts={"lab.example"},
            observed_at="2026-07-18T00:00:00Z",
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {row.url for row in rows},
            {
                "https://lab.example/report?source=coa-123",
                "https://lab.example/report?source=coa-456",
            },
        )


if __name__ == "__main__":
    unittest.main()
