"""Build a deterministic, auditable vendor-document artifact for Catalog V4."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from scripts.vendor_adapters.registry import VendorRegistry
from scripts.vendor_adapters.urls import UnsafeUrl, canonicalize_url

SOURCE_SCHEMA = "dropfinder-vendor-document-sources-v1"
ARTIFACT_SCHEMA = "dropfinder-vendor-document-artifact-v1"
ALLOWED_KINDS = {"coa", "terpene", "combined"}
LABEL_NOISE = {"thca", "thc", "a", "flower", "hemp"}


def _load(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _timestamp(value: Any) -> str:
    raw = str(value or "").strip()
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _label(value: Any) -> str:
    tokens = re.findall(r"[a-z0-9]+", str(value or "").casefold())
    while tokens and tokens[-1] in LABEL_NOISE:
        tokens.pop()
    return " ".join(token for token in tokens if token not in {"thca"})


def _base_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme != "https" or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/") or "/", "", ""))


def _document_id(vendor_id: str, public_url: str) -> str:
    return hashlib.sha256(f"{vendor_id}|{public_url}".encode()).hexdigest()[:24]


@dataclass
class ProductGroup:
    vendor_id: str
    source_key: str
    product_url: str
    source_product_id: str
    labels: set[str] = field(default_factory=set)
    raw_labels: set[str] = field(default_factory=set)
    source_variant_ids: set[str] = field(default_factory=set)


def _catalog_products(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("products") or payload.get("records") or []
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    raise ValueError("catalog must contain a products or records list")


def _product_groups(payload: Any) -> list[ProductGroup]:
    groups: dict[tuple[str, str], ProductGroup] = {}
    for row in _catalog_products(payload):
        vendor_id = str(row.get("source_id") or row.get("vendor_id") or "").strip()
        if not vendor_id:
            continue
        product_url = _base_url(
            row.get("canonical_product_url")
            or row.get("public_purchase_url")
            or row.get("product_url")
            or row.get("url")
        )
        source_product_id = str(row.get("source_product_id") or row.get("product_id") or "").strip()
        source_key = source_product_id or product_url
        if not source_key:
            continue
        group = groups.setdefault(
            (vendor_id, source_key),
            ProductGroup(vendor_id, source_key, product_url, source_product_id),
        )
        for field_name in ("name", "source_title", "strain", "strain_name"):
            raw = str(row.get(field_name) or "").strip()
            normalized = _label(raw)
            if raw and normalized:
                group.raw_labels.add(raw)
                group.labels.add(normalized)
        variant_id = str(row.get("source_variant_id") or row.get("variant_id") or "").strip()
        if variant_id:
            group.source_variant_ids.add(variant_id)
    return sorted(groups.values(), key=lambda item: (item.vendor_id, item.source_key))


def _source_documents(payload: Any) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(payload, dict) or payload.get("schema_version") != SOURCE_SCHEMA:
        raise ValueError(f"document sources must use {SOURCE_SCHEMA}")
    rows: list[dict[str, Any]] = []
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise ValueError("document sources must contain a sources list")
    for source in sources:
        if not isinstance(source, dict):
            continue
        vendor_id = str(source.get("vendor_id") or "").strip()
        source_page = str(source.get("source_page") or "").strip()
        observed_at = _timestamp(source.get("observed_at") or payload.get("generated_at"))
        documents = source.get("documents")
        if not vendor_id or not isinstance(documents, list):
            raise ValueError("every document source requires vendor_id and documents")
        for document in documents:
            if not isinstance(document, dict):
                continue
            rows.append({
                **document,
                "vendor_id": vendor_id,
                "source_page": source_page,
                "observed_at": observed_at,
            })
    return _timestamp(payload.get("generated_at")), rows


def build_artifact(
    catalog: Any,
    profiles_path: str | Path,
    source_payload: Any,
    *,
    generated_at: Any = None,
) -> dict[str, Any]:
    registry = VendorRegistry.from_profiles(profiles_path)
    adapters = {adapter.vendor_id: adapter for adapter in registry.all()}
    groups = _product_groups(catalog)
    source_generated_at, source_documents = _source_documents(source_payload)
    by_vendor: dict[str, list[ProductGroup]] = {}
    for group in groups:
        by_vendor.setdefault(group.vendor_id, []).append(group)

    documents: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    status_by_vendor: dict[str, dict[str, Any]] = {}
    seen_urls: set[tuple[str, str]] = set()

    for raw in sorted(source_documents, key=lambda row: (row["vendor_id"], str(row.get("public_url") or ""))):
        vendor_id = raw["vendor_id"]
        adapter = adapters.get(vendor_id)
        public_url = str(raw.get("public_url") or raw.get("url") or "").strip()
        label = str(raw.get("label") or "").strip()
        kind = str(raw.get("kind") or "").strip().lower()
        source_page = str(raw.get("source_page") or "").strip()
        document_id = _document_id(vendor_id, public_url)
        base = {
            "document_id": document_id,
            "vendor_id": vendor_id,
            "kind": kind,
            "label": label,
            "public_url": public_url,
            "mime_type": str(raw.get("mime_type") or "").strip(),
            "source_page": source_page,
            "observed_at": raw["observed_at"],
        }
        status = status_by_vendor.setdefault(vendor_id, {
            "vendor_id": vendor_id,
            "source_documents": 0,
            "mapped_documents": 0,
            "unmatched_documents": 0,
            "reasons": {},
        })
        status["source_documents"] += 1

        reason = ""
        if adapter is None:
            reason = "vendor_profile_missing"
        elif kind not in ALLOWED_KINDS:
            reason = "unsupported_document_kind"
        elif not label or not _label(label):
            reason = "document_label_missing"
        else:
            try:
                canonicalize_url(public_url, allowed_hosts=set(adapter.allowed_document_hosts))
                canonicalize_url(source_page, allowed_hosts=set(adapter.allowed_document_hosts))
            except UnsafeUrl:
                reason = "document_url_outside_vendor_boundary"

        key = (vendor_id, public_url)
        if not reason and key in seen_urls:
            reason = "duplicate_document_url"
        seen_urls.add(key)

        matches: list[ProductGroup] = []
        if not reason:
            normalized = _label(label)
            matches = [group for group in by_vendor.get(vendor_id, []) if normalized in group.labels]
            if not matches:
                reason = "no_exact_catalog_product"
            elif len(matches) > 1:
                reason = "ambiguous_exact_catalog_product"

        if reason:
            unmatched.append({**base, "reason": reason})
            status["unmatched_documents"] += 1
            status["reasons"][reason] = status["reasons"].get(reason, 0) + 1
            continue

        target = matches[0]
        documents.append({
            **base,
            "scope": "product",
            "mapping_scope": "product",
            "source_product_id": target.source_product_id or target.product_url,
            "product_url": target.product_url,
            "provenance": {
                "method": "unique_exact_normalized_product_label",
                "matched_label": label,
                "catalog_labels": sorted(target.raw_labels),
                "source_page": source_page,
                "observed_at": raw["observed_at"],
            },
        })
        status["mapped_documents"] += 1

    statuses = []
    for vendor_id in sorted(status_by_vendor):
        status = status_by_vendor[vendor_id]
        status["reasons"] = dict(sorted(status["reasons"].items()))
        status["status"] = "mapped" if status["mapped_documents"] else "unmatched"
        statuses.append(status)

    artifact_generated_at = _timestamp(generated_at or (catalog.get("generated_at") if isinstance(catalog, dict) else None) or source_generated_at)
    return {
        "schema_version": ARTIFACT_SCHEMA,
        "generated_at": artifact_generated_at,
        "catalog_generated_at": str(catalog.get("generated_at") or "") if isinstance(catalog, dict) else "",
        "source_schema_version": SOURCE_SCHEMA,
        "documents": sorted(documents, key=lambda row: (row["vendor_id"], row["document_id"])),
        "unmatched_documents": sorted(unmatched, key=lambda row: (row["vendor_id"], row["document_id"])),
        "source_statuses": statuses,
        "counts": {
            "source_documents": len(source_documents),
            "mapped_documents": len(documents),
            "unmatched_documents": len(unmatched),
            "vendors": len(statuses),
        },
    }


def verify_artifact(payload: Any) -> dict[str, int]:
    if not isinstance(payload, dict) or payload.get("schema_version") != ARTIFACT_SCHEMA:
        raise ValueError(f"artifact must use {ARTIFACT_SCHEMA}")
    documents = payload.get("documents")
    unmatched = payload.get("unmatched_documents")
    counts = payload.get("counts")
    if not isinstance(documents, list) or not isinstance(unmatched, list) or not isinstance(counts, dict):
        raise ValueError("artifact collections are missing")
    if counts.get("mapped_documents") != len(documents) or counts.get("unmatched_documents") != len(unmatched):
        raise ValueError("artifact counts do not match collections")
    if counts.get("source_documents") != len(documents) + len(unmatched):
        raise ValueError("artifact does not account for every source document")
    for document in documents:
        if not isinstance(document, dict) or document.get("scope") != "product":
            raise ValueError("mapped document must have product scope")
        if not document.get("source_product_id") or not document.get("public_url"):
            raise ValueError("mapped document is missing target identity")
    for document in unmatched:
        if not isinstance(document, dict) or not document.get("reason"):
            raise ValueError("unmatched document is missing a reason")
    return {
        "source_documents": len(documents) + len(unmatched),
        "mapped_documents": len(documents),
        "unmatched_documents": len(unmatched),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--vendor-profiles", required=True)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    if args.verify_only:
        summary = verify_artifact(_load(args.output))
    else:
        artifact = build_artifact(_load(args.catalog), args.vendor_profiles, _load(args.sources))
        verify_artifact(artifact)
        _write(args.output, artifact)
        summary = artifact["counts"]
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
