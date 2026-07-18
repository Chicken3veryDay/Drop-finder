from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from scripts.vendor_adapters.discovery import discover_html_documents, discover_json_documents
from scripts.vendor_adapters.fetch import fetch_public_document
from scripts.vendor_adapters.urls import UnsafeUrl, canonicalize_url


class MalformedPortBoundaryTests(unittest.TestCase):
    def test_canonicalization_normalizes_lazy_port_errors(self):
        for value in (
            "https://cdn.example.com:notaport/report.pdf",
            "https://cdn.example.com:99999/report.pdf",
        ):
            with self.subTest(value=value), self.assertRaisesRegex(UnsafeUrl, "malformed URL"):
                canonicalize_url(value, allowed_hosts={"cdn.example.com"})

    def test_valid_default_and_explicit_ports_remain_supported(self):
        self.assertEqual(
            canonicalize_url("https://cdn.example.com:443/report.pdf", allowed_hosts={"cdn.example.com"}),
            "https://cdn.example.com/report.pdf",
        )
        self.assertEqual(
            canonicalize_url("https://cdn.example.com:8443/report.pdf", allowed_hosts={"cdn.example.com"}),
            "https://cdn.example.com:8443/report.pdf",
        )

    def test_json_discovery_skips_bad_port_and_keeps_later_candidate(self):
        payload = json.dumps([
            {"title": "Bad COA", "coa_url": "https://cdn.example.com:notaport/bad.pdf"},
            {"title": "Good COA", "coa_url": "https://cdn.example.com/good.pdf"},
        ])
        rows = discover_json_documents(
            payload,
            vendor_id="vendor",
            source_url="https://shop.example/api/products",
            allowed_hosts={"shop.example", "cdn.example.com"},
            observed_at="2026-07-17T00:00:00Z",
        )
        self.assertEqual([row.url for row in rows], ["https://cdn.example.com/good.pdf"])

    def test_html_discovery_skips_bad_port_and_keeps_later_candidate(self):
        html = (
            '<a href="https://cdn.example.com:notaport/bad.pdf">Bad COA</a>'
            '<a href="https://cdn.example.com/good.pdf">Good COA</a>'
        )
        rows = discover_html_documents(
            html,
            vendor_id="vendor",
            page_url="https://shop.example/products/item",
            allowed_hosts={"shop.example", "cdn.example.com"},
            observed_at="2026-07-17T00:00:00Z",
        )
        self.assertEqual([row.url for row in rows], ["https://cdn.example.com/good.pdf"])

    def test_fetch_returns_bounded_error_without_building_opener(self):
        with patch("scripts.vendor_adapters.fetch.urllib.request.build_opener") as build_opener:
            result = fetch_public_document(
                "https://cdn.example.com:notaport/report.pdf",
                allowed_hosts={"cdn.example.com"},
            )
        build_opener.assert_not_called()
        self.assertEqual(result.requested_url, "")
        self.assertEqual(result.final_url, "")
        self.assertEqual(result.status, 0)
        self.assertEqual(result.body, b"")
        self.assertEqual(result.error, "UnsafeUrl: malformed URL")


if __name__ == "__main__":
    unittest.main()
