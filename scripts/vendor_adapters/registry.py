"""Configuration-driven registry for every current DropFinder source."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VendorAdapter:
    vendor_id: str
    vendor_name: str
    canonical_origin: str
    allowed_document_hosts: frozenset[str]
    discovery_strategy: str
    parser_strategy: str
    lab_index_urls: tuple[str, ...]
    product_page_discovery: bool
    structured_api_discovery: bool


class VendorRegistry:
    def __init__(self, adapters: dict[str, VendorAdapter]) -> None:
        self._adapters = dict(adapters)

    def get(self, vendor_id: str) -> VendorAdapter:
        try:
            return self._adapters[vendor_id]
        except KeyError as exc:
            raise KeyError(f"no vendor adapter registered for {vendor_id!r}") from exc

    def all(self) -> tuple[VendorAdapter, ...]:
        return tuple(self._adapters[key] for key in sorted(self._adapters))

    @classmethod
    def from_profiles(cls, path: str | Path) -> "VendorRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        errors = validate_profiles(payload)
        if errors:
            raise ValueError("invalid vendor profiles: " + "; ".join(errors))
        adapters: dict[str, VendorAdapter] = {}
        for profile in payload.get("vendors", []):
            adapter = profile.get("adapter") or {}
            vendor_id = str(profile["vendor_id"])
            if vendor_id in adapters:
                raise ValueError(f"duplicate vendor profile: {vendor_id}")
            adapters[vendor_id] = VendorAdapter(
                vendor_id=vendor_id,
                vendor_name=str(profile["vendor_name"]),
                canonical_origin=str(profile["canonical_origin"]),
                allowed_document_hosts=frozenset(str(item).lower() for item in profile.get("allowed_document_hosts", [])),
                discovery_strategy=str(adapter.get("discovery_strategy") or "product_page_links"),
                parser_strategy=str(adapter.get("parser_strategy") or "safe_auto"),
                lab_index_urls=tuple(str(item) for item in profile.get("lab_index_urls", [])),
                product_page_discovery=bool(adapter.get("product_page_discovery", True)),
                structured_api_discovery=bool(adapter.get("structured_api_discovery", True)),
            )
        return cls(adapters)


def validate_profiles(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != "dropfinder-vendor-profiles-v1":
        errors.append("schema_version must be dropfinder-vendor-profiles-v1")
    allowed_age = {
        "identity_verification_required",
        "identity_verification_conditional",
        "self_attestation_21_plus",
        "no_observed_gate",
        "uncertain",
    }
    allowed_availability = {"public", "partial", "not_observed", "inaccessible", "unsupported", "uncertain"}
    allowed_evidence = {"current", "conflicting", "inaccessible", "stale"}
    vendors = payload.get("vendors")
    if not isinstance(vendors, list):
        return [*errors, "vendors must be a list"]
    seen: set[str] = set()
    for index, profile in enumerate(vendors):
        prefix = f"vendors[{index}]"
        if not isinstance(profile, dict):
            errors.append(f"{prefix} must be an object")
            continue
        vendor_id = str(profile.get("vendor_id") or "")
        if not vendor_id:
            errors.append(f"{prefix}.vendor_id missing")
        elif vendor_id in seen:
            errors.append(f"duplicate vendor_id: {vendor_id}")
        seen.add(vendor_id)
        age = profile.get("age_verification")
        if not isinstance(age, dict):
            errors.append(f"{vendor_id}: age_verification missing")
        else:
            if age.get("classification") not in allowed_age:
                errors.append(f"{vendor_id}: invalid age classification")
            for field in ("scope", "summary"):
                if not age.get(field):
                    errors.append(f"{vendor_id}: age_verification.{field} missing")
        labs = profile.get("labs")
        if not isinstance(labs, dict):
            errors.append(f"{vendor_id}: labs missing")
        else:
            for key in ("coa_availability", "terpene_availability"):
                if labs.get(key) not in allowed_availability:
                    errors.append(f"{vendor_id}: invalid {key}")
            if not isinstance(labs.get("mapping_capability"), dict):
                errors.append(f"{vendor_id}: mapping_capability missing")
        if not profile.get("canonical_origin"):
            errors.append(f"{vendor_id}: canonical_origin missing")
        if not profile.get("allowed_document_hosts"):
            errors.append(f"{vendor_id}: allowed_document_hosts missing")
        if not profile.get("verified_at"):
            errors.append(f"{vendor_id}: verified_at missing")
        evidence = profile.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{vendor_id}: evidence missing")
        else:
            for evidence_index, item in enumerate(evidence):
                evidence_prefix = f"{vendor_id}.evidence[{evidence_index}]"
                if not isinstance(item, dict):
                    errors.append(f"{evidence_prefix}: must be an object")
                    continue
                if item.get("status") not in allowed_evidence:
                    errors.append(f"{evidence_prefix}: invalid status")
                for field in ("url", "summary", "observed_at"):
                    if not item.get(field):
                        errors.append(f"{evidence_prefix}: {field} missing")
    return errors
