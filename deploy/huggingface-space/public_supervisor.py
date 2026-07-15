from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

RUNTIME_DIR = Path(os.getenv("DROPFINDER_RUNTIME_DIR", "/app/runtime")).resolve()
WEB_DIR = Path(os.getenv("DROPFINDER_WEB_DIR", "/app/web")).resolve()
MIGRATION = Path(os.getenv("DROPFINDER_STATE_MIGRATION_SCRIPT", "/app/migrate_runtime_state.py")).resolve()


def restore_embedded_seed() -> None:
    source = WEB_DIR / "data"
    destination = RUNTIME_DIR / "data"
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("catalog.json", "status.json", "runtime.json", "quarantine.json", "rejections.json"):
        incoming = source / name
        current = destination / name
        if incoming.is_file() and not current.exists():
            shutil.copy2(incoming, current)
    if MIGRATION.is_file():
        subprocess.run(
            [sys.executable, str(MIGRATION)],
            cwd="/app",
            env=os.environ.copy(),
            check=True,
        )


def main() -> int:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    restore_embedded_seed()
    asgi_app = os.getenv("DROPFINDER_ASGI_APP", "strict_space_app:app").strip() or "strict_space_app:app"
    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            asgi_app,
            "--host",
            "0.0.0.0",
            "--port",
            os.getenv("PORT", "7860"),
            "--proxy-headers",
            "--forwarded-allow-ips=*",
        ],
        cwd="/app",
        env=os.environ.copy(),
    )

    def shutdown(signum, _frame) -> None:
        if child.poll() is None:
            child.send_signal(signal.SIGTERM)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
