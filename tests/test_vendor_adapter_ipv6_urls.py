from __future__ import annotations

from unittest import mock
import unittest

from scripts.vendor_adapters.discovery import discover_html_documents
from scripts.vendor_adapters.fetch import fetch_public_document
from scripts.vendor_adapters.urls import UnsafeUrl, canonicalize_url


GLOBAL_IPV6 = "2606:4700:4700::1111"
SECOND_GLOBAL_IPV6 = "2001:4860:4860::8888"


class IPv6UrlCanonicalizationTests(unittest.TestCase):
    def test_preserves_bracketed_global_ipv6_authority(self) -> None:
        value = canonicalize_url(
            f"https://[{GLOBAL_IPV6}]/reports/coa.pdf",
            allowed_hosts={GLOBAL_IPV6},
        )
        self.assertEqual(value, f"https://[{GLOBAL_IPV6}]/reports/coa.pdf")

    def test_omits_default_port_without_removing_ipv6_brackets(self) -> None:
        value = canonicalize_url(
            f"https://[{GLOBAL_IPV6}]:443/reports/coa.pdf",
            allowed_hosts={f"[{GLOBAL_IPV6}]"},
        )
        self.assertEqual(value, f"https://[{GLOBAL_IPV6}]/reports/coa.pdf")

    def test_preserves_non_default_ipv6_port(self) -> None:
        value = canonicalize_url(
            f"https://[{SECOND_GLOBAL_IPV6}]:8443/reports/coa.pdf",
            allowed_hosts={SECOND_GLOBAL_IPV6},
        )
        self.assertEqual(
            value,
            f"https://[{SECOND_GLOBAL_IPV6}]:8443/reports/coa.pdf",
        )

    def test_ipv4_and_dns_authorities_are_unchanged(self) -> None:
        self.assertEqual(
            canonicalize_url("https://example.com:443/report.pdf"),
            "https://example.com/report.pdf",
        )
        self.assertEqual(
            canonicalize_url("https://8.8.8.8:8443/report.pdf"),
            "https://8.8.8.8:8443/report.pdf",
        )

    def test_rejects_non_global_ipv6_literals(self) -> None:
        for host in ("::1", "fe80::1", "fd00::1"):
            with self.subTest(host=host), self.assertRaises(UnsafeUrl):
                canonicalize_url(f"https://[{host}]/report.pdf")

    def test_html_discovery_preserves_ipv6_candidate(self) -> None:
        rows = discover_html_documents(
            f'<a href="https://[{GLOBAL_IPV6}]/reports/coa.pdf">COA report</a>',
            vendor_id="ipv6-vendor",
            page_url="https://vendor.example/product",
            allowed_hosts={GLOBAL_IPV6},
            observed_at="2026-07-16T00:00:00Z",
            product_id="product-1",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].url, f"https://[{GLOBAL_IPV6}]/reports/coa.pdf")

    def test_fetch_uses_ipv6_canonical_url_without_network(self) -> None:
        expected = f"https://[{GLOBAL_IPV6}]/reports/coa.pdf"

        class Response:
            status = 200
            headers = {"Content-Type": "application/pdf"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def geturl(self) -> str:
                return expected

            def read(self, _limit: int) -> bytes:
                return b"pdf"

        class Opener:
            def open(self, request, *, timeout):
                self.request_url = request.full_url
                self.timeout = timeout
                return Response()

        opener = Opener()
        with mock.patch(
            "scripts.vendor_adapters.fetch.urllib.request.build_opener",
            return_value=opener,
        ):
            result = fetch_public_document(
                expected,
                allowed_hosts={GLOBAL_IPV6},
                timeout=1.0,
            )

        self.assertEqual(opener.request_url, expected)
        self.assertEqual(result.requested_url, expected)
        self.assertEqual(result.final_url, expected)
        self.assertEqual(result.body, b"pdf")
        self.assertEqual(result.error, "")


if __name__ == "__main__":
    unittest.main()
