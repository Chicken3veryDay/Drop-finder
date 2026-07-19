"""Build and validate versioned vendor-document publication artifacts."""
from __future__ import annotations

from typing import Any

from .publication_common import (
    SCHEMA_VERSION,
    catalog_products,
    digest,
    source_product_id,
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


def verify_artifact(
    artifact: Any,
    catalog_payload: dict[str, Any],
    profiles_payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        raise ValueError("document artifact must be an object")
    if artifact.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    if artifact.get("catalog_sha256") != digest(catalog_payload):
        raise ValueError("document artifact catalog binding mismatch")
    if artifact.get("profiles_sha256") != digest(profiles_payload):
        raise ValueError("document artifact profile binding mismatch")

    products = catalog_products(catalog_payload)
    vendor_profiles(profiles_payload)
    targets = {
        (vendor_id(product), source_product_id(product))
        for product in products
        if vendor_id(product) and source_product_id(product)
    }
    documents = artifact.get("documents")
    unmatched = artifact.get("unmatched_documents")
    decisions = artifact.get("mapping_decisions")
    checks = artifact.get("checks")
    if not all(isinstance(value, list) for value in (documents, unmatched, decisions, checks)):
        raise ValueError("document artifact collections must be lists")

    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("document entries must be objects")
        target = (
            str(document.get("vendor_id") or ""),
            str(document.get("source_product_id") or ""),
        )
        if target not in targets:
            raise ValueError(f"document target is absent from catalog: {target}")
        if document.get("scope") not in {"variant", "weight", "batch", "product", "vendor"}:
            raise ValueError("document has invalid mapping scope")
        if not str(document.get("url") or "").startswith(("https://", "http://")):
            raise ValueError("document URL is missing or invalid")

    expected = {
        "product_count": len(products),
        "mapped_document_count": len(documents),
        "unmatched_count": len(unmatched),
    }
    for field, value in expected.items():
        if artifact.get(field) != value:
            raise ValueError(f"{field} mismatch: {artifact.get(field)!r} != {value!r}")
    return {
        "schema_version": SCHEMA_VERSION,
        "product_count": len(products),
        "mapped_document_count": len(documents),
        "unmatched_count": len(unmatched),
        "check_count": len(checks),
        "failed_check_count": sum(
            1 for item in checks if isinstance(item, dict) and not item.get("ok")
        ),
    }
