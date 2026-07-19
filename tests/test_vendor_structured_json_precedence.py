from __future__ import annotations

import json
import unittest

from scripts.vendor_adapters.models import DocumentCandidate
from scripts.vendor_adapters.parsers import parse_document, parse_structured_json


class StructuredJsonPrecedenceTests(unittest.TestCase):
    def candidate(self) -> DocumentCandidate:
        return DocumentCandidate(
            vendor_id="example",
            url="https://cdn.example.com/blue-dream.json",
            document_kind="coa",
            product_id="p1",
            variant_id="v-7g",
        )

    def test_structured_result_outranks_marketing_metadata(self) -> None:
        record = parse_structured_json(
            {
                "title": "Blue Dream THCA Flower 30%",
                "results": [
                    {"analyte": "THCA", "result": "27.45%"},
                    {"analyte": "Delta 9 THC", "result": "0.21%"},
                ],
            },
            self.candidate(),
        )
        self.assertEqual(record.cannabinoids["thca"], 27.45)
        self.assertEqual(record.cannabinoids["delta_9_thc"], 0.21)
        self.assertEqual(record.confidence, "high")
        self.assertEqual(record.parser_id, "structured_json_v2")
        self.assertEqual(
            record.field_provenance["cannabinoids.thca"]["source_location"],
            "json_path:$.results[0].result",
        )

    def test_numeric_result_with_separate_percent_unit_is_preserved(self) -> None:
        record = parse_structured_json(
            {"results": [{"analyte": "THCA", "result": 27.45, "unit": "%"}]},
            self.candidate(),
        )
        self.assertEqual(record.cannabinoids["thca"], 27.45)
        self.assertEqual(record.confidence, "high")

    def test_dictionary_property_order_does_not_change_structured_metrics(self) -> None:
        first = {
            "title": "Blue Dream THCA Flower 30%",
            "results": [{"unit": "%", "result": 27.45, "analyte": "THCA"}],
        }
        second = {
            "results": [{"analyte": "THCA", "result": 27.45, "unit": "%"}],
            "title": "Blue Dream THCA Flower 30%",
        }
        left = parse_structured_json(first, self.candidate())
        right = parse_structured_json(second, self.candidate())
        self.assertEqual(left.cannabinoids, right.cannabinoids)
        self.assertEqual(left.field_provenance, right.field_provenance)

    def test_metadata_only_percentage_is_not_promoted_to_structured_lab_evidence(self) -> None:
        record = parse_structured_json(
            {"title": "Blue Dream THCA Flower 30%", "description": "Premium flower"},
            self.candidate(),
        )
        self.assertEqual(record.cannabinoids, {})
        self.assertEqual(record.terpenes, {})
        self.assertEqual(record.parse_status, "partial")
        self.assertEqual(record.confidence, "none")
        self.assertTrue(any("no recognized structured analyte/result rows" in warning for warning in record.warnings))

    def test_conflicting_structured_rows_keep_first_array_row_and_emit_warning(self) -> None:
        record = parse_structured_json(
            {
                "results": [
                    {"analyte": "THCA", "result": "27.45%"},
                    {"analyte": "THCA", "result": "28.00%"},
                ]
            },
            self.candidate(),
        )
        self.assertEqual(record.cannabinoids["thca"], 27.45)
        self.assertTrue(any("conflicting structured value for cannabinoids.thca" in warning for warning in record.warnings))
        self.assertEqual(
            record.field_provenance["cannabinoids.thca"]["source_location"],
            "json_path:$.results[0].result",
        )

    def test_json_content_type_dispatch_uses_structural_precedence(self) -> None:
        payload = json.dumps(
            {
                "title": "Blue Dream THCA Flower 30%",
                "results": [{"analyte": "THCA", "result": "27.45%"}],
            }
        ).encode()
        record = parse_document(payload, "application/json", self.candidate())
        self.assertEqual(record.cannabinoids["thca"], 27.45)
        self.assertEqual(record.parser_id, "structured_json_v2")


if __name__ == "__main__":
    unittest.main()
