from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VendorDocumentPublicationWorkflowTests(unittest.TestCase):
    def test_catalog_validation_uses_verified_offline_artifact(self) -> None:
        workflow = (ROOT / ".github/workflows/catalog-v4.yml").read_text(encoding="utf-8")
        self.assertIn("scripts.vendor_adapters.publication generate", workflow)
        self.assertIn("--offline", workflow)
        self.assertIn("scripts.vendor_adapters.publication verify", workflow)
        self.assertIn("--documents /tmp/dropfinder-vendor-documents.json", workflow)
        self.assertIn("--vendor-profiles data/vendor_profiles.json", workflow)
        self.assertIn("--vendor-expansion data/vendor_expansion.json", workflow)
        self.assertIn("/tmp/dropfinder-vendor-documents.json", workflow)

    def test_scheduled_publication_generates_and_reverifies_live_artifact(self) -> None:
        workflow = (ROOT / ".github/workflows/dropfinder-cloud.yml").read_text(encoding="utf-8")
        self.assertIn("scripts.vendor_adapters.publication generate", workflow)
        self.assertIn("scripts.vendor_adapters.publication verify", workflow)
        self.assertIn("--documents /tmp/dropfinder-generated-data/vendor-document-artifact.json", workflow)
        self.assertIn("/tmp/dropfinder-candidate/data/vendor-document-artifact.json", workflow)
        self.assertIn("/tmp/dropfinder-pages/data/vendor-document-artifact.json", workflow)
        self.assertIn("--max-product-pages-per-vendor 4", workflow)


if __name__ == "__main__":
    unittest.main()
