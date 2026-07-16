#!/usr/bin/env python3
"""Strict, browser-compatible JSON parsing and serialization helpers."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


class StrictJsonError(ValueError):
    """Raised when data cannot be represented as interoperable JSON."""


def _reject_constant(token: str) -> None:
    raise StrictJsonError(f"non-standard JSON numeric constant: {token}")


def _validate_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise StrictJsonError(f"non-finite number at {path}: {value!r}")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _validate_finite(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_finite(child, f"{path}[{index}]")


def loads(text: str, *, source: str = "<json>") -> Any:
    """Parse strict JSON and reject every recursively non-finite number."""
    try:
        payload = json.loads(text, parse_constant=_reject_constant)
        _validate_finite(payload)
        return payload
    except (json.JSONDecodeError, StrictJsonError) as exc:
        raise StrictJsonError(f"invalid strict JSON in {source}: {exc}") from exc


def load(path: Path) -> Any:
    return loads(path.read_text(encoding="utf-8"), source=str(path))


def dumps(payload: Any) -> str:
    """Serialize deterministic strict JSON suitable for browser JSON.parse()."""
    _validate_finite(payload)
    try:
        return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise StrictJsonError(f"value is not strict-JSON serializable: {exc}") from exc


def validate_tree(root: Path) -> list[Path]:
    paths = [root] if root.is_file() else sorted(root.rglob("*.json"))
    if not paths:
        raise StrictJsonError(f"no JSON files found under {root}")
    for path in paths:
        load(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate files with browser-compatible strict JSON rules.")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    paths = validate_tree(args.path)
    print(f"validated {len(paths)} strict JSON file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
