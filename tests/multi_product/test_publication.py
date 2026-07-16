from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.multi_product import PSILOCYBIN_MUSHROOM
from scripts.multi_product.publication import self_test


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


if __name__ == "__main__":
    unittest.main()
