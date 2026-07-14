from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading

from r2_state import backup, configured, restore


def _require_secure_configuration() -> None:
    token = os.getenv("DROPFINDER_OPERATOR_TOKEN", "").strip()
    if len(token) < 24:
        raise SystemExit(
            "DROPFINDER_OPERATOR_TOKEN must be set as a Space secret and contain at least 24 characters."
        )
    if not configured():
        raise SystemExit(
            "R2 persistence secrets are incomplete. Configure R2_ENDPOINT_URL, "
            "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, and R2_BUCKET."
        )


def main() -> int:
    _require_secure_configuration()
    os.makedirs("/app/runtime", exist_ok=True)
    os.makedirs("/app/logs", exist_ok=True)
    restore()

    stop = threading.Event()
    interval = max(60, int(os.getenv("DROPFINDER_BACKUP_INTERVAL_SECONDS", "300")))

    def backup_loop() -> None:
        while not stop.wait(interval):
            try:
                backup()
            except Exception as exc:
                print(f"R2 backup failed: {exc}", file=sys.stderr, flush=True)

    thread = threading.Thread(target=backup_loop, name="r2-backup", daemon=True)
    thread.start()
    child = subprocess.Popen(["/app/run.sh"], env=os.environ.copy())

    def shutdown(signum, _frame) -> None:
        print(f"Received signal {signum}; stopping DropFinder.", flush=True)
        stop.set()
        if child.poll() is None:
            child.send_signal(signal.SIGTERM)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        return_code = child.wait()
    finally:
        stop.set()
        thread.join(timeout=5)
        try:
            backup()
        except Exception as exc:
            print(f"Final R2 backup failed: {exc}", file=sys.stderr, flush=True)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
