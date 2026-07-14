#!/usr/bin/env python3
"""Final complete-data merger with a direct-product URL contract."""
from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import autonomous_merge as base  # type: ignore

_original_reject_reason = base.reject_reason
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
    return None


base.reject_reason = reject_reason


def self_test() -> int:
    import tempfile

    assert direct_product_url("https://x.test/products/blue-dream?variant=1")
    assert direct_product_url("https://x.test/product/blue-dream")
    assert not direct_product_url("https://x.test/product-category/thca-flower")
    assert not direct_product_url("https://x.test/collections/thca-flower")
    with tempfile.TemporaryDirectory() as temporary:
        base.self_test(Path(temporary))
    invalid = base.complete_fixture("listing", "Listing THCA Flower 3.5g", 20)
    invalid["url"] = "https://x.test/product-category/thca-flower"
    assert reject_reason(invalid) == "non_product_destination_url"
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
