from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .builder import build_catalog, write_result
from .verify import verify_publication


def main() -> int:
    rows = [
        {
            "source_id": "fixture",
            "vendor": "Fixture Farms",
            "source_product_id": "p-1",
            "source_variant_id": "v-1",
            "name": "Blue Dream THCA Flower | 3.5g",
            "variant": "3.5g",
            "url": "https://example.test/products/blue-dream?variant=v-1",
            "availability": "in_stock",
            "price": 35,
            "regular_price": 40,
            "thca": 25,
            "delta9_thc": "ND",
            "lineage": "Sativa-leaning hybrid",
            "effects": ["Calm", "Creative"],
            "grow_environment": "indoor",
        },
        {
            "source_id": "fixture",
            "vendor": "Fixture Farms",
            "source_product_id": "p-1",
            "source_variant_id": "v-2",
            "name": "Blue Dream THCA Flower | 7g",
            "variant": "7g",
            "url": "https://example.test/products/blue-dream?variant=v-2",
            "availability": "in_stock",
            "price": 60,
            "thca": 25,
            "delta9_thc": "ND",
        },
        {
            "source_id": "fixture",
            "vendor": "Fixture Farms",
            "source_product_id": "sold",
            "name": "Sold Flower THCA Flower",
            "variant": "3.5g",
            "url": "https://example.test/products/sold",
            "availability": "out_of_stock",
            "price": 20,
        },
    ]
    result = build_catalog(rows, generated_at="2026-01-01T00:00:00+00:00", detail_shards=4)
    assert result.product_count == 1
    assert result.variant_count == 2
    assert result.rejected_count == 1
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write_result(result, root)
        verification = verify_publication(root)
        assert verification["products"] == 1 and verification["variants"] == 2
    print(json.dumps({"catalog_v4_selftest": "passed", "generation_id": result.generation_id}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
