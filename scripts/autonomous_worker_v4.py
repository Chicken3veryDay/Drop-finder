#!/usr/bin/env python3
"""Stable production wrapper for strict autonomous DropFinder workers."""
from __future__ import annotations

import math
import re
import sys
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


def _finite_positive(value: object) -> float | None:
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


_original_record = core.record
_original_candidate_to_row = worker.candidate_to_row


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

    row["grams"] = grams
    row["weight_source"] = weight_source
    row["price_type"] = "exact" if normalized_price is not None and exact_pairing else "starting_at" if normalized_price is not None else "unavailable"
    row["pricing_confidence"] = "exact_variant" if weight_source == "variant" else "exact_title" if weight_source == "title" else "unpaired"
    row["price_per_gram"] = round(normalized_price / grams, 4) if normalized_price and grams and exact_pairing else None
    return row


def accurate_candidate_to_row(candidate: dict, source_id: str, vendor: str) -> dict | None:
    """Prefer product-page price metadata over a nearby category-card price."""
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
                return worker.decorate(row, evidence, "product_detail_metadata")

    row = _original_candidate_to_row(candidate, source_id, vendor)
    if row:
        row = dict(row)
        row["price_source"] = "product_card_fallback"
        if not row.get("variant") and row.get("pricing_confidence") != "exact_title":
            row["price_type"] = "starting_at" if row.get("price") is not None else "unavailable"
            row["price_per_gram"] = None
            row["pricing_confidence"] = "unpaired"
    return row


# Patch the shared scanner module so every Shopify, WooCommerce, JSON-LD, and
# product-detail path uses the same strict weight and price-pairing contract.
core.grams = strict_grams
core.record = strict_record
worker.candidate_to_row = accurate_candidate_to_row


def self_test() -> int:
    reliability.self_test()
    assert 403 in reliability.RETRYABLE_HTTP
    assert "/cbd-hemp-flower/" in worker.PRODUCT_PATHS

    assert strict_grams("Orange Push Pop $49.99 · 4.8 stars") is None
    assert strict_grams("Orange Push Pop 4 oz THCA Flower") == 113.398
    assert strict_grams("Free THCA Flower 1/8th") == 3.544
    assert strict_grams("THCA Flower MINIS · 29+ grams") == 29.0
    assert strict_grams("Sizes: 3.5g, 7g, 14g") is None

    route = ("shopify", "https://example.test/collections/thca-flower/products.json", "thca_flower")
    exact = core.record(
        "fixture",
        "Fixture",
        route,
        "Blue Dream THCA Flower 3.5g",
        "https://example.test/products/blue-dream",
        "Indoor flower",
        35,
        True,
        "",
        "3.5g",
    )
    assert exact and exact["grams"] == 3.5 and exact["price_per_gram"] == 10.0
    assert exact["pricing_confidence"] == "exact_variant"

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
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    return worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
