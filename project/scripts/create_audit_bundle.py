#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = 1
CHUNK_SIZE = 1024 * 1024


class AuditBundleError(RuntimeError):
    pass


def git(repo: Path, *args: str, check: bool = True) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise AuditBundleError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def split_nul(blob: bytes, *, label: str) -> list[bytes]:
    if not blob:
        return []
    if not blob.endswith(b"\0"):
        raise AuditBundleError(f"{label} is not NUL terminated")
    values = blob[:-1].split(b"\0")
    if any(not value for value in values):
        raise AuditBundleError(f"{label} contains an empty record")
    return values


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(CHUNK_SIZE):
            digest.update(block)
    return digest.hexdigest()


def canonical_path_blob(paths: Iterable[bytes], *, trailing_nul: bool) -> bytes:
    ordered = sorted(paths)
    blob = b"\0".join(ordered)
    if trailing_nul and ordered:
        blob += b"\0"
    return blob


def safe_text_path(raw: bytes) -> str:
    text = os.fsdecode(raw)
    if text.startswith("/") or text == ".." or text.startswith("../") or "/../" in text:
        raise AuditBundleError(f"unsafe tracked path: {raw!r}")
    return text


def add_regular_file(archive: tarfile.TarFile, source: Path, info: tarfile.TarInfo) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(source, flags)
    try:
        before = os.fstat(descriptor)
        current = os.lstat(source)
        if (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino):
            raise AuditBundleError(f"file identity changed while archiving: {source}")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            archive.addfile(info, handle)
    finally:
        os.close(descriptor)


def create_source_tar(repo: Path, paths: list[bytes], destination: Path, commit_time: int) -> None:
    raw_tar = destination.with_suffix("")
    with tarfile.open(raw_tar, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for raw_path in sorted(paths):
            relative = safe_text_path(raw_path)
            source = repo / relative
            file_stat = os.lstat(source)
            info = archive.gettarinfo(str(source), arcname=relative)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = commit_time
            info.pax_headers = {}
            if stat.S_ISREG(file_stat.st_mode):
                add_regular_file(archive, source, info)
            elif stat.S_ISLNK(file_stat.st_mode) or stat.S_ISDIR(file_stat.st_mode):
                archive.addfile(info)
            else:
                raise AuditBundleError(f"unsupported tracked file type: {relative}")

    with raw_tar.open("rb") as source, destination.open("wb") as raw_destination:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw_destination,
            compresslevel=9,
            mtime=0,
        ) as compressed:
            shutil.copyfileobj(source, compressed, length=CHUNK_SIZE)
    raw_tar.unlink()


def verify_source_tar(path: Path, expected_paths: list[bytes]) -> None:
    expected = [safe_text_path(value) for value in sorted(expected_paths)]
    with tarfile.open(path, mode="r:gz") as archive:
        actual = [member.name.rstrip("/") for member in archive.getmembers()]
    if actual != expected:
        raise AuditBundleError("source archive path list does not match tracked-file population")


def write_checksums(output: Path, names: list[str]) -> None:
    lines = [f"{sha256_file(output / name)}  {name}" for name in sorted(names)]
    (output / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_bundle(repo: Path, output: Path, repository: str | None) -> None:
    root = Path(git(repo, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if root != repo.resolve():
        raise AuditBundleError(f"repository root mismatch: expected {repo.resolve()}, got {root}")

    status = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if status:
        raise AuditBundleError("repository checkout is not clean")

    commit = git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").decode("ascii").strip()
    commit_time = int(git(repo, "show", "-s", "--format=%ct", "HEAD").decode("ascii").strip())
    branch_output = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    branch = branch_output.decode("utf-8", errors="replace").strip() or None

    tracked_raw = git(repo, "ls-files", "-z", "--cached")
    tracked_paths = split_nul(tracked_raw, label="git ls-files")
    tracked_canonical = canonical_path_blob(tracked_paths, trailing_nul=True)

    tree_names_raw = git(repo, "ls-tree", "-r", "--name-only", "-z", "--full-tree", "HEAD")
    tree_names = split_nul(tree_names_raw, label="git ls-tree names")
    if sorted(tracked_paths) != sorted(tree_names):
        raise AuditBundleError("index tracked paths do not match the audited commit tree")

    tree_raw = git(repo, "ls-tree", "-r", "-z", "--full-tree", "HEAD")

    output.mkdir(parents=True, exist_ok=False)
    (output / "tracked-files.nul").write_bytes(tracked_canonical)
    (output / "tree.nul").write_bytes(tree_raw)
    (output / "status.nul").write_bytes(status)

    source_name = f"source-{commit}.tar.gz"
    create_source_tar(repo, tracked_paths, output / source_name, commit_time)
    verify_source_tar(output / source_name, tracked_paths)

    bundle_name = f"repository-{commit}.bundle"
    bundle_path = output / bundle_name
    git(repo, "bundle", "create", str(bundle_path), "HEAD")
    git(repo, "bundle", "verify", str(bundle_path))

    with tempfile.TemporaryDirectory(prefix="audit-bundle-clone-") as clone_dir:
        clone = Path(clone_dir) / "repository"
        subprocess.run(
            ["git", "clone", "--quiet", str(bundle_path), str(clone)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        cloned_head = git(clone, "rev-parse", "HEAD").decode("ascii").strip()
        if cloned_head != commit:
            raise AuditBundleError(f"bundle clone resolved {cloned_head}, expected {commit}")
        if git(clone, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
            raise AuditBundleError("offline bundle clone is not clean")

    final_status = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    final_commit = git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    final_tree = git(repo, "rev-parse", "HEAD^{tree}").decode("ascii").strip()
    if final_status or final_commit != commit or final_tree != tree:
        raise AuditBundleError("repository state changed while creating the audit bundle")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "repository": repository,
        "commit": commit,
        "tree": tree,
        "branch": branch,
        "detached": branch is None,
        "commit_timestamp_utc": dt.datetime.fromtimestamp(commit_time, dt.timezone.utc).isoformat(),
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tracked_file_count": len(tracked_paths),
        "tracked_files_sha256": hashlib.sha256(tracked_canonical).hexdigest(),
        "tree_nul_sha256": hashlib.sha256(tree_raw).hexdigest(),
        "status_clean": not status,
        "authoritative_checkout": bundle_name,
        "source_archive": source_name,
        "notes": [
            "Clone the Git bundle to obtain the exact audited commit without network access.",
            "tracked-files.nul is byte-sorted, NUL-delimited, and includes a trailing NUL when non-empty.",
            "tree.nul is the raw output of git ls-tree -r -z --full-tree HEAD.",
        ],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "README.txt").write_text(
        "Offline audit bundle\n\n"
        f"Repository: {repository or 'unspecified'}\n"
        f"Commit: {commit}\n"
        f"Tree: {tree}\n\n"
        f"Clone: git clone {bundle_name} repository\n"
        "Then verify: git -C repository rev-parse HEAD\n"
        "Use tracked-files.nul as the complete NUL-safe Stage A input population.\n",
        encoding="utf-8",
    )

    checksum_names = [
        bundle_name,
        source_name,
        "tracked-files.nul",
        "tree.nul",
        "status.nul",
        "manifest.json",
        "README.txt",
    ]
    write_checksums(output, checksum_names)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a complete offline audit bundle")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        create_bundle(args.repository_root, args.output, args.repository)
    except (AuditBundleError, OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(f"audit bundle creation failed: {error}", file=os.sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
