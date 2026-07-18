from __future__ import annotations

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
        request_calls: list[tuple[str, str, dict[str, str]]] = []
        factory_calls: list[tuple[object, ...]] = []

        class Response:
            status = 200

            def getheader(self, name: str, default=None):
                return "application/pdf" if name.lower() == "content-type" else default

            def read(self, _limit: int) -> bytes:
                return b"pdf"

            def close(self) -> None:
                return None

        class Connection:
            def request(self, method: str, target: str, body=None, headers=None) -> None:
                request_calls.append((method, target, dict(headers or {})))

            def getresponse(self):
                return Response()

            def close(self) -> None:
                return None

        def connection_factory(*args):
            factory_calls.append(args)
            return Connection()

        result = fetch_public_document(
            expected,
            allowed_hosts={GLOBAL_IPV6},
            timeout=1.0,
            _connection_factory=connection_factory,
        )

        self.assertEqual(factory_calls[0][0:3], ("https", GLOBAL_IPV6, 443))
        self.assertEqual(factory_calls[0][3][4], (GLOBAL_IPV6, 443, 0, 0))
        self.assertEqual(request_calls[0][0:2], ("GET", "/reports/coa.pdf"))
        self.assertEqual(request_calls[0][2]["Host"], f"[{GLOBAL_IPV6}]")
        self.assertEqual(result.requested_url, expected)
        self.assertEqual(result.final_url, expected)
        self.assertEqual(result.body, b"pdf")
        self.assertEqual(result.error, "")


if __name__ == "__main__":
    unittest.main()
