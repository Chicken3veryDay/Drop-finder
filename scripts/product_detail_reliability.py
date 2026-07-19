"""Bounded product-detail retries and observable verification outcomes."""
from __future__ import annotations

import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

PRODUCT_DETAIL_RETRY_DELAYS = (0.0, 1.0, 3.0)
RETRYABLE_HTTP = {202, 408, 425, 429, 500, 502, 503, 504}
_FAILURE_RECORD_LIMIT = 24
_OUTCOME_KEY = "_product_detail_verification_outcome"


def _bounded_text(value: Any, limit: int = 300) -> str:
    return " ".join(str(value or "").split())[:limit]


def _product_identity(value: dict[str, Any]) -> str:
    return _bounded_text(
        value.get("source_product_id")
        or value.get("product_id")
        or value.get("id")
        or value.get("url"),
        160,
    )


def _record(value: dict[str, Any], reason: str, attempts: int, retryable: bool) -> dict[str, Any]:
    return {
        "product_id": _product_identity(value),
        "url": _bounded_text(value.get("url"), 500),
        "reason": reason,
        "attempts": max(1, int(attempts)),
        "retryable": bool(retryable),
    }


def _exception_retryable(worker: Any, error: BaseException) -> bool:
    classify = getattr(worker.aggregate, "classify_route_failure", None)
    if callable(classify):
        try:
            return bool(classify(error).get("retryable"))
        except Exception:
            pass
    return isinstance(error, (TimeoutError, ConnectionError))


def _fetch_detail(worker: Any, target: str) -> dict[str, Any]:
    last_error: BaseException | None = None
    for attempt, delay in enumerate(PRODUCT_DETAIL_RETRY_DELAYS, start=1):
        if delay:
            time.sleep(delay)
        try:
            payload, content_type, status = worker.core.fetch(target)
        except Exception as error:
            last_error = error
            retryable = _exception_retryable(worker, error)
            if retryable and attempt < len(PRODUCT_DETAIL_RETRY_DELAYS):
                continue
            return {
                "kind": "failure",
                "reason": "product_detail_fetch_error",
                "attempts": attempt,
                "retryable": retryable,
                "error": f"{type(error).__name__}: {_bounded_text(error)}",
            }
        retryable = status in RETRYABLE_HTTP
        if status != 200:
            if retryable and attempt < len(PRODUCT_DETAIL_RETRY_DELAYS):
                continue
            return {
                "kind": "failure",
                "reason": "product_detail_http_status",
                "attempts": attempt,
                "retryable": retryable,
                "http_status": status,
            }
        if content_type not in {"text/html", "application/xhtml+xml"}:
            return {
                "kind": "failure",
                "reason": "product_detail_content_type",
                "attempts": attempt,
                "retryable": False,
                "content_type": content_type,
            }
        return {
            "kind": "response",
            "payload": payload,
            "content_type": content_type,
            "http_status": status,
            "attempts": attempt,
            "retryable": False,
        }
    return {
        "kind": "failure",
        "reason": "product_detail_fetch_error",
        "attempts": len(PRODUCT_DETAIL_RETRY_DELAYS),
        "retryable": True,
        "error": f"{type(last_error).__name__}: {_bounded_text(last_error)}" if last_error else "detail fetch failed",
    }


def _verify_product(worker: Any, reliability: Any, product: dict[str, Any]) -> dict[str, Any]:
    if reliability._authoritative_structured_product(product):
        return {"kind": "verified", "product": product, "attempts": 0}
    target = str(product.get("url") or "")
    direct = worker.core.text(
        f"{product.get('name', '')} {product.get('variant', '')} {worker.path_text(target)}"
    )
    if worker.has_product_evidence(direct):
        return {
            "kind": "verified",
            "product": worker.decorate(product, direct, "product_title_or_url"),
            "attempts": 0,
        }
    fetched = _fetch_detail(worker, target)
    if fetched["kind"] == "failure":
        return {**fetched, "record": _record(product, fetched["reason"], fetched["attempts"], fetched["retryable"])}
    evidence = worker.product_detail_evidence(fetched["payload"], target)
    if not worker.has_product_evidence(evidence):
        return {
            "kind": "rejection",
            "reason": "product_detail_missing_evidence",
            "attempts": fetched["attempts"],
            "record": _record(product, "product_detail_missing_evidence", fetched["attempts"], False),
        }
    return {
        "kind": "verified",
        "product": worker.decorate(product, evidence, "product_detail_metadata"),
        "attempts": fetched["attempts"],
    }


def verify_products_with_diagnostics(
    worker: Any,
    reliability: Any,
    products: list[dict[str, Any]],
    source_id: str,
    vendor: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    del source_id, vendor
    discovered = worker.core.dedupe(products)
    outcomes: list[dict[str, Any]] = []
    if discovered:
        with ThreadPoolExecutor(max_workers=min(8, len(discovered))) as pool:
            futures = {pool.submit(_verify_product, worker, reliability, product): product for product in discovered}
            for future in as_completed(futures):
                product = futures[future]
                try:
                    outcomes.append(future.result())
                except Exception as error:
                    retryable = _exception_retryable(worker, error)
                    outcomes.append({
                        "kind": "failure",
                        "reason": "product_detail_worker_error",
                        "attempts": 1,
                        "retryable": retryable,
                        "record": _record(product, "product_detail_worker_error", 1, retryable),
                    })
    verified = [outcome["product"] for outcome in outcomes if outcome.get("kind") == "verified"]
    failures = [outcome["record"] for outcome in outcomes if outcome.get("kind") == "failure"]
    rejections = [outcome["record"] for outcome in outcomes if outcome.get("kind") == "rejection"]
    return worker.core.dedupe(verified), {
        "discovered_products": len(discovered),
        "verified_products": len(verified),
        "verification_failures": failures[:_FAILURE_RECORD_LIMIT],
        "verification_rejections": rejections[:_FAILURE_RECORD_LIMIT],
        "retry_attempts": sum(max(0, int(outcome.get("attempts") or 0) - 1) for outcome in outcomes),
    }


def _set_candidate_outcome(candidate: dict[str, Any], outcome: dict[str, Any]) -> None:
    candidate[_OUTCOME_KEY] = {
        "kind": outcome.get("kind"),
        "reason": outcome.get("reason"),
        "attempts": int(outcome.get("attempts") or 1),
        "retryable": bool(outcome.get("retryable")),
        "record": outcome.get("record"),
    }


def _candidate_to_row(worker: Any, reliability: Any, candidate: dict[str, Any], source_id: str, vendor: str) -> dict[str, Any] | None:
    candidate.pop(_OUTCOME_KEY, None)
    target = str(candidate.get("url") or "")
    if not target:
        outcome = {
            "kind": "failure",
            "reason": "missing_product_target",
            "attempts": 1,
            "retryable": False,
            "record": _record(candidate, "missing_product_target", 1, False),
        }
        _set_candidate_outcome(candidate, outcome)
        return None
    fetched = _fetch_detail(worker, target)
    if fetched["kind"] == "failure":
        outcome = {**fetched, "record": _record(candidate, fetched["reason"], fetched["attempts"], fetched["retryable"])}
        _set_candidate_outcome(candidate, outcome)
        return None
    evidence = worker.product_detail_evidence(fetched["payload"], "")
    if not worker.has_product_evidence(evidence):
        outcome = {
            "kind": "rejection",
            "reason": "product_detail_missing_evidence",
            "attempts": fetched["attempts"],
            "retryable": False,
            "record": _record(candidate, "product_detail_missing_evidence", fetched["attempts"], False),
        }
        _set_candidate_outcome(candidate, outcome)
        return None
    meta = worker.core.meta_values(fetched["payload"])
    title = meta.get("og:title") or meta.get("twitter:title") or reliability._slug_title(target) or candidate.get("name")
    price = meta.get("product:price:amount") or meta.get("og:price:amount") or candidate.get("price")
    stock = meta.get("product:availability") or candidate.get("stock")
    image = meta.get("og:image") or meta.get("twitter:image") or ""
    route = ("html", target, "product_detail")
    row = worker.core.record(source_id, vendor, route, title, target, evidence, price, stock, image)
    if not row:
        outcome = {
            "kind": "rejection",
            "reason": "product_detail_record_rejected",
            "attempts": fetched["attempts"],
            "retryable": False,
            "record": _record(candidate, "product_detail_record_rejected", fetched["attempts"], False),
        }
        _set_candidate_outcome(candidate, outcome)
        return None
    _set_candidate_outcome(candidate, {"kind": "verified", "attempts": fetched["attempts"], "retryable": False})
    return worker.decorate(row, evidence, "product_detail_metadata")


def _reason_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(record.get("reason") or "unknown") for record in records).items()))


def _fallback_scan(worker: Any, reliability: Any, source: tuple) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_id, vendor, _ = source
    rows: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    for index, target in enumerate(worker.FALLBACK_HTML_ROUTES.get(source_id, []), 1):
        route = ("html", target, "thca_flower")
        started = time.monotonic()
        result: dict[str, Any] = {
            "route_id": f"{source_id}-fallback-{index}",
            "url": target,
            "source_type": "html_card_product_detail",
        }
        try:
            payload, content_type, http_status = worker.core.fetch(target)
            candidates = worker.card_candidates(payload, route)
            extracted: list[dict[str, Any]] = []
            if candidates:
                with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as pool:
                    futures = {
                        pool.submit(_candidate_to_row, worker, reliability, candidate, source_id, vendor): candidate
                        for candidate in candidates
                    }
                    for future in as_completed(futures):
                        candidate = futures[future]
                        try:
                            row = future.result()
                        except Exception as error:
                            retryable = _exception_retryable(worker, error)
                            _set_candidate_outcome(candidate, {
                                "kind": "failure",
                                "reason": "product_detail_worker_error",
                                "attempts": 1,
                                "retryable": retryable,
                                "record": _record(candidate, "product_detail_worker_error", 1, retryable),
                            })
                            row = None
                        if row:
                            extracted.append(row)
            extracted = worker.core.dedupe(extracted)
            failures = [
                outcome["record"]
                for candidate in candidates
                if (outcome := candidate.get(_OUTCOME_KEY, {})).get("kind") == "failure" and outcome.get("record")
            ]
            rejections = [
                outcome["record"]
                for candidate in candidates
                if (outcome := candidate.get(_OUTCOME_KEY, {})).get("kind") == "rejection" and outcome.get("record")
            ]
            result.update(
                http_status=http_status,
                content_type=content_type,
                status="degraded" if failures else "healthy" if extracted else "empty",
                candidates=len(candidates),
                products=len(extracted),
                verification_failures=len(failures),
                verification_failure_reasons=_reason_counts(failures),
                verification_failure_records=failures[:_FAILURE_RECORD_LIMIT],
                verification_rejections=len(rejections),
                verification_rejection_reasons=_reason_counts(rejections),
                retry_attempts=sum(max(0, int((candidate.get(_OUTCOME_KEY) or {}).get("attempts") or 1) - 1) for candidate in candidates),
            )
            rows.extend(extracted)
        except Exception as error:
            result.update(status="error", error=f"{type(error).__name__}: {_bounded_text(error)}")
        result["duration_seconds"] = round(time.monotonic() - started, 3)
        attempts.append(result)
    return worker.core.dedupe(rows), attempts


def _diagnostic_scan_source(worker: Any, reliability: Any, source: tuple) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.monotonic()
    source_id, vendor, _ = source
    raw_products, status = worker.aggregate.scan_all_routes(source)
    products, diagnostics = verify_products_with_diagnostics(worker, reliability, raw_products, source_id, vendor)
    primary_failures = diagnostics["verification_failures"]
    primary_rejections = diagnostics["verification_rejections"]
    verification_route = {
        "route_id": f"{source_id}-product-verification",
        "source_type": "product_detail_verification",
        "status": "degraded" if primary_failures else "healthy" if products else "empty",
        "candidates": diagnostics["discovered_products"],
        "products": diagnostics["verified_products"],
        "verification_failures": len(primary_failures),
        "verification_failure_reasons": _reason_counts(primary_failures),
        "verification_failure_records": primary_failures,
        "verification_rejections": len(primary_rejections),
        "verification_rejection_reasons": _reason_counts(primary_rejections),
        "retry_attempts": diagnostics["retry_attempts"],
    }
    fallback_results: list[dict[str, Any]] = []
    if source_id in worker.FALLBACK_HTML_ROUTES:
        fallback, fallback_results = _fallback_scan(worker, reliability, source)
        products = worker.resolve_route_overlaps([*products, *fallback])
    admitted, reasons, quality = worker.gate(products)
    status = dict(status)
    route_results = [*list(status.get("route_results") or []), verification_route, *fallback_results]
    total_failures = sum(int(route.get("verification_failures") or 0) for route in route_results)
    total_rejections = sum(int(route.get("verification_rejections") or 0) for route in route_results)
    quality = {
        **quality,
        "discovered_products": diagnostics["discovered_products"],
        "verification_failures": total_failures,
        "verification_rejections": total_rejections,
    }
    healthy_routes = [route for route in route_results if route.get("status") == "healthy" and route.get("url")]
    status.update(
        admitted=admitted,
        status="quarantined" if not admitted else "degraded" if total_failures else "healthy",
        products=len(products),
        reason_codes=reasons,
        health_reason_codes=["product_detail_verification_incomplete"] if total_failures else [],
        quality=quality,
        worker="cloud_scan_v2+bounded_product_detail_verifier",
        route_results=route_results,
        routes_attempted=len(route_results),
        active_route=(max(healthy_routes, key=lambda row: int(row.get("products") or 0)).get("url", "") if healthy_routes else ""),
        retry_attempts=sum(int(route.get("retry_attempts") or 0) for route in route_results),
        duration_seconds=round(time.monotonic() - started, 3),
    )
    return products if admitted else [], status


def install(reliability: Any) -> dict[str, Any]:
    worker = reliability.worker
    if getattr(worker, "_product_detail_reliability_installed", False):
        return {"installed": True}

    def verify_products(products: list[dict[str, Any]], source_id: str, vendor: str) -> list[dict[str, Any]]:
        verified, _ = verify_products_with_diagnostics(worker, reliability, products, source_id, vendor)
        return verified

    worker.verify_products = verify_products
    worker.candidate_to_row = lambda candidate, source_id, vendor: _candidate_to_row(
        worker, reliability, candidate, source_id, vendor
    )
    worker.fallback_scan = lambda source: _fallback_scan(worker, reliability, source)
    worker.scan_source = lambda source: _diagnostic_scan_source(worker, reliability, source)
    worker._product_detail_reliability_installed = True
    return {"installed": True}


def self_test(reliability: Any) -> None:
    worker = reliability.worker
    assert getattr(worker, "_product_detail_reliability_installed", False)
    assert PRODUCT_DETAIL_RETRY_DELAYS
    assert RETRYABLE_HTTP
