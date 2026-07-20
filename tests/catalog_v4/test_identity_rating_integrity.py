from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.catalog_v4 import build_catalog, verify_publication, write_result
from scripts.catalog_v4.verify import VerificationError


def row(*, variant: str, price: float, collected_at: str, rating=None, review_count=None, name="Candy Runtz THCa Flower Smalls") -> dict:
    return {
        "source_id": "vendor",
        "vendor": "Vendor",
        "source_product_id": "product-1",
        "source_variant_id": f"variant-{variant}",
        "name": f"{name} | {variant}",
        "variant": variant,
        "url": f"https://vendor.example/products/candy-runtz?variant={variant}",
        "route_url": "https://vendor.example/api/products",
        "availability": "in_stock",
        "price": price,
        "collected_at": collected_at,
        "rating": rating,
        "review_count": review_count,
    }


def payload(data: bytes) -> dict:
    return json.loads(data.decode("utf-8"))


class CatalogIdentityRatingIntegrityTests(unittest.TestCase):
    def test_builder_publishes_selected_canonical_name_and_matching_search_identity(self) -> None:
        result = build_catalog(
            [row(variant="3.5g", price=25, collected_at="2026-01-01T00:00:00Z")],
            generated_at="2026-02-01T00:00:00Z",
            detail_shards=1,
        )
        product = payload(result.files["catalog-v4/index.json"])["products"][0]
        self.assertEqual(product["strain_name"], "Candy Runtz")
        self.assertEqual(product["search"]["strain"], "candy runtz")

    def test_rating_and_count_are_selected_from_one_complete_record(self) -> None:
        result = build_catalog(
            [
                row(variant="3.5g", price=25, collected_at="2026-02-01T00:00:00Z", rating=4.9),
                row(variant="7g", price=40, collected_at="2026-01-01T00:00:00Z", rating=3.1, review_count=1000),
            ],
            generated_at="2026-03-01T00:00:00Z",
            detail_shards=1,
        )
        index_product = payload(result.files["catalog-v4/index.json"])["products"][0]
        self.assertEqual((index_product["rating"], index_product["review_count"]), (3.1, 1000))
        detail_product = payload(result.files["catalog-v4/details/000.json"])["products"][0]
        provenance = detail_product["rating_provenance"]
        self.assertEqual(provenance["method"], "atomic_source_record_pair")
        self.assertTrue(provenance["source_record_id"])
        self.assertEqual(provenance["collected_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(provenance["source_path"], "https://vendor.example/api/products")

    def test_newer_complete_pair_wins_and_partial_records_never_compose(self) -> None:
        complete = build_catalog(
            [
                row(variant="3.5g", price=25, collected_at="2026-01-01T00:00:00Z", rating=3.1, review_count=1000),
                row(variant="7g", price=40, collected_at="2026-02-01T00:00:00Z", rating=4.9, review_count=1200),
            ],
            generated_at="2026-03-01T00:00:00Z",
            detail_shards=1,
        )
        product = payload(complete.files["catalog-v4/index.json"])["products"][0]
        self.assertEqual((product["rating"], product["review_count"]), (4.9, 1200))

        partial = build_catalog(
            [
                row(variant="3.5g", price=25, collected_at="2026-02-01T00:00:00Z", rating=4.9),
                row(variant="7g", price=40, collected_at="2026-01-01T00:00:00Z", review_count=1000),
            ],
            generated_at="2026-03-01T00:00:00Z",
            detail_shards=1,
        )
        product = payload(partial.files["catalog-v4/index.json"])["products"][0]
        self.assertEqual((product["rating"], product["review_count"]), (None, None))
        detail = payload(partial.files["catalog-v4/details/000.json"])["products"][0]
        self.assertEqual(detail["rating_provenance"]["source"], "unavailable")

    def test_verifier_rejects_non_atomic_rating_provenance(self) -> None:
        result = build_catalog(
            [row(variant="3.5g", price=25, collected_at="2026-01-01T00:00:00Z", rating=4.7, review_count=182)],
            generated_at="2026-03-01T00:00:00Z",
            detail_shards=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_result(result, root)
            detail_path = root / "catalog-v4" / "details" / "000.json"
            detail = json.loads(detail_path.read_text(encoding="utf-8"))
            detail["products"][0]["rating_provenance"].pop("method")
            encoded = (json.dumps(detail, indent=2, sort_keys=True) + "\n").encode("utf-8")
            detail_path.write_bytes(encoded)

            manifest_path = root / "catalog-v4" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            descriptor = manifest["product_detail_shards"][0]
            descriptor["bytes"] = len(encoded)
            descriptor["sha256"] = hashlib.sha256(encoded).hexdigest()
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(VerificationError, "non-atomic rating provenance"):
                verify_publication(root)


if __name__ == "__main__":
    unittest.main()
