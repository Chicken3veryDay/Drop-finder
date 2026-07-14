from __future__ import annotations


from app.reliability.contracts import CertificationGateResult


def certification_gates(
    *,
    positive_total: int,
    positive_accepted: int,
    negative_total: int,
    negative_rejected: int,
    ambiguous_total: int,
    ambiguous_fail_closed: int,
    identity_overlap: float,
    duplicate_rate: float,
    required_coverage_regression: float,
    optional_coverage_regression: float,
    replay_deterministic: bool,
    evidence_integrity: bool,
    source_route_match: bool,
    shadow_passed: bool | None,
) -> tuple[CertificationGateResult, ...]:
    positive_recall = (
        (positive_accepted / positive_total * 100) if positive_total else 0.0
    )
    negative_precision = (
        (negative_rejected / negative_total * 100) if negative_total else 0.0
    )
    ambiguous_rate = (
        (ambiguous_fail_closed / ambiguous_total * 100) if ambiguous_total else 0.0
    )
    rows = [
        CertificationGateResult(
            gate_name="evidence_integrity",
            passed=evidence_integrity,
            measured=evidence_integrity,
            threshold=True,
        ),
        CertificationGateResult(
            gate_name="source_route_match",
            passed=source_route_match,
            measured=source_route_match,
            threshold=True,
        ),
        CertificationGateResult(
            gate_name="positive_evidence_present",
            passed=positive_total > 0,
            measured=positive_total,
            threshold=1,
        ),
        CertificationGateResult(
            gate_name="negative_evidence_present",
            passed=negative_total > 0,
            measured=negative_total,
            threshold=1,
        ),
        CertificationGateResult(
            gate_name="ambiguous_evidence_present",
            passed=ambiguous_total > 0,
            measured=ambiguous_total,
            threshold=1,
        ),
        CertificationGateResult(
            gate_name="known_positive_recall",
            passed=positive_recall >= 98.0,
            measured=round(positive_recall, 3),
            threshold=98.0,
        ),
        CertificationGateResult(
            gate_name="known_negative_precision",
            passed=negative_precision == 100.0,
            measured=round(negative_precision, 3),
            threshold=100.0,
        ),
        CertificationGateResult(
            gate_name="ambiguous_fail_closed",
            passed=ambiguous_rate == 100.0,
            measured=round(ambiguous_rate, 3),
            threshold=100.0,
        ),
        CertificationGateResult(
            gate_name="identity_continuity",
            passed=identity_overlap >= 98.0,
            measured=identity_overlap,
            threshold=98.0,
        ),
        CertificationGateResult(
            gate_name="duplicate_rate",
            passed=duplicate_rate < 1.0,
            measured=duplicate_rate,
            threshold="<1.0",
        ),
        CertificationGateResult(
            gate_name="required_field_coverage",
            passed=required_coverage_regression >= 0.0,
            measured=required_coverage_regression,
            threshold=">=0 regression points",
        ),
        CertificationGateResult(
            gate_name="optional_field_coverage",
            passed=optional_coverage_regression >= -2.0,
            measured=optional_coverage_regression,
            threshold=">=-2 regression points",
        ),
        CertificationGateResult(
            gate_name="replay_deterministic",
            passed=replay_deterministic,
            measured=replay_deterministic,
            threshold=True,
        ),
    ]
    if shadow_passed is not None:
        rows.append(
            CertificationGateResult(
                gate_name="shadow_live",
                passed=shadow_passed,
                measured=shadow_passed,
                threshold=True,
            )
        )
    return tuple(rows)
