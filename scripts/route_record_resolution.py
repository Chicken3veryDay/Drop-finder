"""Deterministic duplicate resolution for scanner route candidates."""
from __future__ import annotations

import json
from typing import Any, Iterable

_SOURCE_AUTHORITY = {
    "shopify": 50,
    "woo": 50,
    "json_ld_product": 40,
    "html_product_detail": 30,
    "html_card_product_detail": 20,
    "html": 10,
}
_FILLABLE_FIELDS = ("availability", "price", "grams", "image", "thca")


def _is_present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _is_supported(field: str, value: Any) -> bool:
    if field == "availability":
        return str(value or "").strip().lower() in {"in_stock", "out_of_stock"}
    if field in {"price", "grams", "thca"}:
        try:
            return float(value) > 0
        except (TypeError, ValueError):
            return False
    return _is_present(value)


def _route_authority(row: dict[str, Any]) -> int:
    return _SOURCE_AUTHORITY.get(str(row.get("source_type") or "").strip().lower(), 0)


def _fingerprint(row: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in row.items()
        if key not in {"contributing_routes", "resolution_provenance"}
    }
    return json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)


def _quality(row: dict[str, Any]) -> tuple[Any, ...]:
    evidence = sum(_is_supported(field, row.get(field)) for field in _FILLABLE_FIELDS)
    return (
        int(not bool(row.get("stale"))),
        int(_is_supported("availability", row.get("availability"))),
        _route_authority(row),
        evidence,
        int(_is_present(row.get("source_weight_label"))),
        str(row.get("collected_at") or ""),
        _fingerprint(row),
    )


def _normalized_value(field: str, value: Any) -> Any:
    if field in {"price", "grams", "thca"}:
        try:
            return round(float(value), 8)
        except (TypeError, ValueError):
            return None
    return str(value or "").strip().lower() if field == "availability" else value


def _route_reference(row: dict[str, Any]) -> dict[str, str]:
    return {
        "source_type": str(row.get("source_type") or ""),
        "route_url": str(row.get("route_url") or ""),
    }


def _merge_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted((dict(row) for row in candidates), key=_quality, reverse=True)
    winner = ranked[0]
    filled_fields: dict[str, str] = {}
    conflict_fields: list[str] = []

    for field in _FILLABLE_FIELDS:
        supported = [row for row in ranked if _is_supported(field, row.get(field))]
        distinct = {
            _normalized_value(field, row.get(field))
            for row in supported
        }
        distinct.discard(None)
        if len(distinct) > 1:
            conflict_fields.append(field)
        if _is_supported(field, winner.get(field)) or not supported:
            continue
        source = supported[0]
        winner[field] = source[field]
        filled_fields[field] = str(source.get("source_type") or "")
        if field == "grams":
            winner["source_weight_label"] = source.get("source_weight_label") or ""
            winner["weight_provenance"] = source.get("weight_provenance") or "unavailable"

    try:
        price = float(winner.get("price"))
        grams = float(winner.get("grams"))
        winner["price_per_gram"] = round(price / grams, 4) if price > 0 and grams > 0 else None
    except (TypeError, ValueError, ZeroDivisionError):
        winner["price_per_gram"] = None

    route_map = {
        (reference["source_type"], reference["route_url"]): reference
        for reference in (_route_reference(row) for row in ranked)
    }
    winner["contributing_routes"] = [route_map[key] for key in sorted(route_map)]
    if len(ranked) > 1:
        winner["resolution_provenance"] = {
            "method": "deterministic_quality_merge_v1",
            "candidate_count": len(ranked),
            "winning_source_type": str(winner.get("source_type") or ""),
            "winning_route_url": str(winner.get("route_url") or ""),
            "filled_fields": dict(sorted(filled_fields.items())),
            "conflict_fields": sorted(conflict_fields),
        }
    return winner


def resolve_records(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve duplicate scanner rows without using traversal order as authority."""
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = (
            str(row.get("source_id") or ""),
            str(row.get("url") or ""),
            str(row.get("variant") or ""),
        )
        grouped.setdefault(key, []).append(row)
    resolved = [_merge_candidates(grouped[key]) for key in sorted(grouped)]
    return sorted(
        resolved,
        key=lambda row: (
            str(row.get("vendor") or ""),
            str(row.get("name") or ""),
            row.get("price") if row.get("price") is not None else 1e12,
        ),
    )
