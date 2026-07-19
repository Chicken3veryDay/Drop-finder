from __future__ import annotations

from contextlib import contextmanager
import unittest

import scripts.autonomous_worker_v2 as worker_v2


@contextmanager
def patched(obj, **values):
    original = {name: getattr(obj, name) for name in values}
    try:
        for name, value in values.items():
            setattr(obj, name, value)
        yield
    finally:
        for name, value in original.items():
            setattr(obj, name, value)


ROUTE = ("html", "https://example.test/flower", "thca_flower")


class CardCandidateOwnershipTests(unittest.TestCase):
    def test_adjacent_cards_do_not_share_price_or_stock(self):
        payload = """
        <div class="card">
          <a href="/products/alpha-thca-flower">Alpha THCA Flower</a>
        </div>
        <div class="card">
          <a href="/products/beta-thca-flower">Beta THCA Flower</a>
          <span>$99.00</span><span>Out of stock</span>
        </div>
        """
        rows = worker_v2.scored_card_candidates(payload, ROUTE)
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(set(by_name), {"Alpha THCA Flower", "Beta THCA Flower"})
        for row in by_name.values():
            self.assertIsNone(row["price"])
            self.assertEqual(row["stock"], "")

    def test_opposing_sibling_stock_tokens_do_not_change_candidates(self):
        payload = """
        <article><a href="/products/alpha-thca-flower">Alpha THCA Flower</a><span>In stock</span></article>
        <article><a href="/products/beta-thca-flower">Beta THCA Flower</a><span>Out of stock</span></article>
        """
        rows = worker_v2.scored_card_candidates(payload, ROUTE)
        self.assertEqual([row["stock"] for row in rows], ["", ""])

    def test_repeated_anchors_keep_the_most_descriptive_title(self):
        payload = """
        <a href="/products/alpha-thca-flower">Product</a>
        <a href="/products/alpha-thca-flower">Alpha THCA Flower Indoor</a>
        <span>$88.00</span>
        """
        rows = worker_v2.scored_card_candidates(payload, ROUTE)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Alpha THCA Flower Indoor")
        self.assertIsNone(rows[0]["price"])

    def test_detail_conversion_never_falls_back_to_card_price_or_stock(self):
        captured = {}

        def record(source_id, vendor, route, title, target, evidence, price, stock, image=""):
            captured.update(price=price, stock=stock, target=target, title=title)
            return {"source_id": source_id, "vendor": vendor, "url": target}

        candidate = {
            "name": "Alpha THCA Flower",
            "url": "https://example.test/products/alpha-thca-flower",
            "price": 99,
            "stock": "in_stock",
        }
        with patched(
            worker_v2.worker.core,
            fetch=lambda _url: ("<html>Alpha THCA Flower</html>", "text/html", 200),
            meta_values=lambda _payload: {"og:title": "Alpha THCA Flower"},
            record=record,
        ), patched(
            worker_v2.worker,
            product_detail_evidence=lambda _payload, _target: "alpha thca flower",
            has_product_evidence=lambda _value: True,
            decorate=lambda row, _evidence, _source: row,
        ):
            row = worker_v2.descriptive_candidate_to_row(candidate, "example", "Example")

        self.assertIsNotNone(row)
        self.assertIsNone(captured["price"])
        self.assertIsNone(captured["stock"])

    def test_own_detail_metadata_remains_authoritative(self):
        captured = {}

        def record(source_id, vendor, route, title, target, evidence, price, stock, image=""):
            captured.update(price=price, stock=stock, image=image)
            return {"source_id": source_id, "vendor": vendor, "url": target}

        candidate = {
            "name": "Alpha THCA Flower",
            "url": "https://example.test/products/alpha-thca-flower",
            "price": 999,
            "stock": "out_of_stock",
        }
        with patched(
            worker_v2.worker.core,
            fetch=lambda _url: ("<html>Alpha THCA Flower</html>", "text/html", 200),
            meta_values=lambda _payload: {
                "og:title": "Alpha THCA Flower",
                "product:price:amount": "42.00",
                "product:availability": "in stock",
                "og:image": "https://example.test/alpha.jpg",
            },
            record=record,
        ), patched(
            worker_v2.worker,
            product_detail_evidence=lambda _payload, _target: "alpha thca flower",
            has_product_evidence=lambda _value: True,
            decorate=lambda row, _evidence, _source: row,
        ):
            row = worker_v2.descriptive_candidate_to_row(candidate, "example", "Example")

        self.assertIsNotNone(row)
        self.assertEqual(captured["price"], "42.00")
        self.assertEqual(captured["stock"], "in stock")
        self.assertEqual(captured["image"], "https://example.test/alpha.jpg")


if __name__ == "__main__":
    unittest.main()
