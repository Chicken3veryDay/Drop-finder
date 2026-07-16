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


def _is_retryable(status: dict) -> bool:
    if status.get("products"):
        return False
    for route in status.get("route_results") or []:
        if route.get("retryable") is True:
            return True
        try:
            http_status = int(route.get("http_status"))
        except (TypeError, ValueError):
            continue
        if http_status in RETRYABLE_HTTP:
            return True
    return False


def resilient_scan_all_routes(source: tuple) -> tuple[list[dict], dict]:
    """Retry only transient transport failures; deterministic parse failures stay visible."""
    history: list[dict] = []
    final_products: list[dict] = []
    final_status: dict = {}
    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        if delay:
            time.sleep(delay)
        products, status = _original_scan_all_routes(source)
        status = dict(status)
        for route in status.get("route_results") or []:
            route = dict(route)
            route["retry_attempt"] = attempt
            history.append(route)
        final_products, final_status = products, status
        if products or not _is_retryable(status):
            break
    final_status = dict(final_status)
    final_status["retry_attempts"] = max((row.get("retry_attempt", 1) for row in history), default=1)
    final_status["route_results"] = history or list(final_status.get("route_results") or [])
    final_status["routes_attempted"] = len(final_status["route_results"])
    return final_products, final_status


worker.card_candidates = scored_card_candidates
worker.candidate_to_row = descriptive_candidate_to_row
worker.aggregate.scan_all_routes = resilient_scan_all_routes


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
    assert _is_retryable({"products": 0, "route_results": [{"http_status": 202}]})
    assert _is_retryable({"products": 0, "route_results": [{"retryable": True, "error_category": "timeout"}]})
    assert not _is_retryable({"products": 0, "route_results": [{"retryable": False, "error_category": "processing_error"}]})
    assert not _is_retryable({"products": 0, "route_results": [{"http_status": 404}]})
    assert _slug_title("https://example.test/products/archive-runtz-indoor-thca-flower") == "Archive Runtz Indoor Thca Flower"
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    return worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
