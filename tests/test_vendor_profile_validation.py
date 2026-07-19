from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.vendor_adapters.coverage import verify_coverage
from scripts.vendor_adapters.live_check import run_live_checks
from scripts.vendor_adapters.registry import VendorRegistry, validate_profiles


ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "data" / "vendor_profiles.json"
SOURCES = ROOT / "scripts" / "cloud_scan.py"
RESEARCH = ROOT / "research" / "vendors"


class VendorProfileValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.valid_payload = json.loads(PROFILES.read_text(encoding="utf-8"))

    def write_payload(self, payload: object) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "profiles.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def mutated(self, mutator) -> dict:
        payload = copy.deepcopy(self.valid_payload)
        mutator(payload["vendors"][0])
        return payload

    def test_checked_in_profiles_remain_valid_and_registry_values_are_not_coerced(self) -> None:
        self.assertEqual(validate_profiles(self.valid_payload), [])
        registry = VendorRegistry.from_profiles(PROFILES)
        source = self.valid_payload["vendors"][0]
        adapter = registry.get(source["vendor_id"])
        self.assertEqual(adapter.vendor_name, source["vendor_name"])
        self.assertEqual(adapter.allowed_document_hosts, frozenset(source["allowed_document_hosts"]))
        self.assertEqual(adapter.lab_index_urls, tuple(source["lab_index_urls"]))
        self.assertIs(adapter.product_page_discovery, source["adapter"]["product_page_discovery"])
        self.assertIs(adapter.structured_api_discovery, source["adapter"]["structured_api_discovery"])

    def test_string_document_host_allowlist_is_rejected_before_any_live_probe(self) -> None:
        payload = self.mutated(lambda profile: profile.__setitem__("allowed_document_hosts", "shop.example"))
        path = self.write_payload(payload)
        errors = validate_profiles(payload)
        self.assertTrue(any("allowed_document_hosts must be a non-empty list" in error for error in errors), errors)
        with self.assertRaisesRegex(ValueError, "allowed_document_hosts"):
            VendorRegistry.from_profiles(path)
        coverage = verify_coverage(path, SOURCES, RESEARCH)
        self.assertFalse(coverage["ok"])
        with patch("scripts.vendor_adapters.live_check.fetch_public_document") as fetch:
            report = run_live_checks(path)
        fetch.assert_not_called()
        self.assertEqual(report["probe_count"], len(errors))
        self.assertEqual(report["failure_count"], len(errors))
        self.assertTrue(all(row["kind"] == "configuration" for row in report["checks"]))

    def test_missing_category_url_is_rejected_and_live_check_returns_an_artifact(self) -> None:
        payload = self.mutated(lambda profile: profile.pop("category_url"))
        path = self.write_payload(payload)
        errors = validate_profiles(payload)
        self.assertTrue(any("category_url must be a non-empty string" in error for error in errors), errors)
        self.assertFalse(verify_coverage(path, SOURCES, RESEARCH)["ok"])
        with patch("scripts.vendor_adapters.live_check.fetch_public_document") as fetch:
            report = run_live_checks(path)
        fetch.assert_not_called()
        self.assertGreater(report["failure_count"], 0)
        self.assertTrue(any("category_url" in row["error"] for row in report["checks"]))

    def test_other_consumer_shapes_fail_closed(self) -> None:
        mutations = {
            "lab urls": lambda profile: profile.__setitem__("lab_index_urls", "https://shop.example/labs"),
            "adapter object": lambda profile: profile.__setitem__("adapter", []),
            "boolean capability": lambda profile: profile["adapter"].__setitem__("product_page_discovery", "true"),
            "strategy identifier": lambda profile: profile["adapter"].__setitem__("parser_strategy", "../../parser"),
            "public hostname": lambda profile: profile.__setitem__("allowed_document_hosts", ["localhost"]),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                payload = self.mutated(mutate)
                self.assertNotEqual(validate_profiles(payload), [])

    def test_non_object_root_is_rejected(self) -> None:
        self.assertEqual(validate_profiles([]), ["vendor profiles root must be an object"])


if __name__ == "__main__":
    unittest.main()
