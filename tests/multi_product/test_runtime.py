from __future__ import annotations

import re
import unittest
from types import SimpleNamespace
from urllib.parse import urljoin, urlsplit, urlunsplit

from scripts.multi_product.runtime import install_multi_product_runtime, runtime_self_test


class FakeCore:
    SOURCES = [("existing", "Existing", [("html", "https://example.test/shop", "storewide")])]
    POTENCY = re.compile(r"\bTHC-?A\s*[:\-]?\s*(\d{1,2}(?:\.\d+)?)\s*%", re.I)
    ANCHOR = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
    HARD_EXCLUDE = re.compile(r"$^")

    @staticmethod
    def text(value):
        return " ".join(re.sub(r"<[^>]+>", " ", str(value or "")).split())

    @staticmethod
    def url(value, base):
        target = urljoin(base, str(value or ""))
        parsed = urlsplit(target)
        return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path, parsed.query, ""))

    @staticmethod
    def num(value):
        try:
            parsed = float(str(value).replace("$", "").strip())
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def availability(value):
        return "in_stock" if "stock" in str(value).lower() else "unknown"

    @staticmethod
    def now():
        return "2026-07-15T00:00:00+00:00"


class RuntimeTests(unittest.TestCase):
    def make_reliability(self):
        worker = SimpleNamespace(
            core=FakeCore,
            FALLBACK_EXCLUDE=re.compile(r"$^"),
            PRODUCT_PATHS=("/product/", "/products/"),
            FALLBACK_HTML_ROUTES={},
            path_text=lambda target: urlsplit(target).path.replace("-", " "),
        )
        return SimpleNamespace(worker=worker)

    def test_install_and_self_test(self):
        reliability = self.make_reliability()
        state = install_multi_product_runtime(reliability)
        self.assertTrue(state["installed"])
        runtime_self_test(reliability)
        self.assertIn("cali_canna", {source[0] for source in reliability.worker.core.SOURCES})

    def test_product_links_follow_supported_types_only(self):
        reliability = self.make_reliability()
        install_multi_product_runtime(reliability)
        payload = """
          <a href="/products/thca-vape">THCA Disposable Vape 1mL</a>
          <a href="/products/empty-cart">Empty Vape Cartridge</a>
          <a href="/products/psilo">Psilocybin Mushrooms 7g</a>
          <a href="/collections/thca-flower">THCA Flower</a>
        """
        links = reliability.worker.core.product_links(
            payload,
            ("html", "https://example.test/shop", "storewide"),
        )
        self.assertNotIn("/collections/", reliability.worker.PRODUCT_PATHS)
        self.assertEqual(
            links,
            [
                "https://example.test/products/thca-vape",
                "https://example.test/products/psilo",
            ],
        )


if __name__ == "__main__":
    unittest.main()
