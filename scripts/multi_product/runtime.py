from __future__ import annotations

import hashlib
import re
import urllib.parse
from collections import Counter
from typing import Any

from . import (
    CONTROLLED_PRODUCT_TYPES,
    ENABLED_PRODUCT_TYPES,
    classify_product,
    comparison_price,
    completeness_score,
    normalized_text,
    quantity_fields,
    type_specific_fields,
)

NON_PRODUCT_EXCLUDE = re.compile(
    r"\b(?:battery|charger|empty\s+cart|replacement\s+coil|atomizer|glass|"
    r"grinder|tray|apparel|shirts?|hoodies?|hats?|posters?|gift\s*cards?|"
    r"subscriptions?|wholesale|display\s+case|storage\s+jar|fertilizer|pets?)\b",
    re.I,
)

STOREWIDE_ROUTES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "arete": (("html", "https://arete.shop/l/national/products", "storewide"),),
    "black_tie_cbd": (
        ("html", "https://www.blacktiecbd.net/collections/all", "storewide"),
        ("shopify", "https://www.blacktiecbd.net/products.json?limit=250", "storewide"),
    ),
    "crysp": (("woo", "https://crysp.co/wp-json/wc/store/v1/products?per_page=100", "storewide"),),
    "five_leaf_wellness": (("woo", "https://fiveleafwellness.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),),
    "green_unicorn_farms": (("woo", "https://greenunicornfarms.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),),
    "hello_mary": (("woo", "https://shophellomary.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),),
    "holy_city_farms": (("woo", "https://holycityfarms.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),),
    "loud_house_hemp": (("woo", "https://loudhempproducts.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),),
    "lucky_elk": (("shopify", "https://luckyelk.com/products.json?limit=250", "storewide"),),
    "preston_herb_co": (("html", "https://www.prestonherbco.com/categories", "storewide"),),
    "pure_roots_botanicals": (("woo", "https://purerootsbotanicals.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),),
    "quantum_exotics": (("html", "https://www.quantumexotics.com/shop", "storewide"),),
    "secret_nature": (
        ("shopify", "https://secretnature.com/products.json?limit=250", "storewide"),
        ("shopify", "https://secretnaturecbd.com/products.json?limit=250", "storewide"),
    ),
    "sherlocks_glass": (("woo", "https://sherlocksglass.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),),
    "smoky_mountain_cbd": (("woo", "https://www.smokymountaincbd.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),),
    "stoney_branch_farms": (("shopify", "https://stoneybranch.com/products.json?limit=250", "storewide"),),
    "wnc_cbd": (
        ("html", "https://wnc-cbd.com/shop", "storewide"),
        ("shopify", "https://wnc-cbd.com/products.json?limit=250", "storewide"),
    ),
    "cali_canna": (
        ("woo", "https://calicanna.cc/wp-json/wc/store/v1/products?per_page=100", "storewide"),
        ("html", "https://calicanna.cc/shop/", "storewide"),
    ),
}

FALLBACK_ROUTES: dict[str, tuple[str, ...]] = {
    "arete": ("https://arete.shop/l/national/products",),
    "black_tie_cbd": ("https://www.blacktiecbd.net/collections/all",),
    "crysp": ("https://crysp.co/shop/",),
    "five_leaf_wellness": ("https://fiveleafwellness.com/shop/",),
    "green_unicorn_farms": ("https://greenunicornfarms.com/shop/",),
    "hello_mary": ("https://shophellomary.com/shop/",),
    "holy_city_farms": ("https://holycityfarms.com/shop/",),
    "loud_house_hemp": ("https://loudhempproducts.com/shop/",),
    "lucky_elk": ("https://luckyelk.com/collections/all",),
    "preston_herb_co": ("https://www.prestonherbco.com/categories",),
    "pure_roots_botanicals": ("https://purerootsbotanicals.com/shop/",),
    "quantum_exotics": ("https://www.quantumexotics.com/shop",),
    "secret_nature": ("https://secretnature.com/collections/all",),
    "sherlocks_glass": ("https://sherlocksglass.com/shop/",),
    "smoky_mountain_cbd": ("https://www.smokymountaincbd.com/shop/",),
    "stoney_branch_farms": ("https://stoneybranch.com/collections/all",),
    "wnc_cbd": ("https://wnc-cbd.com/shop",),
    "cali_canna": ("https://calicanna.cc/shop/",),
}


def _evidence(classification: Any, source: str, text: str) -> dict[str, Any]:
    evidence = dict(classification.evidence)
    evidence["type_tags"] = list(classification.type_tags)
    evidence["evidence_source"] = source
    evidence["evidence_sha256"] = hashlib.sha256(text.lower().encode("utf-8")).hexdigest()
    evidence["permits_public_purchase_link"] = classification.permits_public_purchase_link
    return evidence


def _augment_sources(core: Any) -> None:
    existing: dict[str, tuple[str, str, list[tuple[str, str, str]]]] = {}
    order: list[str] = []
    for source in core.SOURCES:
        source_id, vendor, routes = source
        existing[source_id] = (source_id, vendor, list(routes))
        order.append(source_id)
    if "cali_canna" not in existing:
        existing["cali_canna"] = ("cali_canna", "Cali Canna", [])
        order.append("cali_canna")
    for source_id, extra_routes in STOREWIDE_ROUTES.items():
        if source_id not in existing:
            continue
        sid, vendor, routes = existing[source_id]
        seen = {route[1] for route in routes}
        routes.extend(route for route in extra_routes if route[1] not in seen)
        existing[source_id] = (sid, vendor, routes)
    core.SOURCES = [existing[source_id] for source_id in order]


def install_multi_product_runtime(reliability: Any) -> dict[str, Any]:
    worker = reliability.worker
    core = worker.core
    if getattr(worker, "_multi_product_runtime_installed", False):
        return {"installed": True, "source_count": len(core.SOURCES)}

    def generalized_record(
        source_id: str,
        vendor: str,
        route: tuple[str, str, str],
        name: Any,
        target: Any,
        description: Any = "",
        price: Any = None,
        stock: Any = "",
        image: Any = "",
        variant: Any = "",
        rating: Any = None,
        review_count: Any = None,
        delta9_thc: Any = None,
        direct_total_thc: Any = None,
    ) -> dict[str, Any] | None:
        clean_name = core.text(name)
        clean_description = core.text(description)[: getattr(core, "DESCRIPTION_LIMIT", 2400)]
        clean_variant = core.text(variant)
        normalized_url = core.url(target, route[1])
        combined = normalized_text(clean_name, clean_description, clean_variant, normalized_url, route[2])
        classification = classify_product(
            name=clean_name,
            description=normalized_text(clean_description, clean_variant),
            url=normalized_url,
            route_hint=route[2],
        )
        if not clean_name or not normalized_url or classification is None:
            return None
        current_price = core.num(price)
        quantity = quantity_fields(combined, classification.primary_type)
        price_fields = comparison_price(current_price, quantity)
        type_fields = type_specific_fields(combined, classification.primary_type)
        if hasattr(core, "percent_from_text") and hasattr(core, "THCA_PATTERNS"):
            thca = core.percent_from_text(combined, core.THCA_PATTERNS)
            parsed_delta9 = core.percent_number(delta9_thc) or core.percent_from_text(combined, core.DELTA9_PATTERNS)
            parsed_total = core.percent_number(direct_total_thc) or core.percent_from_text(combined, core.TOTAL_THC_PATTERNS)
            rating_value, review_value = core.rating_pair(rating, review_count)
        else:
            thca_values = [core.num(value) for value in core.POTENCY.findall(combined)]
            thca = max((value for value in thca_values if value is not None and value <= 100), default=None)
            parsed_delta9 = None
            parsed_total = None
            rating_value = None
            review_value = None
        row: dict[str, Any] = {
            "id": hashlib.sha256(f"{source_id}|{normalized_url}|{clean_variant}".encode()).hexdigest()[:24],
            "source_id": source_id,
            "vendor": vendor,
            "name": clean_name,
            "source_title": clean_name,
            "description": clean_description,
            "url": normalized_url,
            "public_purchase_url": normalized_url if classification.permits_public_purchase_link else None,
            "image": core.url(image, route[1]) if image else "",
            "price": current_price,
            **quantity,
            **price_fields,
            "thca": thca if classification.primary_type == "cannabis_flower" else None,
            "delta9_thc": parsed_delta9 if classification.primary_type == "cannabis_flower" else None,
            "direct_total_thc": parsed_total if classification.primary_type == "cannabis_flower" else None,
            "rating": rating_value,
            "review_count": review_value,
            "availability": core.availability(stock),
            "variant": clean_variant,
            "source_type": route[0],
            "route_url": route[1],
            "collected_at": core.now(),
            "primary_type": classification.primary_type,
            "type_tags": list(classification.type_tags),
            "classification_evidence": _evidence(classification, "storefront_record", combined),
            **type_fields,
        }
        row["strain"] = None
        row["completeness_score"] = completeness_score(row)
        return row

    def generalized_product_links(payload: str, route: tuple[str, str, str]) -> list[str]:
        base = urllib.parse.urlsplit(route[1])
        seen: list[str] = []
        for href, label in core.ANCHOR.findall(payload):
            target = core.url(href, route[1])
            parsed = urllib.parse.urlsplit(target)
            label = core.text(label)
            path = parsed.path.lower()
            if not target or parsed.netloc != base.netloc.lower() or target == core.url(route[1], route[1]):
                continue
            if not any(marker in path for marker in worker.PRODUCT_PATHS):
                continue
            if classify_product(name=label, url=worker.path_text(target), route_hint=route[2]) is None:
                continue
            if target not in seen:
                seen.append(target)
            if len(seen) >= 120:
                break
        return seen

    def has_product_evidence(value: str) -> bool:
        return classify_product(name=value) is not None

    def evidence_payload(value: str, source: str) -> dict[str, Any]:
        normalized = core.text(value)
        classification = classify_product(name=normalized)
        if classification is None:
            return {
                "primary_type": "",
                "type_tags": [],
                "evidence_source": source,
                "evidence_sha256": hashlib.sha256(normalized.lower().encode("utf-8")).hexdigest(),
            }
        return _evidence(classification, source, normalized)

    def gate(products: list[dict[str, Any]]) -> tuple[bool, list[str], dict[str, Any]]:
        reasons: list[str] = []
        count = len(products)
        valid_urls = sum(bool(str(row.get("url") or "").strip()) for row in products)
        priced = sum(core.num(row.get("price")) is not None for row in products)
        evidenced = sum(
            isinstance(row.get("classification_evidence"), dict)
            and row["classification_evidence"].get("primary_type") in ENABLED_PRODUCT_TYPES
            and row.get("primary_type") in ENABLED_PRODUCT_TYPES
            and row["classification_evidence"].get("primary_type") == row.get("primary_type")
            for row in products
        )
        if count == 0:
            reasons.append("no_qualifying_products")
        if count and valid_urls / count < 0.90:
            reasons.append("insufficient_product_urls")
        if count and priced == 0:
            reasons.append("no_priced_products")
        if count and evidenced != count:
            reasons.append("missing_product_level_evidence")
        counts = Counter(str(row.get("primary_type") or "") for row in products)
        return not reasons, reasons, {
            "products": count,
            "url_coverage": round(valid_urls / count, 4) if count else 0,
            "priced_products": priced,
            "evidenced_products": evidenced,
            "products_by_type": dict(sorted(counts.items())),
        }

    core.record = generalized_record
    core.product_links = generalized_product_links
    core.HARD_EXCLUDE = NON_PRODUCT_EXCLUDE
    worker.FALLBACK_EXCLUDE = NON_PRODUCT_EXCLUDE
    worker.has_product_evidence = has_product_evidence
    worker.evidence_payload = evidence_payload
    worker.gate = gate
    # Collection pages are retrieval roots, not product-detail candidates.
    # Preserve the existing product-path allowlist instead of widening it.
    _augment_sources(core)
    for source_id, targets in FALLBACK_ROUTES.items():
        configured = worker.FALLBACK_HTML_ROUTES.setdefault(source_id, [])
        for target in targets:
            if target not in configured:
                configured.append(target)
    worker._multi_product_runtime_installed = True
    return {"installed": True, "source_count": len(core.SOURCES)}


def runtime_self_test(reliability: Any) -> None:
    state = install_multi_product_runtime(reliability)
    assert state["installed"] is True
    worker = reliability.worker
    row = worker.core.record(
        "fixture",
        "Fixture",
        ("html", "https://example.test/shop", "storewide"),
        "THCA Live Resin Disposable Vape 1mL",
        "https://example.test/products/vape",
        "Myrcene, total terpenes 4.2%, 800 puffs",
        25,
        "in_stock",
    )
    assert row is not None
    assert row["primary_type"] == "cannabis_vape"
    assert row["price_per_ml"] == 25.0
    assert row["puff_count"] == 800
    assert row["public_purchase_url"]
    controlled = worker.core.record(
        "fixture",
        "Fixture",
        ("html", "https://example.test/shop", "storewide"),
        "Psilocybe Cubensis Psilocybin Mushrooms 7g",
        "https://example.test/products/mushroom",
        "Psilocybin potency 2.5%",
        70,
        "in_stock",
    )
    assert controlled is not None
    assert controlled["primary_type"] == "psilocybin_mushroom"
    assert controlled["public_purchase_url"] is None
    assert controlled["price_per_gram"] == 10.0
    assert "cali_canna" in {source[0] for source in worker.core.SOURCES}
