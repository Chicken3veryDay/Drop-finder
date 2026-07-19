from __future__ import annotations

import copy
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
    def test_artifact_maps_only_the_unambiguous_report(self) -> None:
        artifact = build_artifact(
            CATALOG,
            PROFILES,
            observed_at="2026-07-19T12:00:00Z",
            fetcher=fetcher,
        )
        receipt = verify_artifact(artifact, CATALOG, PROFILES)

        self.assertEqual(artifact["candidate_count"], 2)
        self.assertEqual(artifact["mapped_document_count"], 1)
        self.assertEqual(artifact["unmatched_count"], 1)
        self.assertEqual(receipt["mapped_document_count"], 1)
        document = artifact["documents"][0]
        self.assertEqual(document["vendor_id"], "lucky_elk")
        self.assertEqual(document["source_product_id"], "blue-dream")
        self.assertEqual(document["kind"], "coa")
        self.assertEqual(document["scope"], "weight")
        self.assertEqual(document["grams"], 3.5)
        self.assertIn("blue-dream-3-5g-coa.pdf", document["url"])
        self.assertEqual(
            artifact["unmatched_documents"][0]["reason"],
            "no_unambiguous_product_match",
        )

        result = build_catalog(
            CATALOG["products"],
            generated_at="2026-07-19T12:00:00Z",
            vendor_profiles=PROFILES,
            document_records=artifact["documents"],
            detail_shards=1,
        )
        detail = json.loads(result.files["catalog-v4/details/000.json"])
        documents = detail["products"][0]["variants"][0]["documents"]
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["kind"], "coa")
        self.assertEqual(documents[0]["scope"], "weight")

    def test_verifier_rejects_a_stale_catalog_binding(self) -> None:
        artifact = build_artifact(CATALOG, PROFILES, fetcher=fetcher)
        changed = copy.deepcopy(CATALOG)
        changed["products"][0]["price"] = 26.0
        with self.assertRaisesRegex(ValueError, "catalog binding mismatch"):
            verify_artifact(artifact, changed, PROFILES)

    def test_offline_artifact_is_hash_bound_and_explicit(self) -> None:
        artifact = build_artifact(
            CATALOG,
            PROFILES,
            observed_at="2026-07-19T12:00:00Z",
            offline=True,
        )
        receipt = verify_artifact(artifact, CATALOG, PROFILES)
        self.assertEqual(artifact["candidate_count"], 0)
        self.assertEqual(artifact["mapped_document_count"], 0)
        self.assertEqual(artifact["unmatched_count"], 0)
        self.assertEqual(receipt["failed_check_count"], 1)
        self.assertEqual(artifact["checks"][0]["error"], "offline_not_run")

    def test_equal_cross_product_scores_remain_unmatched(self) -> None:
        ambiguous_catalog = copy.deepcopy(CATALOG)
        second = copy.deepcopy(ambiguous_catalog["products"][0])
        second.update(
            id="p-blue-other",
            source_product_id="blue-dream-other",
            source_variant_id="other-35",
            url="https://luckyelk.com/products/blue-dream-other?variant=35",
        )
        ambiguous_catalog["products"].append(second)
        one_report = (
            '<a href="https://cdn.shopify.com/s/files/blue-dream-coa.pdf">'
            "Blue Dream THCA Flower 3.5g COA</a>"
        )

        def ambiguous_fetcher(url: str, **_options) -> FetchResult:
            body = one_report if url.endswith("/coa-tests") else "<html></html>"
            return FetchResult(url, url, 200, "text/html", body.encode("utf-8"))

        artifact = build_artifact(
            ambiguous_catalog,
            PROFILES,
            fetcher=ambiguous_fetcher,
        )
        self.assertEqual(artifact["candidate_count"], 1)
        self.assertEqual(artifact["mapped_document_count"], 0)
        self.assertEqual(artifact["unmatched_count"], 1)
        self.assertEqual(artifact["ambiguous_count"], 1)
        self.assertEqual(
            artifact["unmatched_documents"][0]["reason"],
            "ambiguous_product_match",
        )


if __name__ == "__main__":
    unittest.main()
