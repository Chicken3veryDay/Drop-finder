#!/usr/bin/env python3
"""Reliability upgrades for the strict autonomous DropFinder retrieval worker."""
from __future__ import annotations

import re
import sys
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import autonomous_worker as worker  # type: ignore

GENERIC_LABEL = re.compile(
    r"^(?:product|flower|strain|indica|sativa|hybrid|"
    r"indica[, /]+hybrid[, /]+sativa|unknown|untitled)$",
    re.I,
)
RETRYABLE_HTTP = {202, 408, 425, 429, 500, 502, 503, 504}
RETRY_DELAYS = (0.0, 2.0, 5.0)

# Green Unicorn's public category page is a useful fallback when its Woo endpoint
# replies with the transient 202 response observed on GitHub-hosted workers.
worker.FALLBACK_HTML_ROUTES.setdefault(
    "green_unicorn_farms",
    ["https://greenunicornfarms.com/category/thca-flower/"],
)

_original_scan_all_routes = worker.aggregate.scan_all_routes
_original_candidate_to_row = worker.candidate_to_row


def _slug_title(target: str) -> str:
    try:
        slug = urllib.parse.unquote(urllib.parse.urlsplit(target).path.rstrip("/").split("/")[-1])
    except ValueError:
        slug = ""
    return re.sub(r"\s+", " ", slug.replace("-", " ").replace("_", " ")).strip().title()


def _candidate_score(label: str, target: str, price: object) -> float:
    form_text = f"{label} {worker.path_text(target)}"
    score = 0.0
    if worker.has_product_evidence(form_text):
        score += 100.0
    if not GENERIC_LABEL.fullmatch(label):
        score += 30.0
    if price is not None:
        score += 10.0
    score += min(len(label), 80) / 100.0
    return score


def scored_card_candidates(payload: str, route: tuple) -> list[dict]:
    """Choose the best descriptive anchor when a product URL appears repeatedly."""
    base_host = urllib.parse.urlsplit(route[1]).netloc.lower()
    candidates: dict[str, dict] = {}
    for match in worker.core.ANCHOR.finditer(payload):
        target = worker.core.url(match.group(1), route[1])
        parsed = urllib.parse.urlsplit(target)
        if not target or parsed.netloc.lower() != base_host:
            continue
        path = parsed.path.lower()
        if not any(marker in path for marker in worker.PRODUCT_PATHS):
            continue
        label = worker.core.text(match.group(2))
        if len(label) < 4 or label.lower() in {
            "options",
            "view product",
            "learn more",
            "shop now",
            "add to cart",
        }:
            continue
        form_text = f"{label} {worker.path_text(target)}"
        if worker.core.HARD_EXCLUDE.search(form_text) or worker.FALLBACK_EXCLUDE.search(form_text):
            continue
        nearby = worker.core.text(payload[match.start() : min(len(payload), match.end() + 2200)])
        prices = [worker.core.num(value) for value in worker.PRICE.findall(nearby)]
        price = next((value for value in prices if value is not None), None)
        stock = (
            "out_of_stock"
            if "out of stock" in nearby.lower()
            else "in_stock"
            if any(token in nearby.lower() for token in ("add to cart", "choose an option", "in stock"))
            else ""
        )
        candidate = {
            "name": label,
            "url": target,
            "price": price,
            "stock": stock,
            "card_evidence": form_text,
            "candidate_score": _candidate_score(label, target, price),
        }
        current = candidates.get(target)
        if current is None or candidate["candidate_score"] > current.get("candidate_score", -1):
            candidates[target] = candidate
    return sorted(candidates.values(), key=lambda row: row.get("candidate_score", 0), reverse=True)[:120]


def descriptive_candidate_to_row(candidate: dict, source_id: str, vendor: str) -> dict | None:
    """Resolve taxonomy-fragment anchors from the product's own metadata."""
    name = worker.core.text(candidate.get("name"))
    if not GENERIC_LABEL.fullmatch(name):
        return _original_candidate_to_row(candidate, source_id, vendor)

    target = str(candidate.get("url") or "")
    detail_route = ("html", target, "product_detail")
    try:
        payload, content_type, status = worker.core.fetch(target)
    except Exception:
        return None
    if status != 200 or content_type not in {"text/html", "application/xhtml+xml"}:
        return None

    evidence = worker.product_detail_evidence(payload, target)
    if not worker.has_product_evidence(evidence):
        return None
    meta = worker.core.meta_values(payload)
    title = (
        meta.get("og:title")
        or meta.get("twitter:title")
        or _slug_title(target)
        or name
    )
    price = (
        meta.get("product:price:amount")
        or meta.get("og:price:amount")
        or candidate.get("price")
    )
    stock = meta.get("product:availability") or candidate.get("stock")
    image = meta.get("og:image") or meta.get("twitter:image") or ""
    row = worker.core.record(source_id, vendor, detail_route, title, target, evidence, price, stock, image)
    return worker.decorate(row, evidence, "product_detail_metadata") if row else None


def _route_is_retryable(route: dict) -> bool:
    try:
        return int(route.get("http_status")) in RETRYABLE_HTTP
    except (TypeError, ValueError):
        return False


def _is_retryable(status: dict) -> bool:
    return any(_route_is_retryable(route) for route in status.get("route_results") or [])


def resilient_scan_all_routes(source: tuple) -> tuple[list[dict], dict]:
    """Retry transiently failed routes without repeating successful siblings."""
    source_id, vendor, routes = source
    started = time.monotonic()
    pending = list(enumerate(routes, start=1))
    history: list[dict] = []
    terminal_by_route: dict[int, dict] = {}
    merged_products: list[dict] = []
    final_status: dict = {
        "source_id": source_id,
        "name": vendor,
        "enabled": True,
    }

    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        if not pending:
            break
        if delay:
            time.sleep(delay)

        attempt_routes = [route for _, route in pending]
        products, status = _original_scan_all_routes((source_id, vendor, attempt_routes))
        final_status.update(dict(status))
        merged_products = worker.core.dedupe([*merged_products, *products])
        route_results = list(status.get("route_results") or [])
        retry_pending: list[tuple[int, tuple]] = []

        for offset, (original_index, route) in enumerate(pending):
            result = dict(route_results[offset]) if offset < len(route_results) else {
                "url": route[1],
                "source_type": route[0],
                "status": "error",
                "error": "aggregate scanner omitted route result",
            }
            result["route_id"] = f"{source_id}-{original_index}"
            result["retry_attempt"] = attempt
            history.append(result)
            terminal_by_route[original_index] = result
            if attempt < len(RETRY_DELAYS) and _route_is_retryable(result):
                retry_pending.append((original_index, route))

        pending = retry_pending

    active_route = ""
    active_count = -1
    for original_index in sorted(terminal_by_route):
        result = terminal_by_route[original_index]
        if result.get("status") != "healthy":
            continue
        try:
            product_count = int(result.get("products") or 0)
        except (TypeError, ValueError):
            product_count = 0
        if product_count > active_count:
            active_count = product_count
            active_route = str(result.get("url") or "")

    final_status.update(
        status="healthy" if merged_products else "degraded",
        products=len(merged_products),
        routes_attempted=len(history),
        active_route=active_route,
        route_results=history,
        retry_attempts=max((row.get("retry_attempt", 1) for row in history), default=1),
        duration_seconds=round(time.monotonic() - started, 3),
    )
    return merged_products, final_status


# Patch the proven strict worker in place. Its admission, product-evidence, and
# publication contracts remain unchanged.
worker.card_candidates = scored_card_candidates
worker.candidate_to_row = descriptive_candidate_to_row
worker.aggregate.scan_all_routes = resilient_scan_all_routes


def _self_test_route_retries() -> None:
    global _original_scan_all_routes, RETRY_DELAYS

    source_id = "test_source"
    vendor = "Test Vendor"
    healthy_route = ("html", "https://example.test/flower", "thca_flower")
    transient_route = ("woo", "https://example.test/api", "mixed_flower")
    product_a = {
        "source_id": source_id,
        "vendor": vendor,
        "name": "Alpha THCA Flower",
        "url": "https://example.test/products/alpha",
        "variant": "",
    }
    product_b = {
        "source_id": source_id,
        "vendor": vendor,
        "name": "Beta THCA Flower",
        "url": "https://example.test/products/beta",
        "variant": "",
    }
    calls: list[tuple] = []

    def partial_then_recovered(test_source: tuple) -> tuple[list[dict], dict]:
        calls.append(test_source)
        attempted = test_source[2]
        if len(calls) == 1:
            assert attempted == [healthy_route, transient_route]
            return [product_a], {
                "source_id": source_id,
                "name": vendor,
                "products": 1,
                "route_results": [
                    {"status": "healthy", "http_status": 200, "products": 1, "url": healthy_route[1]},
                    {"status": "http_error", "http_status": 429, "products": 0, "url": transient_route[1]},
                ],
            }
        assert attempted == [transient_route]
        return [product_b], {
            "source_id": source_id,
            "name": vendor,
            "products": 1,
            "route_results": [
                {"status": "healthy", "http_status": 200, "products": 1, "url": transient_route[1]},
            ],
        }

    previous_scan = _original_scan_all_routes
    previous_delays = RETRY_DELAYS
    try:
        _original_scan_all_routes = partial_then_recovered
        RETRY_DELAYS = (0.0, 0.0, 0.0)
        products, status = resilient_scan_all_routes(
            (source_id, vendor, [healthy_route, transient_route])
        )
        assert [row["name"] for row in products] == ["Alpha THCA Flower", "Beta THCA Flower"]
        assert len(calls) == 2
        assert status["retry_attempts"] == 2
        assert status["routes_attempted"] == 3
        assert [row["route_id"] for row in status["route_results"]] == [
            f"{source_id}-1",
            f"{source_id}-2",
            f"{source_id}-2",
        ]
        assert [row["retry_attempt"] for row in status["route_results"]] == [1, 1, 2]
        assert status["products"] == 2
        assert status["status"] == "healthy"

        calls.clear()

        def partial_with_terminal_404(test_source: tuple) -> tuple[list[dict], dict]:
            calls.append(test_source)
            return [product_a], {
                "source_id": source_id,
                "name": vendor,
                "products": 1,
                "route_results": [
                    {"status": "healthy", "http_status": 200, "products": 1, "url": healthy_route[1]},
                    {"status": "http_error", "http_status": 404, "products": 0, "url": transient_route[1]},
                ],
            }

        _original_scan_all_routes = partial_with_terminal_404
        products, status = resilient_scan_all_routes(
            (source_id, vendor, [healthy_route, transient_route])
        )
        assert len(calls) == 1
        assert products == [product_a]
        assert status["retry_attempts"] == 1
        assert status["route_results"][1]["http_status"] == 404
    finally:
        _original_scan_all_routes = previous_scan
        RETRY_DELAYS = previous_delays


def self_test() -> int:
    worker.self_test()
    route = ("html", "https://example.test/collections/thca-flower", "thca_flower")
    fixture = """
      <a href='/products/blue-dream-thca-flower'>Hybrid</a><span>$24.99</span>
      <a href='/products/blue-dream-thca-flower'>Blue Dream THCA Flower</a><span>$24.99</span>
    """
    rows = scored_card_candidates(fixture, route)
    assert len(rows) == 1
    assert rows[0]["name"] == "Blue Dream THCA Flower"
    assert rows[0]["price"] == 24.99
    assert _is_retryable({"products": 1, "route_results": [{"http_status": 202}]})
    assert not _is_retryable({"products": 1, "route_results": [{"http_status": 404}]})
    _self_test_route_retries()
    assert _slug_title("https://example.test/products/archive-runtz-indoor-thca-flower") == "Archive Runtz Indoor Thca Flower"
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    return worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
