"""Bounded recovery for current storefront paths, prices, and admission outliers."""
from __future__ import annotations

import html as html_module
import re
import urllib.parse
from typing import Any, Callable

Route = tuple[str, str, str]

# These are current first-party listing/discovery paths. They supplement the
# canonical route table rather than replacing routes that still provide useful
# structured data or failure diagnostics.
ROUTE_EXTENSIONS: dict[str, tuple[Route, ...]] = {
    "beleafer": (
        ("html", "https://beleafer.com/product-category/hemp-flower/", "mixed_flower"),
        ("html", "https://beleafer.com/product-category/hemp-flower/indoor/", "mixed_flower"),
    ),
    "five_leaf_wellness": (
        ("html", "https://fiveleafwellness.com/product-category/new-releases/", "storewide"),
        ("html", "https://fiveleafwellness.com/product-category/mid-tier/", "storewide"),
    ),
    "veteran_grown_hemp": (
        ("html", "https://www.veterangrownhemp.com/flower", "thca_flower"),
        ("html", "https://www.veterangrownhemp.com/shop", "storewide"),
    ),
    "wnc_cbd": (
        ("html", "https://wnc-cbd.com/xmlsitemap.php", "sitemap"),
        ("html", "https://wnc-cbd.com/sitemap.xml", "sitemap"),
    ),
}

_LOC = re.compile(r"<loc>\s*([^<]+?)\s*</loc>", re.I)
_VISIBLE_PRICE_PATTERNS = (
    re.compile(
        r"(?:price|now|sale\s+price|current\s+price|from)\s*:?\s*"
        r"(?:</?[^>]+>\s*){0,10}\$\s*([0-9]{1,4}(?:\.[0-9]{1,2})?)",
        re.I | re.S,
    ),
    re.compile(
        r"woocommerce-Price-amount[^>]*>.*?\$\s*([0-9]{1,4}(?:\.[0-9]{1,2})?)",
        re.I | re.S,
    ),
    re.compile(
        r'"(?:formattedPrice|formatted_price|displayPrice|display_price)"\s*:\s*'
        r'"\$\s*([0-9]{1,4}(?:\.[0-9]{1,2})?)"',
        re.I,
    ),
    re.compile(
        r'"(?:salePrice|sale_price|discountedPrice|discounted_price|minPrice|min_price|price)"'
        r"\s*:\s*([0-9]{1,4}(?:\.[0-9]{1,2})?)",
        re.I,
    ),
)


def _route_key(route: Route) -> tuple[str, str]:
    return route[0], route[1].rstrip("/")


def _dedupe_routes(routes: list[Route] | tuple[Route, ...]) -> tuple[Route, ...]:
    output: dict[tuple[str, str], Route] = {}
    for route in routes:
        if not isinstance(route, tuple) or len(route) != 3:
            continue
        output.setdefault(_route_key(route), route)
    return tuple(output.values())


def extend_route_repairs(route_repair: Any) -> None:
    """Make current recovery paths part of every final-boundary route reapply."""
    for source_id, additions in ROUTE_EXTENSIONS.items():
        existing = tuple(route_repair.ROUTE_REPAIRS.get(source_id, ()))
        route_repair.ROUTE_REPAIRS[source_id] = _dedupe_routes((*additions, *existing))
        route_repair.FALLBACK_REPAIRS[source_id] = tuple(
            route[1] for route in route_repair.ROUTE_REPAIRS[source_id] if route[0] == "html"
        )


def recover_meta_values(core: Any, original: Callable[[str], dict[str, str]], payload: str) -> dict[str, str]:
    """Recover a product price only from price-labelled first-party page markup."""
    values = dict(original(payload))
    if values.get("product:price:amount") or values.get("og:price:amount"):
        return values

    candidates: list[float] = []
    for pattern in _VISIBLE_PRICE_PATTERNS:
        for match in pattern.finditer(payload[:1_500_000]):
            parsed = core.num(match.group(1))
            # Exclude common integer-cent payloads and implausible retail values.
            if parsed is not None and parsed <= 2000:
                candidates.append(parsed)
    if candidates:
        values["product:price:amount"] = str(min(candidates))
    return values


def _candidate_score(row: dict[str, Any]) -> float:
    try:
        return float(row.get("candidate_score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _slug_label(target: str) -> str:
    try:
        slug = urllib.parse.unquote(urllib.parse.urlsplit(target).path.rstrip("/").split("/")[-1])
    except ValueError:
        slug = ""
    slug = re.sub(r"\.html?$", "", slug, flags=re.I)
    return " ".join(slug.replace("-", " ").replace("_", " ").split()).title()


def recover_card_candidates(
    worker: Any,
    original: Callable[[str, Route], list[dict[str, Any]]],
    payload: str,
    route: Route,
) -> list[dict[str, Any]]:
    """Recover malformed candidate lists and bounded sitemap/product-page links.

    Discovery is not admission: every returned candidate still passes the
    independent product-detail evidence, price, and stock verifier.
    """
    try:
        candidates = [dict(row) for row in original(payload, route) if isinstance(row, dict)]
    except (TypeError, ValueError):
        candidates = []

    by_url = {str(row.get("url") or ""): row for row in candidates if str(row.get("url") or "")}
    base_host = urllib.parse.urlsplit(route[1]).netloc.casefold()

    def add(target: str, label: str, score: float) -> None:
        normalized = worker.core.url(html_module.unescape(target), route[1])
        if not normalized or normalized in by_url:
            return
        parsed = urllib.parse.urlsplit(normalized)
        if parsed.netloc.casefold() != base_host:
            return
        path = parsed.path.casefold()
        if not any(marker in path for marker in (*worker.PRODUCT_PATHS, "/product-page/")):
            return
        clean_label = worker.core.text(label) or _slug_label(normalized)
        by_url[normalized] = {
            "name": clean_label,
            "url": normalized,
            "price": None,
            "stock": "",
            "card_evidence": worker.core.text(f"{clean_label} {worker.path_text(normalized)}"),
            "candidate_score": score,
        }

    # BigCommerce publishes current product URLs in its first-party XML sitemap.
    for raw in _LOC.findall(payload):
        target = html_module.unescape(raw.strip())
        path = urllib.parse.urlsplit(target).path.casefold()
        if "/products/" in path and "thca" in path:
            add(target, _slug_label(target), 150.0)

    # Rebuild directly from HTML when an upstream candidate has a malformed score.
    for match in worker.core.ANCHOR.finditer(payload):
        target = worker.core.url(match.group(1), route[1])
        if not target:
            continue
        path = urllib.parse.urlsplit(target).path.casefold()
        if not any(marker in path for marker in (*worker.PRODUCT_PATHS, "/product-page/")):
            continue
        label = worker.core.text(match.group(2))
        form_text = worker.core.text(f"{label} {worker.path_text(target)}")
        if worker.core.HARD_EXCLUDE.search(form_text) or worker.FALLBACK_EXCLUDE.search(form_text):
            continue
        add(target, label, 120.0 + min(len(label), 80) / 100.0)

    return sorted(by_url.values(), key=_candidate_score, reverse=True)[:120]


def _consistent_evidence(row: dict[str, Any]) -> bool:
    evidence = row.get("classification_evidence")
    if not isinstance(evidence, dict):
        return False
    primary = str(row.get("primary_type") or "")
    evidence_primary = str(evidence.get("primary_type") or "")
    tags = {
        str(value)
        for value in (
            row.get("type_tags")
            or evidence.get("type_tags")
            or []
        )
    }
    return bool(primary and evidence_primary == primary and (not tags or primary in tags))


def install_late(worker: Any) -> None:
    """Filter isolated malformed records instead of quarantining valid siblings."""
    if getattr(worker, "_scraper_recovery_gate_installed", False):
        return
    original_gate = worker.gate

    def recovery_gate(products: list[dict[str, Any]]):
        retained = [row for row in products if isinstance(row, dict) and _consistent_evidence(row)]
        rejected = len(products) - len(retained)
        if rejected:
            products[:] = retained
        admitted, reasons, quality = original_gate(products)
        quality = dict(quality)
        quality["rejected_inconsistent_evidence"] = rejected
        return admitted, reasons, quality

    worker.gate = recovery_gate
    worker._scraper_recovery_gate_installed = True


def install(worker: Any) -> dict[str, int]:
    """Install current route, markup, candidate, and admission recovery."""
    try:
        import route_repair
    except ImportError:
        from scripts import route_repair  # type: ignore

    extend_route_repairs(route_repair)
    route_repair.apply_route_repairs(worker)
    if getattr(worker, "_scraper_recovery_installed", False):
        return {"installed": 1, "extended_sources": len(ROUTE_EXTENSIONS)}

    original_meta = worker.core.meta_values
    original_candidates = worker.card_candidates
    worker.core.meta_values = lambda payload: recover_meta_values(worker.core, original_meta, payload)
    worker.card_candidates = lambda payload, route: recover_card_candidates(
        worker, original_candidates, payload, route
    )
    if "/product-page/" not in worker.PRODUCT_PATHS:
        worker.PRODUCT_PATHS = (*worker.PRODUCT_PATHS, "/product-page/")

    original_run = worker.run

    def recovered_run(*args: Any, **kwargs: Any):
        # install_runtime() has finished by the time run() executes, so this is
        # the stable seam for wrapping the final multi-product admission gate.
        install_late(worker)
        route_repair.apply_route_repairs(worker)
        return original_run(*args, **kwargs)

    worker.run = recovered_run
    worker._scraper_recovery_installed = True
    return {"installed": 1, "extended_sources": len(ROUTE_EXTENSIONS)}
