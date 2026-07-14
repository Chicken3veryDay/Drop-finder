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

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

RUNTIME_DIR = Path(os.getenv("DROPFINDER_RUNTIME_DIR", "/app/runtime")).resolve()
DB_PATHS = tuple(
    Path(path).resolve()
    for path in (
        os.getenv("DROPFINDER_DB_PATH", "/app/runtime/dropfinder.db"),
        os.getenv("DROPFINDER_RELIABILITY_DB_PATH", "/app/runtime/reliability.db"),
    )
)
STATE_KEY = os.getenv("R2_STATE_KEY", "dropfinder/state-v1.tar.gz").strip()


def configured() -> bool:
    return all(
        os.getenv(name, "").strip()
        for name in (
            "R2_ENDPOINT_URL",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_BUCKET",
        )
    )


def _client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"].strip(),
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"].strip(),
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"].strip(),
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 5, "mode": "standard"},
            connect_timeout=10,
            read_timeout=60,
        ),
    )


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
        print("R2 persistence is not configured; starting with ephemeral state.", flush=True)
        return False
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dropfinder-restore-") as tmp:
        archive_path = Path(tmp) / "state.tar.gz"
        try:
            _client().download_file(os.environ["R2_BUCKET"].strip(), STATE_KEY, str(archive_path))
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                print("No prior R2 snapshot exists; initializing clean state.", flush=True)
                return False
            raise
        with tarfile.open(archive_path, "r:gz") as archive:
            _safe_extract(archive, RUNTIME_DIR)
        print(f"Restored DropFinder state from s3://{os.environ['R2_BUCKET']}/{STATE_KEY}", flush=True)
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
            if resolved in db_set or source.name.endswith(("-wal", "-shm")):
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


def backup() -> bool:
    if not configured():
        return False
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dropfinder-backup-") as tmp:
        tmp_path = Path(tmp)
        snapshot_root = tmp_path / "runtime"
        _copy_runtime(snapshot_root)
        manifest = {
            "schema_version": "dropfinder-r2-snapshot-v1",
            "created_at": time.time(),
            "state_key": STATE_KEY,
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
        _client().upload_file(
            str(archive_path),
            os.environ["R2_BUCKET"].strip(),
            STATE_KEY,
            ExtraArgs={
                "ContentType": "application/gzip",
                "Metadata": {
                    "sha256": digest,
                    "schema": "dropfinder-r2-snapshot-v1",
                },
            },
        )
        print(f"Backed up DropFinder state to R2 ({archive_path.stat().st_size} bytes, sha256={digest})", flush=True)
        return True
