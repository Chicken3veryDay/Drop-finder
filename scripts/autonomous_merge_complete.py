#!/usr/bin/env python3
"""Final complete-data merger with direct URLs and one normalization contract."""
from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import autonomous_merge as base  # type: ignore
from catalog_normalization import (  # type: ignore
    NORMALIZATION_CONTRACT,
    normalize_product,
    normalization_failures,
    self_test as normalization_self_test,
)

_original_reject_reason = base.reject_reason
_original_sanitize = base.sanitize
_original_merge = base.merge
_PRODUCT_MARKERS = (
    "/product/",
    "/products/",
    "/product-page/",
    "/l/national/product/",
    "/cbd-hemp-flower/",
    "/hemp-products/",
)
_LISTING_MARKERS = (
    "/product-category/",
    "/product-tag/",
    "/collections/",
    "/category/",
    "/categories/",
)


def direct_product_url(value: object) -> bool:
    try:
        parsed = urllib.parse.urlsplit(str(value or ""))
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    path = urllib.parse.unquote(parsed.path).lower()
    if any(marker in path for marker in _LISTING_MARKERS):
        return False
    return any(marker in path for marker in _PRODUCT_MARKERS)


def reject_reason(product: dict) -> str | None:
    reason = _original_reject_reason(product)
    if reason:
        return reason
    if not direct_product_url(product.get("url")):
        return "non_product_destination_url"
    # Raw adapter rows are classified before normalization. Accepted rows carry
    # comparison_complete and must also satisfy the source-independent display
    # contract before the final invariant check and publication.
    if product.get("comparison_complete") is True or product.get("normalization_contract"):
        if normalization_failures(product):
            return "final_normalization_contract_failed"
    return None


def sanitize(products: list[dict]) -> tuple[list[dict], list[dict]]:
    accepted, rejected = _original_sanitize(products)
    normalized: list[dict] = []
    for product in accepted:
        row = normalize_product(product)
        failures = normalization_failures(row)
        if failures:
            rejected.append({
                "id": row.get("id"),
                "source_id": row.get("source_id"),
                "vendor": row.get("vendor"),
                "name": row.get("name"),
                "raw_name": row.get("raw_name"),
                "variant": row.get("variant"),
                "raw_variant": row.get("raw_variant"),
                "url": row.get("url"),
                "price": row.get("price"),
                "grams": row.get("grams"),
                "price_per_gram": row.get("price_per_gram"),
                "thca": row.get("thca"),
                "availability": row.get("availability"),
                "reason": "final_normalization_contract_failed",
                "normalization_failures": failures,
            })
            continue
        normalized.append(row)
    return base.dedupe(normalized), rejected


def merge(input_dir: Path, output_dir: Path, min_active: int, min_products: int) -> dict:
    runtime = _original_merge(input_dir, output_dir, min_active, min_products)
    updates = {
        "catalog.json": {"normalization_contract": NORMALIZATION_CONTRACT},
        "status.json": {"normalization_contract": NORMALIZATION_CONTRACT},
        "runtime.json": {"normalization_contract": NORMALIZATION_CONTRACT},
    }
    for filename, additions in updates.items():
        path = output_dir / filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(additions)
        if filename == "status.json":
            services = dict(payload.get("services") or {})
            services["final_normalizer"] = "healthy"
            payload["services"] = services
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    runtime = json.loads((output_dir / "runtime.json").read_text(encoding="utf-8"))
    return runtime


base.reject_reason = reject_reason
base.sanitize = sanitize
base.merge = merge


def self_test() -> int:
    import tempfile

    normalization_self_test()
    assert direct_product_url("https://x.test/products/blue-dream?variant=1")
    assert direct_product_url("https://x.test/product/blue-dream")
    assert not direct_product_url("https://x.test/product-category/thca-flower")
    assert not direct_product_url("https://x.test/collections/thca-flower")
    with tempfile.TemporaryDirectory() as temporary:
        base.self_test(Path(temporary))
        catalog = json.loads((Path(temporary) / "out" / "catalog.json").read_text(encoding="utf-8"))
        assert catalog["normalization_contract"] == NORMALIZATION_CONTRACT
        assert all(row["normalization_contract"] == NORMALIZATION_CONTRACT for row in catalog["products"])
        assert all(not any(token in row["name"].lower() for token in ("thca", " weight:", " size:")) for row in catalog["products"])
        assert all(row["variant"] == row["package_label"] for row in catalog["products"])
    invalid = base.complete_fixture("listing", "Listing THCA Flower 3.5g", 20)
    invalid["url"] = "https://x.test/product-category/thca-flower"
    assert reject_reason(invalid) == "non_product_destination_url"
    normalized, rejected = sanitize([
        base.complete_fixture("clean", "Blue Dream THCA Flower Weight: 3.5g", 20),
    ])
    assert not rejected
    assert normalized[0]["name"] == "Blue Dream"
    assert normalized[0]["variant"] == "3.5 g"
    assert normalization_failures(normalized[0]) == []
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
