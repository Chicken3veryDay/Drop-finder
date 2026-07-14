from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading

from hf_state import backup, configured, restore


def _require_secure_configuration() -> None:
    token = os.getenv("DROPFINDER_OPERATOR_TOKEN", "").strip()
    if len(token) < 24:
        raise SystemExit(
            "DROPFINDER_OPERATOR_TOKEN must be set as a Space secret and contain at least 24 characters."
        )
    if not configured():
        raise SystemExit(
            "Private Hub persistence is incomplete. Configure HF_TOKEN and HF_STATE_REPO."
        )


def main() -> int:
    _require_secure_configuration()
    os.makedirs("/app/runtime", exist_ok=True)
    os.makedirs("/app/logs", exist_ok=True)
    restore()

    stop = threading.Event()
    interval = max(300, int(os.getenv("DROPFINDER_BACKUP_INTERVAL_SECONDS", "1800")))

    def backup_loop() -> None:
        while not stop.wait(interval):
            try:
                backup()
            except Exception as exc:
                print(f"Private Hub backup failed: {exc}", file=sys.stderr, flush=True)

    thread = threading.Thread(target=backup_loop, name="hf-state-backup", daemon=True)
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
            backup(force=True)
        except Exception as exc:
            print(f"Final private Hub backup failed: {exc}", file=sys.stderr, flush=True)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
