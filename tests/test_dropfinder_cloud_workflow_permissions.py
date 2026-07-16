from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "dropfinder-cloud.yml"


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


class DropfinderCloudWorkflowPermissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lines = WORKFLOW.read_text(encoding="utf-8").splitlines()

    def test_non_publishing_jobs_inherit_read_only_repository_access(self) -> None:
        self.assertEqual(_mapping(self.lines, "permissions", 0), {"contents": "read"})
        for job in ("python-validation", "frontend", "scan"):
            self.assertNotIn("    permissions:", _block(self.lines, job, 2))

    def test_only_publish_job_receives_repository_write_access(self) -> None:
        publish = _block(self.lines, "publish", 2)
        self.assertEqual(_mapping(publish, "permissions", 4), {"contents": "write"})
        self.assertEqual(
            [line for line in self.lines if line.strip() == "contents: write"],
            ["      contents: write"],
        )

    def test_permission_regression_runs_when_it_changes(self) -> None:
        path_entry = '      - "tests/test_dropfinder_cloud_workflow_permissions.py"'
        self.assertEqual(self.lines.count(path_entry), 2)
        self.assertIn(
            "          python -m unittest -v tests.test_dropfinder_cloud_workflow_permissions",
            self.lines,
        )


if __name__ == "__main__":
    unittest.main()
