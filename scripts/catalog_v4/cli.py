from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .builder import build_catalog, write_result
from .normalization import normalize_weight
from .vendor_profiles import merge_vendor_profiles, optional_json, write_public_age_index
from .verify import verify_publication

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VENDOR_PROFILES = ROOT / "data" / "vendor_profiles.json"
DEFAULT_VENDOR_EXPANSION = ROOT / "data" / "vendor_expansion.json"


def _optional_json(path: Path | None) -> Any:
    """Compatibility wrapper retained for existing callers and tests."""
    return optional_json(path)


def declared_product_type(product: dict[str, Any]) -> str:
    direct = product.get("primary_type")
    if isinstance(direct, str) and direct.strip():
        return direct.strip().lower()
    evidence = product.get("classification_evidence")
    if isinstance(evidence, dict):
        inferred = evidence.get("primary_type")
        if isinstance(inferred, str):
            return inferred.strip().lower()
    return ""


def strict_flower_products(products: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Adapt the generalized raw catalog to the mature flower catalog-v4 contract.

    Explicit non-flower records remain available to the type-aware raw-catalog UI
    but are excluded from the flower-specific catalog-v4 builder. Legacy untyped
    rows remain eligible. When generalized retrieval could not normalize a flat
    flower record's weight, recover it conservatively from its variant or source
    title using the catalog-v4 parser. Structured records keep weight resolution
    at child-variant scope so a parent title cannot override package labels.
    """
    admitted: list[dict[str, Any]] = []
    excluded = 0
    for product in products:
        if not isinstance(product, dict):
            continue
        product_type = declared_product_type(product)
        if product_type and product_type != "cannabis_flower":
            excluded += 1
            continue
        prepared = dict(product)
        nested_variants = prepared.get("variants")
        has_nested_variants = isinstance(nested_variants, list) and bool(nested_variants)
        if (
            not has_nested_variants
            and prepared.get("grams") in (None, "")
            and prepared.get("weight_grams") in (None, "")
        ):
            label = next(
                (
                    prepared.get(key)
                    for key in ("source_weight_label", "weight_label", "variant", "weight", "size", "source_title", "name", "title")
                    if prepared.get(key) not in (None, "")
                ),
                None,
            )
            grams, _ = normalize_weight(None, label)
            if grams is not None:
                prepared["grams"] = float(grams)
        admitted.append(prepared)
    return admitted, excluded


def main() -> int:
    parser = argparse.ArgumentParser(description="Build DropFinder catalog v4 from an admitted legacy/structured catalog")
    parser.add_argument("--input", type=Path, required=True, help="Input JSON containing a products array")
    parser.add_argument("--output", type=Path, required=True, help="cloud_pages/data output root")
    parser.add_argument("--vendor-profiles", type=Path, default=DEFAULT_VENDOR_PROFILES)
    parser.add_argument("--vendor-expansion", type=Path, default=DEFAULT_VENDOR_EXPANSION)
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
    publication_products, excluded_non_flower_products = strict_flower_products(products)

    source_profile_payloads = [
        value
        for value in (
            optional_json(args.vendor_profiles),
            optional_json(args.vendor_expansion),
        )
        if isinstance(value, dict)
    ]
    vendor_profiles = merge_vendor_profiles(source_profile_payloads)
    documents_payload = optional_json(args.documents)
    document_records = None
    if isinstance(documents_payload, dict):
        candidate = documents_payload.get("documents")
        document_records = candidate if isinstance(candidate, list) else None
    elif isinstance(documents_payload, list):
        document_records = documents_payload

    result = build_catalog(
        publication_products,
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
    age_index_path = write_public_age_index(args.output, source_profile_payloads)
    verified = verify_publication(args.output)
    summary = {
        **verified,
        "rejected_variants": result.rejected_count,
        "excluded_non_flower_products": excluded_non_flower_products,
        "manifest": "catalog-v4/manifest.json",
        "vendor_age_index": str(age_index_path.relative_to(args.output)),
        "vendor_age_profiles": len(vendor_profiles["vendors"]),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
