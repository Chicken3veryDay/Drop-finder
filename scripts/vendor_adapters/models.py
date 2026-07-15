"""Typed contracts for public vendor compliance and laboratory evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from typing import Any, Literal

AgeGateClassification = Literal[
    "identity_verification_required",
    "identity_verification_conditional",
    "self_attestation_21_plus",
    "no_observed_gate",
    "uncertain",
]
Availability = Literal["public", "partial", "not_observed", "inaccessible", "unsupported", "uncertain"]
EvidenceStatus = Literal["current", "conflicting", "inaccessible", "stale"]
DocumentKind = Literal["coa", "terpene_report", "combined_lab_report", "legal_document", "unknown"]
ParseStatus = Literal["parsed", "partial", "unsupported_scanned", "unsupported_format", "invalid", "unavailable"]
MappingScope = Literal["variant", "weight", "batch", "product", "vendor", "unmatched"]


def stable_document_id(*parts: str) -> str:
    material = "\x1f".join(str(part or "").strip().lower() for part in parts)
    return sha256(material.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class Provenance:
    source_url: str
    discovery_method: str
    observed_at: str
    source_type: str = "public_web"
    evidence_status: EvidenceStatus = "current"
    notes: str = ""


@dataclass(frozen=True)
class DocumentCandidate:
    vendor_id: str
    url: str
    document_kind: DocumentKind = "unknown"
    title: str = ""
    product_url: str = ""
    product_id: str = ""
    variant_id: str = ""
    variant_label: str = ""
    weight_grams: float | None = None
    batch_id: str = ""
    content_type_hint: str = ""
    provenance: Provenance | None = None
    document_id: str = ""

    def __post_init__(self) -> None:
        if not self.document_id:
            object.__setattr__(
                self,
                "document_id",
                stable_document_id(
                    self.vendor_id,
                    self.url,
                    self.document_kind,
                    self.product_id,
                    self.variant_id,
                    self.batch_id,
                ),
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ParsedLabRecord:
    document_id: str
    vendor_id: str
    source_url: str
    document_kind: DocumentKind
    parse_status: ParseStatus
    parser_id: str
    report_title: str = ""
    laboratory: str = ""
    report_date: str = ""
    sample_id: str = ""
    batch_id: str = ""
    product_name: str = ""
    variant_label: str = ""
    weight_grams: float | None = None
    cannabinoids: dict[str, float] = field(default_factory=dict)
    terpenes: dict[str, float] = field(default_factory=dict)
    total_cannabinoids: float | None = None
    total_terpenes: float | None = None
    limitations: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MappingDecision:
    product_id: str
    document_id: str
    scope: MappingScope
    score: int
    reasons: tuple[str, ...]
    ambiguous: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
