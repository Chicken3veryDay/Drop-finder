"""Generate and verify vendor-document artifacts for Catalog V4."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from scripts.catalog_v4.strict_json import dumps_strict, load_path_strict

from .publication_artifact import build_artifact, verify_artifact

DEFAULT_PROFILES = Path(__file__).resolve().parents[2] / "data" / "vendor_profiles.json"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        dumps_strict(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate")
    generate.add_argument("--catalog", type=Path, required=True)
    generate.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--observed-at")
    generate.add_argument("--offline", action="store_true")
    generate.add_argument("--timeout", type=float, default=10.0)
    generate.add_argument("--max-index-bytes", type=int, default=2_000_000)
    generate.add_argument("--max-product-page-bytes", type=int, default=1_000_000)
    generate.add_argument("--max-product-pages-per-vendor", type=int, default=12)

    verify = commands.add_parser("verify")
    verify.add_argument("--artifact", type=Path, required=True)
    verify.add_argument("--catalog", type=Path, required=True)
    verify.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)

    args = parser.parse_args()
    catalog = load_path_strict(args.catalog)
    profiles = load_path_strict(args.profiles)
    if args.command == "generate":
        artifact = build_artifact(
            catalog,
            profiles,
            observed_at=args.observed_at,
            offline=args.offline,
            timeout=args.timeout,
            max_index_bytes=args.max_index_bytes,
            max_product_page_bytes=args.max_product_page_bytes,
            max_product_pages_per_vendor=args.max_product_pages_per_vendor,
        )
        receipt = verify_artifact(artifact, catalog, profiles)
        _write(args.output, artifact)
        print(dumps_strict({"artifact": str(args.output), **receipt}, indent=2, sort_keys=True))
        return 0

    artifact = load_path_strict(args.artifact)
    print(dumps_strict(verify_artifact(artifact, catalog, profiles), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
