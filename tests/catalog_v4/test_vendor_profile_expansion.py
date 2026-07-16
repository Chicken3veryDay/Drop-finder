from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.catalog_v4.cli import strict_flower_products
from scripts.catalog_v4.vendor_profiles import merge_vendor_profiles
from scripts.vendor_expansion import apply_registry, load_registry, public_age_index

ROOT = Path(__file__).resolve().parents[2]


class VendorExpansionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.expansion = load_registry(ROOT / "data" / "vendor_expansion.json")
        self.current = json.loads((ROOT / "data" / "vendor_profiles.json").read_text(encoding="utf-8"))

    def test_registry_contains_at_least_twenty_unique_custom_sources(self) -> None:
        vendors = self.expansion["vendors"]
        self.assertGreaterEqual(len(vendors), 20)
        self.assertEqual(len(vendors), len({vendor["vendor_id"] for vendor in vendors}))
        self.assertTrue(all(vendor["routes"] for vendor in vendors))
        self.assertTrue(all(vendor["age_verification"]["display"] for vendor in vendors))

    def test_registry_installs_routes_without_replacing_existing_sources(self) -> None:
        worker = SimpleNamespace(
            core=SimpleNamespace(SOURCES=[("existing", "Existing", [("html", "https://example.test", "storewide")])]),
            FALLBACK_HTML_ROUTES={"existing": ["https://example.test"]},
            PRODUCT_PATHS=("/product/", "/products/"),
        )
        installed = apply_registry(worker, self.expansion)
        source_ids = [source[0] for source in worker.core.SOURCES]
        self.assertEqual(source_ids[0], "existing")
        self.assertEqual(len(installed), len(self.expansion["vendors"]))
        self.assertIn("cali_canna", source_ids)
        self.assertIn("flow_gardens", worker.FALLBACK_HTML_ROUTES)
        self.assertEqual(len(source_ids), len(set(source_ids)))

    def test_nested_current_and_expansion_profiles_merge_for_catalog_builder(self) -> None:
        merged = merge_vendor_profiles([self.current, self.expansion])
        profiles = {vendor["vendor_id"]: vendor for vendor in merged["vendors"]}
        self.assertGreaterEqual(len(profiles), 37)
        self.assertEqual(profiles["black_tie_cbd"]["age_gate_classification"], "self_attestation_21_plus")
        self.assertEqual(profiles["flow_gardens"]["age_gate_classification"], "self_attestation_21_plus")
        self.assertTrue(profiles["flow_gardens"]["age_gate_evidence_reference"].startswith("https://"))

    def test_public_age_index_distinguishes_confirmation_from_verification(self) -> None:
        index = public_age_index([self.current, self.expansion])
        profiles = {vendor["vendor_id"]: vendor for vendor in index["vendors"]}
        self.assertEqual(index["vendor_count"], len(profiles))
        self.assertEqual(profiles["flow_gardens"]["display"], "confirmation")
        self.assertNotEqual(profiles["flow_gardens"]["display"], "verification")
        self.assertEqual(profiles["cali_canna"]["display"], "unknown")

    def test_catalog_v4_filters_non_flower_and_recovers_title_weights(self) -> None:
        rows = [
            {"id": "legacy", "name": "Legacy THCA Flower 3.5g"},
            {"id": "flower", "primary_type": "cannabis_flower", "source_title": "Blue Dream THCA Flower quarter"},
            {"id": "vape", "primary_type": "cannabis_vape"},
            {"id": "mushroom", "classification_evidence": {"primary_type": "psilocybin_mushroom"}},
        ]
        admitted, excluded = strict_flower_products(rows)
        self.assertEqual([row["id"] for row in admitted], ["legacy", "flower"])
        self.assertEqual(admitted[0]["grams"], 3.5)
        self.assertEqual(admitted[1]["grams"], 7.0)
        self.assertEqual(excluded, 2)


if __name__ == "__main__":
    unittest.main()
