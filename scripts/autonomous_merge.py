#!/usr/bin/env python3
"""Publish the type-aware DropFinder catalog with durable route diagnostics.

The generalized publication module owns product admission and serialization. This
entry point adds the repository-specific source-health policy: every attempted
route is retained in a bounded public shape while source admission remains a
separate, source-level decision.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from multi_product import publication

_PUBLIC_ROUTE_FIELDS = (
    "route_id",
    "url",
    "source_type",
    "status",
    "http_status",
    "content_type",
    "products",
    "candidates",
    "duration_seconds",
    "retry_attempt",
    "retry_attempts",
    "verification_rejections",
    "admitted_products",
)
_ERROR_LIMIT = 300
_VERIFICATION_REASON = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_MAX_VERIFICATION_REASONS = 12
_MAX_VERIFICATION_FAILURES = 100_000
_MAX_VERIFICATION_RECORDS = 24

_original_merge = publication.merge
_original_self_test = publication.self_test
_original_reject_reason = publication.reject_reason


def reject_reason(product: dict[str, Any]) -> str | None:
    """Reject the legacy self-validating listing-card provenance at publication."""
    evidence = product.get("classification_evidence")
    if (
        isinstance(evidence, dict)
        and evidence.get("evidence_source") == "product_card_title_or_url"
    ):
        return "unverified_listing_card_evidence"
    return _original_reject_reason(product)


def _public_verification_reasons(value: Any) -> dict[str, int]:
    """Normalize fixed diagnostic reason codes into a bounded public shape."""
    if not isinstance(value, dict):
        return {}
    public: dict[str, int] = {}
    for raw_key in sorted(value, key=lambda key: str(key)):
        if len(public) >= _MAX_VERIFICATION_REASONS:
            break
        key = str(raw_key)
        if not _VERIFICATION_REASON.fullmatch(key):
            continue
        try:
            count = int(value[raw_key])
        except (TypeError, ValueError):
            continue
        if count > 0:
            public[key] = min(count, _MAX_VERIFICATION_FAILURES)
    return public


def _public_verification_records(value: Any) -> list[dict[str, Any]]:
    """Retain a bounded, non-secret product verification failure ledger."""
    if not isinstance(value, list):
        return []
    records: list[dict[str, Any]] = []
    for item in value:
        if len(records) >= _MAX_VERIFICATION_RECORDS:
            break
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason") or "")
        if not _VERIFICATION_REASON.fullmatch(reason):
            continue
        try:
            attempts = max(1, min(int(item.get("attempts") or 1), 10))
        except (TypeError, ValueError):
            attempts = 1
        record = {
            "product_id": str(item.get("product_id") or "")[:160],
            "url": str(item.get("url") or "")[:500],
            "reason": reason,
            "attempts": attempts,
            "retryable": bool(item.get("retryable")),
        }
        records.append(record)
    return records


def _public_route_result(route: dict[str, Any]) -> dict[str, Any]:
    """Return the bounded, non-secret route diagnostic contract."""
    public: dict[str, Any] = {}
    for field in _PUBLIC_ROUTE_FIELDS:
        value = route.get(field)
        if value not in (None, ""):
            public[field] = value
    reasons = _public_verification_reasons(route.get("verification_failure_reasons"))
    if reasons:
        public["verification_failure_reasons"] = reasons
        public["verification_failures"] = min(sum(reasons.values()), _MAX_VERIFICATION_FAILURES)
    else:
        try:
            failures = int(route.get("verification_failures") or 0)
        except (TypeError, ValueError):
            failures = 0
        if failures > 0:
            public["verification_failures"] = min(failures, _MAX_VERIFICATION_FAILURES)
    records = _public_verification_records(route.get("verification_failure_records"))
    if records:
        public["verification_failure_records"] = records
    rejection_reasons = _public_verification_reasons(route.get("verification_rejection_reasons"))
    if rejection_reasons:
        public["verification_rejection_reasons"] = rejection_reasons
        public["verification_rejections"] = min(sum(rejection_reasons.values()), _MAX_VERIFICATION_FAILURES)
    error = route.get("error")
    if error not in (None, ""):
        public["error"] = str(error)[:_ERROR_LIMIT]
    return public


def _source_status(row: dict[str, Any], accepted_count: int, rejected_count: int) -> dict[str, Any]:
    quality = dict(row.get("quality") or {})
    quality["products"] = accepted_count
    quality["rejected_products"] = rejected_count

    route_results = [
        _public_route_result(route)
        for route in row.get("route_results", [])
        if isinstance(route, dict)
    ]
    healthy_routes = sum(route.get("status") == "healthy" for route in route_results)
    non_healthy_routes = len(route_results) - healthy_routes
    verification_failures = min(
        sum(int(route.get("verification_failures") or 0) for route in route_results),
        _MAX_VERIFICATION_FAILURES,
    )
    try:
        blocking_verification_failures = int(
            quality.get("blocking_verification_failures", verification_failures)
        )
    except (TypeError, ValueError):
        blocking_verification_failures = verification_failures
    blocking_verification_failures = max(
        0, min(blocking_verification_failures, _MAX_VERIFICATION_FAILURES)
    )
    active_route = str(row.get("active_route") or "")
    fallback_active = any(
        route.get("status") == "healthy"
        and route.get("url") == active_route
        and (
            "fallback" in str(route.get("route_id") or "").casefold()
            or "fallback" in str(route.get("source_type") or "").casefold()
        )
        for route in route_results
    )

    source_status = str(row.get("status") or "")
    public_status = (
        "degraded"
        if blocking_verification_failures > 0 or source_status == "degraded"
        else "healthy"
    )

    return {
        "source_id": row.get("source_id"),
        "name": row.get("name"),
        "enabled": True,
        "status": public_status,
        "products": accepted_count,
        "active_route": active_route,
        "routes_attempted": len(route_results),
        "healthy_routes": healthy_routes,
        "non_healthy_routes": non_healthy_routes,
        "verification_failures": verification_failures,
        "blocking_verification_failures": blocking_verification_failures,
        "fallback_active": fallback_active,
        "retry_attempts": max(
            (int(route.get("retry_attempt") or 1) for route in route_results),
            default=int(row.get("retry_attempts") or 0),
        ),
        "duration_seconds": row.get("duration_seconds", 0),
        "quality": quality,
        "route_results": route_results,
    }


def merge(input_dir: Path, output_dir: Path, min_active: int, min_products: int) -> dict[str, Any]:
    runtime = _original_merge(input_dir, output_dir, min_active, min_products)
    status_path = output_dir / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    sources = status.get("sources") or []
    status["healthy_routes"] = sum(int(source.get("healthy_routes") or 0) for source in sources)
    status["non_healthy_routes"] = sum(int(source.get("non_healthy_routes") or 0) for source in sources)
    status["active_verification_failures"] = min(
        sum(
            int(
                source.get(
                    "blocking_verification_failures",
                    source.get("verification_failures") or 0,
                )
                or 0
            )
            for source in sources
        ),
        _MAX_VERIFICATION_FAILURES,
    )
    status["diagnostic_verification_failures"] = min(
        sum(int(source.get("verification_failures") or 0) for source in sources),
        _MAX_VERIFICATION_FAILURES,
    )
    status["fallback_active_sources"] = sum(bool(source.get("fallback_active")) for source in sources)
    status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return runtime


def self_test(root: Path) -> int:
    _original_self_test(root)

    with TemporaryDirectory(prefix="dropfinder-route-health-") as temp_dir:
        temp = Path(temp_dir)
        input_dir = temp / "input"
        output_dir = temp / "output"
        input_dir.mkdir(parents=True)
        product = publication._fixture(
            product_id="flower",
            primary_type=publication.CANNABIS_FLOWER,
            name="Blue Dream THCA Flower",
            url="https://example.test/products/flower",
            evidence={"explicit_thca": True, "explicit_flower": True, "explicit_vape": False},
        )
        detail_verified = dict(product)
        detail_verified["classification_evidence"] = {
            **product["classification_evidence"],
            "evidence_source": "product_detail_metadata",
        }
        structured = dict(product)
        structured["classification_evidence"] = {
            **product["classification_evidence"],
            "evidence_source": "storefront_record",
        }
        card_derived = dict(product)
        card_derived["classification_evidence"] = {
            **product["classification_evidence"],
            "evidence_source": "product_card_title_or_url",
        }
        assert publication.reject_reason(detail_verified) is None
        assert publication.reject_reason(structured) is None
        assert publication.reject_reason(card_derived) == "unverified_listing_card_evidence"

        routes = [
            {
                "route_id": "a-1",
                "url": "https://example.test/primary",
                "source_type": "shopify",
                "status": "http_error",
                "http_status": 429,
                "retry_attempt": 1,
                "error": "HTTP 429",
                "response_body": "must-not-publish",
                "headers": {"authorization": "must-not-publish"},
            },
            {
                "route_id": "a-fallback-1",
                "url": "https://example.test/fallback",
                "source_type": "html_card_product_detail",
                "status": "healthy",
                "http_status": 200,
                "products": 1,
                "candidates": 3,
                "verification_failures": 999,
                "verification_failure_reasons": {
                    "product_detail_fetch_error": 1,
                    "product_detail_missing_evidence": 1,
                    "../must_not_publish": 25,
                    "negative_count": -4,
                },
                "retry_attempt": 2,
            },
        ]
        (input_dir / "shard-0.json").write_text(
            json.dumps(
                {
                    "schema_version": publication.SHARD_SCHEMA,
                    "products": [detail_verified],
                    "sources": [
                        {
                            "source_id": "a",
                            "name": "A",
                            "admitted": True,
                            "status": "healthy",
                            "products": 1,
                            "active_route": "https://example.test/fallback",
                            "routes_attempted": len(routes),
                            "route_results": routes,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        merge(input_dir, output_dir, 1, 1)
        status = json.loads((output_dir / "status.json").read_text(encoding="utf-8"))
        source = status["sources"][0]
        assert source["status"] == "degraded"
        assert source["routes_attempted"] == 2
        assert source["healthy_routes"] == 1
        assert source["non_healthy_routes"] == 1
        assert source["verification_failures"] == 2
        assert source["fallback_active"] is True
        assert source["retry_attempts"] == 2
        assert [route["status"] for route in source["route_results"]] == ["http_error", "healthy"]
        assert source["route_results"][0]["http_status"] == 429
        assert source["route_results"][1]["verification_failures"] == 2
        assert source["route_results"][1]["verification_failure_reasons"] == {
            "product_detail_fetch_error": 1,
            "product_detail_missing_evidence": 1,
        }
        assert "response_body" not in source["route_results"][0]
        assert "headers" not in source["route_results"][0]
        assert "../must_not_publish" not in source["route_results"][1]["verification_failure_reasons"]
        assert "negative_count" not in source["route_results"][1]["verification_failure_reasons"]
        assert status["healthy_routes"] == 1
        assert status["non_healthy_routes"] == 1
        assert status["active_verification_failures"] == 2
        assert status["fallback_active_sources"] == 1
    return 0


publication.reject_reason = reject_reason
publication._source_status = _source_status
publication.merge = merge
publication.self_test = self_test


if __name__ == "__main__":
    raise SystemExit(publication.main())
