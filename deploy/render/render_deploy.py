from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API_ROOT = "https://api.render.com/v1"
REPOSITORY_URL = "https://github.com/Chicken3veryDay/Drop-finder"
REPOSITORY_BRANCH = "deploy/full-stack-hf"
SERVICE_NAME = "dropfinder-os"
TERMINAL_DEPLOY_FAILURES = {"build_failed", "update_failed", "canceled", "deactivated", "pre_deploy_failed"}
ACTIVE_DEPLOY_STATES = {"created", "queued", "build_in_progress", "update_in_progress", "pre_deploy_in_progress"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def required_env(name: str, *, minimum: int = 1) -> str:
    value = os.getenv(name, "").strip()
    if len(value) < minimum:
        raise RuntimeError(f"{name} is missing or shorter than {minimum} characters")
    return value


class RenderAPI:
    def __init__(self, token: str) -> None:
        self.token = token

    def request(self, method: str, path: str, payload: Any | None = None) -> Any:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            API_ROOT + path,
            method=method,
            data=body,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "DropFinder-Render-Deployer/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"Render API {method} {path} returned HTTP {exc.code}: {raw[:2000]}") from exc


def render_env(hf_token: str, operator_token: str, state_repo: str) -> list[dict[str, str]]:
    return [
        {"key": "HF_TOKEN", "value": hf_token},
        {"key": "DROPFINDER_OPERATOR_TOKEN", "value": operator_token},
        {"key": "HF_STATE_REPO", "value": state_repo},
        {"key": "HF_STATE_PATH", "value": "dropfinder/state-v1.tar.gz"},
        {"key": "DROPFINDER_BACKUP_INTERVAL_SECONDS", "value": "1800"},
        {"key": "DROPFINDER_SCAN_INTERVAL_SECONDS", "value": "10800"},
        {"key": "DROPFINDER_SCAN_STALE_AFTER_SECONDS", "value": "14400"},
        {"key": "DROPFINDER_SCAN_WORKERS", "value": "2"},
        {"key": "DROPFINDER_MIN_ACTIVE_SOURCES", "value": "5"},
        {"key": "DROPFINDER_MIN_PRODUCTS", "value": "25"},
        {"key": "DROPFINDER_HOSTING_MODE", "value": "render_autonomous_service"},
    ]


def service_details() -> dict[str, Any]:
    return {
        "runtime": "docker",
        "plan": "free",
        "region": "ohio",
        "numInstances": 1,
        "healthCheckPath": "/health",
        "maxShutdownDelaySeconds": 60,
        "envSpecificDetails": {
            "dockerContext": ".",
            "dockerfilePath": "./deploy/render/Dockerfile",
        },
    }


def list_services(api: RenderAPI, owner_id: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "name": SERVICE_NAME,
            "ownerId": owner_id,
            "limit": 20,
            "includePreviews": "false",
        }
    )
    rows = api.request("GET", f"/services?{query}") or []
    return [row.get("service", row) for row in rows if isinstance(row, dict)]


def select_owner(api: RenderAPI) -> dict[str, Any]:
    owners = api.request("GET", "/owners?limit=20") or []
    candidates = [row.get("owner", row) for row in owners if isinstance(row, dict)]
    if not candidates:
        raise RuntimeError("Render API key has no accessible workspace")
    user_owned = [owner for owner in candidates if owner.get("type") == "user"]
    return (user_owned or candidates)[0]


def create_or_update_service(
    api: RenderAPI,
    owner_id: str,
    env_vars: list[dict[str, str]],
) -> tuple[dict[str, Any], str | None, bool]:
    matches = [service for service in list_services(api, owner_id) if service.get("name") == SERVICE_NAME]
    if len(matches) > 1:
        raise RuntimeError(f"multiple Render services are named {SERVICE_NAME}")
    if not matches:
        created = api.request(
            "POST",
            "/services",
            {
                "type": "web_service",
                "name": SERVICE_NAME,
                "ownerId": owner_id,
                "repo": REPOSITORY_URL,
                "branch": REPOSITORY_BRANCH,
                "autoDeploy": "no",
                "envVars": env_vars,
                "serviceDetails": service_details(),
            },
        )
        service = created.get("service", created)
        return service, created.get("deployId"), True

    service = matches[0]
    service_id = str(service["id"])
    service = api.request(
        "PATCH",
        f"/services/{service_id}",
        {
            "name": SERVICE_NAME,
            "repo": REPOSITORY_URL,
            "branch": REPOSITORY_BRANCH,
            "autoDeploy": "no",
            "rootDir": "",
            "serviceDetails": service_details(),
        },
    )
    api.request("PUT", f"/services/{service_id}/env-vars", env_vars)
    return service, None, False


def find_or_trigger_deploy(api: RenderAPI, service_id: str, deploy_id: str | None) -> str:
    if deploy_id:
        return deploy_id
    time.sleep(5)
    rows = api.request("GET", f"/services/{service_id}/deploys?limit=20") or []
    deploys = [row.get("deploy", row) for row in rows if isinstance(row, dict)]
    active = [deploy for deploy in deploys if deploy.get("status") in ACTIVE_DEPLOY_STATES]
    if active:
        return str(active[0]["id"])
    deploy = api.request(
        "POST",
        f"/services/{service_id}/deploys",
        {"clearCache": "clear"},
    )
    if not isinstance(deploy, dict) or not deploy.get("id"):
        raise RuntimeError(f"Render did not return a deploy ID: {deploy!r}")
    return str(deploy["id"])


def wait_for_deploy(api: RenderAPI, service_id: str, deploy_id: str) -> dict[str, Any]:
    final: dict[str, Any] = {}
    for _ in range(180):
        final = api.request("GET", f"/services/{service_id}/deploys/{deploy_id}") or {}
        deploy_status = str(final.get("status") or "unknown")
        print(json.dumps({"render_deploy": deploy_id, "status": deploy_status}), flush=True)
        if deploy_status == "live":
            return final
        if deploy_status in TERMINAL_DEPLOY_FAILURES:
            raise RuntimeError(f"Render deploy {deploy_id} failed with status {deploy_status}")
        time.sleep(10)
    raise RuntimeError(f"Render deploy {deploy_id} did not become live")


def app_url_for(service: dict[str, Any]) -> str:
    details = service.get("serviceDetails") if isinstance(service.get("serviceDetails"), dict) else {}
    candidate = details.get("url") or service.get("url")
    if candidate:
        return str(candidate).rstrip("/")
    slug = str(service.get("slug") or "").strip()
    if not slug:
        raise RuntimeError("Render service did not provide a URL or slug")
    return f"https://{slug}.onrender.com"


def fetch_json(
    app_url: str,
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> Any:
    request = urllib.request.Request(
        app_url + path,
        method=method,
        headers={"User-Agent": "DropFinder-Deployment-Verifier/1.0", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_http(app_url: str) -> tuple[dict[str, Any], dict[str, Any]]:
    last_error = ""
    for _ in range(90):
        try:
            health = fetch_json(app_url, "/health")
            ready = fetch_json(app_url, "/ready")
            if health.get("status") == "healthy" and ready.get("ready") is True:
                return health, ready
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            print(f"Render health verification retry: {last_error}", flush=True)
        time.sleep(10)
    raise RuntimeError(f"Render service never passed health/readiness checks: {last_error}")


def verify_hosted_scan(app_url: str, operator_token: str) -> dict[str, Any]:
    initial = fetch_json(app_url, "/api/scan-state")
    initial_count = int(initial.get("scan_count") or 0)
    initial_success = initial.get("last_success_at")
    trigger = fetch_json(
        app_url,
        "/api/scan",
        method="POST",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    print("Hosted scan trigger:", json.dumps(trigger, sort_keys=True), flush=True)

    latest = initial
    saw_scan = bool(initial.get("running"))
    for _ in range(120):
        latest = fetch_json(app_url, "/api/scan-state")
        current_count = int(latest.get("scan_count") or 0)
        saw_scan = saw_scan or bool(latest.get("running")) or current_count > initial_count
        fresh_success = latest.get("last_success_at") and latest.get("last_success_at") != initial_success
        print("Hosted scan state:", json.dumps(latest, sort_keys=True), flush=True)
        if saw_scan and not latest.get("running") and fresh_success and not latest.get("last_error"):
            return latest
        time.sleep(15)
    raise RuntimeError(f"hosted Render scan did not complete successfully: {latest}")


def verify_catalog(app_url: str) -> dict[str, Any]:
    health = fetch_json(app_url, "/health")
    ready = fetch_json(app_url, "/ready")
    catalog = fetch_json(app_url, "/api/catalog")
    source_status = fetch_json(app_url, "/api/status")
    runtime = fetch_json(app_url, "/api/runtime")
    products = catalog.get("products") or []

    if health.get("status") != "healthy" or ready.get("ready") is not True:
        raise RuntimeError("post-scan health/readiness verification failed")
    if catalog.get("product_count") != len(products):
        raise RuntimeError("hosted catalog count invariant failed")
    if source_status.get("degraded_sources") != 0:
        raise RuntimeError("hosted source health invariant failed")
    if source_status.get("healthy_sources") != source_status.get("enabled_sources"):
        raise RuntimeError("hosted active-source invariant failed")
    if source_status.get("mode") != "render_autonomous_service":
        raise RuntimeError(f"unexpected hosted mode: {source_status.get('mode')}")
    if any(
        not product.get("classification_evidence", {}).get("explicit_thca")
        or not product.get("classification_evidence", {}).get("explicit_flower")
        for product in products
    ):
        raise RuntimeError("hosted product-evidence invariant failed")
    return {
        "health": health,
        "ready": ready,
        "catalog": catalog,
        "status": source_status,
        "runtime": runtime,
    }


def main() -> int:
    render_token = required_env("RENDER_API_KEY", minimum=12)
    hf_token = required_env("HF_TOKEN", minimum=8)
    operator_token = required_env("DROPFINDER_OPERATOR_TOKEN", minimum=24)
    state_repo = required_env("HF_STATE_REPO", minimum=3)

    api = RenderAPI(render_token)
    owner = select_owner(api)
    owner_id = str(owner.get("id") or "")
    if not owner_id:
        raise RuntimeError("Render workspace did not contain an ID")

    service, deploy_id, created = create_or_update_service(
        api,
        owner_id,
        render_env(hf_token, operator_token, state_repo),
    )
    service_id = str(service.get("id") or "")
    if not service_id:
        raise RuntimeError(f"Render service did not contain an ID: {service!r}")
    deploy_id = find_or_trigger_deploy(api, service_id, deploy_id)
    deploy = wait_for_deploy(api, service_id, deploy_id)
    service = api.request("GET", f"/services/{service_id}") or service
    app_url = app_url_for(service)
    health, ready = wait_for_http(app_url)
    scan = verify_hosted_scan(app_url, operator_token)
    verified = verify_catalog(app_url)

    receipt = {
        "schema_version": "dropfinder-render-deployment-v1",
        "status": "healthy",
        "verified_at": utc_now(),
        "hosting_provider": "render",
        "hosting_plan": "free",
        "service_created": created,
        "service_id": service_id,
        "service_name": SERVICE_NAME,
        "service_url": app_url,
        "dashboard_url": service.get("dashboardUrl"),
        "deploy_id": deploy_id,
        "deploy_status": deploy.get("status"),
        "repository": REPOSITORY_URL,
        "branch": REPOSITORY_BRANCH,
        "state_repository": state_repo,
        "state_repository_private": True,
        "requires_user_pc": False,
        "hosting_account_count": 2,
        "health": health,
        "ready": ready,
        "scan": scan,
        "product_count": verified["catalog"].get("product_count"),
        "healthy_sources": verified["status"].get("healthy_sources"),
        "degraded_sources": verified["status"].get("degraded_sources"),
        "runtime_mode": verified["status"].get("mode"),
    }
    output = Path(os.getenv("DROPFINDER_DEPLOYMENT_RECEIPT", "deployment/render-deployment.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Render deployment failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
