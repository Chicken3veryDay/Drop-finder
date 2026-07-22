"""Validated custom storefront-route registry for the autonomous worker."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "data" / "vendor_expansion.json"
SUPPORTED_ROUTE_TYPES = frozenset({"shopify", "woo", "html"})
MINIMUM_EXPANSION_VENDORS = 20
PRODUCTION_SHARD_COUNT = 6

# Relative live-CI costs observed from repeated bounded production scans. The
# values are only scheduling hints. They never change source routes, parsers,
# evidence gates, or publication semantics.
SOURCE_COST_HINTS = {
    "hello_mary": 180,
    "cali_canna": 160,
    "five_leaf_wellness": 130,
    "bay_smokes": 110,
    "dr_ganja": 90,
    "exhale_wellness": 80,
    "wnc_cbd": 300,
    "eight_horses_hemp": 70,
    "green_unicorn_farms": 70,
    "holy_city_farms": 60,
    "hemp_hop": 60,
    "veteran_grown_hemp": 50,
}


def _source_cost(worker: Any, source: tuple[Any, Any, Any]) -> int:
    source_id, _vendor, routes = source
    route_count = len(routes) if isinstance(routes, (list, tuple)) else 0
    fallback_count = len(worker.FALLBACK_HTML_ROUTES.get(str(source_id), []))
    return SOURCE_COST_HINTS.get(str(source_id), 10 + route_count * 8 + fallback_count * 5)


def balance_sources(worker: Any, shard_count: int = PRODUCTION_SHARD_COUNT) -> tuple[tuple[str, ...], ...]:
    """Reorder sources so index-modulo sharding spreads expensive storefronts.

    The worker's stable shard contract selects ``index % shard_count``. This
    builds capacity-bounded greedy bins, then interleaves those bins so each
    modulo partition receives one source per row. Every source appears exactly
    once and source identity remains unchanged.
    """
    sources = list(worker.core.SOURCES)
    if shard_count < 1:
        raise ValueError("shard_count must be positive")
    if len(sources) < 2:
        return tuple((str(source[0]),) for source in sources)

    quotient, remainder = divmod(len(sources), shard_count)
    capacities = [quotient + (1 if index < remainder else 0) for index in range(shard_count)]
    bins: list[list[tuple[Any, Any, Any]]] = [[] for _ in range(shard_count)]
    loads = [0] * shard_count

    ordered = sorted(
        sources,
        key=lambda source: (-_source_cost(worker, source), str(source[0])),
    )
    for source in ordered:
        candidates = [index for index in range(shard_count) if len(bins[index]) < capacities[index]]
        target = min(candidates, key=lambda index: (loads[index], len(bins[index]), index))
        bins[target].append(source)
        loads[target] += _source_cost(worker, source)

    interleaved: list[tuple[Any, Any, Any]] = []
    for row in range(max(capacities, default=0)):
        for index in range(shard_count):
            if row < len(bins[index]):
                interleaved.append(bins[index][row])
    worker.core.SOURCES[:] = interleaved
    return tuple(tuple(str(source[0]) for source in bucket) for bucket in bins)


def load_registry(path: str | Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "dropfinder-vendor-expansion-v1":
        raise ValueError("unsupported vendor expansion schema")
    vendors = payload.get("vendors")
    if not isinstance(vendors, list) or len(vendors) < MINIMUM_EXPANSION_VENDORS:
        raise ValueError(f"vendor expansion must contain at least {MINIMUM_EXPANSION_VENDORS} vendors")

    seen: set[str] = set()
    for index, vendor in enumerate(vendors):
        if not isinstance(vendor, dict):
            raise ValueError(f"vendors[{index}] must be an object")
        vendor_id = str(vendor.get("vendor_id") or "").strip()
        vendor_name = str(vendor.get("vendor_name") or "").strip()
        if not vendor_id or not vendor_name:
            raise ValueError(f"vendors[{index}] is missing vendor identity")
        if vendor_id in seen:
            raise ValueError(f"duplicate vendor_id: {vendor_id}")
        seen.add(vendor_id)
        routes = vendor.get("routes")
        if not isinstance(routes, list) or not routes:
            raise ValueError(f"{vendor_id}: routes missing")
        for route_index, route in enumerate(routes):
            if not isinstance(route, dict):
                raise ValueError(f"{vendor_id}.routes[{route_index}] must be an object")
            route_type = str(route.get("type") or "")
            route_url = str(route.get("url") or "")
            scope = str(route.get("scope") or "")
            if route_type not in SUPPORTED_ROUTE_TYPES:
                raise ValueError(f"{vendor_id}: unsupported route type {route_type!r}")
            if not route_url.startswith("https://"):
                raise ValueError(f"{vendor_id}: route must use https")
            if not scope:
                raise ValueError(f"{vendor_id}: route scope missing")
        age = vendor.get("age_verification")
        if not isinstance(age, dict) or not age.get("classification") or not age.get("display"):
            raise ValueError(f"{vendor_id}: age verification metadata missing")
    return payload


def apply_registry(worker: Any, payload: dict[str, Any]) -> tuple[str, ...]:
    """Install expansion sources without weakening the worker's admission gates."""
    existing = {str(source[0]) for source in worker.core.SOURCES}
    installed: list[str] = []
    product_paths = list(worker.PRODUCT_PATHS)

    for vendor in payload["vendors"]:
        vendor_id = str(vendor["vendor_id"])
        if vendor_id not in existing:
            routes = [
                (str(route["type"]), str(route["url"]), str(route["scope"]))
                for route in vendor["routes"]
            ]
            worker.core.SOURCES.append((vendor_id, str(vendor["vendor_name"]), routes))
            existing.add(vendor_id)
            installed.append(vendor_id)

        fallbacks = [str(url) for url in vendor.get("fallback_html_routes") or [] if str(url).startswith("https://")]
        if fallbacks:
            current = list(worker.FALLBACK_HTML_ROUTES.get(vendor_id, []))
            worker.FALLBACK_HTML_ROUTES[vendor_id] = list(dict.fromkeys([*current, *fallbacks]))

        for path in vendor.get("product_paths") or []:
            value = str(path)
            if value.startswith("/") and value not in product_paths:
                product_paths.append(value)

    worker.PRODUCT_PATHS = tuple(product_paths)
    # The registry documents vendors; route_repair owns current canonical paths
    # and first-party product-detail extraction fallbacks. source_recovery adds
    # audited current paths and defers final parser hooks until runtime composition.
    try:
        from route_repair import apply_route_repairs, install as install_route_repairs
        from source_recovery import install as install_source_recovery
    except ImportError:
        from scripts.route_repair import apply_route_repairs, install as install_route_repairs
        from scripts.source_recovery import install as install_source_recovery

    parser_capabilities = (
        hasattr(worker, "run")
        and hasattr(worker, "card_candidates")
        and hasattr(worker, "product_detail_evidence")
        and hasattr(worker.core, "meta_values")
    )
    if parser_capabilities:
        install_route_repairs(worker)
        install_source_recovery(worker)
        balance_sources(worker)
    else:
        apply_route_repairs(worker)
    return tuple(installed)


def public_age_index(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Create the browser-safe age-control lookup from one or more registries."""
    by_id: dict[str, dict[str, Any]] = {}
    generated_at = ""
    for payload in payloads:
        generated_at = max(generated_at, str(payload.get("generated_at") or ""))
        vendors = payload.get("vendors") if isinstance(payload, dict) else None
        if not isinstance(vendors, list):
            continue
        for vendor in vendors:
            if not isinstance(vendor, dict):
                continue
            vendor_id = str(vendor.get("vendor_id") or vendor.get("source_id") or "").strip()
            vendor_name = str(vendor.get("vendor_name") or vendor.get("name") or "").strip()
            if not vendor_id or not vendor_name:
                continue
            age = vendor.get("age_verification") if isinstance(vendor.get("age_verification"), dict) else {}
            classification = str(age.get("classification") or vendor.get("age_gate_classification") or "uncertain")
            display = str(age.get("display") or _display_for_classification(classification))
            evidence = vendor.get("evidence") if isinstance(vendor.get("evidence"), list) else []
            evidence_url = str(age.get("evidence_url") or vendor.get("age_gate_evidence_reference") or "")
            if not evidence_url:
                for item in evidence:
                    if isinstance(item, dict) and item.get("evidence_type") == "storefront_or_category" and item.get("url"):
                        evidence_url = str(item["url"])
                        break
            by_id[vendor_id] = {
                "vendor_id": vendor_id,
                "vendor_name": vendor_name,
                "classification": classification,
                "display": display,
                "provider": str(age.get("provider") or "none_observed"),
                "scope": str(age.get("scope") or "unknown"),
                "summary": str(age.get("summary") or "Age-control details have not been confirmed."),
                "evidence_url": evidence_url,
                "observed_at": str(age.get("observed_at") or vendor.get("verified_at") or ""),
                "status": str(age.get("status") or "current"),
            }
    return {
        "schema_version": "dropfinder-vendor-age-index-v1",
        "generated_at": generated_at,
        "vendor_count": len(by_id),
        "vendors": [by_id[key] for key in sorted(by_id)],
    }


def _display_for_classification(classification: str) -> str:
    if classification in {"identity_verification_required", "identity_verification_conditional"}:
        return "verification"
    if classification == "self_attestation_21_plus":
        return "confirmation"
    if classification == "no_observed_gate":
        return "no_gate_observed"
    return "unknown"
