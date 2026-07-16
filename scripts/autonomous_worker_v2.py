#!/usr/bin/env python3
"""Reliability upgrades for the strict autonomous DropFinder retrieval worker."""
from __future__ import annotations

import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
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
_VERIFICATION_FAILURE = "_product_detail_verification_failure"

# Green Unicorn's public category page is a useful fallback when its Woo endpoint
# replies with the transient 202 response observed on GitHub-hosted workers.
worker.FALLBACK_HTML_ROUTES.setdefault(
    "green_unicorn_farms",
    ["https://greenunicornfarms.com/category/thca-flower/"],
)

_original_scan_all_routes = worker.aggregate.scan_all_routes
_original_verify_products = worker.verify_products


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


def _verification_rejected(candidate: dict, reason: str) -> None:
    candidate[_VERIFICATION_FAILURE] = reason
    return None


def descriptive_candidate_to_row(candidate: dict, source_id: str, vendor: str) -> dict | None:
    """Verify every HTML card candidate against the product's own metadata."""
    candidate.pop(_VERIFICATION_FAILURE, None)
    name = worker.core.text(candidate.get("name"))
    target = str(candidate.get("url") or "")
    if not target:
        return _verification_rejected(candidate, "missing_product_target")
    detail_route = ("html", target, "product_detail")
    try:
        payload, content_type, status = worker.core.fetch(target)
    except Exception:
        return _verification_rejected(candidate, "product_detail_fetch_error")
    if status != 200:
        return _verification_rejected(candidate, "product_detail_http_status")
    if content_type not in {"text/html", "application/xhtml+xml"}:
        return _verification_rejected(candidate, "product_detail_content_type")

    # The card URL is discovery input, not confirming evidence. Exclude it so
    # a stale THCA-flower slug cannot validate unrelated response content.
    evidence = worker.product_detail_evidence(payload, "")
    if not worker.has_product_evidence(evidence):
        return _verification_rejected(candidate, "product_detail_missing_evidence")
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
    if not row:
        return _verification_rejected(candidate, "product_detail_record_rejected")
    return worker.decorate(row, evidence, "product_detail_metadata")


def verified_fallback_scan(source: tuple) -> tuple[list[dict], list[dict]]:
    """Retrieve HTML-card details and retain bounded verification failure diagnostics."""
    source_id, vendor, _ = source
    targets = worker.FALLBACK_HTML_ROUTES.get(source_id, [])
    rows: list[dict] = []
    attempts: list[dict] = []
    for index, target in enumerate(targets, 1):
        route = ("html", target, "thca_flower")
        started = time.monotonic()
        result = {
            "route_id": f"{source_id}-fallback-{index}",
            "url": target,
            "source_type": "html_card_product_detail",
        }
        try:
            payload, content_type, http_status = worker.core.fetch(target)
            candidates = worker.card_candidates(payload, route)
            extracted: list[dict] = []
            if candidates:
                with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as pool:
                    futures = {
                        pool.submit(worker.candidate_to_row, candidate, source_id, vendor): candidate
                        for candidate in candidates
                    }
                    for future in as_completed(futures):
                        try:
                            row = future.result()
                        except Exception:
                            row = None
                            futures[future][_VERIFICATION_FAILURE] = "product_detail_worker_error"
                        if row:
                            extracted.append(row)
            extracted = worker.core.dedupe(extracted)
            failure_reasons: dict[str, int] = {}
            for candidate in candidates:
                reason = str(candidate.get(_VERIFICATION_FAILURE) or "")
                if reason:
                    failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
            result.update(
                http_status=http_status,
                content_type=content_type,
                status="healthy" if extracted else "empty",
                candidates=len(candidates),
                products=len(extracted),
                verification_failures=sum(failure_reasons.values()),
                verification_failure_reasons=dict(sorted(failure_reasons.items())),
            )
            rows.extend(extracted)
        except Exception as exc:
            result.update(status="error", error=f"{type(exc).__name__}: {worker.core.text(exc)[:300]}")
        result["duration_seconds"] = round(time.monotonic() - started, 3)
        attempts.append(result)
    return worker.core.dedupe(rows), attempts


def _authoritative_structured_product(product: dict) -> bool:
    """Recognize rows created by the installed Shopify/Woo product parsers."""
    if str(product.get("source_type") or "") not in {"shopify", "woo"}:
        return False
    evidence = product.get("classification_evidence")
    if not isinstance(evidence, dict) or evidence.get("evidence_source") != "storefront_record":
        return False
    primary = str(product.get("primary_type") or "")
    tags = {str(value) for value in product.get("type_tags") or evidence.get("type_tags") or []}
    return bool(primary and evidence.get("primary_type") == primary and primary in tags)


def provenance_aware_verify_products(products: list[dict], source_id: str, vendor: str) -> list[dict]:
    """Preserve authoritative structured records; verify every other row independently."""
    authoritative: list[dict] = []
    unresolved: list[dict] = []
    for product in worker.core.dedupe(products):
        if _authoritative_structured_product(product):
            authoritative.append(product)
        else:
            unresolved.append(product)
    return worker.core.dedupe([*authoritative, *_original_verify_products(unresolved, source_id, vendor)])


def _is_retryable(status: dict) -> bool:
    if status.get("products"):
        return False
    for route in status.get("route_results") or []:
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


# Patch the proven strict worker in place. HTML card admission now requires
# product-detail metadata; structured product parsers retain distinct provenance.
worker.card_candidates = scored_card_candidates
worker.candidate_to_row = descriptive_candidate_to_row
worker.fallback_scan = verified_fallback_scan
worker.verify_products = provenance_aware_verify_products
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
    assert not _is_retryable({"products": 0, "route_results": [{"http_status": 404}]})
    assert _slug_title("https://example.test/products/archive-runtz-indoor-thca-flower") == "Archive Runtz Indoor Thca Flower"

    category_url = "https://example.test/collections/verification"
    responses = {
        "https://example.test/products/gone-thca-flower": ("", "text/html", 404),
        "https://example.test/products/stale-thca-flower": (
            '<meta property="og:title" content="Ceramic Coffee Mug">',
            "text/html",
            200,
        ),
        "https://example.test/products/cbd-flower": (
            '<meta property="og:title" content="CBD Flower">',
            "text/html",
            200,
        ),
        "https://example.test/products/thca-gummies": (
            '<meta property="og:title" content="THCA Gummies">',
            "text/html",
            200,
        ),
        "https://example.test/products/verified": (
            """
            <meta property="og:title" content="Verified THCA Flower">
            <meta name="description" content="Loose indoor THCA flower buds">
            <meta property="product:price:amount" content="31.00">
            <meta property="product:availability" content="in stock">
            """,
            "text/html",
            200,
        ),
        category_url: (
            """
            <a href="/products/gone-thca-flower">Removed Listing THCA Flower</a>
            <span>$24.99</span>
            """,
            "text/html",
            200,
        ),
    }
    fetch_calls: list[str] = []
    original_fetch = worker.core.fetch
    original_routes = worker.FALLBACK_HTML_ROUTES.get("verification_fixture")

    def fake_fetch(target: str) -> tuple[str, str, int]:
        fetch_calls.append(target)
        if target == "https://example.test/products/timeout":
            raise TimeoutError("synthetic timeout")
        return responses[target]

    def candidate(slug: str, name: str = "Listing Claims THCA Flower") -> dict:
        return {
            "name": name,
            "url": f"https://example.test/products/{slug}",
            "price": 24.99,
            "stock": "in_stock",
            "card_evidence": f"{name} /products/{slug}",
        }

    worker.core.fetch = fake_fetch
    worker.FALLBACK_HTML_ROUTES["verification_fixture"] = [category_url]
    try:
        expected_reasons = {
            "gone-thca-flower": "product_detail_http_status",
            "timeout": "product_detail_fetch_error",
            "stale-thca-flower": "product_detail_missing_evidence",
            "cbd-flower": "product_detail_missing_evidence",
            "thca-gummies": "product_detail_missing_evidence",
        }
        for rejected, expected_reason in expected_reasons.items():
            rejected_candidate = candidate(rejected)
            assert descriptive_candidate_to_row(
                rejected_candidate, "verification_fixture", "Verification Fixture"
            ) is None
            assert rejected_candidate[_VERIFICATION_FAILURE] == expected_reason

        verified = descriptive_candidate_to_row(
            candidate("verified"), "verification_fixture", "Verification Fixture"
        )
        assert verified is not None
        assert verified["name"] == "Verified THCA Flower"
        assert verified["price"] == 31.0
        assert verified["classification_evidence"]["evidence_source"] == "product_detail_metadata"
        assert worker.gate([verified])[0]

        generic_verified = descriptive_candidate_to_row(
            candidate("verified", "Hybrid"), "verification_fixture", "Verification Fixture"
        )
        assert generic_verified is not None
        assert generic_verified["classification_evidence"]["evidence_source"] == "product_detail_metadata"

        fallback_rows, fallback_attempts = worker.fallback_scan(
            ("verification_fixture", "Verification Fixture", [])
        )
        assert fallback_rows == []
        assert fallback_attempts[0]["status"] == "empty"
        assert fallback_attempts[0]["candidates"] == 1
        assert fallback_attempts[0]["products"] == 0
        assert fallback_attempts[0]["verification_failures"] == 1
        assert fallback_attempts[0]["verification_failure_reasons"] == {
            "product_detail_http_status": 1
        }
        assert fetch_calls.count("https://example.test/products/gone-thca-flower") == 2
    finally:
        worker.core.fetch = original_fetch
        if original_routes is None:
            worker.FALLBACK_HTML_ROUTES.pop("verification_fixture", None)
        else:
            worker.FALLBACK_HTML_ROUTES["verification_fixture"] = original_routes
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    return worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
