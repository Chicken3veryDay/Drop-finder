#!/usr/bin/env python3
"""Stable production wrapper for strict autonomous DropFinder workers."""
from __future__ import annotations

import concurrent.futures
import json
import math
import re
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Import the proven reliability layer directly. The experimental global
# browser-transport wrapper is intentionally not imported because it reduced
# successful source coverage on live GitHub-hosted runs.
import autonomous_worker_v2 as reliability  # type: ignore

worker = reliability.worker
core = worker.core

# Some storefront WAFs intermittently answer public category/API requests with
# 403 before succeeding on a later request. Retry is bounded and does not turn a
# persistent block into a fake success.
reliability.RETRYABLE_HTTP.add(403)

# Green Unicorn product URLs use this WooCommerce path rather than /product/.
# Product-detail evidence remains mandatory after candidate discovery.
if "/cbd-hemp-flower/" not in worker.PRODUCT_PATHS:
    worker.PRODUCT_PATHS = (*worker.PRODUCT_PATHS, "/cbd-hemp-flower/")

# A weight must include an actual unit, an explicit fractional-ounce suffix, or
# an unambiguous flower-weight word. The previous expression made "oz" optional,
# allowing a review score, price digit, or list number such as "4" to become
# four ounces. That produced imaginary 113.398 g products and fake $/g values.
_WEIGHT_TOKEN = re.compile(
    r"""
    (?<![\d.])(?:
        (?P<ordinal>1/8|1/4|1/2)(?:st|nd|rd|th)(?:\s*(?:oz|ounces?))?
      | (?P<fraction>1/8|1/4|1/2)\s*(?:oz|ounces?)
      | (?P<number>\d+(?:\.\d+)?)\s*\+?\s*(?P<unit>g|grams?|oz|ounces?|lb|lbs|pounds?)
      | (?P<word>eighth|quarter\s+(?:oz|ounces?)|half(?:\s+|-)??(?:oz|ounces?)|one\s+ounce|an\s+ounce|ounce|zip)
    )\b
    """,
    re.I | re.X,
)

_FRACTION_GRAMS = {"1/8": 3.5437, "1/4": 7.0874, "1/2": 14.1748}
_WORD_GRAMS = {
    "eighth": 3.5437,
    "quarter oz": 7.0874,
    "quarter ounce": 7.0874,
    "quarter ounces": 7.0874,
    "half oz": 14.1748,
    "half-oz": 14.1748,
    "half ounce": 14.1748,
    "half ounces": 14.1748,
    "one ounce": 28.3495,
    "an ounce": 28.3495,
    "ounce": 28.3495,
    "zip": 28.3495,
}

_THCA_PATTERNS = (
    re.compile(
        r"\b(?:total\s+)?(?:thca|thc-a)\b\s*(?:content|potency|percentage|percent)?\s*[:=\-]?\s*(\d{1,2}(?:\.\d+)?)\s*%",
        re.I,
    ),
    re.compile(r"(\d{1,2}(?:\.\d+)?)\s*%\s*(?:total\s+)?(?:thca|thc-a)\b", re.I),
    re.compile(r'"(?:thca|thc_a|thca_percent|thca_percentage)"\s*:\s*"?(\d{1,2}(?:\.\d+)?)', re.I),
)


def _finite_positive(value: object) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _weight_values(value: object) -> list[float]:
    text = core.text(value)
    weights: list[float] = []
    for match in _WEIGHT_TOKEN.finditer(text):
        grams: float | None = None
        fraction = match.group("ordinal") or match.group("fraction")
        if fraction:
            grams = _FRACTION_GRAMS.get(fraction)
        elif match.group("word"):
            key = re.sub(r"\s+", " ", match.group("word").lower()).strip()
            grams = _WORD_GRAMS.get(key)
        else:
            number = _finite_positive(match.group("number"))
            unit = str(match.group("unit") or "").lower()
            if number is not None:
                if unit.startswith("g"):
                    grams = number
                elif unit.startswith("oz") or unit.startswith("ounce"):
                    grams = number * 28.3495
                elif unit.startswith("lb") or unit.startswith("pound"):
                    grams = number * 453.59237
        if grams is not None and 0.1 <= grams <= 1814.37:
            weights.append(round(grams, 3))
    return weights


def _single_weight(value: object) -> float | None:
    values = sorted(set(_weight_values(value)))
    return values[0] if len(values) == 1 else None


def strict_grams(value: object) -> float | None:
    """Return a weight only when one explicit, unambiguous value is present."""
    return _single_weight(value)


def trusted_weight(name: object, variant: object, description: object) -> tuple[float | None, str | None]:
    variant_weight = _single_weight(variant)
    if variant_weight is not None:
        return variant_weight, "variant"

    title_weight = _single_weight(name)
    if title_weight is not None:
        return title_weight, "title"

    # A description may contain one useful package size, but product pages often
    # list every selectable size. Multiple distinct weights are intentionally
    # treated as ambiguous and never paired with a single displayed price.
    description_weight = _single_weight(description)
    if description_weight is not None:
        return description_weight, "description_single"
    return None, None


def _thca_values(value: object) -> list[float]:
    values: list[float] = []
    raw = str(value or "")
    for pattern in _THCA_PATTERNS:
        for match in pattern.findall(raw):
            number = _finite_positive(match)
            if number is not None and number <= 100:
                values.append(round(number, 3))
    return sorted(set(values))


def trusted_thca(*values: object) -> tuple[float | None, str | None]:
    labels = ("variant", "title", "description", "product_page")
    for index, value in enumerate(values):
        candidates = _thca_values(value)
        if len(candidates) == 1:
            return candidates[0], labels[index] if index < len(labels) else "evidence"
    return None, None


def _image(item: dict, fallback: str = "") -> str:
    images = item.get("images") or []
    if images and isinstance(images[0], dict):
        return str(images[0].get("src") or fallback)
    return fallback


def _woo_price(item: dict) -> float | None:
    prices = item.get("prices") if isinstance(item.get("prices"), dict) else {}
    try:
        minor = int(prices.get("currency_minor_unit", 2) or 2)
    except (TypeError, ValueError):
        minor = 2
    raw = next(
        (
            core.num(prices.get(key))
            for key in ("sale_price", "price", "regular_price")
            if core.num(prices.get(key)) is not None
        ),
        None,
    )
    return round(raw / (10**minor), 4) if raw is not None else None


def _attribute_label(attributes: object) -> str:
    labels: list[str] = []
    for attribute in attributes if isinstance(attributes, list) else []:
        if not isinstance(attribute, dict):
            continue
        name = core.text(attribute.get("name"))
        value = core.text(attribute.get("value"))
        if value:
            labels.append(f"{name}: {value}" if name else value)
    return " · ".join(labels)


def _woo_description(item: dict) -> str:
    categories = " ".join(
        core.text(row.get("name")) for row in item.get("categories", []) if isinstance(row, dict)
    )
    tags = " ".join(core.text(row.get("name")) for row in item.get("tags", []) if isinstance(row, dict))
    attributes = " ".join(
        f"{core.text(row.get('name'))}: "
        + ", ".join(core.text(term.get("name")) for term in row.get("terms", []) if isinstance(term, dict))
        for row in item.get("attributes", [])
        if isinstance(row, dict)
    )
    return core.text(
        f"{item.get('short_description', '')} {item.get('description', '')} {categories} {tags} {attributes}"
    )


def _fetch_json(target: str) -> dict | None:
    try:
        payload, content_type, status = core.fetch(target)
        if status != 200 or content_type not in {"application/json", "text/json"}:
            return None
        decoded = json.loads(payload)
        return decoded if isinstance(decoded, dict) else None
    except Exception:
        return None


def _variation_row(
    parent: dict,
    stub: dict,
    detail: dict,
    source_id: str,
    vendor: str,
    route: tuple,
) -> dict | None:
    variant = core.text(detail.get("variation")) or _attribute_label(stub.get("attributes"))
    if not variant:
        return None
    parent_description = _woo_description(parent)
    description = core.text(f"{parent_description} {_woo_description(detail)} {variant}")
    target = str(detail.get("permalink") or parent.get("permalink") or "")
    row = core.record(
        source_id,
        vendor,
        route,
        core.text(f"{parent.get('name', '')} {variant}"),
        target,
        description,
        _woo_price(detail),
        detail.get("is_in_stock") if detail.get("is_in_stock") is not None else parent.get("is_in_stock"),
        _image(detail, _image(parent)),
        variant,
    )
    if row:
        row["parent_product_id"] = parent.get("id")
        row["variant_id"] = detail.get("id") or stub.get("id")
        row["price_source"] = "woo_store_api_variation"
        row["stock_source"] = "woo_store_api_variation"
    return row


_original_record = core.record
_original_candidate_to_row = worker.candidate_to_row
_original_woo = core.woo
_original_scan_source = worker.scan_source


def strict_record(
    sid,
    vendor,
    route,
    name,
    target,
    desc="",
    price=None,
    stock="",
    image="",
    variant="",
):
    row = _original_record(sid, vendor, route, name, target, desc, price, stock, image, variant)
    if not row:
        return None

    grams, weight_source = trusted_weight(name, variant, desc)
    normalized_price = core.num(price)
    exact_pairing = weight_source in {"variant", "title"}
    potency, potency_source = trusted_thca(variant, name, desc)
    existing_potency = _finite_positive(row.get("thca"))

    row["grams"] = grams
    row["weight_source"] = weight_source
    row["price_type"] = "exact" if normalized_price is not None and exact_pairing else "starting_at" if normalized_price is not None else "unavailable"
    row["pricing_confidence"] = "exact_variant" if weight_source == "variant" else "exact_title" if weight_source == "title" else "unpaired"
    row["price_per_gram"] = round(normalized_price / grams, 4) if normalized_price and grams and exact_pairing else None
    row["thca"] = potency or existing_potency
    row["thca_source"] = potency_source if potency is not None else "legacy_pattern" if existing_potency is not None else None
    return row


def woo_with_variations(payload: str, source_id: str, vendor: str, route: tuple) -> list[dict]:
    try:
        decoded = json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return _original_woo(payload, source_id, vendor, route)
    products = decoded if isinstance(decoded, list) else decoded.get("products", []) if isinstance(decoded, dict) else []
    products = [row for row in products if isinstance(row, dict)]
    root = route[1].split("/products?", 1)[0].rstrip("/")
    rows: list[dict] = []
    variation_jobs: list[tuple[dict, dict, str]] = []

    for parent in products:
        variations = [row for row in parent.get("variations", []) if isinstance(row, dict) and row.get("id")]
        if variations:
            for stub in variations[:180]:
                variation_jobs.append((parent, stub, f"{root}/products/{stub['id']}"))
            continue

        description = _woo_description(parent)
        row = core.record(
            source_id,
            vendor,
            route,
            parent.get("name"),
            parent.get("permalink"),
            description,
            _woo_price(parent),
            parent.get("is_in_stock") if parent.get("is_in_stock") is not None else parent.get("stock_status"),
            _image(parent),
        )
        if row:
            row["parent_product_id"] = parent.get("id")
            row["price_source"] = "woo_store_api_product"
            rows.append(row)

    def resolve(job: tuple[dict, dict, str]) -> dict | None:
        parent, stub, target = job
        detail = _fetch_json(target)
        return _variation_row(parent, stub, detail, source_id, vendor, route) if detail else None

    if variation_jobs:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(variation_jobs))) as executor:
            futures = [executor.submit(resolve, job) for job in variation_jobs]
            for future in concurrent.futures.as_completed(futures):
                try:
                    row = future.result()
                except Exception:
                    row = None
                if row:
                    rows.append(row)
    return core.dedupe(rows)


def _apply_page_fields(row: dict, payload: str) -> dict:
    enriched = dict(row)
    if _finite_positive(enriched.get("thca")) is None:
        potency, source = trusted_thca(payload)
        if potency is not None:
            enriched["thca"] = potency
            enriched["thca_source"] = source or "product_page"
    if enriched.get("availability") == "unknown":
        lower = core.text(payload).lower()
        if "out of stock" in lower or "sold out" in lower:
            enriched["availability"] = "out_of_stock"
            enriched["stock_source"] = "product_page_text"
        elif "in stock" in lower or "add to cart" in lower:
            enriched["availability"] = "in_stock"
            enriched["stock_source"] = "product_page_text"
    if not enriched.get("image"):
        meta = core.meta_values(payload)
        image = meta.get("og:image") or meta.get("twitter:image")
        if image:
            enriched["image"] = core.url(image, str(enriched.get("url") or ""))
    return enriched


def accurate_candidate_to_row(candidate: dict, source_id: str, vendor: str) -> dict | None:
    """Prefer product-page price metadata and page-level potency over a nearby card price."""
    target = str(candidate.get("url") or "")
    detail_route = ("html", target, "product_detail")
    try:
        payload, content_type, status = core.fetch(target)
    except Exception:
        payload, content_type, status = "", "", 0

    if status == 200 and content_type in {"text/html", "application/xhtml+xml"}:
        evidence = worker.product_detail_evidence(payload, target)
        if worker.has_product_evidence(evidence):
            meta = core.meta_values(payload)
            title = meta.get("og:title") or meta.get("twitter:title") or candidate.get("name")
            price = meta.get("product:price:amount") or meta.get("og:price:amount") or candidate.get("price")
            stock = meta.get("product:availability") or candidate.get("stock")
            image = meta.get("og:image") or meta.get("twitter:image") or ""
            row = core.record(source_id, vendor, detail_route, title, target, evidence, price, stock, image)
            if row:
                row["price_source"] = "product_detail_metadata"
                return worker.decorate(_apply_page_fields(row, payload), evidence, "product_detail_metadata")

    row = _original_candidate_to_row(candidate, source_id, vendor)
    if row:
        row = dict(row)
        row["price_source"] = "product_card_fallback"
        if not row.get("variant") and row.get("pricing_confidence") != "exact_title":
            row["price_type"] = "starting_at" if row.get("price") is not None else "unavailable"
            row["price_per_gram"] = None
            row["pricing_confidence"] = "unpaired"
    return row


def completeness_enriched_scan_source(source: tuple) -> tuple[list[dict], dict]:
    products, status = _original_scan_source(source)
    if not products:
        return products, status

    def enrich(row: dict) -> dict:
        needs_page = (
            _finite_positive(row.get("thca")) is None
            or row.get("availability") == "unknown"
            or not row.get("image")
        )
        if not needs_page:
            return row
        try:
            payload, content_type, http_status = core.fetch(str(row.get("url") or ""))
        except Exception:
            return row
        if http_status != 200 or content_type not in {"text/html", "application/xhtml+xml"}:
            return row
        return _apply_page_fields(row, payload)

    enriched: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(products))) as executor:
        futures = [executor.submit(enrich, row) for row in products]
        for future in concurrent.futures.as_completed(futures):
            try:
                enriched.append(future.result())
            except Exception:
                pass
    enriched = core.dedupe(enriched)
    status = dict(status)
    quality = dict(status.get("quality") or {})
    quality.update(
        exact_pricing=sum(row.get("pricing_confidence") in {"exact_variant", "exact_title"} for row in enriched),
        weighted_products=sum(_finite_positive(row.get("grams")) is not None for row in enriched),
        potency_products=sum(_finite_positive(row.get("thca")) is not None for row in enriched),
        known_stock=sum(row.get("availability") in {"in_stock", "out_of_stock"} for row in enriched),
    )
    status.update(products=len(enriched), quality=quality, worker="autonomous_worker_v4_complete_variants")
    return enriched, status


# Patch the shared scanner module so every Shopify, WooCommerce, JSON-LD, and
# product-detail path uses the same strict weight, potency, and price contract.
core.grams = strict_grams
core.record = strict_record
core.woo = woo_with_variations
worker.candidate_to_row = accurate_candidate_to_row
worker.scan_source = completeness_enriched_scan_source


def self_test() -> int:
    reliability.self_test()
    assert 403 in reliability.RETRYABLE_HTTP
    assert "/cbd-hemp-flower/" in worker.PRODUCT_PATHS

    assert strict_grams("Orange Push Pop $49.99 · 4.8 stars") is None
    assert strict_grams("Orange Push Pop 4 oz THCA Flower") == 113.398
    assert strict_grams("Free THCA Flower 1/8th") == 3.544
    assert strict_grams("THCA Flower MINIS · 29+ grams") == 29.0
    assert strict_grams("Sizes: 3.5g, 7g, 14g") is None
    assert trusted_thca("THCA: 30.7%")[0] == 30.7
    assert trusted_thca("30.7% THCA")[0] == 30.7
    assert trusted_thca("THCA flower with no lab percentage")[0] is None

    route = ("shopify", "https://example.test/collections/thca-flower/products.json", "thca_flower")
    exact = core.record(
        "fixture",
        "Fixture",
        route,
        "Blue Dream THCA Flower 3.5g",
        "https://example.test/products/blue-dream",
        "Indoor flower with 28.4% THCA",
        35,
        True,
        "https://example.test/image.jpg",
        "3.5g",
    )
    assert exact and exact["grams"] == 3.5 and exact["price_per_gram"] == 10.0
    assert exact["pricing_confidence"] == "exact_variant"
    assert exact["thca"] == 28.4

    ambiguous = core.record(
        "fixture",
        "Fixture",
        route,
        "Orange Push Pop THCA Flower",
        "https://example.test/products/orange-push-pop",
        "Choose 3.5g, 7g, 14g, or 28g · rated 4.8",
        49.99,
        True,
    )
    assert ambiguous and ambiguous["grams"] is None and ambiguous["price_per_gram"] is None
    assert ambiguous["price_type"] == "starting_at"

    woo_route = ("woo", "https://example.test/wp-json/wc/store/v1/products?search=flower", "mixed_flower")
    parent = {
        "id": 10,
        "name": "Blue Dream THCA Flower",
        "description": "Lab result: 27.5% THCA",
        "permalink": "https://example.test/product/blue-dream",
        "images": [{"src": "https://example.test/blue.jpg"}],
    }
    stub = {"id": 11, "attributes": [{"name": "Weight", "value": "14 Grams"}]}
    detail = {
        "id": 11,
        "variation": "Weight: 14 Grams",
        "permalink": "https://example.test/product/blue-dream?attribute_weight=14+grams",
        "prices": {"price": "7499", "currency_minor_unit": 2},
        "is_in_stock": True,
    }
    row = _variation_row(parent, stub, detail, "fixture", "Fixture", woo_route)
    assert row and row["grams"] == 14 and row["price"] == 74.99
    assert row["price_per_gram"] == round(74.99 / 14, 4) and row["thca"] == 27.5
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    return worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
