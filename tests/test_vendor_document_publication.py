from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.catalog_v4 import build_catalog
from scripts.vendor_adapters.fetch import FetchResult
from scripts.vendor_adapters.publication_artifact import build_artifact, verify_artifact

ROOT = Path(__file__).resolve().parents[1]
PROFILES = json.loads((ROOT / "data" / "vendor_profiles.json").read_text(encoding="utf-8"))
CATALOG = {
    "schema_version": "dropfinder-cloud-catalog-v3",
    "products": [
        {
            "id": "p-blue-35",
            "source_id": "lucky_elk",
            "source_product_id": "blue-dream",
            "source_variant_id": "35",
            "vendor": "Lucky Elk",
            "name": "Blue Dream THCA Flower 3.5g",
            "url": "https://luckyelk.com/products/blue-dream?variant=35",
            "price": 25.0,
            "grams": 3.5,
            "source_weight_label": "3.5g",
            "availability": "in_stock",
            "variant": "3.5g",
            "collected_at": "2026-07-19T00:00:00Z",
        }
    ],
}
INDEX_HTML = """
<a href="https://cdn.shopify.com/s/files/blue-dream-3-5g-coa.pdf">Blue Dream THCA Flower 3.5g COA</a>
<a href="https://cdn.shopify.com/s/files/archive-runtz-7g-coa.pdf">Archive Runtz THCA Flower 7g COA</a>
"""


def fetcher(url: str, **_options) -> FetchResult:
    body = INDEX_HTML if url.endswith("/coa-tests") else "<html><body>Blue Dream</body></html>"
    return FetchResult(url, url, 200, "text/html", body.encode("utf-8"))


class VendorDocumentPublicationTests(unittest.TestCase):
    pass
