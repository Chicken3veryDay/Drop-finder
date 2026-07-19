from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from .builder import build_catalog, write_result
from .normalization import clean_text, normalize_weight, safe_decimal
from .strict_json import StrictJsonError, load_path_strict
from .vendor_profiles import merge_vendor_profiles, optional_json, write_public_age_index
from .verify import verify_publication

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VENDOR_PROFILES = ROOT / "data" / "vendor_profiles.json"
DEFAULT_VENDOR_EXPANSION = ROOT / "data" / "vendor_expansion.json"
POUND_UNIT = re.compile(r"\b(?:lb|lbs|pounds?)\b", re.I)


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


def _weight_evidence_labels(product: dict[str, Any]) -> Iterable[Any]:
    seen: set[str] = set()
    for key in (
        "source_weight_label",
        "weight_label",
        "variant",
        "weight",
        "size",
        "source_title",
        "name",
        "title",
    ):
        value = product.get(key)
        normalized = clean_text(value).casefold()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        yield value


def _legacy_pound_correction(direct: Any, label: Any) -> tuple[Decimal | None, str]:
    """Repair the known pre-#162 pound-as-ounce conversion, and nothing broader."""
    label_weight, matched_label = normalize_weight(None, label)
    direct_weight = safe_decimal(direct, minimum=Decimal("0.05"), maximum=Decimal("5000"))
    if label_weight is None or direct_weight is None or not POUND_UNIT.search(matched_label):
        return None, ""
    expected_from_legacy_ounce = direct_weight * Decimal("16")
    tolerance = max(Decimal("0.05"), label_weight * Decimal("0.02"))
    if abs(label_weight - expected_from_legacy_ounce) > tolerance:
        return None, ""
    return label_weight, matched_label


def strict_flower_products(products: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Adapt the generalized raw catalog to the mature flower catalog-v4 contract.

    Explicit non-flower records remain available to the type-aware raw-catalog UI
    but are excluded from the flower-specific catalog-v4 builder. Legacy untyped
    rows remain eligible. Package weights require explicit source text. Newly
    generated cloud-scan rows carry `source_weight_label`; older admitted rows
    may recover the same evidence conservatively from their variant or title.
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
        direct = prepared.get("grams") if prepared.get("grams") not in (None, "") else prepared.get("weight_grams")
        for label in _weight_evidence_labels(prepared):
            grams, matched_label = normalize_weight(direct, label)
            if grams is None:
                grams, matched_label = _legacy_pound_correction(direct, label)
            if grams is None:
                continue
            prepared["grams"] = float(grams)
            prepared["source_weight_label"] = matched_label
            break
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

    try:
        payload = load_path_strict(args.input)
    except StrictJsonError as exc:
        raise SystemExit(str(exc)) from exc
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
