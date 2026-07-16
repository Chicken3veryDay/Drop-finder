#!/usr/bin/env python3
"""Stage multi-product publication behind a strict JSON compatibility boundary."""
from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from . import publication
from .strict_json import StrictJsonError, dumps, load

OUTPUT_FILENAMES = (
    "catalog.json",
    "status.json",
    "quarantine.json",
    "rejections.json",
    "runtime.json",
)


def _validate_input_shards(input_dir: Path) -> list[Path]:
    paths = sorted(input_dir.rglob("shard-*.json"))
    if not paths:
        raise RuntimeError("no worker shard results")
    for path in paths:
        load(path)
    return paths


def _validated_output_text(stage: Path) -> dict[str, str]:
    output: dict[str, str] = {}
    for filename in OUTPUT_FILENAMES:
        path = stage / filename
        if not path.is_file():
            raise StrictJsonError(f"publication did not create required output: {path}")
        output[filename] = dumps(load(path))
    return output


def _replace_outputs(output_dir: Path, content: dict[str, str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary: dict[str, Path] = {}
    try:
        for filename, text in content.items():
            descriptor, raw_path = tempfile.mkstemp(
                dir=output_dir,
                prefix=f".{filename}.",
                suffix=".tmp",
                text=True,
            )
            path = Path(raw_path)
            temporary[filename] = path
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
        for filename in OUTPUT_FILENAMES:
            os.replace(temporary[filename], output_dir / filename)
    finally:
        for path in temporary.values():
            path.unlink(missing_ok=True)


def merge(input_dir: Path, output_dir: Path, min_active: int, min_products: int) -> dict[str, Any]:
    """Publish only after every input and staged output passes strict JSON validation."""
    _validate_input_shards(input_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=output_dir.parent,
        prefix=".dropfinder-publication-",
    ) as directory:
        stage = Path(directory)
        publication.merge(input_dir, stage, min_active, min_products)
        content = _validated_output_text(stage)
        runtime = load(stage / "runtime.json")
        _replace_outputs(output_dir, content)
        return runtime


def self_test(root: Path) -> int:
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    publication.self_test(root)
    for filename in OUTPUT_FILENAMES:
        load(root / "out" / filename)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("cloud_pages/data"))
    parser.add_argument("--min-active", type=int, default=5)
    parser.add_argument("--min-products", type=int, default=25)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test(Path("/tmp/dropfinder-autonomous-merge-test"))
    if args.input is None:
        parser.error("--input is required")
    runtime = merge(args.input, args.output, args.min_active, args.min_products)
    print(dumps(runtime), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
