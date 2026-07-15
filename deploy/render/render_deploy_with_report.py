from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import render_complete_verifier
import render_deploy

KNOWN_RENDER_SERVICE_ID = os.getenv("RENDER_SERVICE_ID", "srv-d9barmojs32c739o9ke0").strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def redact(value: str) -> str:
    result = value
    for name in ("RENDER_API_KEY", "HF_TOKEN", "DROPFINDER_OPERATOR_TOKEN"):
        secret = os.getenv(name, "").strip()
        if secret:
            result = result.replace(secret, "[REDACTED]")
    return result


def apply_render_api_retries() -> None:
    original = render_deploy.RenderAPI.request

    def resilient_request(self, method: str, path: str, payload=None):
        method_upper = method.upper()
        attempts = 5 if method_upper == "GET" else 3 if method_upper in {"PUT", "PATCH", "DELETE"} else 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return original(self, method, path, payload)
            except (TimeoutError, OSError) as exc:
                last_error = exc
                if attempt >= attempts:
                    raise
                delay = min(20, attempt * 3)
                print(
                    f"Render API transient {method} {path} failure "
                    f"({type(exc).__name__}); retry {attempt}/{attempts - 1} in {delay}s",
                    flush=True,
                )
                time.sleep(delay)
        if last_error:
            raise last_error
        raise RuntimeError("Render API retry loop ended unexpectedly")

    render_deploy.RenderAPI.request = resilient_request


def apply_known_service_target() -> None:
    if not KNOWN_RENDER_SERVICE_ID:
        raise RuntimeError("RENDER_SERVICE_ID is empty")

    def known_owner(_api) -> dict:
        return {"id": "known-service-owner-bypass", "type": "known_service"}

    def update_known_service(api, _owner_id: str, env_vars: list[dict[str, str]]):
        service_id = KNOWN_RENDER_SERVICE_ID
        service = api.request(
            "PATCH",
            f"/services/{service_id}",
            {
                "name": render_deploy.SERVICE_NAME,
                "repo": render_deploy.REPOSITORY_URL,
                "branch": render_deploy.REPOSITORY_BRANCH,
                "autoDeploy": "no",
                "rootDir": "",
                "serviceDetails": render_deploy.service_details(),
            },
        )
        api.request("PUT", f"/services/{service_id}/env-vars", env_vars)
        if not isinstance(service, dict):
            service = {}
        service = dict(service)
        service.setdefault("id", service_id)
        service.setdefault("name", render_deploy.SERVICE_NAME)
        service.setdefault("url", "https://dropfinder-os.onrender.com")
        return service, None, False

    render_deploy.select_owner = known_owner
    render_deploy.create_or_update_service = update_known_service


def apply_free_tier_compatibility() -> None:
    original = render_deploy.service_details

    def free_service_details() -> dict:
        details = dict(original())
        details.pop("maxShutdownDelaySeconds", None)
        return details

    render_deploy.service_details = free_service_details


def apply_complete_catalog_floor() -> None:
    original = render_deploy.render_env

    def complete_env(hf_token: str, operator_token: str, state_repo: str) -> list[dict[str, str]]:
        rows = original(hf_token, operator_token, state_repo)
        result: list[dict[str, str]] = []
        required = {
            "DROPFINDER_MIN_ACTIVE_SOURCES": "4",
            "DROPFINDER_MIN_PRODUCTS": "25",
            "DROPFINDER_REQUIRED_NORMALIZATION_CONTRACT": "dropfinder-product-normalization-v1",
            "DROPFINDER_STATE_MIGRATION_SCRIPT": "/app/migrate_runtime_state.py",
        }
        seen: set[str] = set()
        for row in rows:
            item = dict(row)
            key = str(item.get("key") or "")
            if key in required:
                item["value"] = required[key]
                seen.add(key)
            result.append(item)
        for key, value in required.items():
            if key not in seen:
                result.append({"key": key, "value": value})
        return result

    render_deploy.render_env = complete_env


def apply_quality_safe_scan_retention() -> None:
    """Allow rollout when a weak live scan is rejected and the prior catalog remains valid."""

    def verify_scan(app_url: str, operator_token: str) -> dict:
        initial = render_deploy.fetch_json(app_url, "/api/scan-state")
        initial_count = int(initial.get("scan_count") or 0)
        initial_success = initial.get("last_success_at")
        trigger = render_deploy.fetch_json(
            app_url,
            "/api/scan",
            method="POST",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        print("Hosted scan trigger:", json.dumps(trigger, sort_keys=True), flush=True)

        latest = initial
        saw_scan = bool(initial.get("running"))
        for _ in range(120):
            latest = render_deploy.fetch_json(app_url, "/api/scan-state")
            current_count = int(latest.get("scan_count") or 0)
            saw_scan = saw_scan or bool(latest.get("running")) or current_count > initial_count
            fresh_success = bool(
                latest.get("last_success_at")
                and latest.get("last_success_at") != initial_success
            )
            print("Hosted scan state:", json.dumps(latest, sort_keys=True), flush=True)
            if saw_scan and not latest.get("running"):
                if fresh_success and not latest.get("last_error"):
                    result = dict(latest)
                    result.update(scan_result="published", publication_retained=False)
                    return result

                error = str(latest.get("last_error") or "")
                quality_floor_rejection = any(
                    token in error
                    for token in (
                        "active-source floor failed",
                        "complete-product floor failed",
                        "complete product floor failed",
                    )
                )
                if quality_floor_rejection:
                    verified = render_deploy.verify_catalog(app_url)
                    result = dict(latest)
                    result.update(
                        scan_result="rejected_by_quality_floor",
                        publication_retained=True,
                        retained_product_count=verified["catalog"].get("product_count"),
                        retained_healthy_sources=verified["status"].get("healthy_sources"),
                        retained_comparison_contract=verified["catalog"].get("comparison_contract"),
                        retained_normalization_contract=verified["catalog"].get("normalization_contract"),
                    )
                    return result
                if error:
                    raise RuntimeError(f"hosted Render scan failed outside the quality floor: {latest}")
            time.sleep(15)
        raise RuntimeError(f"hosted Render scan did not complete: {latest}")

    render_deploy.verify_hosted_scan = verify_scan


def main() -> int:
    error_path = Path("deployment/render-deployment-error.json")
    try:
        apply_render_api_retries()
        apply_free_tier_compatibility()
        apply_known_service_target()
        apply_complete_catalog_floor()
        render_complete_verifier.apply()
        apply_quality_safe_scan_retention()
        code = render_deploy.main()
        if error_path.exists():
            error_path.unlink()
        return code
    except Exception as exc:
        report = {
            "schema_version": "dropfinder-render-deployment-error-v6",
            "status": "failed",
            "failed_at": utc_now(),
            "error_type": type(exc).__name__,
            "error": redact(str(exc))[:8000],
            "traceback": redact(traceback.format_exc())[-12000:],
            "known_service_target_enabled": True,
            "known_service_id": KNOWN_RENDER_SERVICE_ID,
            "render_api_get_retries_enabled": True,
            "render_api_idempotent_write_retries_enabled": True,
            "complete_data_verifier_enabled": True,
            "normalization_verifier_enabled": True,
            "quality_safe_retention_enabled": True,
            "minimum_active_sources": 4,
            "minimum_complete_products": 25,
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
