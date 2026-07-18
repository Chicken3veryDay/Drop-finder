import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import autonomous_worker as worker


class RouteOverlapResolutionTests(unittest.TestCase):
    def row(self, **overrides):
        row = {
            "source_id": "fixture",
            "vendor": "Fixture",
            "name": "Blue Dream THCA Flower",
            "url": "https://example.com/product/blue-dream",
            "variant": "",
            "availability": "unknown",
            "grams": None,
            "price": 35.0,
            "image": "",
            "source_type": "html_card_product_detail",
            "classification_evidence": {"explicit_thca": True, "explicit_flower": True},
        }
        row.update(overrides)
        return row

    def test_structured_record_wins_over_degraded_fallback_in_either_order(self):
        structured = self.row(
            availability="in_stock",
            grams=3.5,
            image="https://example.com/blue.jpg",
            source_type="woo",
        )
        fallback = self.row()

        for rows in ([structured, fallback], [fallback, structured]):
            with self.subTest(order=[row["source_type"] for row in rows]):
                resolved = worker.resolve_route_overlaps(rows)
                self.assertEqual(1, len(resolved))
                self.assertEqual("woo", resolved[0]["source_type"])
                self.assertEqual("in_stock", resolved[0]["availability"])
                self.assertEqual(3.5, resolved[0]["grams"])
                self.assertEqual("https://example.com/blue.jpg", resolved[0]["image"])

    def test_fallback_only_product_is_preserved(self):
        fallback = self.row(url="https://example.com/product/fallback-only")
        self.assertEqual([fallback], worker.resolve_route_overlaps([fallback]))

    def test_distinct_product_keys_are_not_collapsed(self):
        first = self.row(url="https://example.com/product/one")
        second = self.row(url="https://example.com/product/two")
        resolved = worker.resolve_route_overlaps([first, second])
        self.assertEqual(2, len(resolved))
        self.assertEqual({first["url"], second["url"]}, {row["url"] for row in resolved})


if __name__ == "__main__":
    unittest.main()
