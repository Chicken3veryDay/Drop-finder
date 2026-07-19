from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.catalog_v4 import build_catalog
from scripts.vendor_adapters.publication_artifact import build_artifact, verify_artifact

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "data" / "vendor_profiles.json"
SOURCES = ROOT / "data" / "vendor_document_sources.json"
CATALOG = ROOT / "cloud_pages" / "data" / "catalog.json"
WORKFLOW = ROOT / ".github" / "workflows" / "catalog-v4.yml"


def source_payload(*documents: dict) -> dict:
    return {
        "schema_version": "dropfinder-vendor-document-sources-v1",
        "generated_at": "2026-07-19T00:00:00Z",
        "sources": [{
            "vendor_id": "lucky_elk",
            "source_page": "https://luckyelk.com/pages/coa-tests",
            "observed_at": "2026-07-19T00:00:00Z",
            "documents": list(documents),
        }],
    }


def coa(label: str, slug: str) -> dict:
    return {
        "kind": "coa",
        "label": label,
        "mime_type": "image/webp",
        "public_url": f"https://luckyelk.com/cdn/shop/files/{slug}.webp",
    }


def catalog_record() -> dict:
    return {
        "generated_at": "2026-07-19T00:00:00Z",
        "products": [{
            "source_id": "lucky_elk",
            "vendor": "Lucky Elk",
            "source_product_id": "candy-runtz",
            "source_variant_id": "candy-runtz-3.5",
            "source_title": "Candy Runtz THCA Flower",
            "name": "Candy Runtz THCA Flower",
            "variant": "3.5g",
            "url": "https://luckyelk.com/products/candy-runtz?variant=candy-runtz-3.5",
            "availability": "in_stock",
            "price": 25,
        }],
    }


class VendorDocumentPublicationTests(unittest.TestCase):
    def test_unique_exact_label_maps_and_unknown_label_remains_unmatched(self) -> None:
        artifact = build_artifact(
            catalog_record(),
            PROFILES,
            source_payload(
                coa("Candy Runtz", "candy-runtz"),
                coa("Archived Report", "archived-report"),
            ),
        )
        self.assertEqual(artifact["counts"], {
            "source_documents": 2,
            "mapped_documents": 1,
            "unmatched_documents": 1,
            "vendors": 1,
        })
        mapped = artifact["documents"][0]
        self.assertEqual(mapped["source_product_id"], "candy-runtz")
        self.assertEqual(mapped["scope"], "product")
        self.assertEqual(mapped["provenance"]["method"], "unique_exact_normalized_product_label")
        self.assertEqual(artifact["unmatched_documents"][0]["reason"], "no_exact_catalog_product")
        self.assertEqual(verify_artifact(artifact)["source_documents"], 2)

    def test_ambiguous_exact_label_is_not_guessed(self) -> None:
        catalog = catalog_record()
        duplicate = dict(catalog["products"][0])
        duplicate.update(
            source_product_id="candy-runtz-second",
            source_variant_id="candy-runtz-second-3.5",
            url="https://luckyelk.com/products/candy-runtz-second?variant=3.5",
        )
        catalog["products"].append(duplicate)
        artifact = build_artifact(catalog, PROFILES, source_payload(coa("Candy Runtz", "candy-runtz")))
        self.assertEqual(artifact["documents"], [])
        self.assertEqual(artifact["unmatched_documents"][0]["reason"], "ambiguous_exact_catalog_product")

    def test_mapped_artifact_attaches_to_catalog_v4_detail(self) -> None:
        catalog = catalog_record()
        artifact = build_artifact(catalog, PROFILES, source_payload(coa("Candy Runtz", "candy-runtz")))
        result = build_catalog(
            catalog["products"],
            generated_at=catalog["generated_at"],
            document_records=artifact["documents"],
            detail_shards=1,
        )
        detail = json.loads(result.files["catalog-v4/details/000.json"])
        documents = detail["products"][0]["variants"][0]["documents"]
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["kind"], "coa")
        self.assertEqual(documents[0]["scope"], "product")
        self.assertEqual(documents[0]["discovered_label"], "Candy Runtz")

    def test_checked_in_sources_are_all_accounted_for_without_guessing(self) -> None:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        sources = json.loads(SOURCES.read_text(encoding="utf-8"))
        artifact = build_artifact(catalog, PROFILES, sources)
        summary = verify_artifact(artifact)
        self.assertEqual(summary["source_documents"], 8)
        self.assertEqual(summary["mapped_documents"] + summary["unmatched_documents"], 8)
        self.assertEqual(
            {row["vendor_id"] for row in artifact["documents"] + artifact["unmatched_documents"]},
            {"lucky_elk"},
        )
        for row in artifact["documents"]:
            self.assertEqual(row["provenance"]["method"], "unique_exact_normalized_product_label")

    def test_catalog_workflow_generates_verifies_and_supplies_document_artifact(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("scripts.vendor_adapters.publication_artifact", workflow)
        self.assertIn("--sources data/vendor_document_sources.json", workflow)
        self.assertIn("--documents /tmp/vendor-documents.json", workflow)
        self.assertIn("--verify-only", workflow)
        self.assertIn("/tmp/vendor-documents.json", workflow)

    def test_artifact_verifier_rejects_unaccounted_source_documents(self) -> None:
        artifact = build_artifact(catalog_record(), PROFILES, source_payload(coa("Candy Runtz", "candy-runtz")))
        artifact["counts"]["source_documents"] += 1
        with self.assertRaisesRegex(ValueError, "does not account"):
            verify_artifact(artifact)


if __name__ == "__main__":
    unittest.main()
