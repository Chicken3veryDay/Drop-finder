from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = Path(os.getenv("DROPFINDER_RUNTIME_DIR", "/app/runtime")).resolve()
DATA_DIR = RUNTIME_DIR / "data"
SCAN_DIR = RUNTIME_DIR / "scan-results"
LOG_DIR = RUNTIME_DIR / "logs"
WEB_DIR = Path(os.getenv("DROPFINDER_WEB_DIR", "/app/web")).resolve()
SCRIPTS_DIR = Path(os.getenv("DROPFINDER_SCRIPTS_DIR", "/app/scripts")).resolve()
SCAN_INTERVAL = max(1800, int(os.getenv("DROPFINDER_SCAN_INTERVAL_SECONDS", "10800")))
SCAN_STALE_AFTER = max(900, int(os.getenv("DROPFINDER_SCAN_STALE_AFTER_SECONDS", "14400")))
SCAN_WORKERS = max(1, min(4, int(os.getenv("DROPFINDER_SCAN_WORKERS", "3"))))
MIN_ACTIVE = max(1, int(os.getenv("DROPFINDER_MIN_ACTIVE_SOURCES", "5")))
MIN_PRODUCTS = max(1, int(os.getenv("DROPFINDER_MIN_PRODUCTS", "25")))

STATE_LOCK = threading.RLock()
SCAN_LOCK = threading.Lock()
STOP_EVENT = threading.Event()
SCAN_STATE: dict[str, Any] = {
    "running": False,
    "last_started_at": None,
    "last_finished_at": None,
    "last_success_at": None,
    "last_error": None,
    "last_duration_seconds": None,
    "scan_count": 0,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _seed_state() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SCAN_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    seed = WEB_DIR / "data"
    for name in ("catalog.json", "status.json", "runtime.json", "quarantine.json", "rejections.json"):
        destination = DATA_DIR / name
        source = seed / name
        if not destination.exists() and source.exists():
            shutil.copy2(source, destination)
    state_path = RUNTIME_DIR / "scan-state.json"
    stored = _read_json(state_path, {})
    if isinstance(stored, dict):
        with STATE_LOCK:
            for key in SCAN_STATE:
                if key in stored and key != "running":
                    SCAN_STATE[key] = stored[key]
            SCAN_STATE["running"] = False


def _persist_scan_state() -> None:
    with STATE_LOCK:
        payload = dict(SCAN_STATE)
    _write_json(RUNTIME_DIR / "scan-state.json", payload)


def _catalog_age_seconds() -> float | None:
    catalog = _read_json(DATA_DIR / "catalog.json", {})
    raw = catalog.get("generated_at") if isinstance(catalog, dict) else None
    if not raw:
        return None
    try:
        generated = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (datetime.now(timezone.utc) - generated).total_seconds())


def _run_command(command: list[str], log) -> None:
    process = subprocess.run(
        command,
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=1500,
        check=False,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    if process.returncode != 0:
        raise RuntimeError(f"command failed with exit code {process.returncode}: {' '.join(command)}")


def run_scan(reason: str = "scheduled") -> bool:
    if not SCAN_LOCK.acquire(blocking=False):
        return False
    started_monotonic = time.monotonic()
    started_at = utc_now()
    with STATE_LOCK:
        SCAN_STATE.update(
            running=True,
            last_started_at=started_at,
            last_error=None,
            scan_count=int(SCAN_STATE.get("scan_count") or 0) + 1,
            trigger=reason,
        )
    _persist_scan_state()
    run_root = RUNTIME_DIR / "runs" / started_at.replace(":", "-")
    shard_root = run_root / "shards"
    output_root = run_root / "output"
    shard_root.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "latest-scan.log"
    success = False
    try:
        with log_path.open("w", encoding="utf-8") as log:
            log.write(f"DropFinder scan started {started_at}; trigger={reason}\n")
            _run_command(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "autonomous_worker_v4.py"),
                    "--shard",
                    "0",
                    "--shards",
                    "1",
                    "--workers",
                    str(SCAN_WORKERS),
                    "--output",
                    str(shard_root),
                ],
                log,
            )
            _run_command(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "autonomous_merge.py"),
                    "--input",
                    str(shard_root),
                    "--output",
                    str(output_root),
                    "--min-active",
                    str(MIN_ACTIVE),
                    "--min-products",
                    str(MIN_PRODUCTS),
                ],
                log,
            )
        catalog = _read_json(output_root / "catalog.json", {})
        status_payload = _read_json(output_root / "status.json", {})
        products = catalog.get("products") if isinstance(catalog, dict) else None
        if not isinstance(products, list) or catalog.get("product_count") != len(products):
            raise RuntimeError("catalog count invariant failed")
        if status_payload.get("degraded_sources") != 0:
            raise RuntimeError("degraded source invariant failed")
        if status_payload.get("healthy_sources") != status_payload.get("enabled_sources"):
            raise RuntimeError("healthy source invariant failed")
        for name in ("catalog.json", "status.json", "runtime.json", "quarantine.json", "rejections.json"):
            source = output_root / name
            if not source.exists():
                raise RuntimeError(f"scan output missing {name}")
            os.replace(source, DATA_DIR / name)
        success = True
        with STATE_LOCK:
            SCAN_STATE["last_success_at"] = utc_now()
    except Exception as exc:
        with STATE_LOCK:
            SCAN_STATE["last_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        finished = utc_now()
        with STATE_LOCK:
            SCAN_STATE.update(
                running=False,
                last_finished_at=finished,
                last_duration_seconds=round(time.monotonic() - started_monotonic, 3),
            )
        _persist_scan_state()
        SCAN_LOCK.release()
        for old in sorted((RUNTIME_DIR / "runs").glob("*"))[:-3]:
            shutil.rmtree(old, ignore_errors=True)
    return success


def _scheduler_loop() -> None:
    while not STOP_EVENT.wait(30):
        age = _catalog_age_seconds()
        if age is None or age >= SCAN_STALE_AFTER:
            run_scan("startup_or_stale")
        if STOP_EVENT.wait(SCAN_INTERVAL):
            return
        run_scan("scheduled")


def _authorized(authorization: str | None, operator_token: str | None) -> bool:
    expected = os.getenv("DROPFINDER_OPERATOR_TOKEN", "").strip()
    if not expected:
        return False
    supplied = operator_token or ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    import hmac

    return hmac.compare_digest(expected, supplied)


def _require_operator(authorization: str | None, operator_token: str | None) -> None:
    if not _authorized(authorization, operator_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="valid operator token required")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _seed_state()
    STOP_EVENT.clear()
    thread = threading.Thread(target=_scheduler_loop, name="dropfinder-scheduler", daemon=True)
    thread.start()
    try:
        yield
    finally:
        STOP_EVENT.set()
        thread.join(timeout=10)


app = FastAPI(title="DropFinder OS", version="9.0-cloud", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "service": "dropfinder-os",
        "time": utc_now(),
        "scheduler": "running" if not STOP_EVENT.is_set() else "stopped",
    }


@app.get("/ready")
def ready() -> JSONResponse:
    catalog = _read_json(DATA_DIR / "catalog.json", {})
    status_payload = _read_json(DATA_DIR / "status.json", {})
    valid = (
        isinstance(catalog, dict)
        and isinstance(catalog.get("products"), list)
        and catalog.get("product_count") == len(catalog.get("products", []))
        and status_payload.get("degraded_sources") == 0
    )
    code = 200 if valid else 503
    return JSONResponse(
        {
            "ready": valid,
            "product_count": catalog.get("product_count", 0),
            "generated_at": catalog.get("generated_at"),
            "scan": dict(SCAN_STATE),
        },
        status_code=code,
    )


@app.get("/api/catalog")
def catalog() -> Any:
    payload = _read_json(DATA_DIR / "catalog.json")
    if payload is None:
        raise HTTPException(503, "catalog unavailable")
    return payload


@app.get("/api/status")
def source_status() -> Any:
    payload = _read_json(DATA_DIR / "status.json")
    if payload is None:
        raise HTTPException(503, "status unavailable")
    return payload


@app.get("/api/runtime")
def runtime() -> Any:
    return _read_json(DATA_DIR / "runtime.json", {})


@app.get("/api/quarantine")
def quarantine() -> Any:
    return _read_json(DATA_DIR / "quarantine.json", {"count": 0, "sources": []})


@app.get("/api/rejections")
def rejections() -> Any:
    return _read_json(DATA_DIR / "rejections.json", {"count": 0, "products": []})


@app.get("/api/scan-state")
def scan_state() -> dict[str, Any]:
    with STATE_LOCK:
        return dict(SCAN_STATE)


@app.post("/api/scan", status_code=202)
def trigger_scan(
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
    x_operator_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_operator(authorization, x_operator_token)
    with STATE_LOCK:
        if SCAN_STATE.get("running"):
            return {"accepted": False, "reason": "scan_already_running", "scan": dict(SCAN_STATE)}
    background_tasks.add_task(run_scan, "operator")
    return {"accepted": True, "scan": dict(SCAN_STATE)}


@app.get("/data/{name}")
def data_file(name: str) -> FileResponse:
    if name not in {"catalog.json", "status.json", "runtime.json", "quarantine.json", "rejections.json"}:
        raise HTTPException(404, "not found")
    path = DATA_DIR / name
    if not path.exists():
        raise HTTPException(404, "not found")
    return FileResponse(path, media_type="application/json", headers={"Cache-Control": "no-store"})


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
