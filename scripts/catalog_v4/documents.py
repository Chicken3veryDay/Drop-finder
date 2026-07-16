from __future__ import annotations

from typing import Any

from .identity import stable_digest
from .normalization import canonical_url, clean_text, normalized_search

ALLOWED_KINDS = {"coa", "terpene", "combined", "unknown"}
ALLOWED_SCOPES = {"variant", "weight", "batch", "product", "vendor"}


def normalize_documents(
    value: Any,
    *,
    product_id: str,
    vendor_id: str = "",
    variant_id: str = "",
    source_variant_id: str = "",
    grams: float | None = None,
) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    target_vendor_id = clean_text(vendor_id)
    output: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        source_vendor_id = clean_text(raw.get("vendor_id") or raw.get("source_id"))
        if target_vendor_id and source_vendor_id and source_vendor_id != target_vendor_id:
            continue
        public_url = canonical_url(raw.get("url") or raw.get("public_url") or raw.get("source_url"), keep_variant=True)
        if not public_url:
            continue
        kind = normalized_search(raw.get("kind") or raw.get("document_type") or "unknown").replace(" ", "_")
        kind = kind if kind in ALLOWED_KINDS else "unknown"
        scope = normalized_search(raw.get("scope") or "product").replace(" ", "_")
        scope = scope if scope in ALLOWED_SCOPES else "product"
        mapped_variant = clean_text(raw.get("variant_id") or raw.get("source_variant_id"))
        raw_grams = raw.get("grams")
        if (
            scope == "variant"
            and mapped_variant
            and mapped_variant not in {variant_id, source_variant_id}
        ):
            continue
        if scope == "weight" and grams is not None and raw_grams not in (None, ""):
            try:
                if abs(float(raw_grams) - float(grams)) > 0.01:
                    continue
            except (TypeError, ValueError):
                continue
        doc_id = clean_text(raw.get("document_id")) or stable_digest(kind, public_url, clean_text(raw.get("batch") or raw.get("lot")), length=28)
        record = {
            "document_id": doc_id,
            "kind": kind,
            "public_url": public_url,
            "mime_type": clean_text(raw.get("mime_type")),
            "scope": scope,
            "vendor_id": source_vendor_id or target_vendor_id,
            "product_id": product_id,
            "variant_id": variant_id if scope in {"variant", "weight"} else "",
            "batch": clean_text(raw.get("batch")),
            "lot": clean_text(raw.get("lot")),
            "lab": clean_text(raw.get("lab")),
            "test_date": clean_text(raw.get("test_date")),
            "source_page": canonical_url(raw.get("source_page"), keep_variant=True),
            "discovered_label": clean_text(raw.get("label") or raw.get("discovered_label")),
            "provenance": raw.get("provenance") if isinstance(raw.get("provenance"), dict) else {},
        }
        current = output.get(doc_id)
        if current is None or sum(bool(v) for v in record.values()) > sum(bool(v) for v in current.values()):
            output[doc_id] = record
    return sorted(output.values(), key=lambda item: (item["kind"], item["document_id"]))
