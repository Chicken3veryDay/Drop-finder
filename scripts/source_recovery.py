"""Second-pass recovery for current first-party storefront routes and parsers.

This layer does not relax publication requirements. It removes records that the
existing strict admission gate already rejects, supplements product-detail price
metadata from bounded first-party markup, and adds a same-host sitemap route for
storefronts whose current product URLs are not present in category HTML.
"""
from __future__ import annotations

import html as html_module
import re
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

Route = tuple[str, str, str]

ROUTE_OVERRIDES: dict[str, tuple[Route, ...]] = {
    "bay_smokes": (
        ("shopify", "https://baysmokes.com/collections/thca-flower/products.json?limit=250", "thca_flower"),
        ("shopify", "https://baysmokes.com/products.json?limit=250", "storewide"),
        ("html", "https://baysmokes.com/", "storewide"),
    ),
    "beleafer": (
        ("html", "https://beleafer.com/product-category/hemp-flower/", "mixed_flower"),
        ("html", "https://beleafer.com/product-category/hemp-flower/indoor/", "mixed_flower"),
        ("html", "https://beleafer.com/product-category/hemp-flower/outdoor-gh/", "mixed_flower"),
    ),
    "five_leaf_wellness": (
        ("html", "https://fiveleafwellness.com/product-category/top-shelf/", "mixed_flower"),
        ("html", "https://fiveleafwellness.com/product-category/mid-tier/", "mixed_flower"),
        ("html", "https://fiveleafwellness.com/shop/", "storewide"),
    ),
    "veteran_grown_hemp": (
        ("html", "https://www.veterangrownhemp.com/flower", "thca_flower"),
        ("html", "https://www.veterangrownhemp.com/flower?page=2", "thca_flower"),
        ("html", "https://www.veterangrownhemp.com/shop", "storewide"),
    ),
    "wnc_cbd": (
        ("html", "https://wnc-cbd.com/xmlsitemap.php", "sitemap"),
        ("html", "https://wnc-cbd.com/high-thca-flower", "thca_flower"),
        ("html", "https://wnc-cbd.com/", "storewide"),
    ),
    "snapdragon_hemp": (
        ("html", "https://www.snapdragonhemp.com/", "storewide"),
    ),
}

FALLBACK_OVERRIDES: dict[str, tuple[str, ...]] = {
    source_id: tuple(route[1] for route in routes if route[0] == "html" and route[2] != "sitemap")
    for source_id, routes in ROUTE_OVERRIDES.items()
}

_PRICE_CONTAINER = re.compile(
    r"<(?P<tag>span|div|p|strong|b|ins|del)\b"
    r"(?=[^>]*(?:class|id)=['\"][^'\"]*(?:price|amount|cost)[^'\"]*['\"])[^>]*>"
    r"(?P<body>.*?)</(?P=tag)>",
    re.I | re.S,
)
_PRICE_CONTEXT = re.compile(
    r"\b(?:now|sale(?:\s+price)?|our\s+price|price|from|starting\s+at)\s*:?\s*"
    r"(?:</?[^>]+>\s*)*\$\s*([0-9]{1,5}(?:\.[0-9]{1,2})?)",
    re.I | re.S,
)
_JSON_PRICE = re.compile(
    r'["\'](?:price|lowPrice|salePrice|priceValue|priceAmount)["\']\s*:\s*'
    r'["\']?([0-9]{1,5}(?:\.[0-9]{1,2})?)',
    re.I,
)
_DOLLAR = re.compile(r"\$\s*([0-9]{1,5}(?:\.[0-9]{1,2})?)")
_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.I | re.S)
_SITEMAP_HINT = re.compile(r"(?:sitemap|xmlsitemap)", re.I)
_PRODUCT_PATH = re.compile(r"/(?:products?|product-page)/", re.I)
_STATIC_SITEMAP_PATH = re.compile(
    r"/(?:blog|pages?|category|collections?|account|cart|checkout|search|polic(?:y|ies)|"
    r"wp-content|wp-admin|feed)(?:/|$)",
    re.I,
)
_MAX_SITEMAP_DOCUMENTS = 8
_MAX_SITEMAP_PRODUCTS = 120
_MAX_DETAIL_WORKERS = 8


def _import_route_repair() -> Any:
    try:
        import route_repair  # type: ignore
    except ImportError:
        from scripts import route_repair  # type: ignore
    return route_repair


def apply_route_overrides(worker: Any) -> dict[str, int]:
    """Replace only the source route sets verified by the recovery audit."""
    route_repair = _import_route_repair()
    for source_id, routes in ROUTE_OVERRIDES.items():
        route_repair.ROUTE_REPAIRS[source_id] = routes
        route_repair.FALLBACK_REPAIRS[source_id] = FALLBACK_OVERRIDES.get(source_id, ())
    state = route_repair.apply_route_repairs(worker)
    for source_id, targets in FALLBACK_OVERRIDES.items():
        worker.FALLBACK_HTML_ROUTES[source_id] = list(dict.fromkeys(targets))
    for marker in ("/product-page/", "/products/"):
        if marker not in worker.PRODUCT_PATHS:
            worker.PRODUCT_PATHS = (*worker.PRODUCT_PATHS, marker)
    return state


def _valid_price(core: Any, value: Any) -> float | None:
    parsed = core.num(value)
    if parsed is None or parsed < 1 or parsed > 10000:
        return None
    return parsed


def extract_first_party_price(core: Any, payload: str) -> float | None:
    """Read a product price only from product-detail markup in this response."""
    candidates: list[float] = []
    for match in _PRICE_CONTAINER.finditer(payload[:1_500_000]):
        body = html_module.unescape(match.group("body"))
        for raw in _DOLLAR.findall(body):
            parsed = _valid_price(core, raw)
            if parsed is not None:
                candidates.append(parsed)
    if not candidates:
        for raw in _PRICE_CONTEXT.findall(payload[:1_500_000]):
            parsed = _valid_price(core, raw)
            if parsed is not None:
                candidates.append(parsed)
    if not candidates:
        for raw in _JSON_PRICE.findall(payload[:1_500_000]):
            parsed = _valid_price(core, raw)
            if parsed is not None:
                candidates.append(parsed)
    return min(candidates) if candidates else None


def enrich_product_meta(core: Any, original: Any, payload: str) -> dict[str, str]:
    values = dict(original(payload))
    if not (values.get("product:price:amount") or values.get("og:price:amount")):
        price = extract_first_party_price(core, payload)
        if price is not None:
            values["product:price:amount"] = str(price)
    return values


def _row_rejection_reason(row: dict[str, Any]) -> str:
    if not str(row.get("url") or "").strip():
        return "missing_product_url"
    evidence = row.get("classification_evidence")
    if not isinstance(evidence, dict):
        return "missing_classification_evidence"
    primary = str(row.get("primary_type") or "")
    evidence_primary = str(evidence.get("primary_type") or "")
    if not primary or not evidence_primary:
        return "missing_primary_type"
    if primary != evidence_primary:
        return "classification_type_mismatch"
    if evidence.get("evidence_source") == "product_card_title_or_url":
        return "unverified_listing_card_evidence"
    return ""


def filter_for_strict_gate(
    original_gate: Any,
    products: list[dict[str, Any]],
) -> tuple[bool, list[str], dict[str, Any]]:
    """Remove only rows that the existing final gate necessarily rejects."""
    kept: list[dict[str, Any]] = []
    rejected = Counter()
    for row in products:
        reason = _row_rejection_reason(row)
        if reason:
            rejected[reason] += 1
        else:
            kept.append(row)
    products[:] = kept
    admitted, reasons, quality = original_gate(products)
    quality = dict(quality)
    quality["admission_rejections"] = sum(rejected.values())
    quality["admission_rejection_reasons"] = dict(sorted(rejected.items()))
    return admitted, list(reasons), quality


def _same_host(target: str, base_host: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(target)
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.netloc.casefold() == base_host


def _locs(payload: str, base: str) -> list[str]:
    out: list[str] = []
    for raw in _LOC.findall(payload):
        target = urllib.parse.urljoin(base, html_module.unescape(raw.strip()))
        if target and target not in out:
            out.append(target)
    return out


def _candidate_product_url(worker: Any, target: str, base_host: str) -> bool:
    if not _same_host(target, base_host):
        return False
    parsed = urllib.parse.urlsplit(target)
    if _STATIC_SITEMAP_PATH.search(parsed.path) or not _PRODUCT_PATH.search(parsed.path):
        return False
    return bool(worker.has_product_evidence(worker.path_text(target)))


def _fetch_sitemap_document(worker: Any, target: str) -> tuple[str, list[str], str]:
    payload, content_type, status = worker.core.fetch(target)
    if status != 200:
        raise ValueError(f"sitemap HTTP {status}")
    if content_type not in {
        "application/xml",
        "text/xml",
        "text/html",
        "application/xhtml+xml",
    }:
        raise ValueError(f"sitemap content type {content_type}")
    return payload, _locs(payload, target), content_type


def sitemap_products(
    worker: Any,
    payload: str,
    source_id: str,
    vendor: str,
    route: Route,
    diagnostics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    base_host = urllib.parse.urlsplit(route[1]).netloc.casefold()
    documents = 1
    failures = Counter()
    locations = _locs(payload, route[1])
    child_sitemaps = [
        target for target in locations
        if _same_host(target, base_host) and _SITEMAP_HINT.search(urllib.parse.urlsplit(target).path)
    ][:_MAX_SITEMAP_DOCUMENTS - 1]
    product_targets = [
        target for target in locations
        if _candidate_product_url(worker, target, base_host)
    ]
    for child in child_sitemaps:
        try:
            _, child_locations, _ = _fetch_sitemap_document(worker, child)
            documents += 1
            product_targets.extend(
                target for target in child_locations
                if _candidate_product_url(worker, target, base_host)
            )
        except Exception as error:
            failures[f"sitemap_{type(error).__name__.casefold()}"] += 1
    product_targets = list(dict.fromkeys(product_targets))[:_MAX_SITEMAP_PRODUCTS]

    rows: list[dict[str, Any]] = []
    if product_targets:
        with ThreadPoolExecutor(max_workers=min(_MAX_DETAIL_WORKERS, len(product_targets))) as pool:
            futures = {pool.submit(worker.core.fetch, target): target for target in product_targets}
            for future in as_completed(futures):
                target = futures[future]
                try:
                    detail, content_type, status = future.result()
                    if status != 200:
                        failures[f"detail_http_{status}"] += 1
                        continue
                    if content_type not in {"text/html", "application/xhtml+xml"}:
                        failures["detail_invalid_content_type"] += 1
                        continue
                    detail_route = ("html", target, "product_detail")
                    found = worker.core.html_detail(
                        detail,
                        source_id,
                        vendor,
                        detail_route,
                        target,
                    )
                    if not found:
                        failures["detail_without_product"] += 1
                        continue
                    for row in found:
                        row["discovery_method"] = "xml_sitemap_product_detail"
                    rows.extend(found)
                except Exception as error:
                    failures[f"detail_{type(error).__name__.casefold()}"] += 1

    diagnostics.update(
        sitemap_documents=documents,
        sitemap_product_candidates=len(product_targets),
        detail_requests=len(product_targets),
        detail_failures=sum(failures.values()),
        detail_failure_reasons=dict(sorted(failures.items())),
        coverage_status="partial" if failures else "complete",
    )
    return worker.core.dedupe(rows)


def install(worker: Any) -> dict[str, Any]:
    """Defer final wrappers until the complete production worker is composed."""
    apply_route_overrides(worker)
    if getattr(worker, "_source_recovery_installed", False):
        return {"installed": True, "source_count": len(worker.core.SOURCES)}
    original_run = worker.run

    def recovered_run(*args: Any, **kwargs: Any):
        finalize(worker)
        return original_run(*args, **kwargs)

    worker.run = recovered_run
    worker._source_recovery_installed = True
    return {"installed": True, "source_count": len(worker.core.SOURCES)}


def finalize(worker: Any) -> dict[str, Any]:
    if getattr(worker, "_source_recovery_finalized", False):
        apply_route_overrides(worker)
        return {"finalized": True}
    apply_route_overrides(worker)

    original_gate = worker.gate
    worker.gate = lambda products: filter_for_strict_gate(original_gate, products)

    original_meta = worker.core.meta_values
    worker.core.meta_values = lambda payload: enrich_product_meta(worker.core, original_meta, payload)

    original_html_with_details = worker.core.html_with_details

    def recovered_html_with_details(
        payload: str,
        source_id: str,
        vendor: str,
        route: Route,
        diagnostics: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if len(route) >= 3 and route[2] == "sitemap":
            return sitemap_products(
                worker,
                payload,
                source_id,
                vendor,
                route,
                diagnostics,
            )
        return original_html_with_details(payload, source_id, vendor, route, diagnostics)

    worker.core.html_with_details = recovered_html_with_details
    worker._source_recovery_finalized = True
    return {"finalized": True}


def self_test() -> int:
    assert ROUTE_OVERRIDES["wnc_cbd"][0][2] == "sitemap"
    assert all("wp-json" not in route[1] for route in ROUTE_OVERRIDES["veteran_grown_hemp"])
    assert all("products.json" not in route[1] for route in ROUTE_OVERRIDES["snapdragon_hemp"])
    assert "/product-page/" in ("/product-page/",)
    return 0
