from __future__ import annotations

import unittest

from scripts.vendor_adapters.annotate import annotate_products
from scripts.vendor_adapters.mapping import map_documents, score_candidate
from scripts.vendor_adapters.models import DocumentCandidate


class MappingConflictTests(unittest.TestCase):
    def setUp(self) -> None:
        self.product = {
            "id": "p1",
            "source_id": "v",
            "name": "Blue Dream THCA Flower",
            "variant_id": "v7",
            "batch_id": "B1",
            "grams": 7.0,
        }
        self.candidate = DocumentCandidate(
            "v",
            "https://v.example/a.pdf",
            "coa",
            product_id="p1",
            variant_id="v7",
            batch_id="B1",
            weight_grams=7.0,
        )

    def test_explicit_scope_conflicts_are_unmatched(self) -> None:
        cases = (
            ("product id conflict", {"id": "p2"}),
            ("variant id conflict", {"variant_id": "v14"}),
            ("batch id conflict", {"batch_id": "B2"}),
            ("weight conflict", {"grams": 14.0}),
        )
        for expected_reason, changes in cases:
            with self.subTest(expected_reason=expected_reason):
                product = {**self.product, **changes}
                decision = score_candidate(product, self.candidate)
                self.assertEqual(decision.scope, "unmatched")
                self.assertLess(decision.score, 0)
                self.assertEqual(decision.reasons, (expected_reason,))
                self.assertEqual(map_documents([product], [self.candidate]), [])

    def test_variant_label_conflict_is_rejected_without_ids(self) -> None:
        product = {
            "id": "p1",
            "source_id": "v",
            "name": "Blue Dream THCA Flower",
            "variant_label": "7 gram jar",
        }
        candidate = DocumentCandidate(
            "v",
            "https://v.example/label.pdf",
            "coa",
            product_id="p1",
            variant_label="14 gram jar",
        )
        decision = score_candidate(product, candidate)
        self.assertEqual(decision.scope, "unmatched")
        self.assertEqual(decision.reasons, ("variant label conflict",))

    def test_missing_narrow_scope_allows_product_fallback(self) -> None:
        candidate = DocumentCandidate(
            "v",
            "https://v.example/product.pdf",
            "coa",
            product_id="p1",
        )
        decision = score_candidate(self.product, candidate)
        self.assertEqual(decision.scope, "product")
        self.assertIn("exact product id", decision.reasons)
        self.assertEqual(
            map_documents([self.product], [candidate])[0].document_id,
            candidate.document_id,
        )

    def test_scope_precedence_is_variant_batch_weight_product(self) -> None:
        candidates = {
            "product": DocumentCandidate(
                "v", "https://v.example/product.pdf", "coa", product_id="p1"
            ),
            "weight": DocumentCandidate(
                "v", "https://v.example/weight.pdf", "coa", weight_grams=7
            ),
            "batch": DocumentCandidate(
                "v", "https://v.example/batch.pdf", "coa", batch_id="B1"
            ),
            "variant": DocumentCandidate(
                "v", "https://v.example/variant.pdf", "coa", variant_id="v7"
            ),
        }
        scored = {
            scope: score_candidate(self.product, candidate)
            for scope, candidate in candidates.items()
        }
        self.assertGreater(scored["variant"].score, scored["batch"].score)
        self.assertGreater(scored["batch"].score, scored["weight"].score)
        self.assertGreater(scored["weight"].score, scored["product"].score)
        for scope, decision in scored.items():
            self.assertEqual(decision.scope, scope)
        selected = map_documents([self.product], list(candidates.values()))[0]
        self.assertEqual(selected.document_id, candidates["variant"].document_id)

    def test_matching_candidate_wins_and_conflict_is_excluded(self) -> None:
        conflicting = DocumentCandidate(
            "v",
            "https://v.example/conflicting.pdf",
            "coa",
            product_id="p1",
            variant_id="v14",
            batch_id="B2",
            weight_grams=14,
        )
        decision = map_documents([self.product], [conflicting, self.candidate])[0]
        self.assertEqual(decision.document_id, self.candidate.document_id)
        self.assertFalse(decision.ambiguous)

    def test_conflicting_candidate_is_not_annotated(self) -> None:
        product = {
            **self.product,
            "variant_id": "v14",
            "batch_id": "B2",
            "grams": 14,
        }
        output = annotate_products([product], [self.candidate], [])
        self.assertEqual(output[0]["lab_evidence"]["mapping_scope"], "unmatched")
        self.assertEqual(output[0]["lab_evidence"]["document_id"], "")


if __name__ == "__main__":
    unittest.main()
