from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "dropfinder-cloud.yml"


class DropfinderCloudWorkflowPermissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_is_read_only_while_atomic_publication_is_rebuilt(self) -> None:
        self.assertIn("permissions:\n  contents: read", self.text)
        self.assertNotIn("contents: write", self.text)
        self.assertNotIn("git push", self.text)
        self.assertNotIn("git pull --rebase", self.text)
        self.assertNotIn("gh-pages", self.text)
        self.assertNotIn("jobs:\n  publish:", self.text)

    def test_scheduled_mutation_is_paused(self) -> None:
        self.assertNotIn("schedule:", self.text)
        self.assertIn("workflow_dispatch:", self.text)
        self.assertIn("if: github.event_name == 'workflow_dispatch'", self.text)

    def test_manual_scans_only_upload_bounded_artifacts(self) -> None:
        self.assertIn("name: Manual retrieval worker", self.text)
        self.assertIn("actions/upload-artifact@v4", self.text)
        self.assertIn("retention-days: 1", self.text)
        self.assertNotIn("actions/download-artifact", self.text)

    def test_permission_regression_runs_when_it_changes(self) -> None:
        path_entry = '      - "tests/test_dropfinder_cloud_workflow_permissions.py"'
        self.assertEqual(self.text.count(path_entry), 2)
        self.assertIn(
            "python -m unittest -v tests.test_dropfinder_cloud_workflow_permissions",
            self.text,
        )


if __name__ == "__main__":
    unittest.main()
