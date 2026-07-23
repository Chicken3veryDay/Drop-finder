"""Bounded product-detail retries and observable verification outcomes."""
from __future__ import annotations

import re
import time
import urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

PRODUCT_DETAIL_RETRY_DELAYS = (0.0, 1.0, 3.0)
RETRYABLE_HTTP = {202, 408, 425, 429, 500, 502, 503, 504}
MAX_METADATA_DETAIL_TARGETS_PER_SOURCE = 120
LISTING_METADATA_ROUTES: dict[str, tuple[str, ...]] = {
    "plain_jane": (
        "https://plainjane.com/",
        "https://plainjane.com/collections/all?page=3",
    ),
    "gold_canna": (
        "https://goldcanna.com/collections/thca-bulk",
        "https://goldcanna.com/collections/all",
    ),
}
_PRODUCT_CARD = re.compile(r"<product-card\b.*?</product-card>", re.I | re.S)
_PRODUCT_HREF = re.compile(r"href=[\"']([^\"']*/products/[^\"'?#]+)", re.I)
_PLAIN_LINEAGE = re.compile(r"(?:Strain\s+(?:family|profile)\s*:\s*|plainjane-strain-spectrum--)(indica|sativa|hybrid)", re.I)
_GOLD_LINEAGE = re.compile(r"(?:strain-bg-|bs-badge-strain[^>]*>\s*)(indica|sativa|hybrid)", re.I)
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



def _metadata_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().casefold() not in {"", "unknown", "unavailable", "n/a", "none", "-", "—"}
    return bool(value) if isinstance(value, (list, tuple, set, dict)) else True


def _metadata_detail_target(value: Any) -> str:
    target = _bounded_text(value, 1000)
    if not target:
        return ""
    try:
        parsed = urllib.parse.urlsplit(target)
    except ValueError:
        return target
    if not parsed.scheme or not parsed.netloc:
        return target
    path = parsed.path or "/"
    if any(marker in path.casefold() for marker in ("/product/", "/products/", "/shop/")):
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def _metadata_missing_score(product: dict[str, Any]) -> int:
    score = 0
    if not _metadata_present(product.get("description")):
        score += 1
    if not any(_metadata_present(product.get(field)) for field in ("thca", "thca_percent", "delta9_thc", "direct_total_thc", "total_thc")):
        score += 2
    if not (_metadata_present(product.get("rating")) and _metadata_present(product.get("review_count"))):
        score += 2
    if not any(_metadata_present(product.get(field)) for field in ("lineage", "strain_type")):
        score += 1
    if not any(_metadata_present(product.get(field)) for field in ("grow_environment", "environment")):
        score += 1
    if not _metadata_present(product.get("effects")):
        score += 1
    if not _metadata_present(product.get("documents")):
        score += 1
    return score


def _same_product_target(left: Any, right: Any) -> bool:
    return _metadata_detail_target(left).rstrip("/").casefold() == _metadata_detail_target(right).rstrip("/").casefold()


def _detail_row_score(product: dict[str, Any], detail: dict[str, Any]) -> tuple[int, int, int, int, int, int]:
    rating_pair = int(_metadata_present(detail.get("rating")) and _metadata_present(detail.get("review_count")))
    potency = int(any(_metadata_present(detail.get(field)) for field in ("thca", "thca_percent", "delta9_thc", "direct_total_thc", "total_thc")))
    documents = int(_metadata_present(detail.get("documents")))
    classification = int(any(_metadata_present(detail.get(field)) for field in ("lineage", "strain_type", "grow_environment", "environment")))
    description = int(_metadata_present(detail.get("description")))
    target_match = int(_same_product_target(product.get("url"), detail.get("url")))
    return target_match, rating_pair, potency, documents, classification, description


def _select_detail_row(worker: Any, product: dict[str, Any], payload: str, target: str) -> dict[str, Any] | None:
    source_id = _bounded_text(product.get("source_id"), 160)
    vendor = _bounded_text(product.get("vendor"), 200)
    route = ("html", target, "product_detail_enrichment")
    parser = getattr(worker.core, "html_detail", None)
    if not callable(parser):
        return None
    try:
        rows = parser(payload, source_id, vendor, route, target)
    except Exception:
        return None
    candidates = [row for row in rows or [] if isinstance(row, dict)]
    if not candidates:
        return None
    return max(candidates, key=lambda row: _detail_row_score(product, row))


def _merge_detail_metadata(product: dict[str, Any], detail: dict[str, Any], target: str) -> tuple[dict[str, Any], int]:
    merged = dict(product)
    changed = 0
    for field in (
        "description", "thca", "thca_percent", "delta9_thc", "direct_total_thc", "total_thc",
        "lineage", "strain_type", "grow_environment", "environment", "effects",
    ):
        if not _metadata_present(merged.get(field)) and _metadata_present(detail.get(field)):
            merged[field] = detail[field]
            merged[f"{field}_source_path"] = target
            merged[f"{field}_confidence"] = "source_exposed_product_detail"
            changed += 1
    if not (_metadata_present(merged.get("rating")) and _metadata_present(merged.get("review_count"))):
        if _metadata_present(detail.get("rating")) and _metadata_present(detail.get("review_count")):
            merged["rating"] = detail["rating"]
            merged["review_count"] = detail["review_count"]
            merged["rating_source_path"] = target
            merged["review_count_source_path"] = target
            merged["rating_confidence"] = "source_exposed_product_detail"
            merged["review_count_confidence"] = "source_exposed_product_detail"
            changed += 2
    if not _metadata_present(merged.get("image")) and _metadata_present(detail.get("image")):
        merged["image"] = detail["image"]
        changed += 1
    parent_documents = [item for item in merged.get("documents") or [] if isinstance(item, dict)]
    detail_documents = [item for item in detail.get("documents") or [] if isinstance(item, dict)]
    if detail_documents:
        known = {str(item.get("url") or item.get("public_url") or "") for item in parent_documents}
        additions = [item for item in detail_documents if str(item.get("url") or item.get("public_url") or "") not in known]
        if additions:
            merged["documents"] = [*parent_documents, *additions]
            changed += 1
    return merged, changed


def _enrich_authoritative_group(
    worker: Any,
    products: list[dict[str, Any]],
    target: str,
) -> dict[str, Any]:
    fetched = _fetch_detail(worker, target)
    if fetched["kind"] == "failure":
        return {
            "kind": "failure",
            "products": products,
            "target": target,
            "attempts": fetched["attempts"],
            "retryable": fetched["retryable"],
            "record": _record(products[0], f"metadata_{fetched['reason']}", fetched["attempts"], fetched["retryable"]),
        }
    detail = _select_detail_row(worker, products[0], fetched["payload"], target)
    if detail is None:
        return {
            "kind": "empty",
            "products": products,
            "target": target,
            "attempts": fetched["attempts"],
            "record": _record(products[0], "metadata_detail_unavailable", fetched["attempts"], False),
        }
    enriched: list[dict[str, Any]] = []
    changed_fields = 0
    changed_products = 0
    for product in products:
        merged, changed = _merge_detail_metadata(product, detail, target)
        enriched.append(merged)
        changed_fields += changed
        changed_products += int(changed > 0)
    return {
        "kind": "enriched" if changed_fields else "unchanged",
        "products": enriched,
        "target": target,
        "attempts": fetched["attempts"],
        "changed_fields": changed_fields,
        "changed_products": changed_products,
    }


def _enrich_authoritative_products(
    worker: Any,
    reliability: Any,
    products: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    passthrough: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for product in products:
        if not reliability._authoritative_structured_product(product) or _metadata_missing_score(product) == 0:
            passthrough.append(product)
            continue
        target = _metadata_detail_target(product.get("url"))
        if not target:
            passthrough.append(product)
            continue
        grouped[target].append(product)

    ordered = sorted(
        grouped.items(),
        key=lambda item: (-max(_metadata_missing_score(product) for product in item[1]), item[0]),
    )
    selected = ordered[:MAX_METADATA_DETAIL_TARGETS_PER_SOURCE]
    skipped = ordered[MAX_METADATA_DETAIL_TARGETS_PER_SOURCE:]
    for _, group in skipped:
        passthrough.extend(group)

    outcomes: list[dict[str, Any]] = []
    if selected:
        with ThreadPoolExecutor(max_workers=min(8, len(selected))) as pool:
            futures = {
                pool.submit(_enrich_authoritative_group, worker, group, target): (target, group)
                for target, group in selected
            }
            for future in as_completed(futures):
                target, group = futures[future]
                try:
                    outcomes.append(future.result())
                except Exception as error:
                    retryable = _exception_retryable(worker, error)
                    outcomes.append({
                        "kind": "failure",
                        "products": group,
                        "target": target,
                        "attempts": 1,
                        "retryable": retryable,
                        "record": _record(group[0], "metadata_detail_worker_error", 1, retryable),
                    })

    failures: list[dict[str, Any]] = []
    empty: list[dict[str, Any]] = []
    changed_fields = 0
    changed_products = 0
    enriched_targets = 0
    for outcome in outcomes:
        passthrough.extend(outcome.get("products") or [])
        changed_fields += int(outcome.get("changed_fields") or 0)
        changed_products += int(outcome.get("changed_products") or 0)
        enriched_targets += int(outcome.get("kind") == "enriched")
        if outcome.get("kind") == "failure" and outcome.get("record"):
            failures.append(outcome["record"])
        if outcome.get("kind") == "empty" and outcome.get("record"):
            empty.append(outcome["record"])

    return worker.core.dedupe(passthrough), {
        "eligible_targets": len(ordered),
        "attempted_targets": len(selected),
        "enriched_targets": enriched_targets,
        "enriched_products": changed_products,
        "changed_fields": changed_fields,
        "skipped_targets": len(skipped),
        "failures": failures[:_FAILURE_RECORD_LIMIT],
        "empty_results": empty[:_FAILURE_RECORD_LIMIT],
        "retry_attempts": sum(max(0, int(outcome.get("attempts") or 0) - 1) for outcome in outcomes),
    }


def _listing_target(value: Any, base: str) -> str:
    raw = urllib.parse.urljoin(base, str(value or ""))
    return _metadata_detail_target(raw)


def _listing_metadata_from_html(worker: Any, payload: str, route: str) -> dict[str, dict[str, Any]]:
    source = str(payload or "")[:8_000_000]
    metadata: dict[str, dict[str, Any]] = {}

    def merge(target: str, context: str) -> None:
        key = _listing_target(target, route).rstrip("/").casefold()
        if not key:
            return
        current = dict(metadata.get(key) or {})
        lineage_match = _PLAIN_LINEAGE.search(context) or _GOLD_LINEAGE.search(context)
        lineage = lineage_match.group(1) if lineage_match else worker.core.explicit_lineage(context)
        thca = worker.core.first_percent_from_text(context, worker.core.THCA_PATTERNS)
        delta9 = worker.core.first_percent_from_text(context, worker.core.DELTA9_PATTERNS)
        total = worker.core.first_percent_from_text(context, worker.core.TOTAL_THC_PATTERNS)
        rating, review_count = worker.core.embedded_rating_pair(context)
        if lineage and not current.get("strain_type"):
            current["strain_type"] = lineage
        if thca is not None and current.get("thca") in (None, ""):
            current["thca"] = thca
        if delta9 is not None and current.get("delta9_thc") in (None, ""):
            current["delta9_thc"] = delta9
        if total is not None and current.get("direct_total_thc") in (None, ""):
            current["direct_total_thc"] = total
        if rating is not None and review_count is not None and current.get("rating") in (None, ""):
            current["rating"] = rating
            current["review_count"] = review_count
        if current:
            current["source_path"] = route
            metadata[key] = current

    for match in _PRODUCT_CARD.finditer(source):
        block = match.group(0)
        href = _PRODUCT_HREF.search(block)
        if href:
            merge(href.group(1), block)

    anchors = list(_PRODUCT_HREF.finditer(source))
    for index, match in enumerate(anchors):
        start = max(0, match.start() - 900)
        end = min(len(source), match.end() + 3200)
        if index + 1 < len(anchors):
            end = min(end, anchors[index + 1].start() + 700)
        merge(match.group(1), source[start:end])
    return metadata


def _enrich_listing_metadata(
    worker: Any,
    products: list[dict[str, Any]],
    source_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    routes = LISTING_METADATA_ROUTES.get(source_id, ())
    if not routes or not products:
        return products, {"routes": 0, "records": 0, "enriched_products": 0, "changed_fields": 0, "failures": []}
    metadata: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    retry_attempts = 0
    for route in routes:
        fetched = _fetch_detail(worker, route)
        retry_attempts += max(0, int(fetched.get("attempts") or 1) - 1)
        if fetched.get("kind") == "failure":
            failures.append({"url": route, "reason": fetched.get("reason"), "attempts": fetched.get("attempts")})
            continue
        for key, value in _listing_metadata_from_html(worker, fetched["payload"], route).items():
            current = dict(metadata.get(key) or {})
            for field, field_value in value.items():
                if field_value not in (None, "", [], {}) and current.get(field) in (None, "", [], {}):
                    current[field] = field_value
            metadata[key] = current
    output: list[dict[str, Any]] = []
    changed_fields = 0
    enriched_products = 0
    for product in products:
        key = _metadata_detail_target(product.get("url")).rstrip("/").casefold()
        evidence = metadata.get(key) or {}
        merged = dict(product)
        changed = 0
        source_path = str(evidence.get("source_path") or "")
        for field in ("strain_type", "thca", "delta9_thc", "direct_total_thc"):
            if not _metadata_present(merged.get(field)) and _metadata_present(evidence.get(field)):
                merged[field] = evidence[field]
                merged[f"{field}_source_path"] = source_path
                merged[f"{field}_confidence"] = "source_exposed_listing_card"
                changed += 1
        if not (_metadata_present(merged.get("rating")) and _metadata_present(merged.get("review_count"))):
            if _metadata_present(evidence.get("rating")) and _metadata_present(evidence.get("review_count")):
                merged["rating"] = evidence["rating"]
                merged["review_count"] = evidence["review_count"]
                merged["rating_source_path"] = source_path
                merged["review_count_source_path"] = source_path
                changed += 2
        output.append(merged)
        changed_fields += changed
        enriched_products += int(changed > 0)
    return worker.core.dedupe(output), {
        "routes": len(routes),
        "records": len(metadata),
        "enriched_products": enriched_products,
        "changed_fields": changed_fields,
        "retry_attempts": retry_attempts,
        "failures": failures[:_FAILURE_RECORD_LIMIT],
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
    del vendor
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
    enriched, enrichment = _enrich_authoritative_products(worker, reliability, verified)
    enriched, listing_enrichment = _enrich_listing_metadata(worker, enriched, source_id)
    enrichment = {**enrichment, "listing_metadata": listing_enrichment}
    return enriched, {
        "discovered_products": len(discovered),
        "verified_products": len(enriched),
        "verification_failures": failures[:_FAILURE_RECORD_LIMIT],
        "verification_rejections": rejections[:_FAILURE_RECORD_LIMIT],
        "retry_attempts": (
            sum(max(0, int(outcome.get("attempts") or 0) - 1) for outcome in outcomes)
            + int(enrichment.get("retry_attempts") or 0)
            + int(listing_enrichment.get("retry_attempts") or 0)
        ),
        "metadata_enrichment": enrichment,
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
            accepted = extracted if not failures else []
            result.update(
                http_status=http_status,
                content_type=content_type,
                status="degraded" if failures else "healthy" if extracted else "empty",
                candidates=len(candidates),
                products=len(extracted),
                admitted_products=len(accepted),
                verification_failures=len(failures),
                verification_failure_reasons=_reason_counts(failures),
                verification_failure_records=failures[:_FAILURE_RECORD_LIMIT],
                verification_rejections=len(rejections),
                verification_rejection_reasons=_reason_counts(rejections),
                retry_attempts=sum(max(0, int((candidate.get(_OUTCOME_KEY) or {}).get("attempts") or 1) - 1) for candidate in candidates),
            )
            rows.extend(accepted)
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
        "metadata_enrichment": diagnostics.get("metadata_enrichment") or {},
    }
    fallback_results: list[dict[str, Any]] = []
    if source_id in worker.FALLBACK_HTML_ROUTES:
        fallback, fallback_results = _fallback_scan(worker, reliability, source)
        products = worker.resolve_route_overlaps([*products, *fallback])
    admitted, reasons, quality = worker.gate(products)
    status = dict(status)
    retrieval_routes = list(status.get("route_results") or [])
    if (
        not products
        and reasons == ["no_qualifying_products"]
        and retrieval_routes
        and all(int(route.get("http_status") or 0) == 403 for route in retrieval_routes)
    ):
        reasons = ["source_access_forbidden"]
    route_results = [*retrieval_routes, verification_route, *fallback_results]
    total_failures = sum(int(route.get("verification_failures") or 0) for route in route_results)
    blocking_failures = len(primary_failures)
    total_rejections = sum(int(route.get("verification_rejections") or 0) for route in route_results)
    quality = {
        **quality,
        "discovered_products": diagnostics["discovered_products"],
        "verification_failures": total_failures,
        "blocking_verification_failures": blocking_failures,
        "verification_rejections": total_rejections,
    }
    healthy_routes = [route for route in route_results if route.get("status") == "healthy" and route.get("url")]
    status.update(
        admitted=admitted,
        status="quarantined" if not admitted else "degraded" if blocking_failures else "healthy",
        products=len(products),
        reason_codes=reasons,
        health_reason_codes=["product_detail_verification_incomplete"] if blocking_failures else [],
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
