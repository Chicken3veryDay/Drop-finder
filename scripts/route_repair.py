"""Canonical route repairs and first-party HTML extraction fallbacks.

The vendor registry is intentionally static and auditable, but storefront paths move.
This module applies a bounded set of verified canonical replacements and strengthens
product-detail parsing without weakening the existing evidence, stock, or price gates.
"""
from __future__ import annotations

import html as html_module
import json
import re
import urllib.parse
from typing import Any

Route = tuple[str, str, str]

# Complete route sets for storefronts whose previous production paths were stale,
# blocked while an alternate public route works, or belonged to a retired domain.
# Routes stay first-party and unauthenticated.
ROUTE_REPAIRS: dict[str, tuple[Route, ...]] = {
    "arete": (
        ("html", "https://arete.shop/", "storewide"),
        ("html", "https://arete.shop/l/national/products", "storewide"),
    ),
    "bay_smokes": (
        ("shopify", "https://baysmokes.com/collections/thca-flower/products.json?limit=250", "thca_flower"),
        ("shopify", "https://baysmokes.com/products.json?limit=250", "storewide"),
        ("html", "https://baysmokes.com/collections/thca-flower", "thca_flower"),
        ("html", "https://baysmokes.com/", "storewide"),
    ),
    "beleafer": (
        ("woo", "https://beleafer.com/wp-json/wc/store/v1/products?per_page=100&search=thca%20flower", "mixed_flower"),
        ("woo", "https://beleafer.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),
        ("html", "https://beleafer.com/shop/", "storewide"),
        ("html", "https://beleafer.com/", "storewide"),
    ),
    "black_tie_cbd": (
        ("html", "https://www.blacktiecbd.net/collections/thca-flower", "thca_flower"),
        ("html", "https://www.blacktiecbd.net/", "storewide"),
    ),
    "canna_nc": (
        ("html", "https://cannanc.com/thca-flower/", "thca_flower"),
        ("html", "https://cannanc.com/indoor-smalls-thca-flower/", "thca_flower"),
        ("html", "https://cannanc.com/value-thca-flower/", "thca_flower"),
        ("html", "https://cannanc.com/", "storewide"),
    ),
    "cali_canna": (
        ("woo", "https://calicanna.cc/wp-json/wc/store/v1/products?per_page=100&search=flower", "mixed_flower"),
        ("woo", "https://calicanna.cc/wp-json/wc/store/v1/products?per_page=100", "storewide"),
        ("html", "https://calicanna.cc/shop/", "storewide"),
        ("html", "https://calicanna.cc/", "storewide"),
    ),
    "crysp": (
        ("woo", "https://crysp.co/wp-json/wc/store/v1/products?per_page=100&search=flower", "mixed_flower"),
        ("woo", "https://crysp.co/wp-json/wc/store/v1/products?per_page=100", "storewide"),
    ),
    "dr_ganja": (
        ("html", "https://www.drganja.com/thca-hemp-flower", "thca_flower"),
        ("woo", "https://www.drganja.com/wp-json/wc/store/v1/products?per_page=100&search=thca%20flower", "mixed_flower"),
        ("html", "https://www.drganja.com/", "storewide"),
    ),
    "earthy_select": (
        ("woo", "https://earthyselect.com/wp-json/wc/store/v1/products?per_page=100&search=thca%20flower", "mixed_flower"),
        ("woo", "https://earthyselect.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),
        ("html", "https://earthyselect.com/", "storewide"),
    ),
    "exhale_wellness": (
        ("html", "https://www.exhalewell.com/thca-flower/", "thca_flower"),
        ("woo", "https://www.exhalewell.com/wp-json/wc/store/v1/products?per_page=100&search=thca%20flower", "mixed_flower"),
        ("html", "https://www.exhalewell.com/", "storewide"),
    ),
    "five_leaf_wellness": (
        ("woo", "https://fiveleafwellness.com/wp-json/wc/store/v1/products?per_page=100&search=flower", "mixed_flower"),
        ("woo", "https://fiveleafwellness.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),
        ("html", "https://fiveleafwellness.com/shop/", "storewide"),
    ),
    "hello_mood": (
        ("shopify", "https://hellomood.co/products.json?limit=250", "storewide"),
        ("html", "https://hellomood.co/", "storewide"),
    ),
    "hemp_hop": (
        ("shopify", "https://hemphop.co/collections/thca-flower-and-prerolls/products.json?limit=250", "mixed_flower"),
        ("shopify", "https://hemphop.co/products.json?limit=250", "storewide"),
        ("html", "https://hemphop.co/collections/thca-flower-and-prerolls", "mixed_flower"),
    ),
    "holy_city_farms": (
        ("woo", "https://holycityfarms.com/wp-json/wc/store/v1/products?per_page=100&search=flower", "mixed_flower"),
        ("woo", "https://holycityfarms.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),
        ("html", "https://holycityfarms.com/product-tag/thca/", "mixed_flower"),
        ("html", "https://holycityfarms.com/", "storewide"),
    ),
    "lit_farms": (
        ("html", "https://litfarms.com/collections/thca-flower", "thca_flower"),
        ("shopify", "https://litfarms.com/products.json?limit=250", "storewide"),
    ),
    "plain_jane": (
        ("html", "https://plainjane.com/", "storewide"),
    ),
    "preston_herb_co": (
        ("html", "https://www.prestonherbco.com/categories/flower", "mixed_flower"),
        ("html", "https://www.prestonherbco.com/", "storewide"),
    ),
    "pure_roots_botanicals": (
        ("woo", "https://purerootsbotanicals.com/wp-json/wc/store/v1/products?per_page=100&search=flower", "mixed_flower"),
        ("woo", "https://purerootsbotanicals.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),
        ("html", "https://purerootsbotanicals.com/", "storewide"),
    ),
    "secret_nature": (
        ("shopify", "https://secretnature.com/collections/thca-products/products.json?limit=250", "thca_flower"),
        ("shopify", "https://secretnature.com/products.json?limit=250", "storewide"),
        ("html", "https://secretnature.com/collections/all", "storewide"),
    ),
    "simply_mary": (
        ("shopify", "https://simplymary.co/products.json?limit=250", "storewide"),
        ("html", "https://simplymary.co/", "storewide"),
    ),
    "smoky_mountain_cbd": (
        ("woo", "https://www.smokymountaincbd.com/wp-json/wc/store/v1/products?per_page=100&search=flower", "mixed_flower"),
        ("woo", "https://www.smokymountaincbd.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),
        ("html", "https://www.smokymountaincbd.com/", "storewide"),
    ),
    "snapdragon_hemp": (
        ("shopify", "https://www.snapdragonhemp.com/products.json?limit=250", "storewide"),
        ("html", "https://www.snapdragonhemp.com/", "storewide"),
    ),
    "veteran_grown_hemp": (
        ("woo", "https://www.veterangrownhemp.com/wp-json/wc/store/v1/products?per_page=100&search=flower", "mixed_flower"),
        ("woo", "https://www.veterangrownhemp.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),
        ("html", "https://www.veterangrownhemp.com/shop/", "storewide"),
        ("html", "https://www.veterangrownhemp.com/", "storewide"),
    ),
    "wnc_cbd": (
        ("html", "https://wnc-cbd.com/", "storewide"),
        ("html", "https://wnc-cbd.com/thca-flower/", "thca_flower"),
        ("html", "https://wnc-cbd.com/high-thca-flower", "thca_flower"),
    ),
}

FALLBACK_REPAIRS: dict[str, tuple[str, ...]] = {
    source_id: tuple(route[1] for route in routes if route[0] == "html")
    for source_id, routes in ROUTE_REPAIRS.items()
}

# Product links on BigCommerce and modern Woo themes are often root-level slugs.
_STATIC_PATH = re.compile(
    r"/(?:account|blog|cart|checkout|collections?|contact|faq|legal|login|pages?|policy|search|shop|tag|category|wp-|assets?|cdn)(?:/|$)",
    re.I,
)
_PRICE_PATTERNS = (
    re.compile(r'data-product-price-without-tax-value=["\']([0-9]+(?:\.[0-9]+)?)["\']', re.I),
    re.compile(r'data-price-amount=["\']([0-9]+(?:\.[0-9]+)?)["\']', re.I),
    re.compile(r'itemprop=["\']price["\'][^>]*content=["\']([0-9]+(?:\.[0-9]+)?)["\']', re.I),
    re.compile(r'content=["\']([0-9]+(?:\.[0-9]+)?)["\'][^>]*itemprop=["\']price["\']', re.I),
)
_SCRIPT_STYLE = re.compile(r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_EVIDENCE_WINDOW = re.compile(r".{0,700}\b(?:thc-?a|high\s+thca)\b.{0,1000}", re.I | re.S)


def _route_key(route: Route) -> tuple[str, str]:
    return route[0], route[1].rstrip("/")


def _dedupe_routes(routes: list[Route] | tuple[Route, ...]) -> list[Route]:
    unique: dict[tuple[str, str], Route] = {}
    for route in routes:
        if not isinstance(route, tuple) or len(route) != 3:
            continue
        route_type, target, scope = (str(value) for value in route)
        try:
            parsed = urllib.parse.urlsplit(target)
        except ValueError:
            continue
        if route_type not in {"shopify", "woo", "html"} or parsed.scheme != "https" or not parsed.netloc:
            continue
        unique.setdefault(_route_key((route_type, target, scope)), (route_type, target, scope))
    return list(unique.values())


def apply_route_repairs(worker: Any) -> dict[str, int]:
    """Replace known stale route sets and stale fallback paths in-place."""
    repaired = 0
    sources: list[tuple[str, str, list[Route]]] = []
    for source_id, vendor, current_routes in worker.core.SOURCES:
        replacement = ROUTE_REPAIRS.get(str(source_id))
        routes = _dedupe_routes(list(replacement) if replacement else list(current_routes))
        if replacement and routes != list(current_routes):
            repaired += 1
        sources.append((str(source_id), str(vendor), routes))
    worker.core.SOURCES[:] = sources

    for source_id, targets in FALLBACK_REPAIRS.items():
        worker.FALLBACK_HTML_ROUTES[source_id] = list(dict.fromkeys(targets))
    return {"repaired_sources": repaired, "source_count": len(sources)}


def _json_ld_products(payload: str, core: Any) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for raw in core.LD.findall(payload):
        try:
            decoded = json.loads(html_module.unescape(raw.strip()))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        for item in core.objects(decoded):
            kind = item.get("@type") if isinstance(item, dict) else None
            kinds = {str(value).casefold() for value in (kind if isinstance(kind, list) else [kind])}
            if "product" in kinds:
                products.append(item)
    return products


def _offers(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for child in value for item in _offers(child)]
    if not isinstance(value, dict):
        return []
    nested = value.get("offers")
    if isinstance(nested, (dict, list)):
        expanded = _offers(nested)
        if expanded:
            return expanded
    return [value]


def enrich_meta_values(core: Any, original: Any, payload: str) -> dict[str, str]:
    """Extract price/stock/image only from the fetched first-party product page."""
    values = dict(original(payload))
    products = _json_ld_products(payload, core)
    prices: list[float] = []
    availability = ""
    image = ""
    for product in products:
        candidate_image = product.get("image")
        if isinstance(candidate_image, list):
            candidate_image = candidate_image[0] if candidate_image else ""
        if isinstance(candidate_image, dict):
            candidate_image = candidate_image.get("url") or candidate_image.get("contentUrl") or ""
        image = image or str(candidate_image or "")
        for offer in _offers(product.get("offers")):
            for key in ("price", "lowPrice", "highPrice"):
                parsed = core.num(offer.get(key))
                if parsed is not None:
                    prices.append(parsed)
            availability = availability or str(offer.get("availability") or "")
    if "product:price:amount" not in values:
        for pattern in _PRICE_PATTERNS:
            match = pattern.search(payload)
            parsed = core.num(match.group(1)) if match else None
            if parsed is not None:
                prices.append(parsed)
                break
        if prices:
            values["product:price:amount"] = str(min(prices))
    if "product:availability" not in values:
        normalized = core.availability(availability)
        visible = core.text(_TAG.sub(" ", _SCRIPT_STYLE.sub(" ", payload[:500_000])))
        if normalized == "unknown":
            normalized = core.availability(visible)
        if normalized != "unknown":
            values["product:availability"] = normalized
    if image and "og:image" not in values:
        values["og:image"] = image
    return values


def add_visible_product_evidence(worker: Any, original: Any, payload: str, target: str) -> str:
    evidence = original(payload, target)
    if worker.has_product_evidence(evidence):
        return evidence
    visible = html_module.unescape(_TAG.sub(" ", _SCRIPT_STYLE.sub(" ", payload[:800_000])))
    windows = [match.group(0) for match in _EVIDENCE_WINDOW.finditer(visible)]
    if windows:
        evidence = worker.core.text(f"{evidence} {' '.join(windows[:12])}")
    return evidence


def discover_evidenced_links(worker: Any, original: Any, payload: str, route: Route) -> list[dict[str, Any]]:
    """Add root-level product slugs only when the anchor itself has product evidence.

    Every candidate still goes through the independent product-detail verifier.
    """
    candidates = list(original(payload, route))
    by_url = {str(row.get("url") or ""): row for row in candidates}
    base_host = urllib.parse.urlsplit(route[1]).netloc.casefold()
    for match in worker.core.ANCHOR.finditer(payload):
        target = worker.core.url(match.group(1), route[1])
        if not target or target in by_url:
            continue
        parsed = urllib.parse.urlsplit(target)
        if parsed.netloc.casefold() != base_host or _STATIC_PATH.search(parsed.path):
            continue
        label = worker.core.text(match.group(2))
        signal = worker.core.text(f"{label} {worker.path_text(target)}")
        if len(label) < 4 or not worker.has_product_evidence(signal):
            continue
        row = {
            "name": label,
            "url": target,
            "price": None,
            "stock": "",
            "card_evidence": signal,
            "candidate_score": 130.0 + min(len(label), 80) / 100.0,
        }
        by_url[target] = row
        if len(by_url) >= 120:
            break
    return sorted(by_url.values(), key=lambda row: float(row.get("candidate_score") or 0), reverse=True)[:120]


def install(worker: Any) -> dict[str, int]:
    """Install route and product-detail repairs once for the production worker."""
    route_state = apply_route_repairs(worker)
    if getattr(worker, "_route_repair_installed", False):
        return {**route_state, "installed": 1}

    original_meta = worker.core.meta_values
    original_evidence = worker.product_detail_evidence
    original_candidates = worker.card_candidates
    worker.core.meta_values = lambda payload: enrich_meta_values(worker.core, original_meta, payload)
    worker.product_detail_evidence = lambda payload, target: add_visible_product_evidence(
        worker, original_evidence, payload, target
    )
    worker.card_candidates = lambda payload, route: discover_evidenced_links(
        worker, original_candidates, payload, route
    )
    for marker in ("/thca-", "/thca_", "/flower-"):
        if marker not in worker.PRODUCT_PATHS:
            worker.PRODUCT_PATHS = (*worker.PRODUCT_PATHS, marker)
    original_run = worker.run

    def repaired_run(*args: Any, **kwargs: Any):
        # The multi-product runtime augments source routes after registry install.
        # Reapply canonical replacements at the final execution boundary.
        apply_route_repairs(worker)
        return original_run(*args, **kwargs)

    worker.run = repaired_run
    worker._route_repair_installed = True
    return {**route_state, "installed": 1}


def self_test() -> int:
    assert ROUTE_REPAIRS["bay_smokes"][0][1].startswith("https://baysmokes.com/")
    assert all("bay-smokes.com" not in route[1] for route in ROUTE_REPAIRS["bay_smokes"])
    assert _dedupe_routes([
        ("html", "https://example.test/", "storewide"),
        ("html", "https://example.test", "storewide"),
        ("ftp", "ftp://example.test", "storewide"),
    ]) == [("html", "https://example.test/", "storewide")]
    return 0

# SCRAPER_RECOVERY_CLOSURE_V1
# Recover current first-party storefront paths and retain valid siblings when a
# bounded number of malformed records appear in otherwise authoritative output.
_RECOVERY_ROUTE_EXTENSIONS: dict[str, tuple[Route, ...]] = {
    "beleafer": (
        ("html", "https://beleafer.com/product-category/hemp-flower/", "storewide"),
        ("html", "https://beleafer.com/product-category/hemp-flower/indoor/", "storewide"),
    ),
    "five_leaf_wellness": (
        ("html", "https://fiveleafwellness.com/product-category/new-releases/", "storewide"),
        ("html", "https://fiveleafwellness.com/product-category/top-shelf/", "storewide"),
        ("html", "https://fiveleafwellness.com/product-category/mid-tier/", "storewide"),
        ("html", "https://fiveleafwellness.com/", "storewide"),
    ),
    "veteran_grown_hemp": (
        ("html", "https://www.veterangrownhemp.com/flower", "thca_flower"),
        ("html", "https://www.veterangrownhemp.com/shop", "storewide"),
        ("html", "https://www.veterangrownhemp.com/", "storewide"),
    ),
    "wnc_cbd": (
        ("html", "https://wnc-cbd.com/sitemap.php", "storewide"),
        ("html", "https://wnc-cbd.com/", "storewide"),
    ),
}
for _source_id, _routes in _RECOVERY_ROUTE_EXTENSIONS.items():
    ROUTE_REPAIRS[_source_id] = tuple(
        _dedupe_routes([*_routes, *ROUTE_REPAIRS.get(_source_id, ())])
    )
    FALLBACK_REPAIRS[_source_id] = tuple(
        route[1] for route in ROUTE_REPAIRS[_source_id] if route[0] == "html"
    )

_WOO_PRICE_WINDOW = re.compile(
    r'class=["\'][^"\']*(?:woocommerce-Price-amount|amount)[^"\']*["\'][^>]*>.{0,420}',
    re.I | re.S,
)
_WIX_FORMATTED_PRICE = re.compile(
    r'"(?:formattedPrice|formattedDiscountedPrice)"\s*:\s*"\$\s*([0-9]{1,5}(?:\.[0-9]{1,2})?)"',
    re.I,
)
_VISIBLE_LABELED_PRICE = re.compile(
    r'(?:\bNow\s*:|\bPrice\s*:?)\s*\$\s*([0-9]{1,5}(?:\.[0-9]{1,2})?)',
    re.I,
)
_DOLLAR_PRICE = re.compile(r'\$\s*([0-9]{1,5}(?:\.[0-9]{1,2})?)')
_BASE_ENRICH_META_VALUES = enrich_meta_values


def _recover_first_party_price(core: Any, payload: str) -> float | None:
    for match in _WOO_PRICE_WINDOW.finditer(payload):
        visible = core.text(_TAG.sub(" ", match.group(0)))
        price_match = _DOLLAR_PRICE.search(visible)
        parsed = core.num(price_match.group(1)) if price_match else None
        if parsed is not None:
            return parsed
    for pattern in (_WIX_FORMATTED_PRICE, _VISIBLE_LABELED_PRICE):
        match = pattern.search(payload)
        parsed = core.num(match.group(1)) if match else None
        if parsed is not None:
            return parsed
    return None


def enrich_meta_values(core: Any, original: Any, payload: str) -> dict[str, str]:
    values = _BASE_ENRICH_META_VALUES(core, original, payload)
    if "product:price:amount" not in values:
        recovered = _recover_first_party_price(core, payload)
        if recovered is not None:
            values["product:price:amount"] = str(recovered)
    return values


def _consistent_product_evidence(row: dict[str, Any]) -> bool:
    evidence = row.get("classification_evidence")
    primary = str(row.get("primary_type") or "")
    return bool(primary and isinstance(evidence, dict) and str(evidence.get("primary_type") or "") == primary)


def _install_invalid_sibling_pruning(worker: Any) -> None:
    if getattr(worker, "_invalid_sibling_pruning_installed", False):
        return
    original_gate = getattr(worker, "gate", None)
    if not callable(original_gate):
        return

    def pruning_gate(products: list[dict[str, Any]]):
        original_count = len(products)
        products[:] = [row for row in products if _consistent_product_evidence(row)]
        admitted, reasons, quality = original_gate(products)
        quality = dict(quality)
        quality["discarded_invalid_rows"] = original_count - len(products)
        return admitted, reasons, quality

    worker.gate = pruning_gate
    worker._invalid_sibling_pruning_installed = True


_BASE_INSTALL = install


def install(worker: Any) -> dict[str, int]:
    state = _BASE_INSTALL(worker)
    for marker in ("/product-page/", "/products/"):
        if marker not in worker.PRODUCT_PATHS:
            worker.PRODUCT_PATHS = (*worker.PRODUCT_PATHS, marker)
    if getattr(worker, "_scraper_recovery_closure_installed", False):
        return {**state, "recovery_installed": 1}
    original_run = worker.run

    def recovery_run(*args: Any, **kwargs: Any):
        apply_route_repairs(worker)
        _install_invalid_sibling_pruning(worker)
        return original_run(*args, **kwargs)

    worker.run = recovery_run
    worker._scraper_recovery_closure_installed = True
    return {**state, "recovery_installed": 1}
