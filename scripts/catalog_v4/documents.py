from __future__ import annotations

from typing import Any

from .document_urls import canonical_document_url
from .identity import stable_digest
from .normalization import canonical_url, clean_text, normalized_search

ALLOWED_KINDS = {"coa", "terpene", "combined", "unknown"}
ALLOWED_SCOPES = {"variant", "weight", "batch", "product", "vendor"}
WEIGHT_TOLERANCE_GRAMS = 0.01


def _identity(value: Any) -> str:
    return normalized_search(value).replace(" ", "_")


def _reject(
    rejections: list[dict[str, Any]] | None,
    *,
    reason: str,
    raw: dict[str, Any],
    public_url: str = "",
    scope: str = "",
) -> None:
    if rejections is None:
        return
    rejections.append({
        "record_type": "document_mapping",
        "document_id": clean_text(raw.get("document_id")),
        "url": public_url,
        "scope": scope,
        "reason": reason,
    })


def normalize_documents(
    value: Any,
    *,
    product_id: str,
    vendor_id: str = "",
    variant_id: str = "",
    source_variant_id: str = "",
    grams: float | None = None,
    batch: str = "",
    lot: str = "",
    rejections: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    target_vendor_id = clean_text(vendor_id)
    target_variant_ids = {
        value
        for value in (clean_text(variant_id), clean_text(source_variant_id))
        if value
    }
    target_batch_ids = {
        _identity(value)
        for value in (batch, lot)
        if clean_text(value)
    }
    output: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        source_vendor_id = clean_text(raw.get("vendor_id") or raw.get("source_id"))
        if target_vendor_id and source_vendor_id and source_vendor_id != target_vendor_id:
            _reject(rejections, reason="document_vendor_mismatch", raw=raw)
            continue
        public_url = canonical_document_url(raw.get("url") or raw.get("public_url") or raw.get("source_url"))
        if not public_url:
            _reject(rejections, reason="document_invalid_public_url", raw=raw)
            continue
        kind = normalized_search(raw.get("kind") or raw.get("document_type") or "unknown").replace(" ", "_")
        kind = kind if kind in ALLOWED_KINDS else "unknown"
        scope = normalized_search(raw.get("scope") or "product").replace(" ", "_")
        if scope not in ALLOWED_SCOPES:
            _reject(rejections, reason="document_invalid_scope", raw=raw, public_url=public_url, scope=scope)
            continue

        mapped_variant = clean_text(raw.get("variant_id") or raw.get("source_variant_id"))
        raw_grams = raw.get("grams") if raw.get("grams") not in (None, "") else raw.get("weight_grams")
        source_batch_ids = {
            _identity(value)
            for value in (raw.get("batch"), raw.get("lot"))
            if clean_text(value)
        }

        if scope == "variant":
            if not mapped_variant:
                _reject(rejections, reason="document_variant_identity_missing", raw=raw, public_url=public_url, scope=scope)
                continue
            if not target_variant_ids or mapped_variant not in target_variant_ids:
                _reject(rejections, reason="document_variant_identity_mismatch", raw=raw, public_url=public_url, scope=scope)
                continue
        elif scope == "weight":
            if raw_grams in (None, ""):
                _reject(rejections, reason="document_weight_identity_missing", raw=raw, public_url=public_url, scope=scope)
                continue
            try:
                source_grams = float(raw_grams)
            except (TypeError, ValueError):
                _reject(rejections, reason="document_weight_identity_invalid", raw=raw, public_url=public_url, scope=scope)
                continue
            if grams is None or abs(source_grams - float(grams)) > WEIGHT_TOLERANCE_GRAMS:
                _reject(rejections, reason="document_weight_identity_mismatch", raw=raw, public_url=public_url, scope=scope)
                continue
        elif scope == "batch":
            if not source_batch_ids:
                _reject(rejections, reason="document_batch_identity_missing", raw=raw, public_url=public_url, scope=scope)
                continue
            if not target_batch_ids or source_batch_ids.isdisjoint(target_batch_ids):
                _reject(rejections, reason="document_batch_identity_mismatch", raw=raw, public_url=public_url, scope=scope)
                continue

        doc_id = clean_text(raw.get("document_id")) or stable_digest(
            kind,
            public_url,
            clean_text(raw.get("batch") or raw.get("lot")),
            length=28,
        )
        record = {
            "document_id": doc_id,
            "kind": kind,
            "public_url": public_url,
            "mime_type": clean_text(raw.get("mime_type")),
            "scope": scope,
            "vendor_id": source_vendor_id or target_vendor_id,
            "product_id": product_id,
            "variant_id": variant_id if scope in {"variant", "weight", "batch"} else "",
            "source_variant_id": mapped_variant,
            "grams": float(raw_grams) if scope == "weight" else None,
            "batch": clean_text(raw.get("batch")),
            "lot": clean_text(raw.get("lot")),
            "lab": clean_text(raw.get("lab")),
            "test_date": clean_text(raw.get("test_date")),
            "source_page": canonical_url(raw.get("source_page"), keep_variant=True),
            "discovered_label": clean_text(raw.get("label") or raw.get("discovered_label")),
            "provenance": raw.get("provenance") if isinstance(raw.get("provenance"), dict) else {},
        }
        current = output.get(doc_id)
        if current is None or sum(value not in (None, "", [], {}) for value in record.values()) > sum(
            value not in (None, "", [], {}) for value in current.values()
        ):
            output[doc_id] = record
    return sorted(output.values(), key=lambda item: (item["kind"], item["document_id"]))
