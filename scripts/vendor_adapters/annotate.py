"""Pure catalog annotation integration that never removes a product for missing labs."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from .mapping import map_documents, mapping_identity
from .models import DocumentCandidate, MappingDecision, ParsedLabRecord

KIND_PREFERENCE = {
    "combined_lab_report": 0,
    "coa": 1,
    "terpene_report": 2,
    "unknown": 3,
    "legal_document": 4,
}
CATALOG_KIND = {
    "coa": "coa",
    "terpene_report": "terpene",
    "combined_lab_report": "combined",
    "unknown": "unknown",
    "legal_document": "unknown",
}


def _decision_identity(decision: MappingDecision) -> tuple[str, str, str, str, float | None]:
    return (
        decision.vendor_id,
        decision.product_id,
        decision.target_variant_id,
        decision.target_batch_id,
        decision.target_weight_grams,
    )


def _evidence(
    decision: MappingDecision,
    candidate: DocumentCandidate,
    record: ParsedLabRecord | None,
) -> dict[str, Any]:
    return {
        "document_id": decision.document_id,
        "document_kind": candidate.document_kind,
        "mapping_scope": decision.scope,
        "mapping_score": decision.score,
        "mapping_reasons": list(decision.reasons),
        "parse_status": record.parse_status if record else "unavailable",
        "source_url": record.source_url if record else candidate.url,
        "source_path": candidate.source_path,
        "vendor_id": decision.vendor_id,
        "product_id": decision.product_id,
        "variant_id": candidate.variant_id,
        "batch_id": candidate.batch_id,
        "weight_grams": candidate.weight_grams,
        "cannabinoids": record.cannabinoids if record else {},
        "terpenes": record.terpenes if record else {},
        "total_cannabinoids": record.total_cannabinoids if record else None,
        "total_terpenes": record.total_terpenes if record else None,
    }


def _catalog_document(
    decision: MappingDecision,
    candidate: DocumentCandidate,
) -> dict[str, Any]:
    return {
        "document_id": decision.document_id,
        "vendor_id": decision.vendor_id,
        "source_product_id": candidate.product_id or decision.product_id,
        "source_variant_id": candidate.variant_id,
        "url": candidate.url,
        "kind": CATALOG_KIND.get(candidate.document_kind, "unknown"),
        "scope": decision.scope,
        "grams": candidate.weight_grams,
        "batch": candidate.batch_id,
        "label": candidate.title,
        "mime_type": candidate.content_type_hint,
        "source_page": candidate.provenance.source_url if candidate.provenance else "",
        "provenance": candidate.provenance.to_dict() if hasattr(candidate.provenance, "to_dict") else (
            {
                "source_url": candidate.provenance.source_url,
                "discovery_method": candidate.provenance.discovery_method,
                "observed_at": candidate.provenance.observed_at,
                "source_type": candidate.provenance.source_type,
                "evidence_status": candidate.provenance.evidence_status,
                "notes": candidate.provenance.notes,
            }
            if candidate.provenance else {}
        ),
    }


def annotate_products(
    products: list[dict[str, Any]],
    candidates: list[DocumentCandidate],
    parsed_records: list[ParsedLabRecord],
    profiles: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    parsed_by_id = {record.document_id: record for record in parsed_records}
    candidates_by_id = {candidate.document_id: candidate for candidate in candidates}
    decisions = map_documents(products, candidates, parsed_by_id)
    decisions_by_target: dict[tuple[str, str, str, str, float | None], list[MappingDecision]] = defaultdict(list)
    ambiguous_by_target: dict[tuple[str, str, str, str, float | None], list[MappingDecision]] = defaultdict(list)
    for decision in decisions:
        target = _decision_identity(decision)
        if decision.ambiguous:
            ambiguous_by_target[target].append(decision)
        else:
            decisions_by_target[target].append(decision)

    profile_map = profiles or {}
    output: list[dict[str, Any]] = []
    for source in products:
        product = deepcopy(source)
        vendor_id, product_id, _variant_id, _batch_id, _weight = mapping_identity(product)
        target = mapping_identity(product)
        profile = profile_map.get(vendor_id) or {}
        labs = profile.get("labs") or {}
        product["vendor_compliance"] = {
            "age_verification": (profile.get("age_verification") or {}).get("classification", "uncertain"),
            "coa_availability": labs.get("coa_availability", "uncertain"),
            "terpene_availability": labs.get("terpene_availability", "uncertain"),
            "profile_verified_at": profile.get("verified_at", ""),
        }

        selected = sorted(
            decisions_by_target.get(target, []),
            key=lambda item: (KIND_PREFERENCE.get(item.document_kind, 99), -item.score, item.document_id),
        )
        evidence_rows: list[dict[str, Any]] = []
        catalog_documents: list[dict[str, Any]] = []
        for decision in selected:
            candidate = candidates_by_id.get(decision.document_id)
            if candidate is None or candidate.vendor_id != vendor_id:
                continue
            record = parsed_by_id.get(decision.document_id)
            if record is not None and record.vendor_id != vendor_id:
                continue
            evidence_rows.append(_evidence(decision, candidate, record))
            catalog_documents.append(_catalog_document(decision, candidate))

        product["lab_documents"] = evidence_rows
        existing_documents = [item for item in product.get("documents") or [] if isinstance(item, dict)]
        product["documents"] = [*existing_documents, *catalog_documents]
        product["lab_mapping_diagnostics"] = [
            {
                "document_kind": decision.document_kind,
                "mapping_scope": decision.scope,
                "mapping_score": decision.score,
                "reason": "ambiguous_equal_score",
            }
            for decision in ambiguous_by_target.get(target, [])
        ]
        if evidence_rows:
            product["lab_evidence"] = dict(evidence_rows[0])
        else:
            product["lab_evidence"] = {
                "document_id": "",
                "document_kind": "unknown",
                "mapping_scope": "unmatched",
                "parse_status": "unavailable",
                "source_url": "",
                "cannabinoids": {},
                "terpenes": {},
                "total_cannabinoids": None,
                "total_terpenes": None,
            }
        output.append(product)
    return output
