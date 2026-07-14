from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import render_deploy


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def redact(value: str) -> str:
    result = value
    for name in ("RENDER_API_KEY", "HF_TOKEN", "DROPFINDER_OPERATOR_TOKEN"):
        secret = os.getenv(name, "").strip()
        if secret:
            result = result.replace(secret, "[REDACTED]")
    return result


def apply_free_tier_compatibility() -> None:
    original = render_deploy.service_details

    def free_service_details() -> dict:
        details = dict(original())
        details.pop("maxShutdownDelaySeconds", None)
        return details

    render_deploy.service_details = free_service_details


def main() -> int:
    error_path = Path("deployment/render-deployment-error.json")
    try:
        apply_free_tier_compatibility()
        code = render_deploy.main()
        if error_path.exists():
            error_path.unlink()
        return code
    except Exception as exc:
        report = {
            "schema_version": "dropfinder-render-deployment-error-v1",
            "status": "failed",
            "failed_at": utc_now(),
            "error_type": type(exc).__name__,
            "error": redact(str(exc))[:8000],
            "traceback": redact(traceback.format_exc())[-12000:],
            "render_key_present": bool(os.getenv("RENDER_API_KEY", "").strip()),
            "hf_token_present": bool(os.getenv("HF_TOKEN", "").strip()),
            "operator_token_present": bool(os.getenv("DROPFINDER_OPERATOR_TOKEN", "").strip()),
        }
        error_path.parent.mkdir(parents=True, exist_ok=True)
        error_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "traceback"}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
