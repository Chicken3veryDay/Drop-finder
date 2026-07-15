"""Deterministic lab-document mapping for product, variant, weight, and batch scopes."""
from __future__ import annotations

import re
from typing import Any

from .models import DocumentCandidate, MappingDecision, ParsedLabRecord

WEIGHT_RE = re.compile(r"(?<!\d)(0\.5|1|2|3\.5|4|7|8|14|16|28|32)\s*(?:g|grams?)\b", re.I)


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


def score_candidate(product: dict[str, Any], candidate: DocumentCandidate, parsed: ParsedLabRecord | None = None) -> MappingDecision:
    product_id = str(product.get("id") or product.get("product_id") or "")
    variant_id = str(product.get("variant_id") or product.get("variant") or "")
    batch_id = str(product.get("batch_id") or product.get("batch") or "")
    name = _norm(product.get("name") or product.get("title"))
    variant_label = _norm(product.get("variant_label") or product.get("variant"))
    candidate_name = _norm((parsed.product_name if parsed else "") or candidate.title)
    candidate_variant = _norm((parsed.variant_label if parsed else "") or candidate.variant_label)
    candidate_batch = str((parsed.batch_id if parsed else "") or candidate.batch_id)
    reasons: list[str] = []
    scope = "unmatched"
    score = 0
    if candidate.vendor_id != str(product.get("source_id") or product.get("vendor_id") or ""):
        return MappingDecision(product_id, candidate.document_id, "unmatched", -1000, ("vendor mismatch",))
    score += 5
    scope = "vendor"
    reasons.append("same vendor")
    if candidate.product_id and candidate.product_id == product_id:
        score += 80; scope = "product"; reasons.append("exact product id")
    elif name and candidate_name and (name == candidate_name or name in candidate_name or candidate_name in name):
        score += 45; scope = "product"; reasons.append("normalized product-name match")
    if variant_id and candidate.variant_id and variant_id == candidate.variant_id:
        score += 120; scope = "variant"; reasons.append("exact variant id")
    elif variant_label and candidate_variant and variant_label == candidate_variant:
        score += 90; scope = "variant"; reasons.append("exact variant label")
    product_weight = _grams(product)
    report_weight = (parsed.weight_grams if parsed else None) or candidate.weight_grams
    if product_weight is not None and report_weight is not None and abs(product_weight - report_weight) <= 0.02:
        score += 70; scope = "weight" if scope in {"vendor", "product", "unmatched"} else scope; reasons.append("exact normalized weight")
    if batch_id and candidate_batch and _norm(batch_id) == _norm(candidate_batch):
        score += 150; scope = "batch" if scope != "variant" else scope; reasons.append("exact batch id")
    return MappingDecision(product_id, candidate.document_id, scope, score, tuple(reasons))  # type: ignore[arg-type]


def map_documents(products: list[dict[str, Any]], candidates: list[DocumentCandidate], parsed: dict[str, ParsedLabRecord] | None = None) -> list[MappingDecision]:
    parsed = parsed or {}
    decisions: list[MappingDecision] = []
    for product in products:
        scored = [score_candidate(product, candidate, parsed.get(candidate.document_id)) for candidate in candidates]
        scored = [item for item in scored if item.score > 5]
        scored.sort(key=lambda item: (-item.score, item.document_id))
        if not scored:
            continue
        best = scored[0]
        ambiguous = len(scored) > 1 and scored[1].score == best.score
        decisions.append(MappingDecision(best.product_id, best.document_id, best.scope, best.score, best.reasons, ambiguous))
    return sorted(decisions, key=lambda item: (item.product_id, item.document_id))
