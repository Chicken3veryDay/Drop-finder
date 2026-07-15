"""Pure catalog annotation integration that never removes a product for missing labs."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .mapping import map_documents
from .models import DocumentCandidate, ParsedLabRecord


def annotate_products(
    products: list[dict[str, Any]],
    candidates: list[DocumentCandidate],
    parsed_records: list[ParsedLabRecord],
    profiles: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    parsed_by_id = {record.document_id: record for record in parsed_records}
    decisions = map_documents(products, candidates, parsed_by_id)
    decisions_by_product = {decision.product_id: decision for decision in decisions if not decision.ambiguous}
    profile_map = profiles or {}
    output: list[dict[str, Any]] = []
    for source in products:
        product = deepcopy(source)
        product_id = str(product.get("id") or product.get("product_id") or "")
        vendor_id = str(product.get("source_id") or product.get("vendor_id") or "")
        profile = profile_map.get(vendor_id) or {}
        labs = profile.get("labs") or {}
        product["vendor_compliance"] = {
            "age_verification": (profile.get("age_verification") or {}).get("classification", "uncertain"),
            "coa_availability": labs.get("coa_availability", "uncertain"),
            "terpene_availability": labs.get("terpene_availability", "uncertain"),
            "profile_verified_at": profile.get("verified_at", ""),
        }
        decision = decisions_by_product.get(product_id)
        if decision:
            record = parsed_by_id.get(decision.document_id)
            product["lab_evidence"] = {
                "document_id": decision.document_id,
                "mapping_scope": decision.scope,
                "mapping_score": decision.score,
                "mapping_reasons": list(decision.reasons),
                "parse_status": record.parse_status if record else "unavailable",
                "source_url": record.source_url if record else "",
                "cannabinoids": record.cannabinoids if record else {},
                "terpenes": record.terpenes if record else {},
                "total_cannabinoids": record.total_cannabinoids if record else None,
                "total_terpenes": record.total_terpenes if record else None,
            }
        else:
            product["lab_evidence"] = {
                "document_id": "",
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
