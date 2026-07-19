#!/usr/bin/env python3
"""Source-pinned publication provenance, continuity, and receipt gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any

SHARD_SCHEMA = "dropfinder-autonomous-shard-v1"
RECEIPT_SCHEMA = "dropfinder-atomic-publication-v1"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ReleaseGateError(RuntimeError):
    """Raised when a release invariant is not satisfied."""


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def load_json(path: Path) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ReleaseGateError(f"unable to load strict JSON from {path}: {exc}") from exc
    _assert_json_value(value, str(path))
    return value


def _assert_json_value(value: Any, location: str) -> None:
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ReleaseGateError(f"non-finite number at {location}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_json_value(item, f"{location}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ReleaseGateError(f"non-string object key at {location}")
            _assert_json_value(item, f"{location}.{key}")
        return
    raise ReleaseGateError(f"unsupported JSON value at {location}: {type(value).__name__}")


def dump_json(value: Any) -> str:
    _assert_json_value(value, "root")
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(dump_json(value))
        temporary = Path(handle.name)
    temporary.replace(path)


def require_sha(value: str, label: str) -> str:
    normalized = value.strip().lower()
    if not _SHA_RE.fullmatch(normalized):
        raise ReleaseGateError(f"{label} must be a full lowercase 40-character Git SHA")
    return normalized


def stamp_shard(path: Path, source_commit: str) -> dict[str, Any]:
    source_commit = require_sha(source_commit, "source commit")
    payload = load_json(path)
    if not isinstance(payload, dict) or payload.get("schema_version") != SHARD_SCHEMA:
        raise ReleaseGateError(f"unexpected shard schema: {path}")
    existing = payload.get("source_commit")
    if existing not in (None, source_commit):
        raise ReleaseGateError(f"shard already belongs to a different source commit: {path}")
    payload["source_commit"] = source_commit
    atomic_write_json(path, payload)
    return payload


def verify_shards(root: Path, expected_commit: str) -> dict[str, Any]:
    expected_commit = require_sha(expected_commit, "expected source commit")
    paths = sorted(root.rglob("shard-*.json"))
    if not paths:
        raise ReleaseGateError(f"no shard artifacts found under {root}")
    commits: set[str] = set()
    shard_numbers: set[int] = set()
    for path in paths:
        payload = load_json(path)
        if not isinstance(payload, dict) or payload.get("schema_version") != SHARD_SCHEMA:
            raise ReleaseGateError(f"unexpected shard schema: {path}")
        commit = require_sha(str(payload.get("source_commit") or ""), f"source commit in {path}")
        commits.add(commit)
        match = re.search(r"shard-(\d+)\.json$", path.name)
        if not match:
            raise ReleaseGateError(f"invalid shard filename: {path}")
        number = int(match.group(1))
        if number in shard_numbers:
            raise ReleaseGateError(f"duplicate shard number: {number}")
        shard_numbers.add(number)
    if commits != {expected_commit}:
        raise ReleaseGateError(
            f"scan artifact source mismatch: expected {expected_commit}, found {sorted(commits)}"
        )
    return {
        "schema_version": "dropfinder-shard-provenance-v1",
        "source_commit": expected_commit,
        "shard_count": len(paths),
        "shards": sorted(shard_numbers),
    }


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ReleaseGateError(f"{label} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ReleaseGateError(f"{label} must be an integer") from exc
    if parsed < 0:
        raise ReleaseGateError(f"{label} must not be negative")
    return parsed


def publication_metrics(root: Path) -> dict[str, Any]:
    data = root / "data"
    catalog = load_json(data / "catalog.json")
    status = load_json(data / "status.json")
    runtime = load_json(data / "runtime.json")
    manifest = load_json(data / "catalog-v4" / "manifest.json")
    index = load_json(data / "catalog-v4" / "index.json")
    if not all(isinstance(value, dict) for value in (catalog, status, runtime, manifest, index)):
        raise ReleaseGateError("publication metrics require JSON objects")

    generation = str(manifest.get("generation_id") or "")
    if not generation or generation != str(index.get("generation_id") or ""):
        raise ReleaseGateError("catalog-v4 manifest/index generation mismatch")
    legacy_products = _positive_int(catalog.get("product_count"), "legacy product count")
    active_sources = _positive_int(status.get("healthy_sources"), "healthy source count")
    enabled_sources = _positive_int(status.get("enabled_sources"), "enabled source count")
    degraded_sources = _positive_int(status.get("degraded_sources"), "degraded source count")
    v4_products = _positive_int(manifest.get("product_count"), "catalog-v4 product count")
    v4_variants = _positive_int(
        manifest.get("in_stock_variant_count"), "catalog-v4 in-stock variant count"
    )
    if legacy_products != len(catalog.get("products") or []):
        raise ReleaseGateError("legacy catalog product count does not match rows")
    if active_sources != enabled_sources or degraded_sources != 0:
        raise ReleaseGateError("candidate publication is not zero-degraded")
    if runtime.get("zero_degraded_active_services") is not True:
        raise ReleaseGateError("candidate runtime is not zero-degraded")
    if v4_products != _positive_int(index.get("product_count"), "catalog-v4 index product count"):
        raise ReleaseGateError("catalog-v4 manifest/index product count mismatch")
    if v4_variants != _positive_int(
        index.get("in_stock_variant_count"), "catalog-v4 index variant count"
    ):
        raise ReleaseGateError("catalog-v4 manifest/index variant count mismatch")
    shard_products = sum(
        _positive_int(row.get("product_count"), "catalog-v4 detail shard product count")
        for row in manifest.get("product_detail_shards") or []
        if isinstance(row, dict)
    )
    if shard_products != v4_products:
        raise ReleaseGateError("catalog-v4 detail shard counts do not match manifest")
    return {
        "legacy_product_count": legacy_products,
        "active_source_count": active_sources,
        "catalog_v4_product_count": v4_products,
        "catalog_v4_variant_count": v4_variants,
        "generation_id": generation,
        "generated_at": str(manifest.get("generated_at") or runtime.get("generated_at") or ""),
        "zero_degraded": True,
    }


def _drop_fraction(previous: int, candidate: int) -> float:
    if previous <= 0 or candidate >= previous:
        return 0.0
    return (previous - candidate) / previous


def evaluate_continuity(
    previous_root: Path | None,
    candidate_root: Path,
    *,
    max_product_drop: float = 0.30,
    max_source_drop: float = 0.30,
    min_legacy_products: int = 25,
    min_active_sources: int = 5,
    min_v4_products: int = 1,
    min_v4_variants: int = 1,
    override_reason: str = "",
) -> dict[str, Any]:
    candidate = publication_metrics(candidate_root)
    reasons: list[str] = []
    floors = {
        "legacy_product_count": min_legacy_products,
        "active_source_count": min_active_sources,
        "catalog_v4_product_count": min_v4_products,
        "catalog_v4_variant_count": min_v4_variants,
    }
    for key, floor in floors.items():
        if int(candidate[key]) < floor:
            reasons.append(f"{key}_floor:{candidate[key]}<{floor}")

    previous: dict[str, Any] | None = None
    drops: dict[str, float] = {}
    if previous_root is not None:
        previous = publication_metrics(previous_root)
        limits = {
            "legacy_product_count": max_product_drop,
            "active_source_count": max_source_drop,
            "catalog_v4_product_count": max_product_drop,
            "catalog_v4_variant_count": max_product_drop,
        }
        for key, limit in limits.items():
            drop = _drop_fraction(int(previous[key]), int(candidate[key]))
            drops[key] = round(drop, 6)
            if drop > limit:
                reasons.append(f"{key}_drop:{drop:.6f}>{limit:.6f}")

    reason = override_reason.strip()
    override = bool(reason)
    if override and len(reason) < 12:
        raise ReleaseGateError("continuity override reason must contain at least 12 characters")
    if reasons and not override:
        raise ReleaseGateError("publication continuity gate failed: " + ", ".join(reasons))
    return {
        "schema_version": "dropfinder-publication-continuity-v1",
        "status": "accepted_override" if reasons else "accepted",
        "previous": previous,
        "candidate": candidate,
        "drop_fractions": drops,
        "limits": {
            "max_product_drop": max_product_drop,
            "max_source_drop": max_source_drop,
            **floors,
        },
        "anomalies": reasons,
        "override": {
            "used": bool(reasons and override),
            "reason": reason if reasons and override else "",
        },
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def referenced_v4_hashes(root: Path) -> dict[str, str]:
    manifest_path = root / "data" / "catalog-v4" / "manifest.json"
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ReleaseGateError("catalog-v4 manifest must be an object")
    records: list[dict[str, Any]] = []
    for field in ("compact_index", "vendor_profiles", "rejections"):
        record = manifest.get(field)
        if isinstance(record, dict):
            records.append(record)
    records.extend(
        record for record in manifest.get("product_detail_shards") or [] if isinstance(record, dict)
    )
    hashes = {"data/catalog-v4/manifest.json": sha256_file(manifest_path)}
    for record in records:
        relative = str(record.get("path") or "")
        expected = str(record.get("sha256") or "")
        if not relative.startswith("data/catalog-v4/") or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ReleaseGateError(f"invalid catalog-v4 manifest reference: {relative}")
        path = root / relative
        actual = sha256_file(path)
        if actual != expected:
            raise ReleaseGateError(f"catalog-v4 hash mismatch: {relative}")
        hashes[relative] = actual
    return dict(sorted(hashes.items()))


def build_receipt(
    root: Path,
    *,
    source_commit: str,
    generated_commit: str,
    publication_commit: str,
    rollback_commit: str,
    workflow_name: str,
    workflow_run_id: str,
    public_url: str,
    continuity: dict[str, Any],
    endpoint_verification: dict[str, Any],
) -> dict[str, Any]:
    metrics = publication_metrics(root)
    return {
        "schema_version": RECEIPT_SCHEMA,
        "status": "live",
        "source_commit": require_sha(source_commit, "source commit"),
        "generated_data_commit": require_sha(generated_commit, "generated data commit"),
        "publication_commit": require_sha(publication_commit, "publication commit"),
        "rollback_commit": require_sha(rollback_commit, "rollback commit"),
        "workflow": workflow_name,
        "workflow_run_id": str(workflow_run_id),
        "public_url": public_url,
        "generation_id": metrics["generation_id"],
        "generated_at": metrics["generated_at"],
        "product_count": metrics["legacy_product_count"],
        "variant_count": metrics["catalog_v4_variant_count"],
        "catalog_v4_product_count": metrics["catalog_v4_product_count"],
        "active_source_count": metrics["active_source_count"],
        "zero_degraded": metrics["zero_degraded"],
        "catalog_v4_hashes": referenced_v4_hashes(root),
        "continuity": continuity,
        "endpoint_verification": endpoint_verification,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    stamp = subparsers.add_parser("stamp-shard")
    stamp.add_argument("path", type=Path)
    stamp.add_argument("--source-commit", required=True)

    verify = subparsers.add_parser("verify-shards")
    verify.add_argument("root", type=Path)
    verify.add_argument("--expected-commit", required=True)
    verify.add_argument("--output", type=Path)

    continuity = subparsers.add_parser("check-continuity")
    continuity.add_argument("candidate", type=Path)
    continuity.add_argument("--previous", type=Path)
    continuity.add_argument("--max-product-drop", type=float, default=0.30)
    continuity.add_argument("--max-source-drop", type=float, default=0.30)
    continuity.add_argument("--override-reason", default="")
    continuity.add_argument("--output", type=Path, required=True)

    metrics = subparsers.add_parser("metrics")
    metrics.add_argument("root", type=Path)

    receipt = subparsers.add_parser("record-receipt")
    receipt.add_argument("root", type=Path)
    receipt.add_argument("--source-commit", required=True)
    receipt.add_argument("--generated-commit", required=True)
    receipt.add_argument("--publication-commit", required=True)
    receipt.add_argument("--rollback-commit", required=True)
    receipt.add_argument("--workflow-name", required=True)
    receipt.add_argument("--workflow-run-id", required=True)
    receipt.add_argument("--public-url", required=True)
    receipt.add_argument("--continuity", type=Path, required=True)
    receipt.add_argument("--endpoint-verification", type=Path, required=True)
    receipt.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "stamp-shard":
        result = stamp_shard(args.path, args.source_commit)
    elif args.command == "verify-shards":
        result = verify_shards(args.root, args.expected_commit)
        if args.output:
            atomic_write_json(args.output, result)
    elif args.command == "check-continuity":
        result = evaluate_continuity(
            args.previous,
            args.candidate,
            max_product_drop=args.max_product_drop,
            max_source_drop=args.max_source_drop,
            override_reason=args.override_reason,
        )
        atomic_write_json(args.output, result)
    elif args.command == "metrics":
        result = publication_metrics(args.root)
    else:
        result = build_receipt(
            args.root,
            source_commit=args.source_commit,
            generated_commit=args.generated_commit,
            publication_commit=args.publication_commit,
            rollback_commit=args.rollback_commit,
            workflow_name=args.workflow_name,
            workflow_run_id=args.workflow_run_id,
            public_url=args.public_url,
            continuity=load_json(args.continuity),
            endpoint_verification=load_json(args.endpoint_verification),
        )
        atomic_write_json(args.output, result)
    print(dump_json(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
