from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "catalog-v4.yml"
RETIRED_WORKFLOWS = (
    "bootstrap-dropfinder.yml",
    "deploy-pages.yml",
    "dropfinder-ui-publish.yml",
    "pages-branch-fallback.yml",
    "pages-repair.yml",
    "tmp-image-decode-builder.yml",
    "tmp-vape-quantity-builder.yml",
)


class CatalogWorkflowPermissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_catalog_workflow_is_validation_only(self) -> None:
        self.assertIn("permissions:\n  contents: read", self.text)
        self.assertNotIn("contents: write", self.text)
        self.assertNotIn("workflow_run:", self.text)
        self.assertNotIn("jobs:\n  publish:", self.text)
        self.assertNotIn("git push", self.text)
        self.assertNotIn("gh-pages", self.text)

    def test_validation_builds_and_verifies_without_mutating_tracked_data(self) -> None:
        self.assertIn("--input cloud_pages/data/catalog.json", self.text)
        self.assertIn("--output /tmp/dropfinder-catalog-v4", self.text)
        self.assertIn("--verify-only", self.text)
        self.assertIn("actions/upload-artifact@v4", self.text)
        self.assertNotIn("cp -a /tmp/dropfinder-catalog-v4", self.text)

    def test_competing_and_temporary_workflows_are_absent(self) -> None:
        workflow_root = ROOT / ".github" / "workflows"
        for name in RETIRED_WORKFLOWS:
            with self.subTest(workflow=name):
                self.assertFalse((workflow_root / name).exists())

    def test_validation_regression_runs_when_it_changes(self) -> None:
        path_entry = '      - "tests/test_catalog_v4_workflow_permissions.py"'
        self.assertEqual(self.text.count(path_entry), 2)
        self.assertIn(
            "python -m unittest -v tests.test_catalog_v4_workflow_permissions",
            self.text,
        )


if __name__ == "__main__":
    unittest.main()
