from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import time
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.errors import EntryNotFoundError, RepositoryNotFoundError

RUNTIME_DIR = Path(os.getenv("DROPFINDER_RUNTIME_DIR", "/app/runtime")).resolve()
DB_PATHS = tuple(
    Path(path).resolve()
    for path in (
        os.getenv("DROPFINDER_DB_PATH", "/app/runtime/dropfinder.db"),
        os.getenv("DROPFINDER_RELIABILITY_DB_PATH", "/app/runtime/reliability.db"),
    )
)
STATE_PATH = os.getenv("HF_STATE_PATH", "dropfinder/state-v1.tar.gz").strip()
_DIGEST_FILE = RUNTIME_DIR / ".last-hf-state-sha256"


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
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    with tarfile.open(archive_path, "r:gz") as archive:
        _safe_extract(archive, RUNTIME_DIR)
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
            destination_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            destination_connection.close()
    finally:
        source_connection.close()


def _copy_runtime(snapshot_root: Path) -> None:
    snapshot_root.mkdir(parents=True, exist_ok=True)
    db_set = {path.resolve() for path in DB_PATHS}
    if RUNTIME_DIR.exists():
        for source in RUNTIME_DIR.rglob("*"):
            if not source.is_file():
                continue
            resolved = source.resolve()
            if resolved in db_set or source.name.endswith(("-wal", "-shm")) or resolved == _DIGEST_FILE:
                continue
            relative = source.relative_to(RUNTIME_DIR)
            destination = snapshot_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(source, destination)
            except FileNotFoundError:
                continue
    for source in DB_PATHS:
        if source.exists():
            try:
                relative = source.relative_to(RUNTIME_DIR)
            except ValueError:
                relative = Path("databases") / source.name
            _sqlite_backup(source, snapshot_root / relative)


def backup(*, force: bool = False) -> bool:
    if not configured():
        return False
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dropfinder-backup-") as tmp:
        tmp_path = Path(tmp)
        snapshot_root = tmp_path / "runtime"
        _copy_runtime(snapshot_root)
        manifest = {
            "schema_version": "dropfinder-hf-state-v1",
            "created_at": time.time(),
            "state_path": STATE_PATH,
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
        digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        previous = _DIGEST_FILE.read_text(encoding="ascii").strip() if _DIGEST_FILE.exists() else ""
        if not force and digest == previous:
            return False
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
            f"({archive_path.stat().st_size} bytes, sha256={digest})",
            flush=True,
        )
        return True
