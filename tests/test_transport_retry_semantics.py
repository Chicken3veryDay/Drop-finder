from __future__ import annotations

import importlib.util
import socket
import sys
import types
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class CoreStub(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("cloud_scan")
        self.fetch = lambda _target: ("", "text/html", 200)
        self.shopify = lambda *_args: []
        self.woo = lambda *_args: []
        self.html_with_details = lambda *_args: []
        self.dedupe = lambda rows: list(rows)
        self.text = lambda value: str(value)


core = CoreStub()
previous_cloud_scan = sys.modules.get("cloud_scan")
sys.modules["cloud_scan"] = core
try:
    cloud_scan_v2 = load_module("_transport_retry_cloud_scan_v2", SCRIPTS / "cloud_scan_v2.py")
finally:
    if previous_cloud_scan is None:
        sys.modules.pop("cloud_scan", None)
    else:
        sys.modules["cloud_scan"] = previous_cloud_scan

aggregate_stub = types.SimpleNamespace(scan_all_routes=lambda _source: ([], {}))
worker_stub = types.ModuleType("autonomous_worker")
worker_stub.FALLBACK_HTML_ROUTES = {}
worker_stub.aggregate = aggregate_stub
worker_stub.candidate_to_row = lambda *_args: None
worker_stub.path_text = lambda target: target
worker_stub.has_product_evidence = lambda _value: False
worker_stub.product_detail_evidence = lambda *_args: ""
worker_stub.decorate = lambda row, *_args: row
worker_stub.core = types.SimpleNamespace()
worker_stub.PRODUCT_PATHS = ()
worker_stub.FALLBACK_EXCLUDE = types.SimpleNamespace(search=lambda _value: None)
worker_stub.PRICE = types.SimpleNamespace(findall=lambda _value: [])
worker_stub.self_test = lambda: 0
worker_stub.main = lambda: 0
previous_worker = sys.modules.get("autonomous_worker")
sys.modules["autonomous_worker"] = worker_stub
try:
    autonomous_worker_v2 = load_module("_transport_retry_autonomous_worker_v2", SCRIPTS / "autonomous_worker_v2.py")
finally:
    if previous_worker is None:
        sys.modules.pop("autonomous_worker", None)
    else:
        sys.modules["autonomous_worker"] = previous_worker


class TransportClassificationTests(unittest.TestCase):
    source = ("fixture", "Fixture", [("html", "https://example.test/flower", "flower")])

    def route_for(self, exc: BaseException) -> dict:
        previous = core.fetch
        core.fetch = lambda _target: (_ for _ in ()).throw(exc)
        try:
            _products, status = cloud_scan_v2.scan_all_routes(self.source)
        finally:
            core.fetch = previous
        return status["route_results"][0]

    def test_structured_transient_failures_are_retryable(self) -> None:
        cases = (
            (TimeoutError("timed out"), "timeout"),
            (urllib.error.URLError(socket.gaierror,socket.EAI_AGAIN, "temporary failure")), "dns_temporary"),
            (ConnectionResetError("reset"), "connection_reset"),
        )
        for exc, category in cases:
            with self.subTest(category=category):
                route = self.route_for(exc)
                self.assertEqual(route["error_category"], category)
                self.assertIs(route["retryable"], True)
                self.assertTrue(autonomous_worker_v2._is_retryable({"products": 0, "route_results": [route]}))

    def test_deterministic_processing_failure_is_not_retryable(self) -> None:
        route = self.route_for(ValueError("invalid payload"))
        self.assertEqual(route["error_category"], "processing_error")
        self.assertIs(route["retryable"], False)
        self.assertFalse(autonomous_worker_v2._is_retryable({"products": 0, "route_results": [route]}))

        invalid_url = self.route_for(urllib.error.URLError("unknown url type: mailto"))
        self.assertEqual(invalid_url["error_category"], "invalid_url")
        self.assertIs(invalid_url["retryable"], False)


class RetryLoopTests(unittest.TestCase):
    source = ("fixture", "Fixture", [])

    def run_with(self, results):
        previous_scan = autonomous_worker_v2._original_scan_all_routes
        previous_delays = autonmous_worker_v2.RETRY_DELAYS
        calls = []

        def fake_scan(_source):
            calls.append(len(calls) + 1)
            return results[min(len(calls) - 1, len(results) - 1)]

        autonomous_worker_v2._original_scan_all_routes = fake_scan
        autonomous_worker_v2.RETRY_DELAYS = (0.0, 0.0, 0.0)
        try:
            products, status = autonomous_worker_v2.resilient_scan_all_routes(self.source)
        finally:
            autonomous_worker_v2._original_scan_all_routes = previous_scan
            autonomous_worker_v2.RETRY_DELAYS = previous_delays
        return calls, products, status

    def test_transient_failure_recovers_on_second_attempt(self) -> None:
        first = ([], {"products": 0, "route_results": [{"status": "error", "retryable": True, "error_category": "timeout"}]})
        recovered = ([{"id": "product-1"}], {"products": 1, "route_results": [{"status": "healthy", "products": 1}]})
        calls, products, status = self.run_with([first, recovered])
        self.assertEqual(calls, [1, 2])
        self.assertEqual(products, [{"id": "product-1"}])
        self.assertEqual(status["retry_attempts"], 2)
        self.assertEqual([row["retry_attempt"] for row in status["route_results"]], [1, 2])

    def test_terminal_transient_failure_exhausts_bounded_budget(self) -> None:
        failure = ([], {"products": 0, "route_results": [{"status": "error", "retryable": True, "error_category": "connection_reset"}]})
        calls, products, status = self.run_with([failure])
        self.assertEqual(calls, [1, 2, 3])
        self.assertEqual(products, [])
        self.assertEqual(status["retry_attempts"], 3)
        self.assertEqual(status["routes_attempted"], 3)

    def test_deterministic_failure_stops_after_one_attempt(self) -> None:
        failure = ([], {"products": 0, "route_results": [{"status": "error", "retryable": False, "error_category": "processing_error"}]})
        calls, products, status = self.run_with([failure])
        self.assertEqual(calls, [1])
        self.assertEqual(products, [])
        self.assertEqual(status["retry_attempts"], 1)


if __name__ == "__main__":
    unittest.main()
