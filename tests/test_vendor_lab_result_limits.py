from __future__ import annotations

import unittest

from scripts.vendor_adapters.models import DocumentCandidate
from scripts.vendor_adapters.parsers import parse_lab_text, parse_structured_html


CANDIDATE = DocumentCandidate(
    vendor_id="example",
    url="https://cdn.example.com/report.pdf",
    document_kind="coa",
)


class LabResultLimitTests(unittest.TestCase):
    def test_result_before_loq_keeps_the_measured_value(self):
        record = parse_lab_text("THCA 27.45% LOQ 0.10%", CANDIDATE)
        self.assertEqual(record.cannabinoids["thca"], 27.45)
        self.assertEqual(record.field_provenance["cannabinoids.thca"]["raw"], "THCA 27.45% LOQ 0.10%")

    def test_explicit_result_after_limit_wins(self):
        record = parse_lab_text("THCA LOQ 0.10% Result 27.45%", CANDIDATE)
        self.assertEqual(record.cannabinoids["thca"], 27.45)

    def test_action_limit_and_reporting_limit_do_not_replace_results(self):
        cannabinoid = parse_lab_text("Delta-9 THC Result 0.21% Action Limit 0.30%", CANDIDATE)
        terpene = parse_lab_text("Myrcene 1.42% Reporting Limit 0.05%", CANDIDATE)
        self.assertEqual(cannabinoid.cannabinoids["delta_9_thc"], 0.21)
        self.assertEqual(terpene.terpenes["myrcene"], 1.42)

    def test_uncertainty_percentage_does_not_replace_result(self):
        record = parse_lab_text("THCA Result 27.45% Uncertainty 0.50%", CANDIDATE)
        self.assertEqual(record.cannabinoids["thca"], 27.45)

    def test_limit_only_row_is_not_published_as_a_measurement(self):
        record = parse_lab_text("THCA LOQ 0.10%", CANDIDATE)
        self.assertNotIn("thca", record.cannabinoids)
        self.assertTrue(any("limit-only analyte row" in warning for warning in record.warnings))
        self.assertEqual(record.confidence, "none")

    def test_unlabeled_multi_percentage_row_is_not_guessed(self):
        record = parse_lab_text("THCA 27.45% 0.10%", CANDIDATE)
        self.assertNotIn("thca", record.cannabinoids)
        self.assertTrue(any("ambiguous analyte row" in warning for warning in record.warnings))

    def test_single_percentage_rows_remain_supported(self):
        record = parse_lab_text("THCA 27.45%", CANDIDATE)
        self.assertEqual(record.cannabinoids["thca"], 27.45)
        self.assertFalse(any("ambiguous" in warning for warning in record.warnings))

    def test_structured_html_uses_the_same_result_semantics(self):
        record = parse_structured_html(
            "<table><tr><td>THCA</td><td>27.45%</td><td>LOQ</td><td>0.10%</td></tr></table>",
            CANDIDATE,
        )
        self.assertEqual(record.cannabinoids["thca"], 27.45)


if __name__ == "__main__":
    unittest.main()
