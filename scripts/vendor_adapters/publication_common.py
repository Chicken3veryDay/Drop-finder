"""Shared helpers for versioned vendor-document publication artifacts."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

from scripts.catalog_v4.strict_json import dumps_strict
from .registry import validate_profiles

SCHEMA_VERSION = "dropfinder-vendor-document-publication-v1"


def timestamp(value: Any = None) -> str:
    raw = str(value or "").strip()
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def digest(payload: Any) -> str:
    encoded = dumps_strict(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def catalog_products(payload: Any) -> list[dict[str, Any]]:
    products = payload.get("products") if isinstance(payload, dict) else None
    if not isinstance(products, list):
        raise ValueError("catalog must be an object with a products array")
    return [dict(item) for item in products if isinstance(item, dict)]


def vendor_profiles(payload: Any) -> list[dict[str, Any]]:
    errors = validate_profiles(payload)
    if errors:
        raise ValueError("invalid vendor profiles: " + "; ".join(errors))
    return [dict(item) for item in payload["vendors"] if isinstance(item, dict)]


def vendor_id(product: dict[str, Any]) -> str:
    return str(product.get("source_id") or product.get("vendor_id") or "").strip()


def product_id(product: dict[str, Any]) -> str:
    return str(product.get("id") or product.get("product_id") or "").strip()


def source_product_id(product: dict[str, Any]) -> str:
    return str(
        product.get("source_product_id")
        or product.get("product_id")
        or product.get("id")
        or ""
    ).strip()


def source_variant_id(product: dict[str, Any]) -> str:
    return str(
        product.get("source_variant_id")
        or product.get("variant_id")
        or product.get("variant")
        or ""
    ).strip()


def product_url(product: dict[str, Any]) -> str:
    return str(
        product.get("canonical_product_url")
        or product.get("url")
        or product.get("route_url")
        or ""
    ).strip()
