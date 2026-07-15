from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .builder import build_catalog, write_result
from .verify import verify_publication


def _optional_json(path: Path | None) -> Any:
    if path is None or not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build DropFinder catalog v4 from an admitted legacy/structured catalog")
    parser.add_argument("--input", type=Path, required=True, help="Input JSON containing a products array")
    parser.add_argument("--output", type=Path, required=True, help="cloud_pages/data output root")
    parser.add_argument("--vendor-profiles", type=Path)
    parser.add_argument("--documents", type=Path)
    parser.add_argument("--detail-shards", type=int, default=16)
    parser.add_argument("--minimum-products", type=int, default=1)
    parser.add_argument("--minimum-variants", type=int, default=1)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    if args.verify_only:
        print(json.dumps(verify_publication(args.output), indent=2, sort_keys=True))
        return 0

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    products = payload.get("products") if isinstance(payload, dict) else None
    if not isinstance(products, list):
        raise SystemExit("input must be a JSON object with a products array")
    vendor_profiles = _optional_json(args.vendor_profiles)
    documents_payload = _optional_json(args.documents)
    document_records = None
    if isinstance(documents_payload, dict):
        candidate = documents_payload.get("documents")
        document_records = candidate if isinstance(candidate, list) else None
    elif isinstance(documents_payload, list):
        document_records = documents_payload

    result = build_catalog(
        products,
        generated_at=payload.get("generated_at"),
        vendor_profiles=vendor_profiles,
        document_records=document_records,
        detail_shards=args.detail_shards,
    )
    if result.product_count < args.minimum_products:
        raise SystemExit(f"catalog v4 product floor failed: {result.product_count} < {args.minimum_products}")
    if result.variant_count < args.minimum_variants:
        raise SystemExit(f"catalog v4 variant floor failed: {result.variant_count} < {args.minimum_variants}")
    write_result(result, args.output)
    verified = verify_publication(args.output)
    summary = {
        **verified,
        "rejected_variants": result.rejected_count,
        "manifest": "catalog-v4/manifest.json",
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
