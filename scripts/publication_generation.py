#!/usr/bin/env python3
"""Pin autonomous publication artifacts to one immutable source revision."""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHARD_SCHEMA = "dropfinder-autonomous-shard-v1"
OUTPUT_FILES = (
    "catalog.json",
    "status.json",
    "quarantine.json",
    "rejections.json",
    "runtime.json",
)


def _source_commit(value: str) -> str:
    normalized = value.strip().lower()
    if not SHA_RE.fullmatch(normalized):
        raise ValueError(f"invalid source commit: {value!r}")
    return normalized


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object payload: {path}")
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def stamp_shard(path: Path, source_commit: str) -> None:
    source_commit = _source_commit(source_commit)
    payload = _load(path)
    if payload.get("schema_version") != SHARD_SCHEMA:
        raise ValueError(f"unexpected shard schema: {path}")
    existing = payload.get("source_commit")
    if existing not in (None, "", source_commit):
        raise ValueError(f"refusing to replace shard source commit: {path}")
    payload["source_commit"] = source_commit
    _write(path, payload)


def verify_shards(root: Path, expected_commit: str) -> list[Path]:
    expected_commit = _source_commit(expected_commit)
    paths = sorted(root.rglob("shard-*.json"))
    if not paths:
        raise RuntimeError("no worker shard results")
    observed: set[str] = set()
    for path in paths:
        payload = _load(path)
        if payload.get("schema_version") != SHARD_SCHEMA:
            raise ValueError(f"unexpected shard schema: {path}")
        source_commit = _source_commit(str(payload.get("source_commit") or ""))
        observed.add(source_commit)
        if source_commit != expected_commit:
            raise RuntimeError(
                f"shard source commit mismatch: {path}: {source_commit} != {expected_commit}"
            )
    if observed != {expected_commit}:
        raise RuntimeError(f"mixed shard source commits: {sorted(observed)}")
    return paths


def stamp_outputs(root: Path, source_commit: str) -> None:
    source_commit = _source_commit(source_commit)
    for filename in OUTPUT_FILES:
        path = root / filename
        payload = _load(path)
        existing = payload.get("source_commit")
        if existing not in (None, "", source_commit):
            raise ValueError(f"refusing to replace output source commit: {path}")
        payload["source_commit"] = source_commit
        _write(path, payload)


def verify_outputs(root: Path, expected_commit: str) -> None:
    expected_commit = _source_commit(expected_commit)
    observed: set[str] = set()
    for filename in OUTPUT_FILES:
        path = root / filename
        payload = _load(path)
        source_commit = _source_commit(str(payload.get("source_commit") or ""))
        observed.add(source_commit)
        if source_commit != expected_commit:
            raise RuntimeError(
                f"output source commit mismatch: {path}: {source_commit} != {expected_commit}"
            )
    if observed != {expected_commit}:
        raise RuntimeError(f"mixed output source commits: {sorted(observed)}")


def stamp_receipt(receipt_path: Path, runtime_path: Path) -> None:
    receipt = _load(receipt_path)
    runtime = _load(runtime_path)
    source_commit = _source_commit(str(runtime.get("source_commit") or ""))
    generated_commit = _source_commit(str(receipt.get("source_snapshot_commit") or ""))
    receipt["generation_state_commit"] = generated_commit
    receipt["source_snapshot_commit"] = source_commit
    receipt["artifact_source_commit"] = source_commit
    _write(receipt_path, receipt)


def self_test() -> int:
    source = "1" * 40
    other = "2" * 40
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shards = root / "shards"
        shards.mkdir()
        first = shards / "shard-0.json"
        second = shards / "shard-1.json"
        base = {"schema_version": SHARD_SCHEMA, "products": [], "sources": []}
        _write(first, dict(base))
        _write(second, dict(base))
        stamp_shard(first, source)
        stamp_shard(second, source)
        assert verify_shards(shards, source) == [first, second]

        payload = _load(second)
        payload["source_commit"] = other
        _write(second, payload)
        try:
            verify_shards(shards, source)
        except RuntimeError:
            pass
        else:
            raise AssertionError("mixed shard commits must fail")

        outputs = root / "outputs"
        outputs.mkdir()
        for filename in OUTPUT_FILES:
            _write(outputs / filename, {"schema_version": filename})
        stamp_outputs(outputs, source)
        verify_outputs(outputs, source)

        receipt = root / "cdn.json"
        _write(receipt, {"source_snapshot_commit": other})
        stamp_receipt(receipt, outputs / "runtime.json")
        stamped = _load(receipt)
        assert stamped["source_snapshot_commit"] == source
        assert stamped["artifact_source_commit"] == source
        assert stamped["generation_state_commit"] == other
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    shard = subparsers.add_parser("stamp-shard")
    shard.add_argument("path", type=Path)
    shard.add_argument("source_commit")

    verify_shard = subparsers.add_parser("verify-shards")
    verify_shard.add_argument("root", type=Path)
    verify_shard.add_argument("source_commit")

    outputs = subparsers.add_parser("stamp-outputs")
    outputs.add_argument("root", type=Path)
    outputs.add_argument("source_commit")

    verify_output = subparsers.add_parser("verify-outputs")
    verify_output.add_argument("root", type=Path)
    verify_output.add_argument("source_commit")

    receipt = subparsers.add_parser("stamp-receipt")
    receipt.add_argument("receipt", type=Path)
    receipt.add_argument("runtime", type=Path)

    subparsers.add_parser("self-test")
    args = parser.parse_args()

    if args.command == "stamp-shard":
        stamp_shard(args.path, args.source_commit)
    elif args.command == "verify-shards":
        paths = verify_shards(args.root, args.source_commit)
        print(f"verified {len(paths)} shards at {args.source_commit}")
    elif args.command == "stamp-outputs":
        stamp_outputs(args.root, args.source_commit)
    elif args.command == "verify-outputs":
        verify_outputs(args.root, args.source_commit)
        print(f"verified output generation {args.source_commit}")
    elif args.command == "stamp-receipt":
        stamp_receipt(args.receipt, args.runtime)
    else:
        return self_test()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
