"""Pure catalog annotation integration that never removes a product for missing labs."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .mapping import map_documents
from .models import DocumentCandidate, MappingDecision, ParsedLabRecord

ROLE_ORDER = {
    "coa": 0,
    "combined_lab_report": 1,
    "terpene_report": 2,
    "legal_document": 3,
    "unknown": 4,
}


def _target_identity(product: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(product.get("source_id") or product.get("vendor_id") or ""),
        str(product.get("id") or product.get("product_id") or ""),
        str(product.get("variant_id") or product.get("source_variant_id") or product.get("variant") or ""),
    )


def _evidence_record(
    decision: MappingDecision,
    candidate: DocumentCandidate | None,
    parsed: ParsedLabRecord | None,
) -> dict[str, Any]:
    source_url = parsed.source_url if parsed else (candidate.url if candidate else "")
    return {
        "document_id": decision.document_id,
        "document_kind": decision.document_kind,
        "mapping_scope": decision.scope,
        "mapping_score": decision.score,
        "mapping_reasons": list(decision.reasons),
        "parse_status": parsed.parse_status if parsed else "unavailable",
        "source_url": source_url,
        "cannabinoids": parsed.cannabinoids if parsed else {},
        "terpenes": parsed.terpenes if parsed else {},
        "total_cannabinoids": parsed.total_cannabinoids if parsed else None,
        "total_terpenes": parsed.total_terpenes if parsed else None,
        "provenance": candidate.provenance.to_dict() if candidate and hasattr(candidate.provenance, "to_dict") else (
            candidate.provenance.__dict__ if candidate and candidate.provenance else {}
        ),
    }


def _unavailable_evidence() -> dict[str, Any]:
    return {
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


def annotate_products(
    products: list[dict[str, Any]],
    candidates: list[DocumentCandidate],
    parsed_records: list[ParsedLabRecord],
    profiles: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    parsed_by_id = {record.document_id: record for record in parsed_records}
    candidate_by_id = {candidate.document_id: candidate for candidate in candidates}
    decisions = map_documents(products, candidates, parsed_by_id)
    decisions_by_target: dict[tuple[str, str, str], list[MappingDecision]] = {}
    ambiguities_by_target: dict[tuple[str, str, str], list[MappingDecision]] = {}
    for decision in decisions:
        target = (decision.vendor_id, decision.product_id, decision.variant_id)
        destination = ambiguities_by_target if decision.ambiguous else decisions_by_target
        destination.setdefault(target, []).append(decision)

    profile_map = profiles or {}
    output: list[dict[str, Any]] = []
    for source in products:
        product = deepcopy(source)
        vendor_id, product_id, variant_id = _target_identity(product)
        profile = profile_map.get(vendor_id) or {}
        labs = profile.get("labs") or {}
        product["vendor_compliance"] = {
            "age_verification": (profile.get("age_verification") or {}).get("classification", "uncertain"),
            "coa_availability": labs.get("coa_availability", "uncertain"),
            "terpene_availability": labs.get("terpene_availability", "uncertain"),
            "profile_verified_at": profile.get("verified_at", ""),
        }

        target = (vendor_id, product_id, variant_id)
        selected = sorted(
            decisions_by_target.get(target, []),
            key=lambda item: (ROLE_ORDER.get(item.document_kind, 99), -item.score, item.document_id),
        )
        evidence_records: list[dict[str, Any]] = []
        for decision in selected:
            candidate = candidate_by_id.get(decision.document_id)
            parsed = parsed_by_id.get(decision.document_id)
            if candidate and candidate.vendor_id != vendor_id:
                continue
            if parsed and parsed.vendor_id != vendor_id:
                continue
            evidence_records.append(_evidence_record(decision, candidate, parsed))

        product["lab_evidence_records"] = evidence_records
        product["lab_evidence_ambiguities"] = [
            {
                "document_id": decision.document_id,
                "document_kind": decision.document_kind,
                "mapping_scope": decision.scope,
                "mapping_score": decision.score,
                "mapping_reasons": list(decision.reasons),
            }
            for decision in sorted(
                ambiguities_by_target.get(target, []),
                key=lambda item: (ROLE_ORDER.get(item.document_kind, 99), item.document_id),
            )
        ]
        # Backward-compatible primary evidence. The typed collection above is the
        # authoritative multi-document contract; existing consumers continue to
        # receive the strongest COA/combined/terpene record through this field.
        product["lab_evidence"] = evidence_records[0] if evidence_records else _unavailable_evidence()
        output.append(product)
    return output
