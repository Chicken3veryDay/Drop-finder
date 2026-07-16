#!/usr/bin/env python3
"""Publish the type-aware DropFinder catalog with durable route diagnostics.

The generalized publication module owns product admission and serialization. This
entry point adds the repository-specific source-health policy: every attempted
route is retained in a bounded public shape while source admission remains a
separate, source-level decision.
"""
from __future__ import annotations

import json
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
    "verification_failures",
    "verification_failure_reasons",
    "duration_seconds",
    "retry_attempt",
)
_ERROR_LIMIT = 300

_original_merge = publication.merge
_original_self_test = publication.self_test


def _public_route_result(route: dict[str, Any]) -> dict[str, Any]:
    """Return the bounded, non-secret route diagnostic contract."""
    public: dict[str, Any] = {}
    for field in _PUBLIC_ROUTE_FIELDS:
        value = route.get(field)
        if value not in (None, ""):
            public[field] = value
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
    verification_failures = sum(int(route.get("verification_failures") or 0) for route in route_results)
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

    return {
        "source_id": row.get("source_id"),
        "name": row.get("name"),
        "enabled": True,
        "status": "healthy",
        "products": accepted_count,
        "active_route": active_route,
        "routes_attempted": len(route_results),
        "healthy_routes": healthy_routes,
        "non_healthy_routes": non_healthy_routes,
        "verification_failures": verification_failures,
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
    status["verification_failures"] = sum(int(source.get("verification_failures") or 0) for source in sources)
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
                "verification_failures": 2,
                "verification_failure_reasons": {
                    "product_detail_fetch_error": 1,
                    "product_detail_missing_evidence": 1,
                },
                "retry_attempt": 2,
            },
        ]
        (input_dir / "shard-0.json").write_text(
            json.dumps(
                {
                    "schema_version": publication.SHARD_SCHEMA,
                    "products": [product],
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
        assert source["status"] == "healthy"
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
        assert status["healthy_routes"] == 1
        assert status["non_healthy_routes"] == 1
        assert status["verification_failures"] == 2
        assert status["fallback_active_sources"] == 1
    return 0


publication._source_status = _source_status
publication.merge = merge
publication.self_test = self_test


if __name__ == "__main__":
    raise SystemExit(publication.main())
