from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

from . import (
    DETAIL_SCHEMA_VERSION,
    INDEX_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    REJECTION_SCHEMA_VERSION,
    SCHEMA_VERSION,
    VENDOR_SCHEMA_VERSION,
)
from .documents import normalize_documents
from .identity import product_identity, stable_digest, variant_identity
from .selection import select_active_variant
from .strict_json import dumps_strict
from .normalization import (
    canonical_product_url,
    canonical_strain_name,
    canonical_url,
    canonical_variant_url,
    clean_text,
    decimal_number,
    delta9_value,
    effects,
    environment,
    explicit_stock,
    lineage,
    normalize_weight,
    normalized_search,
    percentage,
    rating,
    safe_decimal,
)

TOTAL_THC_FACTOR = Decimal("0.877")


@dataclass(frozen=True)
class BuildResult:
    generation_id: str
    product_count: int
    variant_count: int
    vendor_count: int
    rejected_count: int
    manifest: dict[str, Any]
    files: dict[str, bytes]
    rejections: dict[str, Any]


def _json_bytes(payload: Any) -> bytes:
    return (dumps_strict(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ": "),
    ) + "\n").encode("utf-8")


def _canonical_bytes(payload: Any) -> bytes:
    return dumps_strict(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _timestamp(value: Any) -> str:
    raw = clean_text(value)
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _provenance(raw: dict[str, Any], field: str, value: Any, method: str) -> dict[str, Any]:
    source_path = clean_text(raw.get(f"{field}_source_path") or raw.get("source_path") or raw.get("route_url"))
    return {
        "method": method,
        "source_path": source_path,
        "source_type": clean_text(raw.get("source_type")),
        "collected_at": clean_text(raw.get("collected_at")),
        "raw_value": value,
        "confidence": clean_text(raw.get(f"{field}_confidence") or "source_exposed"),
    }


def _extract_total_thc(raw: dict[str, Any]) -> dict[str, Any]:
    raw_thca = raw.get("thca") if raw.get("thca") not in (None, "") else raw.get("thca_percent")
    raw_delta9 = next(
        (raw.get(key) for key in ("delta9_thc", "delta_9_thc", "d9_thc", "delta9") if raw.get(key) not in (None, "")),
        None,
    )
    raw_direct = next(
        (raw.get(key) for key in ("direct_total_thc", "source_total_thc", "total_thc") if raw.get(key) not in (None, "")),
        None,
    )
    thca = percentage(raw_thca)
    delta9, delta9_method = delta9_value(raw_delta9)
    direct = percentage(raw_direct)
    calculated: Decimal | None = None
    method = "unavailable"
    confidence = "unavailable"
    if thca is not None and delta9 is not None:
        calculated = delta9 + (thca * TOTAL_THC_FACTOR)
        method = "delta9_plus_thca_times_0_877"
        confidence = "calculated_from_measured_inputs"
    elif thca is not None:
        calculated = thca * TOTAL_THC_FACTOR
        method = "thca_only_estimate"
        confidence = "estimate_missing_delta9_statement"
    if calculated is not None and (calculated < 0 or calculated > 100):
        calculated = None
        method = "unavailable"
        confidence = "rejected_impossible_result"
    display = int(calculated.quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if calculated is not None else None
    return {
        "calculated_percent": decimal_number(calculated, "0.0001"),
        "display_percent": display,
        "raw_thca_percent": decimal_number(thca, "0.0001"),
        "raw_delta9_thc_percent": decimal_number(delta9, "0.0001"),
        "direct_source_total_thc_percent": decimal_number(direct, "0.0001"),
        "formula": "delta9_thc + (thca * 0.877)" if calculated is not None else "",
        "method": method,
        "delta9_normalization": delta9_method,
        "confidence": confidence,
        "provenance": {
            "thca": _provenance(raw, "thca", raw_thca, "source_value" if thca is not None else "unavailable"),
            "delta9_thc": _provenance(raw, "delta9_thc", raw_delta9, delta9_method),
            "direct_total_thc": _provenance(raw, "total_thc", raw_direct, "source_value" if direct is not None else "unavailable"),
        },
    }


def _price_fields(raw: dict[str, Any], grams: Decimal) -> tuple[dict[str, Any] | None, str | None]:
    current_raw = next(
        (raw.get(key) for key in ("current_price", "sale_price", "price") if raw.get(key) not in (None, "")),
        None,
    )
    current = safe_decimal(current_raw, minimum=Decimal("0.01"), maximum=Decimal("100000"))
    if current is None:
        return None, "missing_or_invalid_current_price"
    original_raw = next(
        (raw.get(key) for key in ("original_price", "regular_price", "compare_at_price") if raw.get(key) not in (None, "")),
        None,
    )
    original = safe_decimal(original_raw, minimum=Decimal("0.01"), maximum=Decimal("100000"))
    warning = None
    if original is not None and original < current:
        original = None
        warning = "contradictory_original_price_removed"
    if original == current:
        original = None
    discount = None
    if original is not None and original > current:
        discount = ((original - current) / original * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    ppg = (current / grams).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return {
        "current_price": decimal_number(current, "0.01"),
        "original_price": decimal_number(original, "0.01"),
        "discount_percent": decimal_number(discount, "0.01"),
        "price_per_gram": decimal_number(ppg, "0.0001"),
        "pricing_provenance": {
            **_provenance(raw, "price", current_raw, "derived_consistent_variant_pricing"),
            "raw_current_price": current_raw,
            "raw_original_price": original_raw,
        },
        "pricing_warning": warning,
    }, None


def _flatten_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in records:
        if not isinstance(raw, dict):
            continue
        variants = raw.get("variants")
        if isinstance(variants, list) and variants:
            parent = {key: value for key, value in raw.items() if key != "variants"}
            for variant in variants:
                if not isinstance(variant, dict):
                    continue
                parent_documents = parent.get("documents") if isinstance(parent.get("documents"), list) else []
                child_documents = variant.get("documents") if isinstance(variant.get("documents"), list) else []
                merged = dict(parent)
                merged.update(variant)
                if parent_documents or "documents" in variant:
                    merged["documents"] = [*parent_documents, *child_documents]
                merged.setdefault("source_title", raw.get("source_title") or raw.get("name") or raw.get("title"))
                merged.setdefault("name", raw.get("name") or raw.get("title"))
                output.append(merged)
        else:
            output.append(dict(raw))
    return output


def _variant_completeness(variant: dict[str, Any]) -> tuple[int, int, str, str]:
    fields = (
        "source_variant_id",
        "source_weight_label",
        "current_price",
        "original_price",
        "variant_url",
        "image_url",
        "documents",
        "batch",
        "lot",
        "collected_at",
    )
    return (
        sum(variant.get(field) not in (None, "", [], {}) for field in fields),
        int(bool(variant.get("source_variant_id"))),
        clean_text(variant.get("collected_at")),
        str(variant.get("variant_id") or ""),
    )


def _merge_product_field(records: list[dict[str, Any]], key: str) -> Any:
    ranked = sorted(
        records,
        key=lambda row: (
            row.get(key) not in (None, "", [], {}),
            clean_text(row.get("collected_at")),
            sum(row.get(field) not in (None, "", [], {}) for field in row),
        ),
        reverse=True,
    )
    return ranked[0].get(key) if ranked else None



def _product_preference(product: dict[str, Any]) -> tuple[int, int, int, str, str]:
    identity = product.get("provenance", {}).get("identity", {}) if isinstance(product.get("provenance"), dict) else {}
    authority = {
        "source_product_identity": 4,
        "canonical_storefront_handle": 3,
        "canonical_product_url": 2,
        "conservative_vendor_title_fallback": 1,
    }.get(str(identity.get("method") or ""), 0)
    completeness_fields = (
        "vendor_favicon_url", "lineage", "rating", "review_count",
        "effects", "grow_environment", "image_url",
    )
    completeness = sum(product.get(field) not in (None, "", [], {}, "unknown") for field in completeness_fields)
    potency = product.get("total_thc") if isinstance(product.get("total_thc"), dict) else {}
    return (
        authority,
        len(product.get("variants") or []),
        completeness + int(potency.get("calculated_percent") is not None),
        clean_text(product.get("provenance", {}).get("collected_at")),
        str(product.get("product_id") or ""),
    )


def _variant_for_reconciled_product(
    variant: dict[str, Any],
    *,
    selected_product_id: str,
    source_product_id: str,
) -> dict[str, Any]:
    copied = dict(variant)
    identity = dict(copied.get("identity_provenance") or {})
    identity["reconciled_from_product_id"] = source_product_id
    copied["identity_provenance"] = identity
    documents: list[dict[str, Any]] = []
    for raw_document in copied.get("documents") or []:
        if not isinstance(raw_document, dict):
            continue
        document = dict(raw_document)
        document["product_id"] = selected_product_id
        if document.get("scope") in {"variant", "weight"}:
            document["variant_id"] = copied.get("variant_id", "")
        documents.append(document)
    copied["documents"] = documents
    return copied


def _reconcile_product_url_variants(
    candidates: list[dict[str, Any]],
    *,
    selected_product_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    variant_by_id: dict[str, dict[str, Any]] = {}
    resolutions: list[dict[str, Any]] = []
    for product in sorted(candidates, key=lambda item: str(item.get("product_id") or "")):
        source_product_id = str(product.get("product_id") or "")
        for original in product.get("variants") or []:
            if not isinstance(original, dict):
                continue
            candidate = _variant_for_reconciled_product(
                original,
                selected_product_id=selected_product_id,
                source_product_id=source_product_id,
            )
            variant_id = str(candidate.get("variant_id") or "")
            current = variant_by_id.get(variant_id)
            if current is None:
                variant_by_id[variant_id] = candidate
                continue
            selected = max((current, candidate), key=_variant_completeness)
            discarded = candidate if selected is current else current
            variant_by_id[variant_id] = selected
            resolutions.append({
                "variant_id": variant_id,
                "selected_collected_at": selected.get("collected_at", ""),
                "discarded_collected_at": discarded.get("collected_at", ""),
                "method": "product_url_duplicate_variant_id_completeness_then_freshness",
            })

    variant_by_weight: dict[str, dict[str, Any]] = {}
    for candidate in variant_by_id.values():
        weight_key = f"{float(candidate['grams']):.4f}"
        current = variant_by_weight.get(weight_key)
        if current is None:
            variant_by_weight[weight_key] = candidate
            continue
        selected = max((current, candidate), key=_variant_completeness)
        discarded = candidate if selected is current else current
        variant_by_weight[weight_key] = selected
        resolutions.append({
            "normalized_grams": float(candidate["grams"]),
            "selected_variant_id": selected["variant_id"],
            "discarded_variant_id": discarded["variant_id"],
            "method": "product_url_duplicate_weight_completeness_then_freshness",
        })

    variants = sorted(
        variant_by_weight.values(),
        key=lambda row: (float(row["grams"]), float(row["current_price"]), row["variant_id"]),
    )
    return variants, resolutions


def _resolve_duplicate_product_urls(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for product in products:
        grouped[(str(product.get("vendor_id") or ""), str(product.get("canonical_product_url") or ""))].append(product)
    resolved: list[dict[str, Any]] = []
    for key in sorted(grouped):
        candidates = grouped[key]
        if len(candidates) == 1:
            resolved.append(candidates[0])
            continue
        selected_original = max(candidates, key=_product_preference)
        selected = dict(selected_original)
        selected["provenance"] = dict(selected.get("provenance") or {})
        merged_variants, variant_resolutions = _reconcile_product_url_variants(
            candidates,
            selected_product_id=str(selected["product_id"]),
        )
        selected["variants"] = merged_variants
        prior_resolutions: list[dict[str, Any]] = []
        candidate_duplicate_resolutions: dict[str, list[dict[str, Any]]] = {}
        for candidate in sorted(candidates, key=lambda item: str(item.get("product_id") or "")):
            candidate_id = str(candidate.get("product_id") or "")
            candidate_resolutions = candidate.get("provenance", {}).get("duplicate_resolutions", [])
            if not isinstance(candidate_resolutions, list):
                continue
            copied_resolutions = [dict(item) for item in candidate_resolutions if isinstance(item, dict)]
            if copied_resolutions:
                candidate_duplicate_resolutions[candidate_id] = copied_resolutions
            for item in copied_resolutions:
                prior_resolutions.append({**item, "source_product_id": candidate_id})
        selected["provenance"]["duplicate_resolutions"] = prior_resolutions + variant_resolutions
        candidate_variant_count = sum(len(item.get("variants") or []) for item in candidates)
        selected["provenance"]["product_url_conflict_resolution"] = {
            "method": "source_authority_then_variant_coverage_then_completeness_then_freshness",
            "variant_reconciliation_method": "variant_id_then_normalized_weight_completeness_then_freshness",
            "selected_product_id": selected["product_id"],
            "discarded_product_ids": sorted(
                str(item.get("product_id") or "") for item in candidates if item is not selected_original
            ),
            "canonical_product_url": key[1],
            "candidate_variant_count": candidate_variant_count,
            "retained_variant_count": len(merged_variants),
            "discarded_variant_count": candidate_variant_count - len(merged_variants),
            "candidate_variant_counts": {
                str(item.get("product_id") or ""): len(item.get("variants") or [])
                for item in sorted(candidates, key=lambda product: str(product.get("product_id") or ""))
            },
            "candidate_duplicate_resolutions": candidate_duplicate_resolutions,
        }
        resolved.append(selected)
    return resolved


class CatalogBuilder:
    def __init__(self, *, detail_shards: int = 16):
        if not 1 <= detail_shards <= 256:
            raise ValueError("detail_shards must be between 1 and 256")
        self.detail_shards = detail_shards

    def build(
        self,
        records: Iterable[dict[str, Any]],
        *,
        generated_at: Any = None,
        vendor_profiles: dict[str, Any] | list[dict[str, Any]] | None = None,
        document_records: list[dict[str, Any]] | None = None,
    ) -> BuildResult:
        flattened = _flatten_records(records)
        rejections: list[dict[str, Any]] = []
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        normalized_variants: dict[str, list[dict[str, Any]]] = defaultdict(list)

        external_documents: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for document in document_records or []:
            if not isinstance(document, dict):
                continue
            vendor_id = clean_text(document.get("vendor_id") or document.get("source_id"))
            source_key = clean_text(document.get("source_product_id") or document.get("product_id") or document.get("product_url"))
            document_url = clean_text(document.get("url") or document.get("public_url") or document.get("source_url"))
            rejection_base = {
                "record_type": "external_document",
                "source_record_id": stable_digest(vendor_id, source_key, document_url, length=20),
                "source_id": vendor_id,
                "source_title": clean_text(document.get("label") or document.get("title")),
                "url": document_url,
            }
            if not vendor_id:
                rejections.append({**rejection_base, "reason": "external_document_missing_vendor_identity"})
                continue
            if not source_key:
                rejections.append({**rejection_base, "reason": "external_document_missing_product_identity"})
                continue
            external_documents[(vendor_id, source_key)].append(document)

        for ordinal, raw in enumerate(flattened):
            source_id = clean_text(raw.get("source_id"))
            vendor_name = clean_text(raw.get("vendor") or raw.get("vendor_name"))
            source_title = clean_text(raw.get("source_title") or raw.get("name") or raw.get("title"))
            variant_label = clean_text(raw.get("source_weight_label") or raw.get("weight_label") or raw.get("variant"))
            canonical_name = canonical_strain_name(source_title, variant_label)
            source_record_id = stable_digest(
                source_id,
                vendor_name,
                source_title,
                clean_text(raw.get("url")),
                variant_label,
                clean_text(raw.get("source_variant_id") or raw.get("variant_id")),
                length=20,
            )
            base_rejection = {
                "source_record_id": source_record_id,
                "source_id": source_id,
                "vendor": vendor_name,
                "source_title": source_title,
                "url": clean_text(raw.get("url")),
                "variant": variant_label,
            }
            if not source_id or not vendor_name or not canonical_name:
                rejections.append({**base_rejection, "reason": "missing_product_identity_fields"})
                continue
            product_id, identity_provenance = product_identity(raw, canonical_name)
            stock, stock_method = explicit_stock(raw.get("in_stock") if "in_stock" in raw else raw.get("availability") or raw.get("stock_status"))
            if stock is not True:
                rejections.append({
                    **base_rejection,
                    "product_id": product_id,
                    "reason": "out_of_stock_variant" if stock is False else "unknown_stock_variant",
                    "stock_method": stock_method,
                })
                continue
            grams, source_weight_label = normalize_weight(
                raw.get("grams") if raw.get("grams") not in (None, "") else raw.get("weight_grams"),
                variant_label or raw.get("weight") or raw.get("size"),
            )
            if grams is None:
                rejections.append({**base_rejection, "product_id": product_id, "reason": "invalid_or_missing_weight"})
                continue
            price_data, price_error = _price_fields(raw, grams)
            if price_data is None:
                rejections.append({**base_rejection, "product_id": product_id, "reason": price_error})
                continue
            product_url = canonical_product_url(raw.get("canonical_product_url") or raw.get("url") or raw.get("route_url"))
            variant_url = canonical_variant_url(raw.get("variant_url") or raw.get("url") or product_url)
            if not product_url or not variant_url:
                rejections.append({**base_rejection, "product_id": product_id, "reason": "missing_or_invalid_product_url"})
                continue
            variant_id, variant_identity_provenance = variant_identity(
                raw,
                product_id,
                str(grams.normalize()),
                source_weight_label,
                variant_url,
            )
            combined_documents = list(raw.get("documents") or [])
            for key in (
                clean_text(raw.get("source_product_id")),
                clean_text(raw.get("product_id")),
                product_url,
            ):
                if key and (source_id, key) in external_documents:
                    combined_documents.extend(external_documents[(source_id, key)])
            source_variant_id = clean_text(raw.get("source_variant_id") or raw.get("variant_id"))
            target_batch = clean_text(raw.get("batch"))
            target_lot = clean_text(raw.get("lot"))
            documents = normalize_documents(
                combined_documents,
                product_id=product_id,
                vendor_id=source_id,
                variant_id=variant_id,
                source_variant_id=source_variant_id,
                grams=float(grams),
                batch=target_batch,
                lot=target_lot,
                rejections=rejections,
            )
            variant = {
                "variant_id": variant_id,
                "source_variant_id": source_variant_id,
                "grams": decimal_number(grams, "0.0001"),
                "source_weight_label": source_weight_label,
                **price_data,
                "in_stock": True,
                "stock_provenance": _provenance(raw, "availability", raw.get("availability") or raw.get("stock_status") or raw.get("in_stock"), stock_method),
                "variant_url": variant_url,
                "image_url": canonical_url(raw.get("variant_image") or raw.get("image_url") or raw.get("image"), keep_variant=True),
                "documents": documents,
                "batch": target_batch,
                "lot": target_lot,
                "collected_at": clean_text(raw.get("collected_at")),
                "identity_provenance": variant_identity_provenance,
                "raw_variant_label": variant_label,
            }
            product_seed = dict(raw)
            product_seed.update(
                product_id=product_id,
                source_id=source_id,
                vendor_name=vendor_name,
                canonical_strain_name=canonical_name,
                source_title=source_title,
                canonical_product_url=product_url,
                product_identity_provenance=identity_provenance,
            )
            grouped[product_id].append(product_seed)
            normalized_variants[product_id].append(variant)

        products: list[dict[str, Any]] = []
        for product_id in sorted(grouped):
            records_for_product = grouped[product_id]
            variant_by_id: dict[str, dict[str, Any]] = {}
            duplicate_resolutions: list[dict[str, Any]] = []
            for candidate in normalized_variants[product_id]:
                current = variant_by_id.get(candidate["variant_id"])
                if current is None:
                    variant_by_id[candidate["variant_id"]] = candidate
                    continue
                selected = max((current, candidate), key=_variant_completeness)
                discarded = candidate if selected is current else current
                variant_by_id[candidate["variant_id"]] = selected
                duplicate_resolutions.append(
                    {
                        "variant_id": candidate["variant_id"],
                        "selected_collected_at": selected.get("collected_at", ""),
                        "discarded_collected_at": discarded.get("collected_at", ""),
                        "method": "completeness_then_freshness",
                    }
                )
            # One selector entry per normalized weight. Storefronts sometimes
            # expose a stale duplicate variation or the same variant through
            # several routes. Prefer the most complete, freshest, explicit
            # source identity rather than publishing duplicate weights.
            variant_by_weight: dict[str, dict[str, Any]] = {}
            for candidate in variant_by_id.values():
                weight_key = f"{float(candidate['grams']):.4f}"
                current = variant_by_weight.get(weight_key)
                if current is None:
                    variant_by_weight[weight_key] = candidate
                    continue
                selected = max((current, candidate), key=_variant_completeness)
                discarded = candidate if selected is current else current
                variant_by_weight[weight_key] = selected
                duplicate_resolutions.append(
                    {
                        "normalized_grams": float(candidate["grams"]),
                        "selected_variant_id": selected["variant_id"],
                        "discarded_variant_id": discarded["variant_id"],
                        "method": "duplicate_weight_completeness_then_freshness",
                    }
                )
            variants = sorted(
                variant_by_weight.values(),
                key=lambda row: (float(row["grams"]), float(row["current_price"]), row["variant_id"]),
            )
            if not variants:
                continue
            seed = max(
                records_for_product,
                key=lambda row: (
                    sum(row.get(field) not in (None, "", [], {}) for field in row),
                    clean_text(row.get("collected_at")),
                ),
            )
            lineage_value, lineage_provenance = lineage(
                _merge_product_field(records_for_product, "lineage")
                or _merge_product_field(records_for_product, "strain_type"),
                seed.get("source_title"),
                seed.get("description"),
            )
            environment_value, environment_provenance = environment(
                _merge_product_field(records_for_product, "grow_environment")
                or _merge_product_field(records_for_product, "environment"),
                seed.get("source_title"),
                seed.get("description"),
            )
            effect_values, effects_provenance = effects(_merge_product_field(records_for_product, "effects"))
            rating_value, review_count, rating_provenance = rating(
                _merge_product_field(records_for_product, "rating"),
                _merge_product_field(records_for_product, "review_count"),
            )
            potency_candidates = [(_extract_total_thc(row), row) for row in records_for_product]
            potency_rank = {
                "delta9_plus_thca_times_0_877": 3,
                "thca_only_estimate": 2,
                "unavailable": 0,
            }
            potency, potency_source = max(
                potency_candidates,
                key=lambda item: (
                    potency_rank.get(str(item[0].get("method") or ""), 1),
                    item[0].get("calculated_percent") is not None,
                    clean_text(item[1].get("collected_at")),
                ),
            )
            favicon = canonical_url(
                _merge_product_field(records_for_product, "vendor_favicon_url")
                or _merge_product_field(records_for_product, "favicon_url"),
                keep_variant=True,
            )
            products.append(
                {
                    "product_id": product_id,
                    "vendor_id": seed["source_id"],
                    "vendor_name": seed["vendor_name"],
                    "vendor_favicon_url": favicon,
                    "strain_name": min(
                        (clean_text(row.get("canonical_strain_name")) for row in records_for_product if clean_text(row.get("canonical_strain_name"))),
                        key=lambda value: (len(value), value.casefold()),
                    ),
                    "source_title": seed["source_title"],
                    "canonical_product_url": seed["canonical_product_url"],
                    "lineage": lineage_value,
                    "lineage_provenance": lineage_provenance,
                    "total_thc": potency,
                    "rating": rating_value,
                    "review_count": review_count,
                    "rating_provenance": rating_provenance,
                    "effects": effect_values,
                    "effects_provenance": effects_provenance,
                    "grow_environment": environment_value,
                    "environment_provenance": environment_provenance,
                    "image_url": canonical_url(
                        _merge_product_field(records_for_product, "product_image_url")
                        or _merge_product_field(records_for_product, "image_url")
                        or _merge_product_field(records_for_product, "image"),
                        keep_variant=True,
                    ),
                    "variants": variants,
                    "search": {
                        "vendor": normalized_search(seed["vendor_name"]),
                        "strain": normalized_search(seed["canonical_strain_name"]),
                    },
                    "provenance": {
                        "identity": seed["product_identity_provenance"],
                        "source_type": clean_text(seed.get("source_type")),
                        "route_url": canonical_url(seed.get("route_url"), keep_variant=True),
                        "collected_at": clean_text(seed.get("collected_at")),
                        "classification_evidence": seed.get("classification_evidence") if isinstance(seed.get("classification_evidence"), dict) else {},
                        "potency_source_collected_at": clean_text(potency_source.get("collected_at")),
                        "duplicate_resolutions": duplicate_resolutions,
                    },
                }
            )

        products = _resolve_duplicate_product_urls(products)
        products.sort(key=lambda row: (row["vendor_name"].casefold(), row["strain_name"].casefold(), row["product_id"]))
        vendor_payload = self._vendors(products, vendor_profiles)
        generation_basis = {
            "schema_version": SCHEMA_VERSION,
            "products": products,
            "vendors": vendor_payload["vendors"],
            "detail_shards": self.detail_shards,
        }
        generation_id = _sha(_canonical_bytes(generation_basis))[:32]
        stamp = _timestamp(generated_at)

        index_products: list[dict[str, Any]] = []
        detail_shards: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for product in products:
            shard = int(product["product_id"][:8], 16) % self.detail_shards
            default_variant = select_active_variant(product["variants"])
            index_products.append(
                {
                    "product_id": product["product_id"],
                    "default_variant_id": default_variant["variant_id"] if default_variant else None,
                    "detail_shard": shard,
                    "vendor_id": product["vendor_id"],
                    "vendor_name": product["vendor_name"],
                    "vendor_favicon_url": product["vendor_favicon_url"],
                    "strain_name": product["strain_name"],
                    "lineage": product["lineage"],
                    "total_thc_display_percent": product["total_thc"]["display_percent"],
                    "rating": product["rating"],
                    "review_count": product["review_count"],
                    "search": product["search"],
                    "variants": [
                        {
                            "variant_id": variant["variant_id"],
                            "grams": variant["grams"],
                            "source_weight_label": variant["source_weight_label"],
                            "current_price": variant["current_price"],
                            "original_price": variant["original_price"],
                            "discount_percent": variant["discount_percent"],
                            "price_per_gram": variant["price_per_gram"],
                            "product_url": variant["variant_url"],
                            "in_stock": True,
                        }
                        for variant in product["variants"]
                    ],
                }
            )
            detail_shards[shard].append(
                {
                    "product_id": product["product_id"],
                    "vendor_id": product["vendor_id"],
                    "strain_name": product["strain_name"],
                    "source_title": product["source_title"],
                    "canonical_product_url": product["canonical_product_url"],
                    "image_url": product["image_url"],
                    "effects": product["effects"],
                    "grow_environment": product["grow_environment"],
                    "total_thc": product["total_thc"],
                    "lineage_provenance": product["lineage_provenance"],
                    "effects_provenance": product["effects_provenance"],
                    "environment_provenance": product["environment_provenance"],
                    "rating_provenance": product["rating_provenance"],
                    "variants": product["variants"],
                    "provenance": product["provenance"],
                }
            )

        index = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "generation_id": generation_id,
            "generated_at": stamp,
            "product_count": len(index_products),
            "in_stock_variant_count": sum(len(row["variants"]) for row in index_products),
            "products": index_products,
        }
        vendors = {
            **vendor_payload,
            "schema_version": VENDOR_SCHEMA_VERSION,
            "generation_id": generation_id,
            "generated_at": stamp,
        }
        rejection_payload = {
            "schema_version": REJECTION_SCHEMA_VERSION,
            "generation_id": generation_id,
            "generated_at": stamp,
            "count": len(rejections),
            "reason_counts": dict(sorted(Counter(row["reason"] for row in rejections).items())),
            "variants": sorted(
                rejections,
                key=lambda row: (
                    row.get("source_id", ""),
                    row.get("source_title", ""),
                    row.get("source_record_id", ""),
                    row.get("reason", ""),
                ),
            ),
        }

        files: dict[str, bytes] = {
            "catalog-v4/index.json": _json_bytes(index),
            "catalog-v4/vendors.json": _json_bytes(vendors),
            "catalog-v4/rejections.json": _json_bytes(rejection_payload),
        }
        detail_entries: list[dict[str, Any]] = []
        for shard in range(self.detail_shards):
            payload = {
                "schema_version": DETAIL_SCHEMA_VERSION,
                "generation_id": generation_id,
                "generated_at": stamp,
                "shard": shard,
                "product_count": len(detail_shards.get(shard, [])),
                "products": sorted(detail_shards.get(shard, []), key=lambda row: row["product_id"]),
            }
            path = f"catalog-v4/details/{shard:03d}.json"
            files[path] = _json_bytes(payload)
            detail_entries.append({"path": f"data/{path}", "sha256": _sha(files[path]), "product_count": payload["product_count"]})

        manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "catalog_schema_version": SCHEMA_VERSION,
            "generation_id": generation_id,
            "generated_at": stamp,
            "product_count": len(products),
            "in_stock_variant_count": sum(len(row["variants"]) for row in products),
            "vendor_count": len(vendors["vendors"]),
            "compact_index": {
                "path": "data/catalog-v4/index.json",
                "sha256": _sha(files["catalog-v4/index.json"]),
            },
            "product_detail_shards": detail_entries,
            "vendor_profiles": {
                "path": "data/catalog-v4/vendors.json",
                "sha256": _sha(files["catalog-v4/vendors.json"]),
            },
            "rejections": {
                "path": "data/catalog-v4/rejections.json",
                "sha256": _sha(files["catalog-v4/rejections.json"]),
                "count": len(rejections),
            },
            "compatibility": {
                "legacy_catalog_path": "data/catalog.json",
                "legacy_schema": "dropfinder-cloud-catalog-v3",
                "status": "read_only_rollback_input",
            },
        }
        files["catalog-v4/manifest.json"] = _json_bytes(manifest)
        return BuildResult(
            generation_id=generation_id,
            product_count=len(products),
            variant_count=manifest["in_stock_variant_count"],
            vendor_count=manifest["vendor_count"],
            rejected_count=len(rejections),
            manifest=manifest,
            files=files,
            rejections=rejection_payload,
        )

    def _vendors(
        self,
        products: list[dict[str, Any]],
        profiles: dict[str, Any] | list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        source_profiles: dict[str, dict[str, Any]] = {}
        if isinstance(profiles, dict):
            raw_profiles = profiles.get("vendors") if isinstance(profiles.get("vendors"), list) else profiles
            if isinstance(raw_profiles, dict):
                for key, value in raw_profiles.items():
                    if isinstance(value, dict):
                        source_profiles[clean_text(value.get("vendor_id") or key)] = value
            elif isinstance(raw_profiles, list):
                for value in raw_profiles:
                    if isinstance(value, dict):
                        source_profiles[clean_text(value.get("vendor_id") or value.get("source_id"))] = value
        elif isinstance(profiles, list):
            for value in profiles:
                if isinstance(value, dict):
                    source_profiles[clean_text(value.get("vendor_id") or value.get("source_id"))] = value
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for product in products:
            grouped[product["vendor_id"]].append(product)
        vendors = []
        for vendor_id in sorted(grouped):
            rows = grouped[vendor_id]
            profile = source_profiles.get(vendor_id, {})
            favicon = canonical_url(profile.get("favicon_url") or rows[0].get("vendor_favicon_url"), keep_variant=True)
            vendors.append(
                {
                    "vendor_id": vendor_id,
                    "vendor_name": clean_text(profile.get("vendor_name") or rows[0]["vendor_name"]),
                    "favicon_url": favicon,
                    "favicon_provenance": profile.get("favicon_provenance") if isinstance(profile.get("favicon_provenance"), dict) else {},
                    "age_gate_classification": clean_text(profile.get("age_gate_classification") or "uncertain"),
                    "age_gate_evidence_reference": clean_text(profile.get("age_gate_evidence_reference")),
                    "product_count": len(rows),
                    "profile_status": "supplied" if profile else "minimal_generated_from_catalog",
                }
            )
        return {"vendor_count": len(vendors), "vendors": vendors}


def build_catalog(
    records: Iterable[dict[str, Any]],
    *,
    generated_at: Any = None,
    vendor_profiles: dict[str, Any] | list[dict[str, Any]] | None = None,
    document_records: list[dict[str, Any]] | None = None,
    detail_shards: int = 16,
) -> BuildResult:
    return CatalogBuilder(detail_shards=detail_shards).build(
        records,
        generated_at=generated_at,
        vendor_profiles=vendor_profiles,
        document_records=document_records,
    )


def write_result(result: BuildResult, output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    for relative, data in result.files.items():
        path = output_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_bytes(data)
        temp.replace(path)
