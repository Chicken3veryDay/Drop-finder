"""Configuration-driven registry for every current DropFinder source."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from .urls import UnsafeUrl, canonicalize_url


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
        for profile in payload["vendors"]:
            adapter = profile["adapter"]
            vendor_id = profile["vendor_id"]
            if vendor_id in adapters:
                raise ValueError(f"duplicate vendor profile: {vendor_id}")
            adapters[vendor_id] = VendorAdapter(
                vendor_id=vendor_id,
                vendor_name=profile["vendor_name"],
                canonical_origin=profile["canonical_origin"],
                allowed_document_hosts=frozenset(item.lower() for item in profile["allowed_document_hosts"]),
                discovery_strategy=adapter["discovery_strategy"],
                parser_strategy=adapter["parser_strategy"],
                lab_index_urls=tuple(profile["lab_index_urls"]),
                product_page_discovery=adapter["product_page_discovery"],
                structured_api_discovery=adapter["structured_api_discovery"],
            )
        return cls(adapters)


_STRATEGY_ID = re.compile(r"^[a-z][a-z0-9_]*$")


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_public_url(
    errors: list[str],
    *,
    field: str,
    value: Any,
    allowed_hosts: set[str] | None = None,
) -> None:
    if not _nonempty_string(value):
        errors.append(f"{field} must be a non-empty string")
        return
    try:
        canonicalize_url(value, allowed_hosts=allowed_hosts)
    except UnsafeUrl as exc:
        errors.append(f"{field} invalid: {exc}")


def _validated_hosts(errors: list[str], vendor_id: str, value: Any) -> set[str]:
    field = f"{vendor_id}.allowed_document_hosts"
    if not isinstance(value, list) or not value:
        errors.append(f"{field} must be a non-empty list")
        return set()
    hosts: set[str] = set()
    for index, item in enumerate(value):
        item_field = f"{field}[{index}]"
        if not _nonempty_string(item):
            errors.append(f"{item_field} must be a non-empty string")
            continue
        host = item.strip().lower().rstrip(".")
        if any(character in host for character in ("/", ":", "?", "#", "@")):
            errors.append(f"{item_field} must be a hostname, not a URL")
            continue
        try:
            canonicalize_url(f"https://{host}/")
        except UnsafeUrl as exc:
            errors.append(f"{item_field} invalid: {exc}")
            continue
        if host in hosts:
            errors.append(f"{item_field} duplicates {host}")
            continue
        hosts.add(host)
    return hosts


def validate_profiles(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["vendor profiles root must be an object"]
    if payload.get("schema_version") != "dropfinder-vendor-profiles-v1":
        errors.append("schema_version must be dropfinder-vendor-profiles-v1")
    allowed_age = {
        "identity_verification_required",
        "identity_verification_conditional",
        "self_attestation_21_plus",
        "no_observed_gate",
        "uncertain",
    }
    allowed_scopes = {"browsing", "checkout", "delivery", "first_order", "every_order", "unknown"}
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
        raw_vendor_id = profile.get("vendor_id")
        vendor_id = raw_vendor_id.strip() if isinstance(raw_vendor_id, str) else ""
        if not vendor_id:
            errors.append(f"{prefix}.vendor_id must be a non-empty string")
            vendor_id = prefix
        elif vendor_id in seen:
            errors.append(f"duplicate vendor_id: {vendor_id}")
        seen.add(vendor_id)

        for field in ("vendor_name", "canonical_origin", "category_url", "verified_at"):
            if not _nonempty_string(profile.get(field)):
                errors.append(f"{vendor_id}.{field} must be a non-empty string")

        hosts = _validated_hosts(errors, vendor_id, profile.get("allowed_document_hosts"))
        _validate_public_url(
            errors,
            field=f"{vendor_id}.canonical_origin",
            value=profile.get("canonical_origin"),
            allowed_hosts=hosts or None,
        )
        _validate_public_url(
            errors,
            field=f"{vendor_id}.category_url",
            value=profile.get("category_url"),
            allowed_hosts=hosts or None,
        )

        lab_urls = profile.get("lab_index_urls")
        if not isinstance(lab_urls, list):
            errors.append(f"{vendor_id}.lab_index_urls must be a list")
        else:
            for lab_index, url in enumerate(lab_urls):
                _validate_public_url(
                    errors,
                    field=f"{vendor_id}.lab_index_urls[{lab_index}]",
                    value=url,
                    allowed_hosts=hosts or None,
                )

        adapter = profile.get("adapter")
        if not isinstance(adapter, dict):
            errors.append(f"{vendor_id}.adapter must be an object")
        else:
            for field in ("discovery_strategy", "parser_strategy"):
                value = adapter.get(field)
                if not _nonempty_string(value) or _STRATEGY_ID.fullmatch(value.strip()) is None:
                    errors.append(f"{vendor_id}.adapter.{field} must be a strategy identifier")
            for field in ("product_page_discovery", "structured_api_discovery"):
                if not isinstance(adapter.get(field), bool):
                    errors.append(f"{vendor_id}.adapter.{field} must be boolean")
            if "ocr_supported" in adapter and not isinstance(adapter.get("ocr_supported"), bool):
                errors.append(f"{vendor_id}.adapter.ocr_supported must be boolean")

        age = profile.get("age_verification")
        if not isinstance(age, dict):
            errors.append(f"{vendor_id}: age_verification missing")
        else:
            if age.get("classification") not in allowed_age:
                errors.append(f"{vendor_id}: invalid age classification")
            if age.get("scope") not in allowed_scopes:
                errors.append(f"{vendor_id}: invalid age verification scope")
            if not _nonempty_string(age.get("summary")):
                errors.append(f"{vendor_id}: age_verification.summary missing")
        labs = profile.get("labs")
        if not isinstance(labs, dict):
            errors.append(f"{vendor_id}: labs missing")
        else:
            for key in ("coa_availability", "terpene_availability"):
                if labs.get(key) not in allowed_availability:
                    errors.append(f"{vendor_id}: invalid {key}")
            if not isinstance(labs.get("mapping_capability"), dict):
                errors.append(f"{vendor_id}: mapping_capability missing")
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
                    if not _nonempty_string(item.get(field)):
                        errors.append(f"{evidence_prefix}: {field} missing")
                _validate_public_url(
                    errors,
                    field=f"{evidence_prefix}.url",
                    value=item.get("url"),
                    allowed_hosts=hosts or None,
                )
    return errors
