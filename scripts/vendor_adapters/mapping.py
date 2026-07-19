"""Deterministic lab-document mapping for product, variant, weight, and batch scopes."""
from __future__ import annotations

import re
from typing import Any

from .models import DocumentCandidate, DocumentKind, MappingDecision, ParsedLabRecord

WEIGHT_RE = re.compile(r"(?<!\d)(0\.5|1|2|3\.5|4|7|8|14|16|28|32)\s*(?:g|grams?)\b", re.I)
WEIGHT_TOLERANCE_GRAMS = 0.02

# Score bands encode the documented scope precedence. A narrower exact match
# must outrank every possible combination of broader signals.
SCORE_VENDOR = 5
SCORE_PRODUCT_NAME = 45
SCORE_PRODUCT_ID = 80
SCORE_WEIGHT = 200
SCORE_BATCH = 500
SCORE_VARIANT_LABEL = 900
SCORE_VARIANT_ID = 1000
SCOPE_PRECEDENCE = ("variant", "batch", "weight", "product", "vendor")
ROLE_ORDER = {
    "coa": 0,
    "terpene_report": 1,
    "combined_lab_report": 2,
    "legal_document": 3,
    "unknown": 4,
}


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _grams(product: dict[str, Any]) -> float | None:
    raw = product.get("grams") or product.get("weight_grams")
    try:
        if raw not in (None, ""):
            return round(float(raw), 4)
    except (TypeError, ValueError):
        pass
    match = WEIGHT_RE.search(" ".join(str(product.get(key) or "") for key in ("name", "variant", "variant_label")))
    return float(match.group(1)) if match else None


def _target_identity(product: dict[str, Any]) -> tuple[str, str, str]:
    vendor_id = str(product.get("source_id") or product.get("vendor_id") or "")
    product_id = str(product.get("id") or product.get("product_id") or "")
    variant_id = str(product.get("variant_id") or product.get("source_variant_id") or product.get("variant") or "")
    return vendor_id, product_id, variant_id


def _document_kind(candidate: DocumentCandidate, parsed: ParsedLabRecord | None = None) -> DocumentKind:
    if parsed and parsed.document_kind != "unknown":
        return parsed.document_kind
    return candidate.document_kind


def _unmatched(product: dict[str, Any], candidate: DocumentCandidate, reason: str) -> MappingDecision:
    vendor_id, product_id, variant_id = _target_identity(product)
    return MappingDecision(
        product_id,
        candidate.document_id,
        "unmatched",
        -1000,
        (reason,),
        vendor_id=vendor_id,
        variant_id=variant_id,
        document_kind=candidate.document_kind,
    )


def score_candidate(
    product: dict[str, Any],
    candidate: DocumentCandidate,
    parsed: ParsedLabRecord | None = None,
) -> MappingDecision:
    vendor_id, product_id, target_variant_id = _target_identity(product)
    explicit_variant_id = str(product.get("variant_id") or product.get("source_variant_id") or "")
    variant_id = explicit_variant_id or str(product.get("variant") or "")
    batch_id = str(product.get("batch_id") or product.get("batch") or product.get("lot") or "")
    name = _norm(product.get("name") or product.get("title"))
    variant_label = _norm(product.get("variant_label") or product.get("variant"))
    candidate_name = _norm((parsed.product_name if parsed else "") or candidate.title)
    candidate_variant = _norm((parsed.variant_label if parsed else "") or candidate.variant_label)
    candidate_batch = str((parsed.batch_id if parsed else "") or candidate.batch_id)
    product_weight = _grams(product)
    report_weight = (parsed.weight_grams if parsed else None) or candidate.weight_grams
    document_kind = _document_kind(candidate, parsed)

    if candidate.vendor_id != vendor_id:
        return _unmatched(product, candidate, "vendor mismatch")
    if product_id and candidate.product_id and product_id != candidate.product_id:
        return _unmatched(product, candidate, "product id conflict")
    if explicit_variant_id and candidate.variant_id and explicit_variant_id != candidate.variant_id:
        return _unmatched(product, candidate, "variant id conflict")
    variant_ids_match = bool(
        explicit_variant_id
        and candidate.variant_id
        and explicit_variant_id == candidate.variant_id
    )
    if not variant_ids_match and variant_label and candidate_variant and variant_label != candidate_variant:
        return _unmatched(product, candidate, "variant label conflict")
    if batch_id and candidate_batch and _norm(batch_id) != _norm(candidate_batch):
        return _unmatched(product, candidate, "batch id conflict")
    if (
        product_weight is not None
        and report_weight is not None
        and abs(product_weight - report_weight) > WEIGHT_TOLERANCE_GRAMS
    ):
        return _unmatched(product, candidate, "weight conflict")

    reasons: list[str] = ["same vendor"]
    matched_scopes = {"vendor"}
    score = SCORE_VENDOR
    product_associated = False

    if candidate.product_id and candidate.product_id == product_id:
        score += SCORE_PRODUCT_ID
        matched_scopes.add("product")
        reasons.append("exact product id")
        product_associated = True
    elif name and candidate_name and (name == candidate_name or name in candidate_name or candidate_name in name):
        score += SCORE_PRODUCT_NAME
        matched_scopes.add("product")
        reasons.append("normalized product-name match")
        product_associated = True

    # Variant, batch, and package weight refine an established product
    # association. They are not globally identifying properties and must never
    # create a mapping from vendor-only evidence.
    if not product_associated:
        return _unmatched(product, candidate, "product identity insufficient")

    if variant_id and candidate.variant_id and variant_id == candidate.variant_id:
        score += SCORE_VARIANT_ID
        matched_scopes.add("variant")
        reasons.append("exact variant id")
    elif variant_label and candidate_variant and variant_label == candidate_variant:
        score += SCORE_VARIANT_LABEL
        matched_scopes.add("variant")
        reasons.append("exact variant label")

    if (
        product_weight is not None
        and report_weight is not None
        and abs(product_weight - report_weight) <= WEIGHT_TOLERANCE_GRAMS
    ):
        score += SCORE_WEIGHT
        matched_scopes.add("weight")
        reasons.append("exact normalized weight")

    if batch_id and candidate_batch and _norm(batch_id) == _norm(candidate_batch):
        score += SCORE_BATCH
        matched_scopes.add("batch")
        reasons.append("exact batch id")

    scope = next(scope for scope in SCOPE_PRECEDENCE if scope in matched_scopes)
    return MappingDecision(
        product_id,
        candidate.document_id,
        scope,  # type: ignore[arg-type]
        score,
        tuple(reasons),
        vendor_id=vendor_id,
        variant_id=target_variant_id,
        document_kind=document_kind,
    )


def map_documents(
    products: list[dict[str, Any]],
    candidates: list[DocumentCandidate],
    parsed: dict[str, ParsedLabRecord] | None = None,
) -> list[MappingDecision]:
    """Select one canonical mapping per substitutable document role.

    COA, terpene, combined, legal, and unknown evidence are independent roles.
    Ambiguity is therefore evaluated within one role for one exact target identity,
    never across non-substitutable evidence kinds.
    """
    parsed = parsed or {}
    decisions: list[MappingDecision] = []
    for product in products:
        grouped: dict[DocumentKind, list[MappingDecision]] = {}
        for candidate in candidates:
            decision = score_candidate(product, candidate, parsed.get(candidate.document_id))
            if decision.score <= SCORE_VENDOR:
                continue
            grouped.setdefault(decision.document_kind, []).append(decision)
        for document_kind, scored in grouped.items():
            scored.sort(key=lambda item: (-item.score, item.document_id))
            best = scored[0]
            ambiguous = len(scored) > 1 and scored[1].score == best.score
            decisions.append(MappingDecision(
                best.product_id,
                best.document_id,
                best.scope,
                best.score,
                best.reasons,
                ambiguous,
                vendor_id=best.vendor_id,
                variant_id=best.variant_id,
                document_kind=document_kind,
            ))
    return sorted(
        decisions,
        key=lambda item: (
            item.vendor_id,
            item.product_id,
            item.variant_id,
            ROLE_ORDER.get(item.document_kind, 99),
            item.document_id,
        ),
    )
