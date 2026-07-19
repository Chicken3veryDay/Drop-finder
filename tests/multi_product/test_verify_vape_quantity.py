from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.multi_product.verify_vape_quantity import (
    VapeQuantityVerificationError,
    verify_vape_quantity_artifacts,
)


class VapeQuantityArtifactVerifierTests(unittest.TestCase):
    def write_artifacts(self, root: Path, products, rejections):
        catalog = {
            "schema_version": "fixture",
            "generated_at": "2026-07-19T00:00:00+00:00",
            "products": products,
            "product_count": len(products),
            "rejection_counts": {},
        }
        for rejection in rejections:
            reason = rejection["reason"]
            catalog["rejection_counts"][reason] = catalog["rejection_counts"].get(reason, 0) + 1
        status = {
            "schema_version": "fixture",
            "generated_at": catalog["generated_at"],
            "summary": {
                "active_sources": 3,
                "degraded_sources": 0,
            },
            "rejections": rejections,
        }
        catalog_path = root / "catalog.json"
        status_path = root / "status.json"
        catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        return catalog_path, status_path

    def valid_vape(self):
        return {
            "id": "vape-1",
            "primary_type": "cannabis_vape",
            "name": "Live Resin Disposable 1mL",
            "price": 20,
            "grams": None,
            "volume_ml": 1,
            "quantity_value": 1,
            "quantity_unit": "ml",
            "comparison_metric": "price_per_ml",
            "comparison_price": 20,
            "price_per_ml": 20,
        }

    def test_valid_generated_artifacts_produce_authenticated_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path, status_path = self.write_artifacts(
                root,
                [self.valid_vape(), {"id": "flower", "primary_type": "cannabis_flower"}],
                [{
                    "primary_type": "cannabis_vape",
                    "name": "Mass-only disposable 2g",
                    "reason": "unsupported_vape_mass_quantity",
                }],
            )
            receipt = verify_vape_quantity_artifacts(
                catalog_path,
                status_path,
                source_commit="abc123",
                artifact_label="generated-main",
            )
            self.assertTrue(receipt["verified"])
            self.assertEqual(receipt["product_count"], 2)
            self.assertEqual(receipt["vape_count"], 1)
            self.assertEqual(receipt["active_source_count"], 3)
            self.assertEqual(receipt["rejection_counts"]["unsupported_vape_mass_quantity"], 1)
            self.assertEqual(len(receipt["artifact_digest"]), 64)
            self.assertEqual(receipt["source_commit"], "abc123")

    def test_mass_only_vape_cannot_reach_publication(self):
        invalid = self.valid_vape()
        invalid.update({
            "name": "Mass-only disposable 2g",
            "grams": 2,
            "volume_ml": None,
            "quantity_value": 2,
            "quantity_unit": "g",
            "comparison_metric": "price_per_gram",
            "comparison_price": 10,
            "price_per_ml": None,
        })
        with tempfile.TemporaryDirectory() as directory:
            catalog_path, status_path = self.write_artifacts(Path(directory), [invalid], [])
            with self.assertRaisesRegex(VapeQuantityVerificationError, "mass quantity"):
                verify_vape_quantity_artifacts(catalog_path, status_path)

    def test_price_per_ml_must_match_price_and_volume(self):
        invalid = self.valid_vape()
        invalid["price_per_ml"] = 19
        invalid["comparison_price"] = 19
        with tempfile.TemporaryDirectory() as directory:
            catalog_path, status_path = self.write_artifacts(Path(directory), [invalid], [])
            with self.assertRaisesRegex(VapeQuantityVerificationError, "price-per-ml"):
                verify_vape_quantity_artifacts(catalog_path, status_path)

    def test_mass_only_rejection_requires_stable_reason_and_source_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog_path, status_path = self.write_artifacts(
                Path(directory),
                [],
                [{
                    "primary_type": "cannabis_vape",
                    "name": "Mass-only disposable 2g",
                    "reason": "missing_vape_volume",
                }],
            )
            with self.assertRaisesRegex(VapeQuantityVerificationError, "unstable reason"):
                verify_vape_quantity_artifacts(catalog_path, status_path)

        with tempfile.TemporaryDirectory() as directory:
            catalog_path, status_path = self.write_artifacts(
                Path(directory),
                [],
                [{
                    "primary_type": "cannabis_vape",
                    "name": "Vape with unknown quantity",
                    "reason": "unsupported_vape_mass_quantity",
                }],
            )
            with self.assertRaisesRegex(VapeQuantityVerificationError, "does not retain explicit source mass evidence"):
                verify_vape_quantity_artifacts(catalog_path, status_path)


if __name__ == "__main__":
    unittest.main()
