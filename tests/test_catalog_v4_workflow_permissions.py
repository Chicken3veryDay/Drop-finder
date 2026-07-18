from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "catalog-v4.yml"
PUBLISHER_WORKFLOWS = {
    "catalog-v4": ROOT / ".github" / "workflows" / "catalog-v4.yml",
    "autonomous-cloud": ROOT / ".github" / "workflows" / "dropfinder-cloud.yml",
    "artifact-pages": ROOT / ".github" / "workflows" / "deploy-pages.yml",
    "branch-fallback": ROOT / ".github" / "workflows" / "pages-branch-fallback.yml",
    "pages-repair": ROOT / ".github" / "workflows" / "pages-repair.yml",
}


def _block(lines: list[str], header: str, indent: int) -> list[str]:
    marker = f"{' ' * indent}{header}:"
    start = lines.index(marker) + 1
    result: list[str] = []
    for line in lines[start:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        result.append(line)
    return result


def _mapping(lines: list[str], header: str, indent: int) -> dict[str, str]:
    entries: dict[str, str] = {}
    entry_indent = " " * (indent + 2)
    for line in _block(lines, header, indent):
        if not line.startswith(entry_indent) or line.startswith(f"{entry_indent} "):
            continue
        key, separator, value = line.strip().partition(":")
        if separator and value.strip():
            entries[key] = value.strip()
    return entries


class CatalogWorkflowPermissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lines = WORKFLOW.read_text(encoding="utf-8").splitlines()

    def test_validation_inherits_read_only_workflow_permissions(self) -> None:
        self.assertEqual(_mapping(self.lines, "permissions", 0), {"contents": "read"})
        validate = _block(self.lines, "validate", 2)
        self.assertNotIn("    permissions:", validate)

    def test_every_pages_writer_uses_one_repository_wide_lock(self) -> None:
        expected = {
            "group": "dropfinder-pages-publication",
            "cancel-in-progress": "false",
        }
        for name, path in PUBLISHER_WORKFLOWS.items():
            with self.subTest(workflow=name):
                lines = path.read_text(encoding="utf-8").splitlines()
                if name in {"catalog-v4", "autonomous-cloud"}:
                    publish = _block(lines, "publish", 2)
                    actual = _mapping(publish, "concurrency", 4)
                else:
                    actual = _mapping(lines, "concurrency", 0)
                self.assertEqual(actual, expected)

    def test_publishers_refuse_superseded_artifacts(self) -> None:
        required_evidence = {
            "catalog-v4": "Catalog v4 generation was superseded on main; refusing to update gh-pages.",
            "autonomous-cloud": "The production snapshot was superseded on main; refusing to publish stale",
            "artifact-pages": "The Pages artifact was superseded on main; refusing to deploy it.",
            "branch-fallback": "The fallback Pages snapshot was superseded on main; refusing to publish it.",
            "pages-repair": "The Pages repair artifact was superseded on main; refusing to deploy it.",
        }
        for name, path in PUBLISHER_WORKFLOWS.items():
            with self.subTest(workflow=name):
                text = path.read_text(encoding="utf-8")
                self.assertIn(required_evidence[name], text)

    def test_catalog_publish_requires_post_push_manifest_parity(self) -> None:
        publish = _block(self.lines, "publish", 2)
        joined = "\n".join(publish)
        self.assertIn(
            "git show origin/main:cloud_pages/data/catalog-v4/manifest.json",
            joined,
        )
        self.assertIn(
            "Catalog v4 publication completed without main/gh-pages manifest parity.",
            joined,
        )

    def test_only_publish_job_receives_repository_write_access(self) -> None:
        publish = _block(self.lines, "publish", 2)
        self.assertEqual(_mapping(publish, "permissions", 4), {"contents": "write"})
        self.assertEqual(
            [line for line in self.lines if line.strip() == "contents: write"],
            ["      contents: write"],
        )


if __name__ == "__main__":
    unittest.main()
