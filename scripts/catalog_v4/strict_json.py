"""Strict, browser-compatible JSON parsing and serialization helpers."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


class StrictJsonError(ValueError):
    """Raised when a value cannot be represented as interoperable JSON."""


def reject_non_finite_constant(token: str) -> None:
    raise StrictJsonError(f"non-finite JSON constant is not allowed: {token}")


def loads_strict(value: str | bytes | bytearray, *, source: str = "JSON input") -> Any:
    try:
        return json.loads(value, parse_constant=reject_non_finite_constant)
    except (json.JSONDecodeError, StrictJsonError) as exc:
        raise StrictJsonError(f"invalid strict JSON in {source}: {exc}") from exc


def load_path_strict(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StrictJsonError(f"unable to read {path}: {exc}") from exc
    return loads_strict(text, source=str(path))


def assert_json_compatible(value: Any, *, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise StrictJsonError(f"non-finite numeric value at {path}")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise StrictJsonError(f"non-string object key at {path}: {key!r}")
            assert_json_compatible(item, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            assert_json_compatible(item, path=f"{path}[{index}]")
        return
    raise StrictJsonError(f"unsupported JSON value at {path}: {type(value).__name__}")


def dumps_strict(value: Any, **options: Any) -> str:
    assert_json_compatible(value)
    try:
        return json.dumps(value, allow_nan=False, **options)
    except (TypeError, ValueError) as exc:
        raise StrictJsonError(f"value is not strict JSON: {exc}") from exc


def json_safe_raw(value: Any) -> Any:
    """Retain ordinary source evidence while replacing invalid numbers explicitly."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(key): json_safe_raw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_raw(item) for item in value]
    return str(value)
