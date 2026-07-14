from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tarfile
import tempfile
import time
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.errors import EntryNotFoundError, RepositoryNotFoundError

RUNTIME_DIR = Path(os.getenv("DROPFINDER_RUNTIME_DIR", "/app/runtime")).resolve()
STATE_PATH = os.getenv("HF_STATE_PATH", "dropfinder/state-v1.tar.gz").strip()
_DIGEST_FILE = RUNTIME_DIR / ".last-hf-state-sha256"
STATE_FILES = (
    Path("data/catalog.json"),
    Path("data/status.json"),
    Path("data/runtime.json"),
    Path("data/quarantine.json"),
    Path("data/rejections.json"),
    Path("scan-state.json"),
)
DB_PATHS = tuple(
    Path(path).resolve()
    for path in (
        os.getenv("DROPFINDER_DB_PATH", ""),
        os.getenv("DROPFINDER_RELIABILITY_DB_PATH", ""),
    )
    if path.strip()
)


def configured() -> bool:
    return bool(os.getenv("HF_TOKEN", "").strip() and os.getenv("HF_STATE_REPO", "").strip())


def _token() -> str:
    return os.environ["HF_TOKEN"].strip()


def _repo_id() -> str:
    return os.environ["HF_STATE_REPO"].strip()


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if target != destination and destination not in target.parents:
            raise RuntimeError(f"unsafe snapshot path: {member.name}")
        if member.issym() or member.islnk() or member.isdev():
            raise RuntimeError(f"unsupported snapshot member: {member.name}")
    archive.extractall(destination)


def restore() -> bool:
    if not configured():
        print("Hugging Face state persistence is not configured; starting with ephemeral state.", flush=True)
        return False
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    try:
        downloaded = hf_hub_download(
            repo_id=_repo_id(),
            repo_type="dataset",
            filename=STATE_PATH,
            token=_token(),
        )
    except (EntryNotFoundError, RepositoryNotFoundError):
        print("No prior private Hub snapshot exists; initializing clean state.", flush=True)
        return False

    archive_path = Path(downloaded)
    with tarfile.open(archive_path, "r:gz") as archive:
        _safe_extract(archive, RUNTIME_DIR)

    manifest_path = RUNTIME_DIR / "snapshot-manifest.json"
    manifest = {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    finally:
        manifest_path.unlink(missing_ok=True)

    digest = str(manifest.get("content_sha256") or "").strip()
    if not digest:
        digest = _content_fingerprint(RUNTIME_DIR)
    _DIGEST_FILE.write_text(digest + "\n", encoding="ascii")
    print(f"Restored DropFinder state from hf://datasets/{_repo_id()}/{STATE_PATH}", flush=True)
    return True


def _sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30)
    try:
        destination_connection = sqlite3.connect(destination, timeout=30)
        try:
            source_connection.backup(destination_connection, pages=256, sleep=0.02)
        finally:
            destination_connection.close()
    finally:
        source_connection.close()


def _copy_runtime(snapshot_root: Path) -> None:
    snapshot_root.mkdir(parents=True, exist_ok=True)
    for relative in STATE_FILES:
        source = RUNTIME_DIR / relative
        if not source.is_file():
            continue
        destination = snapshot_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())

    for source in DB_PATHS:
        if not source.is_file():
            continue
        try:
            relative = source.relative_to(RUNTIME_DIR)
        except ValueError:
            relative = Path("databases") / source.name
        _sqlite_backup(source, snapshot_root / relative)


def _content_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in {"snapshot-manifest.json", _DIGEST_FILE.name}:
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def backup(*, force: bool = False) -> bool:
    if not configured():
        return False
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dropfinder-backup-") as tmp:
        tmp_path = Path(tmp)
        snapshot_root = tmp_path / "runtime"
        _copy_runtime(snapshot_root)
        digest = _content_fingerprint(snapshot_root)
        previous = _DIGEST_FILE.read_text(encoding="ascii").strip() if _DIGEST_FILE.exists() else ""
        if not force and digest == previous:
            return False

        manifest = {
            "schema_version": "dropfinder-hf-state-v2",
            "created_at": time.time(),
            "state_path": STATE_PATH,
            "content_sha256": digest,
            "files": sorted(
                path.relative_to(snapshot_root).as_posix()
                for path in snapshot_root.rglob("*")
                if path.is_file()
            ),
        }
        (snapshot_root / "snapshot-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        archive_path = tmp_path / "state.tar.gz"
        with tarfile.open(archive_path, "w:gz", compresslevel=6) as archive:
            for path in sorted(snapshot_root.rglob("*")):
                if path.is_file():
                    archive.add(path, arcname=path.relative_to(snapshot_root), recursive=False)

        HfApi(token=_token()).upload_file(
            path_or_fileobj=archive_path,
            path_in_repo=STATE_PATH,
            repo_id=_repo_id(),
            repo_type="dataset",
            commit_message=f"Update DropFinder state {digest[:12]}",
        )
        _DIGEST_FILE.write_text(digest + "\n", encoding="ascii")
        print(
            f"Backed up DropFinder state to private Hub dataset "
            f"({archive_path.stat().st_size} bytes, content_sha256={digest})",
            flush=True,
        )
        return True
