from __future__ import annotations

import argparse
import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.catalog_v4.strict_json import dumps_strict, load_path_strict

SUPPORTED_VAPE_TYPES = {"cannabis_vape", "psilocybin_vape"}
STABLE_QUANTITY_REASONS = {
    "unsupported_vape_mass_quantity",
    "missing_vape_volume",
    "inconsistent_vape_quantity",
    "missing_vape_comparison_price",
    "inconsistent_vape_comparison_price",
}
MASS_LABEL = re.compile(r"(?<!\d)(?:0\.25|0\.5|1|2|3\.5|4|7|14|28|56|112)\s*(?:g|grams?)\b", re.I)
VOLUME_LABEL = re.compile(r"(?<!\d)(?:0\.25|0\.3|0\.5|0\.8|1|1\.5|2|3|5|10)\s*(?:ml|milliliters?)\b", re.I)
TOLERANCE = 0.0001


class VapeQuantityVerificationError(RuntimeError):
    pass


def _positive_finite(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 and parsed == parsed and parsed not in (float("inf"), float("-inf")) else None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_digest(hashes: dict[str, str]) -> str:
    basis = "\n".join(f"{key}:{hashes[key]}" for key in sorted(hashes)).encode("utf-8")
    return hashlib.sha256(basis).hexdigest()


def _product_price(product: dict[str, Any]) -> float | None:
    value = product.get("price") if product.get("price") not in (None, "") else product.get("current_price")
    return _positive_finite(value)


def _validate_published_vape(product: dict[str, Any], index: int) -> None:
    identifier = str(product.get("id") or product.get("product_id") or f"index:{index}")
    primary_type = str(product.get("primary_type") or "")
    if primary_type not in SUPPORTED_VAPE_TYPES:
        raise VapeQuantityVerificationError(f"unsupported published vape type for {identifier}: {primary_type}")
    grams = _positive_finite(product.get("grams"))
    volume_ml = _positive_finite(product.get("volume_ml"))
    quantity_value = _positive_finite(product.get("quantity_value"))
    comparison = _positive_finite(product.get("comparison_price"))
    price_per_ml = _positive_finite(product.get("price_per_ml"))
    current_price = _product_price(product)
    if grams is not None:
        raise VapeQuantityVerificationError(f"published vape retains mass quantity: {identifier}")
    if str(product.get("quantity_unit") or "") != "ml":
        raise VapeQuantityVerificationError(f"published vape quantity_unit is not ml: {identifier}")
    if volume_ml is None:
        raise VapeQuantityVerificationError(f"published vape volume_ml is not finite and positive: {identifier}")
    if quantity_value is not None and abs(quantity_value - volume_ml) > TOLERANCE:
        raise VapeQuantityVerificationError(f"published vape quantity_value disagrees with volume_ml: {identifier}")
    if str(product.get("comparison_metric") or "") != "price_per_ml":
        raise VapeQuantityVerificationError(f"published vape comparison metric is not price_per_ml: {identifier}")
    if comparison is None or price_per_ml is None or current_price is None:
        raise VapeQuantityVerificationError(f"published vape comparison fields are not finite and positive: {identifier}")
    expected = current_price / volume_ml
    if abs(comparison - price_per_ml) > TOLERANCE or abs(price_per_ml - expected) > TOLERANCE:
        raise VapeQuantityVerificationError(f"published vape price-per-ml is inconsistent: {identifier}")
    source_text = " ".join(str(product.get(field) or "") for field in ("name", "source_title", "variant", "source_weight_label"))
    if MASS_LABEL.search(source_text) and not VOLUME_LABEL.search(source_text):
        raise VapeQuantityVerificationError(f"mass-only vape reached publication: {identifier}")


def _validate_rejections(rejections: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for index, row in enumerate(rejections):
        if not isinstance(row, dict):
            raise VapeQuantityVerificationError(f"rejection row {index} is not an object")
        reason = str(row.get("reason") or "")
        counts[reason or "missing_reason"] += 1
        primary_type = str(row.get("primary_type") or "")
        source_text = " ".join(str(row.get(field) or "") for field in ("name", "source_title", "variant", "source_weight_label"))
        mass_only = bool(MASS_LABEL.search(source_text)) and not bool(VOLUME_LABEL.search(source_text))
        if primary_type in SUPPORTED_VAPE_TYPES and mass_only and reason != "unsupported_vape_mass_quantity":
            raise VapeQuantityVerificationError(f"mass-only vape rejection {index} uses unstable reason: {reason or 'missing'}")
        if reason.startswith(("unsupported_vape_", "missing_vape_", "inconsistent_vape_")) and reason not in STABLE_QUANTITY_REASONS:
            raise VapeQuantityVerificationError(f"unknown vape quantity rejection reason: {reason}")
        if reason == "unsupported_vape_mass_quantity" and not MASS_LABEL.search(source_text):
            raise VapeQuantityVerificationError(f"mass-quantity rejection {index} does not retain explicit source mass evidence")
    return counts


def verify_vape_quantity_artifacts(catalog_path: Path, status_path: Path, *, source_commit: str = "", artifact_label: str = "generated") -> dict[str, Any]:
    catalog = load_path_strict(catalog_path)
    status = load_path_strict(status_path)
    if not isinstance(catalog, dict) or not isinstance(status, dict):
        raise VapeQuantityVerificationError("catalog and status artifacts must be JSON objects")
    products = catalog.get("products")
    if not isinstance(products, list):
        raise VapeQuantityVerificationError("catalog products must be a list")
    declared_products = catalog.get("product_count")
    if declared_products is not None and int(declared_products) != len(products):
        raise VapeQuantityVerificationError("catalog product_count does not match products")
    vapes: list[dict[str, Any]] = []
    for index, raw_product in enumerate(products):
        if not isinstance(raw_product, dict):
            raise VapeQuantityVerificationError(f"catalog product {index} is not an object")
        if str(raw_product.get("primary_type") or "") in SUPPORTED_VAPE_TYPES:
            _validate_published_vape(raw_product, index)
            vapes.append(raw_product)
    rejections_value = status.get("rejections")
    rejections = rejections_value if isinstance(rejections_value, list) else []
    rejection_counts = _validate_rejections(rejections)
    declared_rejection_counts = catalog.get("rejection_counts")
    if isinstance(declared_rejection_counts, dict):
        for reason, count in declared_rejection_counts.items():
            if reason in STABLE_QUANTITY_REASONS and rejection_counts.get(reason, 0) != int(count):
                raise VapeQuantityVerificationError(f"catalog rejection count disagrees with status for {reason}")
    summary = status.get("summary") if isinstance(status.get("summary"), dict) else {}
    hashes = {"catalog": _sha256(catalog_path), "status": _sha256(status_path)}
    generation = str(catalog.get("generation_id") or catalog.get("generated_at") or status.get("generation_id") or status.get("generated_at") or "")
    return {
        "verified": True,
        "artifact_label": artifact_label,
        "generation": generation,
        "source_commit": source_commit,
        "product_count": len(products),
        "vape_count": len(vapes),
        "active_source_count": int(summary.get("active_sources") or 0),
        "degraded_source_count": int(summary.get("degraded_sources") or 0),
        "rejection_counts": dict(sorted(rejection_counts.items())),
        "hashes": hashes,
        "artifact_digest": _artifact_digest(hashes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify published DropFinder vape quantity integrity")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--source-commit", default="")
    parser.add_argument("--artifact-label", default="generated")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    receipt = verify_vape_quantity_artifacts(args.catalog, args.status, source_commit=args.source_commit, artifact_label=args.artifact_label)
    text = dumps_strict(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
