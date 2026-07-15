from __future__ import annotations

import argparse
import json
import time
from collections import Counter

from .builder import build_catalog


def fixture(product_count: int, variants_per_product: int) -> list[dict]:
    rows: list[dict] = []
    weights = (1, 3.5, 7, 14, 28, 56)
    for product_number in range(product_count):
        for variant_number in range(variants_per_product):
            grams = weights[variant_number % len(weights)]
            rows.append(
                {
                    "source_id": f"vendor-{product_number % 25:02d}",
                    "vendor": f"Vendor {product_number % 25:02d}",
                    "source_product_id": f"p-{product_number:06d}",
                    "source_variant_id": f"v-{product_number:06d}-{variant_number:02d}",
                    "name": f"Fixture Strain {product_number:06d} THCA Flower | {grams}g",
                    "variant": f"{grams}g",
                    "url": f"https://vendor-{product_number % 25:02d}.example/products/p-{product_number:06d}?variant={variant_number}",
                    "availability": "in_stock",
                    "price": round((6.25 * grams) - (variant_number * 0.05), 2),
                    "thca": 20 + (product_number % 15) / 2,
                    "delta9_thc": "ND",
                    "lineage": ("indica", "hybrid", "sativa")[product_number % 3],
                    "effects": ["Calm", "Focused"],
                    "collected_at": "2026-01-01T00:00:00+00:00",
                }
            )
    return rows


def run(product_count: int, variants_per_product: int, detail_shards: int) -> dict:
    rows = fixture(product_count, variants_per_product)
    started = time.perf_counter()
    result = build_catalog(
        rows,
        generated_at="2026-01-01T00:00:00+00:00",
        detail_shards=detail_shards,
    )
    elapsed = time.perf_counter() - started
    detail_sizes = [len(data) for path, data in result.files.items() if path.startswith("catalog-v4/details/")]
    return {
        "input_rows": len(rows),
        "products": result.product_count,
        "variants": result.variant_count,
        "detail_shards": detail_shards,
        "seconds": round(elapsed, 4),
        "rows_per_second": round(len(rows) / elapsed, 1) if elapsed else None,
        "index_bytes": len(result.files["catalog-v4/index.json"]),
        "detail_bytes": sum(detail_sizes),
        "largest_detail_shard_bytes": max(detail_sizes, default=0),
        "rejections": result.rejected_count,
        "rejection_reasons": Counter(row["reason"] for row in result.rejections["variants"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--products", type=int, default=5000)
    parser.add_argument("--variants", type=int, default=4)
    parser.add_argument("--detail-shards", type=int, default=16)
    args = parser.parse_args()
    if args.products < 1 or args.variants < 1:
        parser.error("products and variants must be positive")
    print(json.dumps(run(args.products, args.variants, args.detail_shards), indent=2, sort_keys=True, default=dict))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
