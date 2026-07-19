"""Vendor-profile normalization shared by catalog generation and UI metadata."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from scripts.vendor_expansion import public_age_index

from .strict_json import dumps_strict, load_path_strict


def optional_json(path: Path | None) -> Any:
    if path is None or not path.is_file():
        return None
    return load_path_strict(path)


def merge_vendor_profiles(payloads: Iterable[Any]) -> dict[str, Any]:
    by_id: dict[str, dict[str, Any]] = {}
    generated_at = ""
    methodologies: list[dict[str, Any]] = []
    accepted_payloads: list[dict[str, Any]] = []

    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        accepted_payloads.append(payload)
        generated_at = max(generated_at, str(payload.get("generated_at") or ""))
        if isinstance(payload.get("methodology"), dict):
            methodologies.append(dict(payload["methodology"]))
        vendors = payload.get("vendors")
        if not isinstance(vendors, list):
            continue
        for raw in vendors:
            if not isinstance(raw, dict):
                continue
            profile = normalize_vendor_profile(raw)
            vendor_id = str(profile.get("vendor_id") or "")
            if vendor_id:
                by_id[vendor_id] = profile

    return {
        "schema_version": "dropfinder-vendor-profiles-v1",
        "generated_at": generated_at,
        "methodology": {
            "merged_sources": len(accepted_payloads),
            "identity_rule": "Self-attested age prompts are confirmation, never identity verification.",
            "source_methodologies": methodologies,
        },
        "vendors": [by_id[key] for key in sorted(by_id)],
    }


def normalize_vendor_profile(raw: dict[str, Any]) -> dict[str, Any]:
    profile = dict(raw)
    age = raw.get("age_verification") if isinstance(raw.get("age_verification"), dict) else {}
    evidence = raw.get("evidence") if isinstance(raw.get("evidence"), list) else []
    evidence_url = str(age.get("evidence_url") or raw.get("age_gate_evidence_reference") or "")
    if not evidence_url:
        for item in evidence:
            if isinstance(item, dict) and item.get("evidence_type") == "storefront_or_category" and item.get("url"):
                evidence_url = str(item["url"])
                break
    favicon = raw.get("favicon") if isinstance(raw.get("favicon"), dict) else {}
    favicon_provenance = favicon.get("provenance") if isinstance(favicon.get("provenance"), dict) else {}
    profile.update(
        age_gate_classification=str(age.get("classification") or raw.get("age_gate_classification") or "uncertain"),
        age_gate_evidence_reference=evidence_url,
        age_gate_provider=str(age.get("provider") or raw.get("age_gate_provider") or "none_observed"),
        age_gate_scope=str(age.get("scope") or raw.get("age_gate_scope") or "unknown"),
        age_gate_summary=str(age.get("summary") or raw.get("age_gate_summary") or "Age-control details have not been confirmed."),
        favicon_url=str(raw.get("favicon_url") or favicon.get("url") or ""),
        favicon_provenance=(
            raw.get("favicon_provenance")
            if isinstance(raw.get("favicon_provenance"), dict)
            else favicon_provenance
        ),
    )
    return profile


def write_public_age_index(
    output_root: Path,
    source_payloads: list[dict[str, Any]],
) -> Path:
    payload = public_age_index(source_payloads)
    path = output_root / "catalog-v4" / "vendor-age-verification.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_strict(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
