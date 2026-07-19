from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import (
    DETAIL_SCHEMA_VERSION,
    INDEX_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    REJECTION_SCHEMA_VERSION,
    VENDOR_SCHEMA_VERSION,
)
from .selection import select_active_variant
from .strict_json import StrictJsonError, load_path_strict


class VerificationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = load_path_strict(path)
    except StrictJsonError as exc:
        raise VerificationError(f"unable to load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"expected JSON object: {path}")
    return value


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_data_path(output_root: Path, declared: str) -> Path:
    value = declared.replace("\\", "/")
    if value.startswith("data/"):
        value = value[5:]
    path = (output_root / value).resolve()
    root = output_root.resolve()
    if root not in path.parents and path != root:
        raise VerificationError(f"manifest path escapes output root: {declared}")
    return path


def _required_text(value: Any, *, field: str, product_id: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise VerificationError(f"missing {field}: {product_id}")
    return normalized


def _https_url(value: Any, *, product_id: str, variant_id: str) -> str:
    normalized = str(value or "").strip()
    try:
        parsed = urlsplit(normalized)
    except ValueError as exc:
        raise VerificationError(f"invalid variant URL: {product_id} {variant_id}") from exc
    if parsed.scheme != "https" or not parsed.netloc:
        raise VerificationError(f"invalid variant URL: {product_id} {variant_id}")
    return normalized


def _variant_identity(variant: dict[str, Any], *, product_id: str, detail: bool) -> tuple[float, str]:
    variant_id = str(variant.get("variant_id") or "")
    if not variant_id:
        raise VerificationError(f"missing variant id: {product_id}")
    try:
        grams = float(variant["grams"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VerificationError(f"invalid variant grams: {product_id} {variant_id}") from exc
    url_field = "variant_url" if detail else "product_url"
    variant_url = _https_url(variant.get(url_field), product_id=product_id, variant_id=variant_id)
    return grams, variant_url


def verify_publication(output_root: Path) -> dict[str, Any]:
    manifest_path = output_root / "catalog-v4" / "manifest.json"
    manifest = _load(manifest_path)
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise VerificationError("unexpected manifest schema")
    generation_id = manifest.get("generation_id")
    if not isinstance(generation_id, str) or len(generation_id) != 32:
        raise VerificationError("invalid generation id")

    index_meta = manifest.get("compact_index") or {}
    index_path = _resolve_data_path(output_root, str(index_meta.get("path") or ""))
    if _hash(index_path) != index_meta.get("sha256"):
        raise VerificationError("compact index hash mismatch")
    index = _load(index_path)
    if index.get("schema_version") != INDEX_SCHEMA_VERSION or index.get("generation_id") != generation_id:
        raise VerificationError("compact index schema/generation mismatch")

    vendors_meta = manifest.get("vendor_profiles") or {}
    vendors_path = _resolve_data_path(output_root, str(vendors_meta.get("path") or ""))
    if _hash(vendors_path) != vendors_meta.get("sha256"):
        raise VerificationError("vendor profile hash mismatch")
    vendors = _load(vendors_path)
    if vendors.get("schema_version") != VENDOR_SCHEMA_VERSION or vendors.get("generation_id") != generation_id:
        raise VerificationError("vendor profile schema/generation mismatch")

    rejections_meta = manifest.get("rejections") or {}
    rejections_path = _resolve_data_path(output_root, str(rejections_meta.get("path") or ""))
    if _hash(rejections_path) != rejections_meta.get("sha256"):
        raise VerificationError("rejections hash mismatch")
    rejections = _load(rejections_path)
    if rejections.get("schema_version") != REJECTION_SCHEMA_VERSION or rejections.get("generation_id") != generation_id:
        raise VerificationError("rejections schema/generation mismatch")
    if rejections.get("count") != len(rejections.get("variants") or []) or rejections_meta.get("count") != rejections.get("count"):
        raise VerificationError("rejections count mismatch")

    product_ids: set[str] = set()
    product_urls: set[tuple[str, str]] = set()
    variant_ids: set[str] = set()
    index_variants_by_product: dict[str, dict[str, tuple[float, str]]] = {}
    allowed_lineages = {"indica", "indica_leaning_hybrid", "hybrid", "sativa_leaning_hybrid", "sativa", "unknown"}
    index_products = index.get("products")
    if not isinstance(index_products, list):
        raise VerificationError("index products must be a list")
    for product in index_products:
        if not isinstance(product, dict):
            raise VerificationError("index product must be an object")
        product_id = str(product.get("product_id") or "")
        if not product_id or product_id in product_ids:
            raise VerificationError("missing or duplicate product id")
        product_ids.add(product_id)
        _required_text(product.get("vendor_id"), field="vendor id", product_id=product_id)
        _required_text(product.get("vendor_name"), field="vendor name", product_id=product_id)
        _required_text(product.get("strain_name"), field="strain name", product_id=product_id)
        if product.get("lineage") not in allowed_lineages:
            raise VerificationError(f"invalid lineage: {product_id}")
        variants = product.get("variants")
        if not isinstance(variants, list) or not variants:
            raise VerificationError(f"product has no variants: {product_id}")
        seen_weights: set[float] = set()
        product_variant_identities: dict[str, tuple[float, str]] = {}
        for variant in variants:
            if not isinstance(variant, dict) or variant.get("in_stock") is not True:
                raise VerificationError(f"non-stock variant published: {product_id}")
            variant_id = str(variant.get("variant_id") or "")
            if not variant_id or variant_id in variant_ids:
                raise VerificationError("missing or duplicate variant id")
            variant_ids.add(variant_id)
            grams, variant_url = _variant_identity(variant, product_id=product_id, detail=False)
            product_variant_identities[variant_id] = (grams, variant_url)
            try:
                current = float(variant["current_price"])
                ppg = float(variant["price_per_gram"])
            except (KeyError, TypeError, ValueError) as exc:
                raise VerificationError(f"invalid variant numeric fields: {product_id}") from exc
            if grams <= 0 or current <= 0 or abs((current / grams) - ppg) > 0.001:
                raise VerificationError(f"variant pricing inconsistency: {variant_id}")
            original = variant.get("original_price")
            discount = variant.get("discount_percent")
            if original is not None:
                original_value = float(original)
                if original_value <= current:
                    raise VerificationError(f"invalid original price: {variant_id}")
                expected = (original_value - current) / original_value * 100
                if discount is None or abs(expected - float(discount)) > 0.02:
                    raise VerificationError(f"discount inconsistency: {variant_id}")
            elif discount is not None:
                raise VerificationError(f"discount without original price: {variant_id}")
            weight_key = round(grams, 4)
            if weight_key in seen_weights:
                raise VerificationError(f"duplicate normalized variant weight: {product_id} {weight_key}")
            seen_weights.add(weight_key)
        index_variants_by_product[product_id] = product_variant_identities
        selected = select_active_variant(variants)
        if selected is None or product.get("default_variant_id") != selected.get("variant_id"):
            raise VerificationError(f"default active variant mismatch: {product_id}")

    detail_product_ids: set[str] = set()
    declared_detail_count = 0
    for entry in manifest.get("product_detail_shards") or []:
        if not isinstance(entry, dict):
            raise VerificationError("invalid detail shard declaration")
        path = _resolve_data_path(output_root, str(entry.get("path") or ""))
        if _hash(path) != entry.get("sha256"):
            raise VerificationError(f"detail shard hash mismatch: {path}")
        payload = _load(path)
        if payload.get("schema_version") != DETAIL_SCHEMA_VERSION or payload.get("generation_id") != generation_id:
            raise VerificationError(f"detail shard schema/generation mismatch: {path}")
        products = payload.get("products")
        if not isinstance(products, list) or payload.get("product_count") != len(products):
            raise VerificationError(f"detail shard count mismatch: {path}")
        declared_detail_count += len(products)
        for product in products:
            product_id = str(product.get("product_id") or "") if isinstance(product, dict) else ""
            if not product_id or product_id in detail_product_ids:
                raise VerificationError("missing or duplicate detail product")
            detail_product_ids.add(product_id)
            product_url = str(product.get("canonical_product_url") or "")
            vendor_id = str(product.get("vendor_id") or "")
            url_key = (vendor_id, product_url)
            if not product_url or url_key in product_urls:
                raise VerificationError(f"missing or duplicate canonical product URL: {product_id}")
            product_urls.add(url_key)
            variants = product.get("variants")
            if not isinstance(variants, list) or not variants:
                raise VerificationError(f"detail product has no variants: {product_id}")
            detail_variant_identities: dict[str, tuple[float, str]] = {}
            for variant in variants:
                if not isinstance(variant, dict):
                    raise VerificationError(f"detail variant must be an object: {product_id}")
                if variant.get("in_stock") is not True:
                    raise VerificationError(f"detail contains non-stock variant: {product_id}")
                variant_id = str(variant.get("variant_id") or "")
                if not variant_id or variant_id in detail_variant_identities:
                    raise VerificationError(f"missing or duplicate detail variant: {product_id}")
                detail_variant_identities[variant_id] = _variant_identity(
                    variant,
                    product_id=product_id,
                    detail=True,
                )
                documents = variant.get("documents")
                if not isinstance(documents, list):
                    raise VerificationError(f"variant documents must be a list: {product_id}")
                for document in documents:
                    if not isinstance(document, dict):
                        raise VerificationError(f"document must be an object: {product_id}")
                    if str(document.get("vendor_id") or "") != vendor_id:
                        raise VerificationError(f"document vendor mismatch: {product_id}")
                    if str(document.get("product_id") or "") != product_id:
                        raise VerificationError(f"document product mismatch: {product_id}")
                    scope = str(document.get("scope") or "")
                    if scope not in {"variant", "weight", "batch", "product", "vendor"}:
                        raise VerificationError(f"document invalid scope: {product_id} {variant_id}")
                    document_variant_id = str(document.get("variant_id") or "")
                    if scope in {"variant", "weight", "batch"}:
                        if document_variant_id != variant_id:
                            raise VerificationError(f"document variant identity mismatch: {product_id} {variant_id}")
                    elif document_variant_id:
                        raise VerificationError(f"broad document has variant identity: {product_id} {variant_id}")
                    if scope == "variant":
                        source_identity = str(document.get("source_variant_id") or "")
                        target_source_identity = str(variant.get("source_variant_id") or "")
                        if not source_identity or source_identity not in {variant_id, target_source_identity}:
                            raise VerificationError(f"document source variant identity mismatch: {product_id} {variant_id}")
                    elif scope == "weight":
                        try:
                            document_grams = float(document["grams"])
                            variant_grams = float(variant["grams"])
                        except (KeyError, TypeError, ValueError) as exc:
                            raise VerificationError(f"document weight identity missing: {product_id} {variant_id}") from exc
                        if abs(document_grams - variant_grams) > 0.01:
                            raise VerificationError(f"document weight identity mismatch: {product_id} {variant_id}")
                    elif scope == "batch":
                        document_batches = {
                            normalized
                            for value in (document.get("batch"), document.get("lot"))
                            if (normalized := str(value or "").strip().casefold())
                        }
                        variant_batches = {
                            normalized
                            for value in (variant.get("batch"), variant.get("lot"))
                            if (normalized := str(value or "").strip().casefold())
                        }
                        if not document_batches or not variant_batches or document_batches.isdisjoint(variant_batches):
                            raise VerificationError(f"document batch identity mismatch: {product_id} {variant_id}")
            index_variant_identities = index_variants_by_product.get(product_id)
            if index_variant_identities is None:
                raise VerificationError(f"detail product absent from index: {product_id}")
            if set(detail_variant_identities) != set(index_variant_identities):
                missing = sorted(set(index_variant_identities) - set(detail_variant_identities))
                extra = sorted(set(detail_variant_identities) - set(index_variant_identities))
                raise VerificationError(
                    f"index/detail variant identity mismatch: {product_id} missing={missing} extra={extra}"
                )
            for variant_id, (detail_grams, detail_url) in detail_variant_identities.items():
                index_grams, index_url = index_variant_identities[variant_id]
                if abs(detail_grams - index_grams) > 0.0001:
                    raise VerificationError(
                        f"index/detail variant weight mismatch: {product_id} {variant_id}"
                    )
                if detail_url != index_url:
                    raise VerificationError(
                        f"index/detail variant URL mismatch: {product_id} {variant_id}"
                    )

    if product_ids != detail_product_ids:
        raise VerificationError("index/detail product identity mismatch")
    if manifest.get("product_count") != len(product_ids) or index.get("product_count") != len(product_ids):
        raise VerificationError("product count mismatch")
    if manifest.get("in_stock_variant_count") != len(variant_ids) or index.get("in_stock_variant_count") != len(variant_ids):
        raise VerificationError("variant count mismatch")
    if declared_detail_count != len(product_ids):
        raise VerificationError("detail product count mismatch")
    if manifest.get("vendor_count") != vendors.get("vendor_count"):
        raise VerificationError("vendor count mismatch")
    return {
        "generation_id": generation_id,
        "products": len(product_ids),
        "variants": len(variant_ids),
        "vendors": vendors.get("vendor_count", 0),
        "detail_shards": len(manifest.get("product_detail_shards") or []),
        "verified": True,
    }
