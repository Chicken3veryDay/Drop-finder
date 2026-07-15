from __future__ import annotations

import hashlib
import re
import urllib.parse
from typing import Any

from .normalization import canonical_product_url, clean_text, normalized_search

PRODUCT_PATH_PATTERNS = (
    re.compile(r"/(?:products?|shop)/([^/?#]+)", re.I),
    re.compile(r"/l/national/products/(?:[^/?#]+/)?([^/?#]+)", re.I),
)


def stable_digest(*parts: Any, length: int = 24) -> str:
    payload = "\x1f".join(clean_text(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def product_identity(raw: dict[str, Any], canonical_name: str) -> tuple[str, dict[str, Any]]:
    source_id = clean_text(raw.get("source_id"))
    explicit = clean_text(
        raw.get("source_product_id")
        or raw.get("product_id")
        or raw.get("product_handle")
        or raw.get("handle")
    )
    if explicit:
        key = f"source:{normalized_search(explicit)}"
        return stable_digest(source_id, key), {"method": "source_product_identity", "value": explicit}
    product_url = canonical_product_url(raw.get("canonical_product_url") or raw.get("url") or raw.get("route_url"))
    if product_url:
        try:
            path = urllib.parse.unquote(urllib.parse.urlsplit(product_url).path)
        except ValueError:
            path = ""
        for pattern in PRODUCT_PATH_PATTERNS:
            match = pattern.search(path)
            if match:
                handle = normalized_search(match.group(1))
                return stable_digest(source_id, "handle", handle), {
                    "method": "canonical_storefront_handle",
                    "value": handle,
                    "canonical_url": product_url,
                }
        return stable_digest(source_id, "url", product_url), {
            "method": "canonical_product_url",
            "value": product_url,
        }
    fallback = normalized_search(canonical_name)
    return stable_digest(source_id, "title", fallback), {
        "method": "conservative_vendor_title_fallback",
        "value": fallback,
        "warning": "identity may change when a stable source identifier becomes available",
    }


def variant_identity(raw: dict[str, Any], product_id: str, grams: str, source_label: str, variant_url: str) -> tuple[str, dict[str, Any]]:
    explicit = clean_text(raw.get("source_variant_id") or raw.get("variant_id") or raw.get("sku"))
    if explicit:
        return stable_digest(product_id, "source_variant", explicit), {
            "method": "source_variant_identity",
            "value": explicit,
        }
    if variant_url:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(variant_url).query)
        for key in ("variant", "variation_id", "attribute_pa_size", "attribute_size"):
            values = query.get(key)
            if values:
                value = clean_text(values[0])
                return stable_digest(product_id, key, value), {
                    "method": "variant_url_parameter",
                    "value": value,
                }
    fallback = f"{grams}|{normalized_search(source_label)}"
    return stable_digest(product_id, "weight", fallback), {
        "method": "weight_label_fallback",
        "value": fallback,
    }
