from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.multi_product import CANNABIS_FLOWER, CANNABIS_VAPE, PSILOCYBIN_MUSHROOM
from scripts.multi_product.publication import SHARD_SCHEMA, merge, sanitize, self_test


def product_fixture(*, product_id: str, name: str, primary_type: str, evidence: dict, **extra):
    url = f"https://example.test/products/{product_id}"
    return {
        "id": product_id,
        "source_id": "fixture",
        "vendor": "Fixture Vendor",
        "name": name,
        "source_title": name,
        "primary_type": primary_type,
        "type_tags": [primary_type],
        "url": url,
        "public_purchase_url": url,
        "price": 50,
        "availability": "in_stock",
        "classification_evidence": {
            "primary_type": primary_type,
            "type_tags": [primary_type],
            **evidence,
        },
        **extra,
    }


def mixed_offer_fixtures() -> list[dict]:
    return [
        product_fixture(
            product_id="flower-bundle",
            name="THCA Flower Bundle 4oz Mix & Match",
            primary_type=CANNABIS_FLOWER,
            evidence={"explicit_thca": True, "explicit_flower": True, "explicit_vape": False},
            grams=113.398,
            price_per_gram=3.1747,
        ),
        product_fixture(
            product_id="stash-kit",
            name="Dad's Day Stash Kit THCA Disposable Vape 1mL",
            primary_type=CANNABIS_VAPE,
            evidence={"explicit_cannabis": True, "explicit_vape": True},
            volume_ml=1,
            price_per_ml=50,
        ),
    ]


def valid_flower_fixture() -> dict:
    return product_fixture(
        product_id="single-flower",
        name="Blue Dream THCA Flower 3.5g",
        primary_type=CANNABIS_FLOWER,
        evidence={"explicit_thca": True, "explicit_flower": True, "explicit_vape": False},
        variant="single-strain jar with freshness pack",
        route_url="https://example.test/collections/bundles",
        grams=3.5,
        price_per_gram=10,
    )


class PublicationTests(unittest.TestCase):
    def test_type_aware_sanitizer_and_controlled_link_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(self_test(root), 0)
            catalog = json.loads((root / "out" / "catalog.json").read_text(encoding="utf-8"))
            controlled = [
                product
                for product in catalog["products"]
                if product["primary_type"] == PSILOCYBIN_MUSHROOM
            ]
            self.assertEqual(len(controlled), 1)
            self.assertEqual(controlled[0]["url"], "")
            self.assertIsNone(controlled[0]["public_purchase_url"])
            self.assertEqual(catalog["products_by_type"]["cannabis_vape"], 1)

    def test_final_sanitizer_rejects_forged_mixed_offer_rows(self) -> None:
        accepted, rejected = sanitize([*mixed_offer_fixtures(), valid_flower_fixture()])

        self.assertEqual([row["id"] for row in accepted], ["single-flower"])
        self.assertEqual(
            [(row["name"], row["reason"]) for row in rejected],
            [
                ("THCA Flower Bundle 4oz Mix & Match", "unsupported_mixed_offer"),
                ("Dad's Day Stash Kit THCA Disposable Vape 1mL", "unsupported_mixed_offer"),
            ],
        )

    def test_merge_keeps_mixed_offers_out_of_catalog_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "shard-0.json").write_text(
                json.dumps({
                    "schema_version": SHARD_SCHEMA,
                    "products": [*mixed_offer_fixtures(), valid_flower_fixture()],
                    "sources": [{
                        "source_id": "fixture",
                        "name": "Fixture Vendor",
                        "admitted": True,
                        "status": "healthy",
                        "products": 3,
                    }],
                }),
                encoding="utf-8",
            )

            merge(root, root / "out", min_active=1, min_products=1)

            catalog = json.loads((root / "out" / "catalog.json").read_text(encoding="utf-8"))
            rejections = json.loads((root / "out" / "rejections.json").read_text(encoding="utf-8"))
            self.assertEqual(catalog["product_count"], 1)
            self.assertEqual(catalog["products_by_type"], {CANNABIS_FLOWER: 1})
            self.assertEqual([row["id"] for row in catalog["products"]], ["single-flower"])
            self.assertEqual(rejections["reason_counts"], {"unsupported_mixed_offer": 2})


if __name__ == "__main__":
    unittest.main()
