"""Deterministic lab-document mapping for product, variant, weight, and batch scopes."""
from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

from .models import DocumentCandidate, MappingDecision, ParsedLabRecord

WEIGHT_RE = re.compile(r"(?<!\d)(0\.5|1|2|3\.5|4|7|8|14|16|28|32)\s*(?:g|grams?)\b", re.I)
WEIGHT_TOLERANCE_GRAMS = 0.02

SCORE_VENDOR = 5
SCORE_PRODUCT_NAME = 45
SCORE_PRODUCT_ID = 80
SCORE_WEIGHT = 200
SCORE_BATCH = 500
SCORE_VARIANT_LABEL = 900
SCORE_VARIANT_ID = 1000
SCOPE_PRECEDENCE = ("variant", "batch", "weight", "product", "vendor")


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


def mapping_identity(product: dict[str, Any]) -> tuple[str, str, str, str, float | None]:
    return (
        str(product.get("source_id") or product.get("vendor_id") or ""),
        str(product.get("id") or product.get("product_id") or ""),
        str(product.get("variant_id") or product.get("source_variant_id") or product.get("variant") or ""),
        str(product.get("batch_id") or product.get("batch") or product.get("lot") or ""),
        _grams(product),
    )


def _decision(
    product: dict[str, Any],
    candidate: DocumentCandidate,
    scope: str,
    score: int,
    reasons: tuple[str, ...],
    *,
    ambiguous: bool = False,
) -> MappingDecision:
    vendor_id, product_id, variant_id, batch_id, weight = mapping_identity(product)
    return MappingDecision(
        product_id,
        candidate.document_id,
        scope,  # type: ignore[arg-type]
        score,
        reasons,
        ambiguous,
        vendor_id=vendor_id,
        document_kind=candidate.document_kind,
        target_variant_id=variant_id,
        target_batch_id=batch_id,
        target_weight_grams=weight,
    )


def _unmatched(product: dict[str, Any], candidate: DocumentCandidate, reason: str) -> MappingDecision:
    return _decision(product, candidate, "unmatched", -1000, (reason,))


def score_candidate(
    product: dict[str, Any],
    candidate: DocumentCandidate,
    parsed: ParsedLabRecord | None = None,
) -> MappingDecision:
    product_id = str(product.get("id") or product.get("product_id") or "")
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

    if candidate.vendor_id != str(product.get("source_id") or product.get("vendor_id") or ""):
        return _unmatched(product, candidate, "vendor mismatch")
    if product_id and candidate.product_id and product_id != candidate.product_id:
        return _unmatched(product, candidate, "product id conflict")
    if explicit_variant_id and candidate.variant_id and explicit_variant_id != candidate.variant_id:
        return _unmatched(product, candidate, "variant id conflict")
    variant_ids_match = bool(explicit_variant_id and candidate.variant_id and explicit_variant_id == candidate.variant_id)
    if not variant_ids_match and variant_label and candidate_variant and variant_label != candidate_variant:
        return _unmatched(product, candidate, "variant label conflict")
    if batch_id and candidate_batch and _norm(batch_id) != _norm(candidate_batch):
        return _unmatched(product, candidate, "batch id conflict")
    if product_weight is not None and report_weight is not None and abs(product_weight - report_weight) > WEIGHT_TOLERANCE_GRAMS:
        return _unmatched(product, candidate, "weight conflict")

    reasons: list[str] = ["same vendor"]
    matched_scopes = {"vendor"}
    score = SCORE_VENDOR
    if candidate.product_id and candidate.product_id == product_id:
        score += SCORE_PRODUCT_ID
        matched_scopes.add("product")
        reasons.append("exact product id")
    elif name and candidate_name and (name == candidate_name or name in candidate_name or candidate_name in name):
        score += SCORE_PRODUCT_NAME
        matched_scopes.add("product")
        reasons.append("normalized product-name match")
    if variant_id and candidate.variant_id and variant_id == candidate.variant_id:
        score += SCORE_VARIANT_ID
        matched_scopes.add("variant")
        reasons.append("exact variant id")
    elif variant_label and candidate_variant and variant_label == candidate_variant:
        score += SCORE_VARIANT_LABEL
        matched_scopes.add("variant")
        reasons.append("exact variant label")
    if product_weight is not None and report_weight is not None and abs(product_weight - report_weight) <= WEIGHT_TOLERANCE_GRAMS:
        score += SCORE_WEIGHT
        matched_scopes.add("weight")
        reasons.append("exact normalized weight")
    if batch_id and candidate_batch and _norm(batch_id) == _norm(candidate_batch):
        score += SCORE_BATCH
        matched_scopes.add("batch")
        reasons.append("exact batch id")
    scope = next(scope for scope in SCOPE_PRECEDENCE if scope in matched_scopes)
    return _decision(product, candidate, scope, score, tuple(reasons))


def map_documents(
    products: list[dict[str, Any]],
    candidates: list[DocumentCandidate],
    parsed: dict[str, ParsedLabRecord] | None = None,
) -> list[MappingDecision]:
    parsed = parsed or {}
    decisions: list[MappingDecision] = []
    by_kind: dict[str, list[DocumentCandidate]] = defaultdict(list)
    for candidate in candidates:
        by_kind[candidate.document_kind].append(candidate)
    for product in products:
        for kind in sorted(by_kind):
            scored = [score_candidate(product, candidate, parsed.get(candidate.document_id)) for candidate in by_kind[kind]]
            scored = [item for item in scored if item.score > SCORE_VENDOR]
            scored.sort(key=lambda item: (-item.score, item.document_id))
            if not scored:
                continue
            best = scored[0]
            ambiguous = len(scored) > 1 and scored[1].score == best.score and scored[1].document_id != best.document_id
            decisions.append(MappingDecision(
                best.product_id,
                best.document_id,
                best.scope,
                best.score,
                best.reasons,
                ambiguous,
                vendor_id=best.vendor_id,
                document_kind=best.document_kind,
                target_variant_id=best.target_variant_id,
                target_batch_id=best.target_batch_id,
                target_weight_grams=best.target_weight_grams,
            ))
    return sorted(
        decisions,
        key=lambda item: (
            item.vendor_id,
            item.product_id,
            item.target_variant_id,
            item.target_batch_id,
            item.target_weight_grams if item.target_weight_grams is not None else -1.0,
            item.document_kind,
            item.document_id,
        ),
    )
