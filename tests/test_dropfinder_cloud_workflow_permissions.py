from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "dropfinder-cloud.yml"


class DropfinderCloudWorkflowPermissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_only_atomic_publish_job_receives_write_access(self) -> None:
        self.assertIn("permissions:\n  contents: read", self.text)
        self.assertEqual(self.text.count("contents: write"), 1)
        self.assertIn("  publish:\n    name: Atomic generation and Pages publication", self.text)
        self.assertIn("    permissions:\n      contents: write", self.text)
        self.assertIn("group: dropfinder-pages-publication", self.text)
        self.assertIn("cancel-in-progress: false", self.text)

    def test_every_release_artifact_is_owned_by_one_immutable_source(self) -> None:
        self.assertIn("ref: ${{ github.sha }}", self.text)
        self.assertIn("stamp-shard", self.text)
        self.assertIn("verify-shards scan-results", self.text)
        self.assertIn('--expected-commit "${GITHUB_SHA}"', self.text)
        self.assertIn("Main advanced after this run started; fresh scans are required.", self.text)
        self.assertIn("refusing to rebase generated output", self.text)
        self.assertNotIn("git pull --rebase", self.text)
        self.assertNotIn("git push --force", self.text)
        self.assertNotIn("workflow_run:", self.text)
        self.assertNotIn("issues:", self.text)

    def test_legacy_and_v4_are_built_and_validated_as_one_candidate(self) -> None:
        self.assertIn("Build one coupled legacy and catalog-v4 candidate", self.text)
        self.assertIn("python scripts/autonomous_merge.py", self.text)
        self.assertIn("python -m scripts.catalog_v4", self.text)
        self.assertIn("check-continuity", self.text)
        self.assertIn("/tmp/dropfinder-candidate", self.text)
        self.assertIn("--previous /tmp/dropfinder-previous", self.text)

    def test_publication_is_fast_forward_and_receipted(self) -> None:
        self.assertIn("git -C /tmp/dropfinder-pages push origin HEAD:gh-pages", self.text)
        self.assertIn("record-receipt /tmp/dropfinder-pages", self.text)
        self.assertIn("deployment/release.json", self.text)
        self.assertIn("atomic-publication-evidence-${{ github.run_id }}", self.text)
        self.assertIn("retention-days: 90", self.text)

    def test_schedule_and_override_are_explicit(self) -> None:
        self.assertIn('cron: "23 */3 * * *"', self.text)
        self.assertIn("continuity_override_reason:", self.text)
        self.assertIn('--override-reason "${OVERRIDE_REASON}"', self.text)
        self.assertNotIn("allow_large_drop", self.text)

    def test_permission_regression_runs_when_it_changes(self) -> None:
        path_entry = '      - "tests/test_dropfinder_cloud_workflow_permissions.py"'
        self.assertEqual(self.text.count(path_entry), 2)
        self.assertIn("tests.test_dropfinder_cloud_workflow_permissions", self.text)
        self.assertIn("tests.test_publication_release", self.text)
        self.assertIn("scripts/route_repair.py scripts/source_recovery.py scripts/vendor_expansion.py", self.text)
        self.assertIn("tests.catalog_v4.test_route_repair", self.text)
        self.assertIn("tests.catalog_v4.test_source_recovery", self.text)

    def test_release_owner_changes_trigger_push_publication(self) -> None:
        push_block = self.text.split("  push:\n", 1)[1].split("  pull_request:\n", 1)[0]
        self.assertIn("    branches: [main]", push_block)
        for path in (
            '      - ".github/workflows/dropfinder-cloud.yml"',
            '      - "tests/test_dropfinder_cloud_workflow_permissions.py"',
            '      - "scripts/publication_release.py"',
            '      - "scripts/route_repair.py"',
            '      - "scripts/source_recovery.py"',
            '      - "scripts/vendor_expansion.py"',
            '      - "web/**"',
        ):
            self.assertIn(path, push_block)

    def test_release_actions_are_immutably_pinned(self) -> None:
        expected = {
            "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5": 4,
            "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065": 3,
            "actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020": 2,
            "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02": 2,
            "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093": 1,
        }
        for action, count in expected.items():
            self.assertEqual(self.text.count(action), count, action)
        for mutable in (
            "actions/checkout@v4",
            "actions/setup-python@v5",
            "actions/setup-node@v4",
            "actions/upload-artifact@v4",
            "actions/download-artifact@v4",
        ):
            self.assertNotIn(mutable, self.text)


if __name__ == "__main__":
    unittest.main()
