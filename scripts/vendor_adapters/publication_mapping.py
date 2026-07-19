"""Convert vendor document candidates into Catalog V4 document records."""
from __future__ import annotations

from typing import Any

from .mapping import map_documents
from .models import DocumentCandidate, MappingDecision
from .publication_common import (
    product_id,
    product_url,
    source_product_id,
    source_variant_id,
    vendor_id,
)


def _kind(value: str) -> str:
    return {
        "coa": "coa",
        "terpene_report": "terpene",
        "combined_lab_report": "combined",
    }.get(str(value or ""), "unknown")


def _target_index(products: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    output: dict[tuple[str, str, str], dict[str, Any]] = {}
    for product in products:
        key = (vendor_id(product), product_id(product), source_variant_id(product))
        if key[0] and key[1]:
            output[key] = product
    return output


def _record(
    decision: MappingDecision,
    candidate: DocumentCandidate,
    target: dict[str, Any],
) -> dict[str, Any]:
    provenance = candidate.to_dict().get("provenance") or {}
    output: dict[str, Any] = {
        "document_id": candidate.document_id,
        "vendor_id": decision.vendor_id,
        "source_product_id": source_product_id(target),
        "product_url": product_url(target),
        "url": candidate.url,
        "kind": _kind(decision.document_kind),
        "scope": decision.scope,
        "label": candidate.title,
        "mime_type": candidate.content_type_hint,
        "source_page": str(provenance.get("source_url") or ""),
        "provenance": {
            **provenance,
            "mapping_score": decision.score,
            "mapping_reasons": list(decision.reasons),
        },
    }
    if decision.scope == "variant":
        output["source_variant_id"] = source_variant_id(target)
    elif decision.scope == "weight":
        output["grams"] = candidate.weight_grams
    elif decision.scope == "batch":
        output["batch"] = candidate.batch_id
    return output


def map_publication_documents(
    products: list[dict[str, Any]],
    candidates: list[DocumentCandidate],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    decisions = map_documents(products, candidates)
    candidate_by_id = {candidate.document_id: candidate for candidate in candidates}
    targets = _target_index(products)
    selected: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    mapped_ids: set[str] = set()
    ambiguous_ids = {decision.document_id for decision in decisions if decision.ambiguous}

    for decision in decisions:
        if decision.ambiguous:
            continue
        candidate = candidate_by_id.get(decision.document_id)
        target = targets.get((decision.vendor_id, decision.product_id, decision.variant_id))
        if candidate is None or target is None:
            continue
        record = _record(decision, candidate, target)
        identity = str(
            record.get("source_variant_id")
            or record.get("grams")
            or record.get("batch")
            or ""
        )
        key = (
            record["vendor_id"],
            record["source_product_id"],
            identity,
            record["kind"],
            record["url"],
        )
        selected[key] = record
        mapped_ids.add(decision.document_id)

    documents = sorted(
        selected.values(),
        key=lambda row: (
            row["vendor_id"],
            row["source_product_id"],
            row["scope"],
            row["kind"],
            row["url"],
        ),
    )
    unmatched: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.document_id in mapped_ids:
            continue
        row = candidate.to_dict()
        row["reason"] = (
            "ambiguous_product_match"
            if candidate.document_id in ambiguous_ids
            else "no_unambiguous_product_match"
        )
        unmatched.append(row)
    unmatched.sort(
        key=lambda row: (
            row["vendor_id"],
            row["document_kind"],
            row["url"],
            row["document_id"],
        )
    )
    return documents, unmatched, [decision.to_dict() for decision in decisions]
