from __future__ import annotations

import hashlib
import json
import math
import time
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SourceState(StrEnum):
    UNCERTIFIED = "uncertified"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    PARTIALLY_QUARANTINED = "partially_quarantined"
    QUARANTINED = "quarantined"
    DISABLED = "disabled"
    UNSUPPORTED = "unsupported"
    RETIRED = "retired"


class RouteState(StrEnum):
    UNKNOWN = "unknown"
    PROBING = "probing"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    QUARANTINED = "quarantined"
    RECERTIFYING = "recertifying"
    SHADOW = "shadow"
    BLOCKED = "blocked"
    RETIRED = "retired"


class AdapterState(StrEnum):
    CANDIDATE = "candidate"
    REPLAY_FAILED = "replay_failed"
    REPLAY_PASSED = "replay_passed"
    SHADOW = "shadow"
    CERTIFIED = "certified"
    ACTIVE = "active"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"
    RETIRED = "retired"


class CertificationState(StrEnum):
    PENDING = "pending"
    COLLECTING_EVIDENCE = "collecting_evidence"
    REPLAYING = "replaying"
    SHADOWING = "shadowing"
    VERIFIED = "verified"
    FAILED = "failed"
    EXPIRED = "expired"
    REVOKED = "revoked"


class IncidentState(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    CANDIDATE_GENERATED = "candidate_generated"
    SHADOWING = "shadowing"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"
    ACCEPTED_RISK = "accepted_risk"
    CLOSED = "closed"


class StrategyType(StrEnum):
    OFFICIAL_API = "official_api"
    JSON_ENDPOINT = "json_endpoint"
    EMBEDDED_JSON = "embedded_json"
    JSON_LD = "json_ld"
    HTML_CARDS = "html_cards"
    SITEMAP = "sitemap"
    BROWSER_NETWORK = "browser_network"
    BROWSER_DOM = "browser_dom"


class DriftSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)


class RouteKey(StrictModel):
    source_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")
    route_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.:-]+$")


class FingerprintBundle(StrictModel):
    body_sha256: str = Field(default="", max_length=64)
    json_shape_sha256: str = Field(default="", max_length=64)
    dom_shape_sha256: str = Field(default="", max_length=64)
    network_shape_sha256: str = Field(default="", max_length=64)
    json_paths: tuple[str, ...] = ()
    dom_anchors: tuple[str, ...] = ()
    network_endpoints: tuple[str, ...] = ()


class RouteMetrics(StrictModel):
    response_bytes: int = Field(default=0, ge=0)
    latency_seconds: float = Field(default=0.0, ge=0)
    product_count: int = Field(default=0, ge=0)
    variant_count: int = Field(default=0, ge=0)
    required_field_coverage: float = Field(default=0.0, ge=0, le=100)
    optional_field_coverage: float = Field(default=0.0, ge=0, le=100)
    identity_overlap: float = Field(default=100.0, ge=0, le=100)
    duplicate_rate: float = Field(default=0.0, ge=0, le=100)
    accepted_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    ambiguous_count: int = Field(default=0, ge=0)
    price_null_rate: float = Field(default=0.0, ge=0, le=100)
    availability_null_rate: float = Field(default=0.0, ge=0, le=100)
    pages_fetched: int = Field(default=1, ge=0)
    browser_escalated: bool = False
    complete: bool = True

    @field_validator(
        "latency_seconds",
        "required_field_coverage",
        "optional_field_coverage",
        "identity_overlap",
        "duplicate_rate",
        "price_null_rate",
        "availability_null_rate",
    )
    @classmethod
    def finite_numbers(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("metric values must be finite")
        return value


class RouteObservation(StrictModel):
    observation_id: str = Field(min_length=1, max_length=160)
    source_id: str = Field(min_length=1, max_length=120)
    route_id: str = Field(min_length=1, max_length=160)
    adapter_id: str = Field(default="", max_length=160)
    strategy_type: StrategyType
    requested_url: str = Field(min_length=1, max_length=2000)
    final_url: str = Field(default="", max_length=2000)
    http_status: int = Field(default=0, ge=0, le=999)
    mime_type: str = Field(default="", max_length=200)
    outcome: Literal["success", "failure", "blocked", "budget_exhausted"]
    error_code: str = Field(default="", max_length=120)
    error_message: str = Field(default="", max_length=2000)
    metrics: RouteMetrics = Field(default_factory=RouteMetrics)
    fingerprints: FingerprintBundle = Field(default_factory=FingerprintBundle)
    evidence_ids: tuple[str, ...] = ()
    observed_at: float = Field(default_factory=time.time, gt=0)
    certified_input: bool = False

    @model_validator(mode="after")
    def successful_observation_contract(self) -> "RouteObservation":
        if self.outcome == "success" and not 200 <= self.http_status < 300:
            raise ValueError("successful observations require a 2xx status")
        return self


class BaselineSnapshot(StrictModel):
    baseline_id: str
    source_id: str
    route_id: str
    adapter_id: str = ""
    sample_count: int = Field(ge=1)
    metrics: dict[str, float]
    metric_mad: dict[str, float] = Field(default_factory=dict)
    fingerprints: FingerprintBundle = Field(default_factory=FingerprintBundle)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class DriftSignal(StrictModel):
    drift_class: str = Field(min_length=1, max_length=120)
    severity: DriftSeverity
    hard_gate: bool = False
    observed: Any = None
    baseline: Any = None
    delta: float | None = None
    message: str = Field(min_length=1, max_length=1000)


class DriftEvaluation(StrictModel):
    source_id: str
    route_id: str
    observation_id: str
    healthy: bool
    target_state: RouteState
    signals: tuple[DriftSignal, ...] = ()
    signature: str
    evaluated_at: float = Field(default_factory=time.time)

    @classmethod
    def create(
        cls,
        *,
        source_id: str,
        route_id: str,
        observation_id: str,
        target_state: RouteState,
        signals: list[DriftSignal],
    ) -> "DriftEvaluation":
        normalized = [
            {
                "class": signal.drift_class,
                "severity": signal.severity,
                "hard": signal.hard_gate,
                "observed": signal.observed,
                "baseline": signal.baseline,
            }
            for signal in sorted(
                signals, key=lambda item: (item.drift_class, item.severity)
            )
        ]
        signature = hashlib.sha256(
            json.dumps(normalized, sort_keys=True, default=str).encode()
        ).hexdigest()[:32]
        return cls(
            source_id=source_id,
            route_id=route_id,
            observation_id=observation_id,
            healthy=not signals,
            target_state=target_state,
            signals=tuple(signals),
            signature=signature,
        )


class AdapterDefinition(StrictModel):
    adapter_id: str = Field(min_length=1, max_length=160)
    source_id: str = Field(min_length=1, max_length=120)
    route_id: str = Field(min_length=1, max_length=160)
    version: int = Field(ge=1)
    parent_adapter_id: str = Field(default="", max_length=160)
    strategy_type: StrategyType
    state: AdapterState = AdapterState.CANDIDATE
    config: dict[str, Any]
    change_set: tuple[dict[str, Any], ...] = ()
    generated_by: Literal["manual", "deterministic_repair", "migration"] = "manual"
    evidence_ids: tuple[str, ...] = ()
    content_sha256: str = ""
    created_at: float = Field(default_factory=time.time)

    @model_validator(mode="after")
    def derive_hash(self) -> "AdapterDefinition":
        digest = hashlib.sha256(
            json.dumps(
                {
                    "source_id": self.source_id,
                    "route_id": self.route_id,
                    "strategy_type": self.strategy_type,
                    "config": self.config,
                },
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
        ).hexdigest()
        if self.content_sha256 and self.content_sha256 != digest:
            raise ValueError("adapter content hash mismatch")
        object.__setattr__(self, "content_sha256", digest)
        return self


class CertificationGateResult(StrictModel):
    gate_name: str = Field(min_length=1, max_length=120)
    passed: bool
    measured: Any = None
    threshold: Any = None
    details: dict[str, Any] = Field(default_factory=dict)


class CertificationReport(StrictModel):
    run_id: str
    source_id: str
    route_id: str
    adapter_id: str
    state: CertificationState
    gate_results: tuple[CertificationGateResult, ...]
    evidence_ids: tuple[str, ...]
    positive_count: int = Field(default=0, ge=0)
    negative_count: int = Field(default=0, ge=0)
    ambiguous_count: int = Field(default=0, ge=0)
    output_digest: str = ""
    started_at: float
    completed_at: float
    expires_at: float | None = None

    @property
    def verified(self) -> bool:
        return self.state == CertificationState.VERIFIED and all(
            gate.passed for gate in self.gate_results
        )


class CanaryResult(StrictModel):
    observation: RouteObservation
    drift: DriftEvaluation
    route_state: RouteState
    incident_id: str = ""
    baseline_updated: bool = False


class PromotionResult(StrictModel):
    transaction_id: str
    source_id: str
    route_id: str
    old_adapter_id: str
    new_adapter_id: str
    generation: int = Field(ge=1)
    committed: bool
    probation_until: float | None = None
    reason: str = ""
