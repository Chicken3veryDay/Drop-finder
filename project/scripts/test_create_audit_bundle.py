from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import create_audit_bundle


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


class AuditBundleTests(unittest.TestCase):
    def create_repository(self, root: Path) -> str:
        run("git", "init", "--quiet", cwd=root)
        run("git", "config", "user.email", "audit@example.invalid", cwd=root)
        run("git", "config", "user.name", "Audit Test", cwd=root)
        (root / "normal.txt").write_text("normal\n", encoding="utf-8")
        (root / "dir with spaces").mkdir()
        (root / "dir with spaces" / "file.txt").write_text("space\n", encoding="utf-8")
        (root / "-leading.txt").write_text("dash\n", encoding="utf-8")
        (root / "line\nbreak.txt").write_text("newline\n", encoding="utf-8")
        os.symlink("normal.txt", root / "link.txt")
        run("git", "add", "--all", cwd=root)
        run("git", "commit", "--quiet", "-m", "fixture", cwd=root)
        return run("git", "rev-parse", "HEAD", cwd=root).stdout.decode("ascii").strip()

    def test_bundle_round_trip_and_nul_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository = base / "repository"
            repository.mkdir()
            expected_commit = self.create_repository(repository)
            output = base / "bundle"

            create_audit_bundle.create_bundle(repository, output, "Example/Repository")

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["commit"], expected_commit)
            self.assertEqual(manifest["tracked_file_count"], 5)
            self.assertTrue(manifest["status_clean"])

            tracked = (output / "tracked-files.nul").read_bytes()
            self.assertTrue(tracked.endswith(b"\0"))
            paths = tracked[:-1].split(b"\0")
            self.assertEqual(paths, sorted(paths))
            self.assertIn(b"line\nbreak.txt", paths)
            self.assertIn(b"-leading.txt", paths)

            checksum = run("sha256sum", "--check", "SHA256SUMS", cwd=output)
            self.assertNotIn(b"FAILED", checksum.stdout)

            clone = base / "clone"
            bundle = output / manifest["authoritative_checkout"]
            run("git", "clone", "--quiet", str(bundle), str(clone), cwd=base)
            cloned_commit = run("git", "rev-parse", "HEAD", cwd=clone).stdout.decode("ascii").strip()
            self.assertEqual(cloned_commit, expected_commit)
            self.assertEqual(run("git", "status", "--short", cwd=clone).stdout, b"")

    def test_dirty_checkout_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository = base / "repository"
            repository.mkdir()
            self.create_repository(repository)
            (repository / "normal.txt").write_text("dirty\n", encoding="utf-8")

            with self.assertRaisesRegex(create_audit_bundle.AuditBundleError, "not clean"):
                create_audit_bundle.create_bundle(repository, base / "bundle", "Example/Repository")


if __name__ == "__main__":
    unittest.main()
