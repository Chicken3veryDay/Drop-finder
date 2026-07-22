from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
for module_name in tuple(sys.modules):
    if module_name == "multi_product" or module_name.startswith("multi_product."):
        del sys.modules[module_name]
try:
    sys.path.remove(str(SCRIPTS))
except ValueError:
    pass
sys.path.insert(0, str(SCRIPTS))

import autonomous_merge
import autonomous_worker_v4 as production
import product_detail_reliability as detail_reliability


class ProductDetailReliabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        production.install_runtime()
        cls.worker = production.worker
        cls.reliability = production.reliability

    def setUp(self) -> None:
        self.original_fetch = self.worker.core.fetch
        self.original_delays = detail_reliability.PRODUCT_DETAIL_RETRY_DELAYS
        detail_reliability.PRODUCT_DETAIL_RETRY_DELAYS = (0.0, 0.0, 0.0)

    def tearDown(self) -> None:
        self.worker.core.fetch = self.original_fetch
        detail_reliability.PRODUCT_DETAIL_RETRY_DELAYS = self.original_delays

    def direct_product(self) -> dict:
        evidence_text = "Direct THCA Flower 3.5g"
        return {
            "id": "direct",
            "source_id": "fixture",
            "vendor": "Fixture Vendor",
            "name": evidence_text,
            "url": "https://example.test/products/direct",
            "price": 25.0,
            "primary_type": "cannabis_flower",
            "source_type": "html",
            "classification_evidence": self.worker.evidence_payload(
                evidence_text,
                "product_title_or_url",
            ),
        }

    def unresolved_product(self) -> dict:
        return {
            "id": "unresolved",
            "source_product_id": "remote-2",
            "source_id": "fixture",
            "vendor": "Fixture Vendor",
            "name": "Mystery Product",
            "url": "https://example.test/products/mystery",
            "price": 29.0,
            "primary_type": "cannabis_flower",
            "source_type": "html",
            "classification_evidence": {},
        }

    def qualifying_detail(self) -> tuple[str, str, int]:
        return (
            """
            <meta property="og:title" content="Recovered THCA Flower">
            <meta name="description" content="Loose indoor THCA flower buds 3.5g">
            """,
            "text/html",
            200,
        )

    def test_retryable_timeout_recovers_once_and_preserves_both_products(self) -> None:
        calls = 0

        def fetch(_target: str):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("temporary timeout")
            return self.qualifying_detail()

        self.worker.core.fetch = fetch
        rows, diagnostics = detail_reliability.verify_products_with_diagnostics(
            self.worker,
            self.reliability,
            [self.direct_product(), self.unresolved_product()],
            "fixture",
            "Fixture Vendor",
        )

        self.assertEqual({row["id"] for row in rows}, {"direct", "unresolved"})
        self.assertEqual(calls, 2)
        self.assertEqual(diagnostics["retry_attempts"], 1)
        self.assertEqual(diagnostics["verification_failures"], [])
        self.assertEqual(diagnostics["verification_rejections"], [])

    def test_exhausted_timeout_emits_structured_terminal_failure(self) -> None:
        calls = 0

        def fetch(_target: str):
            nonlocal calls
            calls += 1
            raise TimeoutError("persistent timeout")

        self.worker.core.fetch = fetch
        rows, diagnostics = detail_reliability.verify_products_with_diagnostics(
            self.worker,
            self.reliability,
            [self.direct_product(), self.unresolved_product()],
            "fixture",
            "Fixture Vendor",
        )

        self.assertEqual([row["id"] for row in rows], ["direct"])
        self.assertEqual(calls, 3)
        self.assertEqual(len(diagnostics["verification_failures"]), 1)
        failure = diagnostics["verification_failures"][0]
        self.assertEqual(failure["product_id"], "remote-2")
        self.assertEqual(failure["reason"], "product_detail_fetch_error")
        self.assertEqual(failure["attempts"], 3)
        self.assertTrue(failure["retryable"])
        self.assertEqual(diagnostics["verification_rejections"], [])

    def test_valid_negative_detail_is_rejected_without_transport_retry(self) -> None:
        calls = 0

        def fetch(_target: str):
            nonlocal calls
            calls += 1
            return ('<meta property="og:title" content="Ceramic Coffee Mug">', "text/html", 200)

        self.worker.core.fetch = fetch
        rows, diagnostics = detail_reliability.verify_products_with_diagnostics(
            self.worker,
            self.reliability,
            [self.unresolved_product()],
            "fixture",
            "Fixture Vendor",
        )

        self.assertEqual(rows, [])
        self.assertEqual(calls, 1)
        self.assertEqual(diagnostics["verification_failures"], [])
        self.assertEqual(diagnostics["verification_rejections"][0]["reason"], "product_detail_missing_evidence")

    def test_source_with_survivors_and_exhausted_verification_is_degraded(self) -> None:
        original_scan = self.worker.aggregate.scan_all_routes
        original_fallback = self.worker.FALLBACK_HTML_ROUTES.pop("fixture", None)

        def scan(_source: tuple):
            return [self.direct_product(), self.unresolved_product()], {
                "source_id": "fixture",
                "name": "Fixture Vendor",
                "route_results": [{
                    "route_id": "fixture-1",
                    "url": "https://example.test/collection",
                    "source_type": "html",
                    "status": "healthy",
                    "http_status": 200,
                    "products": 2,
                }],
            }

        self.worker.aggregate.scan_all_routes = scan
        self.worker.core.fetch = lambda _target: (_ for _ in ()).throw(TimeoutError("persistent timeout"))
        try:
            rows, status = self.worker.scan_source(("fixture", "Fixture Vendor", []))
        finally:
            self.worker.aggregate.scan_all_routes = original_scan
            if original_fallback is not None:
                self.worker.FALLBACK_HTML_ROUTES["fixture"] = original_fallback

        self.assertEqual([row["id"] for row in rows], ["direct"])
        self.assertTrue(status["admitted"])
        self.assertEqual(status["status"], "degraded")
        self.assertEqual(status["health_reason_codes"], ["product_detail_verification_incomplete"])
        self.assertEqual(status["quality"]["verification_failures"], 1)
        verification_route = next(
            route for route in status["route_results"]
            if route.get("source_type") == "product_detail_verification"
        )
        self.assertEqual(verification_route["verification_failure_reasons"], {"product_detail_fetch_error": 1})
        self.assertEqual(verification_route["verification_failure_records"][0]["product_id"], "remote-2")


    def test_redundant_partial_fallback_is_diagnostic_only(self) -> None:
        original_scan = self.worker.aggregate.scan_all_routes
        original_fallback_scan = detail_reliability._fallback_scan
        original_fallback = self.worker.FALLBACK_HTML_ROUTES.get("fixture")

        def scan(_source: tuple):
            return [self.direct_product()], {
                "source_id": "fixture",
                "name": "Fixture Vendor",
                "route_results": [{
                    "route_id": "fixture-1",
                    "url": "https://example.test/collection",
                    "source_type": "shopify",
                    "status": "healthy",
                    "http_status": 200,
                    "products": 1,
                }],
            }

        fallback_route = {
            "route_id": "fixture-fallback-1",
            "url": "https://example.test/collection",
            "source_type": "html_card_product_detail",
            "status": "degraded",
            "candidates": 2,
            "products": 1,
            "admitted_products": 0,
            "verification_failures": 1,
            "verification_failure_reasons": {"product_detail_fetch_error": 1},
            "verification_failure_records": [{
                "product_id": "failed",
                "url": "https://example.test/products/failed",
                "reason": "product_detail_fetch_error",
                "attempts": 3,
                "retryable": True,
            }],
            "verification_rejections": 0,
            "retry_attempts": 2,
        }

        self.worker.aggregate.scan_all_routes = scan
        self.worker.FALLBACK_HTML_ROUTES["fixture"] = ["https://example.test/collection"]
        detail_reliability._fallback_scan = lambda *_args: ([], [fallback_route])
        try:
            rows, status = self.worker.scan_source(("fixture", "Fixture Vendor", []))
        finally:
            self.worker.aggregate.scan_all_routes = original_scan
            detail_reliability._fallback_scan = original_fallback_scan
            if original_fallback is None:
                self.worker.FALLBACK_HTML_ROUTES.pop("fixture", None)
            else:
                self.worker.FALLBACK_HTML_ROUTES["fixture"] = original_fallback

        self.assertEqual([row["id"] for row in rows], ["direct"])
        self.assertTrue(status["admitted"])
        self.assertEqual(status["status"], "healthy")
        self.assertEqual(status["health_reason_codes"], [])
        self.assertEqual(status["quality"]["verification_failures"], 1)
        self.assertEqual(status["quality"]["blocking_verification_failures"], 0)
        self.assertEqual(status["route_results"][-1]["admitted_products"], 0)

    def test_all_forbidden_retrieval_routes_use_precise_reason(self) -> None:
        original_scan = self.worker.aggregate.scan_all_routes
        original_fallback = self.worker.FALLBACK_HTML_ROUTES.pop("fixture", None)

        def scan(_source: tuple):
            return [], {
                "source_id": "fixture",
                "name": "Fixture Vendor",
                "route_results": [
                    {"route_id": "fixture-1", "url": "https://example.test/one", "status": "http_error", "http_status": 403},
                    {"route_id": "fixture-2", "url": "https://example.test/two", "status": "http_error", "http_status": 403},
                ],
            }

        self.worker.aggregate.scan_all_routes = scan
        try:
            rows, status = self.worker.scan_source(("fixture", "Fixture Vendor", []))
        finally:
            self.worker.aggregate.scan_all_routes = original_scan
            if original_fallback is not None:
                self.worker.FALLBACK_HTML_ROUTES["fixture"] = original_fallback

        self.assertEqual(rows, [])
        self.assertFalse(status["admitted"])
        self.assertEqual(status["status"], "quarantined")
        self.assertEqual(status["reason_codes"], ["source_access_forbidden"])

    def test_healthy_empty_routes_remain_no_qualifying_products(self) -> None:
        original_scan = self.worker.aggregate.scan_all_routes
        original_fallback = self.worker.FALLBACK_HTML_ROUTES.pop("fixture", None)

        def scan(_source: tuple):
            return [], {
                "source_id": "fixture",
                "name": "Fixture Vendor",
                "route_results": [
                    {"route_id": "fixture-1", "url": "https://example.test/empty", "status": "empty", "http_status": 200},
                ],
            }

        self.worker.aggregate.scan_all_routes = scan
        try:
            rows, status = self.worker.scan_source(("fixture", "Fixture Vendor", []))
        finally:
            self.worker.aggregate.scan_all_routes = original_scan
            if original_fallback is not None:
                self.worker.FALLBACK_HTML_ROUTES["fixture"] = original_fallback

        self.assertEqual(rows, [])
        self.assertEqual(status["reason_codes"], ["no_qualifying_products"])

    def test_fallback_candidate_uses_the_same_retry_contract(self) -> None:
        calls = 0
        candidate = {
            "name": "Mystery Product",
            "url": "https://example.test/products/fallback",
            "price": 31.0,
            "stock": "in_stock",
        }

        def fetch(_target: str):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("temporary timeout")
            return self.qualifying_detail()

        self.worker.core.fetch = fetch
        row = self.worker.candidate_to_row(candidate, "fixture", "Fixture Vendor")
        self.assertIsNotNone(row)
        self.assertEqual(calls, 2)
        self.assertEqual(candidate[detail_reliability._OUTCOME_KEY]["kind"], "verified")
        self.assertEqual(candidate[detail_reliability._OUTCOME_KEY]["attempts"], 2)


    def test_partial_fallback_route_is_atomic(self) -> None:
        original_fallback = self.worker.FALLBACK_HTML_ROUTES.get("fixture")
        self.worker.FALLBACK_HTML_ROUTES["fixture"] = ["https://example.test/collection"]
        collection = """
        <a href="/products/good">Blue Dream THCA Flower</a>
        <a href="/products/bad">Mystery Product</a>
        """

        def fetch(target: str):
            if target.endswith("/collection"):
                return collection, "text/html", 200
            if target.endswith("/good"):
                return self.qualifying_detail()
            raise TimeoutError("persistent fallback timeout")

        self.worker.core.fetch = fetch
        try:
            rows, attempts = detail_reliability._fallback_scan(
                self.worker,
                self.reliability,
                ("fixture", "Fixture Vendor", []),
            )
        finally:
            if original_fallback is None:
                self.worker.FALLBACK_HTML_ROUTES.pop("fixture", None)
            else:
                self.worker.FALLBACK_HTML_ROUTES["fixture"] = original_fallback

        self.assertEqual(rows, [])
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["status"], "degraded")
        self.assertEqual(attempts[0]["products"], 1)
        self.assertEqual(attempts[0]["admitted_products"], 0)
        self.assertEqual(attempts[0]["verification_failures"], 1)

    def test_merge_keeps_nonblocking_fallback_failures_diagnostic(self) -> None:
        public = autonomous_merge._source_status({
            "source_id": "fixture",
            "name": "Fixture Vendor",
            "status": "healthy",
            "quality": {"products": 1, "blocking_verification_failures": 0},
            "route_results": [{
                "route_id": "fixture-fallback-1",
                "source_type": "html_card_product_detail",
                "status": "degraded",
                "products": 1,
                "admitted_products": 0,
                "verification_failures": 1,
                "verification_failure_reasons": {"product_detail_fetch_error": 1},
            }],
        }, 1, 0)

        self.assertEqual(public["status"], "healthy")
        self.assertEqual(public["verification_failures"], 1)
        self.assertEqual(public["blocking_verification_failures"], 0)
        self.assertEqual(public["route_results"][0]["admitted_products"], 0)

    def test_merge_preserves_degraded_health_and_public_failure_records(self) -> None:
        public = autonomous_merge._source_status({
            "source_id": "fixture",
            "name": "Fixture Vendor",
            "status": "degraded",
            "quality": {"products": 1},
            "route_results": [{
                "route_id": "fixture-product-verification",
                "source_type": "product_detail_verification",
                "status": "degraded",
                "products": 1,
                "candidates": 2,
                "verification_failures": 1,
                "verification_failure_reasons": {"product_detail_fetch_error": 1},
                "verification_failure_records": [{
                    "product_id": "remote-2",
                    "url": "https://example.test/products/mystery",
                    "reason": "product_detail_fetch_error",
                    "attempts": 3,
                    "retryable": True,
                }],
            }],
        }, 1, 0)

        self.assertEqual(public["status"], "degraded")
        self.assertEqual(public["verification_failures"], 1)
        route = public["route_results"][0]
        self.assertEqual(route["verification_failure_records"][0]["product_id"], "remote-2")
        self.assertNotIn("error", route["verification_failure_records"][0])


if __name__ == "__main__":
    unittest.main()
