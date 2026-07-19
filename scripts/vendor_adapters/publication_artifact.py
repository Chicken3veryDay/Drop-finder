"""Build versioned vendor-document publication artifacts."""
from __future__ import annotations

from typing import Any

from .publication_common import (
    SCHEMA_VERSION,
    catalog_products,
    digest,
    timestamp,
    vendor_id,
    vendor_profiles,
)
from .publication_discovery import collect_candidates
from .publication_mapping import map_publication_documents


def build_artifact(
    catalog_payload: dict[str, Any],
    profiles_payload: dict[str, Any],
    **options: Any,
) -> dict[str, Any]:
    products = catalog_products(catalog_payload)
    profiles = vendor_profiles(profiles_payload)
    candidates, checks = collect_candidates(products, profiles, **options)
    documents, unmatched, decisions = map_publication_documents(products, candidates)
    active_vendors = {vendor_id(product) for product in products if vendor_id(product)}
    ambiguous = {
        row.get("document_id")
        for row in decisions
        if isinstance(row, dict) and row.get("ambiguous")
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": timestamp(options.get("observed_at")),
        "catalog_sha256": digest(catalog_payload),
        "profiles_sha256": digest(profiles_payload),
        "product_count": len(products),
        "active_vendor_count": len(active_vendors),
        "candidate_count": len(candidates),
        "mapped_document_count": len(documents),
        "unmatched_count": len(unmatched),
        "ambiguous_count": len(ambiguous),
        "documents": documents,
        "unmatched_documents": unmatched,
        "mapping_decisions": decisions,
        "checks": checks,
    }
