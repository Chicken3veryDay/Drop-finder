from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.vendor_adapters.annotate import annotate_products
from scripts.vendor_adapters.coverage import source_ids_from_python, verify_coverage
from scripts.vendor_adapters.discovery import discover_html_documents, discover_json_documents
from scripts.vendor_adapters.mapping import map_documents, score_candidate
from scripts.vendor_adapters.models import DocumentCandidate, ParsedLabRecord, Provenance, stable_document_id
from scripts.vendor_adapters.parsers import parse_document, parse_pdf, parse_structured_html, parse_structured_json
from scripts.vendor_adapters.registry import VendorRegistry, validate_profiles
from scripts.vendor_adapters.urls import UnsafeUrl, canonicalize_url

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "vendor_adapters"
PROFILES = ROOT / "data" / "vendor_profiles.json"
SOURCES = ROOT / "scripts" / "cloud_scan.py"
RESEARCH = ROOT / "research" / "vendors"


class UrlSafetyTests(unittest.TestCase):
    def test_canonicalizes_and_removes_tracking(self):
        value = canonicalize_url(
            "HTTPS://Example.COM:443/a/../reports/coa.pdf?utm_source=x&batch=2&batch=1#frag",
            allowed_hosts={"example.com"},
        )
        self.assertEqual(value, "https://example.com/reports/coa.pdf?batch=1&batch=2")

    def test_rejects_private_and_local_targets(self):
        for value in ("http://127.0.0.1/a", "http://169.254.169.254/latest", "http://localhost/a", "file:///tmp/a"):
            with self.subTest(value=value), self.assertRaises(UnsafeUrl):
                canonicalize_url(value)

    def test_allows_declared_cdn_subdomain_only(self):
        self.assertEqual(
            canonicalize_url("https://assets.cdn.example.com/a.pdf", allowed_hosts={"cdn.example.com"}),
            "https://assets.cdn.example.com/a.pdf",
        )
        with self.assertRaises(UnsafeUrl):
            canonicalize_url("https://evil.example.net/a.pdf", allowed_hosts={"cdn.example.com"})


class DiscoveryTests(unittest.TestCase):
    def test_html_discovery_is_deduplicated_and_safe(self):
        html = '''<a href="/files/a.pdf?utm_source=x">Blue Dream COA batch BD-1 7g</a>
        <a href="/files/a.pdf">duplicate certificate</a><a href="http://127.0.0.1/a.pdf">lab report</a>'''
        rows = discover_html_documents(
            html, vendor_id="v", page_url="https://vendor.example/products/blue-dream",
            allowed_hosts={"vendor.example"}, observed_at="2026-07-15T00:00:00Z", product_id="p1",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].batch_id, "BD-1")
        self.assertEqual(rows[0].weight_grams, 7.0)
        self.assertEqual(rows[0].url, "https://vendor.example/files/a.pdf")

    def test_json_discovery_preserves_product_variant_batch(self):
        payload = (FIXTURES / "structured_api.json").read_text()
        rows = discover_json_documents(
            payload, vendor_id="v", source_url="https://shop.example/api/products",
            allowed_hosts={"shop.example", "cdn.example.com"}, observed_at="2026-07-15T00:00:00Z",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].product_id, "p1")
        self.assertEqual(rows[0].variant_id, "v-7g")
        self.assertEqual(rows[0].batch_id, "BD-2026-07")
        self.assertNotIn("utm_source", rows[0].url)


class ParserTests(unittest.TestCase):
    def setUp(self):
        raw = json.loads((FIXTURES / "candidate.json").read_text())
        raw["provenance"] = Provenance(**raw["provenance"])
        self.candidate = DocumentCandidate(**raw)

    def test_structured_html_parser(self):
        record = parse_structured_html((FIXTURES / "lab_table.html").read_text(), self.candidate)
        self.assertEqual(record.parse_status, "parsed")
        self.assertEqual(record.cannabinoids["thca"], 27.45)
        self.assertEqual(record.cannabinoids["delta_9_thc"], 0.21)
        self.assertEqual(record.terpenes["myrcene"], 0.82)
        self.assertEqual(record.total_terpenes, 2.10)

    def test_structured_json_parser(self):
        record = parse_structured_json((FIXTURES / "structured_api.json").read_text(), self.candidate)
        self.assertEqual(record.cannabinoids["thca"], 27.45)
        self.assertEqual(record.terpenes["myrcene"], 0.82)

    def test_text_pdf_parser(self):
        record = parse_pdf((FIXTURES / "text_coa.pdf").read_bytes(), self.candidate)
        self.assertEqual(record.parse_status, "parsed")
        self.assertEqual(record.batch_id, "BD-2026-07")
        self.assertEqual(record.cannabinoids["thca"], 27.45)

    def test_scanned_pdf_is_explicitly_unsupported(self):
        record = parse_pdf((FIXTURES / "scanned_stub.pdf").read_bytes(), self.candidate)
        self.assertIn(record.parse_status, {"unsupported_scanned", "unsupported_format"})
        self.assertFalse(record.cannabinoids)

    def test_direct_total_thc_is_distinct_from_delta_9(self):
        record = parse_structured_html(
            "<table><tr><td>Total THC</td><td>24.31%</td></tr><tr><td>Delta 9 THC</td><td>0.19%</td></tr></table>",
            self.candidate,
        )
        self.assertEqual(record.cannabinoids["total_thc"], 24.31)
        self.assertEqual(record.cannabinoids["delta_9_thc"], 0.19)

    def test_impossible_percentages_are_rejected_with_warning(self):
        record = parse_structured_html(
            "<table><tr><td>THCA</td><td>150%</td></tr><tr><td>Myrcene</td><td>-2%</td></tr></table>",
            self.candidate,
        )
        self.assertNotIn("thca", record.cannabinoids)
        self.assertNotIn("myrcene", record.terpenes)
        self.assertTrue(any("impossible percentage" in item for item in record.limitations))

    def test_stable_document_ids_ignore_timestamps(self):
        first = stable_document_id("v", "https://x/a.pdf", "coa", "p", "v1", "b1")
        second = stable_document_id("v", "https://x/a.pdf", "coa", "p", "v1", "b1")
        self.assertEqual(first, second)


class MappingTests(unittest.TestCase):
    def test_exact_variant_and_batch_outweigh_product_name(self):
        candidate = DocumentCandidate("v", "https://v.example/a.pdf", "coa", "Blue Dream", product_id="p1", variant_id="v7", batch_id="B1")
        product = {"id": "p1", "source_id": "v", "name": "Blue Dream THCA Flower", "variant_id": "v7", "batch_id": "B1", "grams": 7}
        decision = score_candidate(product, candidate)
        self.assertGreaterEqual(decision.score, 350)
        self.assertIn(decision.scope, {"variant", "batch"})

    def test_equal_best_scores_remain_ambiguous(self):
        product = {"id": "p1", "source_id": "v", "name": "Blue Dream THCA Flower"}
        candidates = [
            DocumentCandidate("v", "https://v.example/a.pdf", "coa", "Blue Dream THCA Flower"),
            DocumentCandidate("v", "https://v.example/b.pdf", "coa", "Blue Dream THCA Flower"),
        ]
        decisions = map_documents([product], candidates)
        self.assertTrue(decisions[0].ambiguous)
        self.assertEqual(decisions[0].document_id, min(item.document_id for item in candidates))

    def test_missing_lab_data_does_not_remove_product(self):
        products = [{"id": "p1", "source_id": "crysp", "name": "Blue Dream THCA Flower", "price": 20}]
        profiles = {"crysp": {"verified_at": "x", "age_verification": {"classification": "uncertain"}, "labs": {"coa_availability": "partial", "terpene_availability": "uncertain"}}}
        output = annotate_products(products, [], [], profiles)
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["lab_evidence"]["parse_status"], "unavailable")
        self.assertEqual(output[0]["price"], 20)


class CoverageTests(unittest.TestCase):
    def test_profiles_cover_every_configured_source_and_reports(self):
        result = verify_coverage(PROFILES, SOURCES, RESEARCH)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["source_count"], 17)
        self.assertEqual(result["profile_count"], 17)
        self.assertEqual(result["research_count"], 17)

    def test_coverage_fails_when_new_source_is_unprofiled(self):
        source = SOURCES.read_text()
        source = source.replace("SOURCES=[", "SOURCES=[\n('new_vendor','New Vendor',[]),", 1)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cloud_scan.py"
            path.write_text(source)
            result = verify_coverage(PROFILES, path, RESEARCH)
        self.assertFalse(result["ok"])
        self.assertIn("new_vendor", result["missing_profiles"])

    def test_registry_loads_every_profile(self):
        registry = VendorRegistry.from_profiles(PROFILES)
        self.assertEqual(len(registry.all()), 17)
        self.assertEqual(registry.get("secret_nature").discovery_strategy, "central_index_named_documents")

    def test_profile_schema_and_age_integrity(self):
        payload = json.loads(PROFILES.read_text())
        self.assertEqual(validate_profiles(payload), [])
        identity = [p for p in payload["vendors"] if p["age_verification"]["classification"].startswith("identity_verification")]
        self.assertEqual(identity, [], "no vendor may be labeled identity verification without direct evidence")

    def test_machine_readable_profile_contract_uses_issue_enums(self):
        payload = json.loads(PROFILES.read_text())
        allowed_age = {
            "identity_verification_required", "identity_verification_conditional",
            "self_attestation_21_plus", "no_observed_gate", "uncertain",
        }
        allowed_evidence = {"current", "conflicting", "inaccessible", "stale"}
        for profile in payload["vendors"]:
            self.assertIn(profile["age_verification"]["classification"], allowed_age)
            self.assertTrue(profile["verified_at"])
            for evidence in profile["evidence"]:
                self.assertIn(evidence["status"], allowed_evidence)

    def test_public_artifacts_do_not_leak_private_paths(self):
        patterns = ("/mnt/data", "C:\\Users\\", "file://", "127.0.0.1", "169.254.169.254")
        files = [PROFILES, ROOT / "docs" / "VENDOR_AGE_VERIFICATION.md", ROOT / "docs" / "VENDOR_LAB_COVERAGE.md", *RESEARCH.glob("*.md")]
        for path in files:
            text = path.read_text(encoding="utf-8")
            for pattern in patterns:
                with self.subTest(path=path, pattern=pattern):
                    self.assertNotIn(pattern, text)


if __name__ == "__main__":
    unittest.main()
