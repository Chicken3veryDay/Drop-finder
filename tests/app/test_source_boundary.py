from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from app.adapters.registry import AdapterRegistry
from app.reliability.contracts import AdapterState, StrategyType
from app.reliability.store import ReliabilityStore

ROOT = Path(__file__).resolve().parents[2]


class ReliabilityStoreTests(unittest.TestCase):
    def test_registry_versions_and_persists_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reliability.sqlite3"
            with ReliabilityStore(path) as store:
                registry = AdapterRegistry(store)
                first = registry.create(
                    source_id="fixture",
                    route_id="primary",
                    strategy_type=StrategyType.JSON_ENDPOINT,
                    config={"source_url": "https://example.test/products.json"},
                )
                second = registry.create(
                    source_id="fixture",
                    route_id="primary",
                    strategy_type=StrategyType.JSON_ENDPOINT,
                    config={"source_url": "https://example.test/products-v2.json"},
                    parent_adapter_id=first.adapter_id,
                )
                self.assertEqual((first.version, second.version), (1, 2))
                self.assertEqual([row["version"] for row in store.list_adapters("fixture", "primary")], [1, 2])
                activated = store.update_adapter_state(second.adapter_id, AdapterState.ACTIVE)
                self.assertEqual(activated.state, AdapterState.ACTIVE)

            with ReliabilityStore(path) as reopened:
                restored = reopened.get_adapter(second.adapter_id)
                self.assertIsNotNone(restored)
                self.assertEqual(restored.state, AdapterState.ACTIVE)
                self.assertEqual(restored.content_sha256, second.content_sha256)

    def test_duplicate_adapter_identity_fails_on_changed_content(self) -> None:
        with ReliabilityStore() as store:
            registry = AdapterRegistry(store)
            adapter = registry.create(
                source_id="fixture",
                route_id="primary",
                strategy_type=StrategyType.HTML_CARDS,
                config={"source_url": "https://example.test/flower"},
            )
            changed = adapter.model_copy(update={"config": {"source_url": "https://example.test/other"}})
            with self.assertRaisesRegex(ValueError, "already exists"):
                store.register_adapter(changed)


class SourceBoundaryVerifierTests(unittest.TestCase):
    def test_clean_checkout_source_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "receipt.json"
            subprocess.run(
                [sys.executable, "scripts/verify_source_boundary.py", "--output", str(receipt)],
                cwd=ROOT,
                check=True,
                text=True,
            )
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "dropfinder-tracked-source-boundary-v1")
            self.assertEqual(payload["missing_first_party_modules"], [])
            self.assertEqual(payload["obsolete_bootstrap_inputs"], [])
            self.assertIn("app.reliability.store", payload["imported_modules"])


if __name__ == "__main__":
    unittest.main()
