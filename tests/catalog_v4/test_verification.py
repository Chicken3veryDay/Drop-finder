from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.catalog_v4 import VerificationError, build_catalog, verify_publication, write_result


class VerificationTests(unittest.TestCase):
    def build(self, root: Path) -> None:
        result = build_catalog(
            [{
                "source_id": "x", "vendor": "X", "source_product_id": "p", "source_variant_id": "v",
                "name": "X THCA Flower 3.5g", "variant": "3.5g", "url": "https://x.example/products/x?variant=v",
                "availability": "in_stock", "price": 20,
            }],
            generated_at="2026-01-01T00:00:00Z",
            detail_shards=1,
        )
        write_result(result, root)

    def test_hash_tampering_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build(root)
            index = root / "catalog-v4" / "index.json"
            index.write_text(index.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(VerificationError, "hash mismatch"):
                verify_publication(root)

    def test_generation_mismatch_fails_even_with_updated_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build(root)
            index_path = root / "catalog-v4" / "index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["generation_id"] = "0" * 32
            index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest_path = root / "catalog-v4" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            import hashlib
            manifest["compact_index"]["sha256"] = hashlib.sha256(index_path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(VerificationError, "schema/generation mismatch"):
                verify_publication(root)


if __name__ == "__main__":
    unittest.main()
