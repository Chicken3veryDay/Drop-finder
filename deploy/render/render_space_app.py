from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import space_app as base

if str(base.SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(base.SCRIPTS_DIR))

from catalog_normalization import (  # type: ignore
    NORMALIZATION_CONTRACT,
    normalization_failures,
)

WORKER_SCRIPT = os.getenv("DROPFINDER_WORKER_SCRIPT", "autonomous_worker_v6.py").strip()
MERGER_SCRIPT = os.getenv("DROPFINDER_MERGER_SCRIPT", "autonomous_merge_complete.py").strip()
REQUIRED_CONTRACT = os.getenv(
    "DROPFINDER_REQUIRED_COMPARISON_CONTRACT",
    "exact_price_weight_ppg_thca_stock_image_v1",
).strip()
REQUIRED_NORMALIZATION = os.getenv(
    "DROPFINDER_REQUIRED_NORMALIZATION_CONTRACT",
    NORMALIZATION_CONTRACT,
).strip()
EXACT_PRICING = {"exact_variant", "exact_title"}
KNOWN_STOCK = {"in_stock", "out_of_stock"}


def _positive(value: object) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _product_failures(product: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    price = _positive(product.get("price"))
    grams = _positive(product.get("grams"))
    ppg = _positive(product.get("price_per_gram"))
    thca = _positive(product.get("thca"))
    if product.get("comparison_complete") is not True:
        failures.append("comparison_complete")
    if product.get("comparison_contract") != REQUIRED_CONTRACT:
        failures.append("comparison_contract")
    if product.get("normalization_contract") != REQUIRED_NORMALIZATION:
        failures.append("normalization_contract")
    if price is None:
        failures.append("price")
    if grams is None:
        failures.append("grams")
    if ppg is None:
        failures.append("price_per_gram")
    if product.get("pricing_confidence") not in EXACT_PRICING:
        failures.append("pricing_confidence")
    if product.get("weight_source") not in {"variant", "title"}:
        failures.append("weight_source")
    if thca is None or thca > 100:
        failures.append("thca")
    if product.get("availability") not in KNOWN_STOCK:
        failures.append("availability")
    if not str(product.get("image") or "").startswith(("http://", "https://")):
        failures.append("image")
    if not str(product.get("url") or "").startswith(("http://", "https://")):
        failures.append("url")
    if price is not None and grams is not None and ppg is not None:
        calculated = round(price / grams, 4)
        if abs(calculated - ppg) > max(0.02, calculated * 0.01):
            failures.append("price_per_gram_arithmetic")
    failures.extend(normalization_failures(product))
    return sorted(set(failures))


def _validate_output(output_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    catalog = base._read_json(output_root / "catalog.json", {})
    status_payload = base._read_json(output_root / "status.json", {})
    runtime_payload = base._read_json(output_root / "runtime.json", {})
    if not isinstance(catalog, dict) or not isinstance(status_payload, dict) or not isinstance(runtime_payload, dict):
        raise RuntimeError("strict scan output metadata is invalid")
    products = catalog.get("products")
    if not isinstance(products, list) or catalog.get("product_count") != len(products):
        raise RuntimeError("catalog count invariant failed")
    if len(products) < base.MIN_PRODUCTS:
        raise RuntimeError(f"complete product floor failed: {len(products)} < {base.MIN_PRODUCTS}")
    if catalog.get("comparison_contract") != REQUIRED_CONTRACT:
        raise RuntimeError(f"catalog comparison contract failed: {catalog.get('comparison_contract')}")
    if status_payload.get("comparison_contract") != REQUIRED_CONTRACT:
        raise RuntimeError(f"status comparison contract failed: {status_payload.get('comparison_contract')}")
    if runtime_payload.get("comparison_contract") != REQUIRED_CONTRACT:
        raise RuntimeError(f"runtime comparison contract failed: {runtime_payload.get('comparison_contract')}")
    if catalog.get("normalization_contract") != REQUIRED_NORMALIZATION:
        raise RuntimeError(f"catalog normalization contract failed: {catalog.get('normalization_contract')}")
    if status_payload.get("normalization_contract") != REQUIRED_NORMALIZATION:
        raise RuntimeError(f"status normalization contract failed: {status_payload.get('normalization_contract')}")
    if runtime_payload.get("normalization_contract") != REQUIRED_NORMALIZATION:
        raise RuntimeError(f"runtime normalization contract failed: {runtime_payload.get('normalization_contract')}")
    if status_payload.get("services", {}).get("final_normalizer") != "healthy":
        raise RuntimeError("final normalizer is not healthy")
    if status_payload.get("degraded_sources") != 0:
        raise RuntimeError("degraded source invariant failed")
    if status_payload.get("healthy_sources") != status_payload.get("enabled_sources"):
        raise RuntimeError("healthy source invariant failed")
    if int(status_payload.get("healthy_sources") or 0) < base.MIN_ACTIVE:
        raise RuntimeError(
            f"active source floor failed: {status_payload.get('healthy_sources')} < {base.MIN_ACTIVE}"
        )
    failures = []
    for product in products:
        failed = _product_failures(product)
        evidence = product.get("classification_evidence") if isinstance(product.get("classification_evidence"), dict) else {}
        if not evidence.get("explicit_thca"):
            failed.append("explicit_thca_evidence")
        if not evidence.get("explicit_flower"):
            failed.append("explicit_flower_evidence")
        if failed:
            failures.append({"id": product.get("id"), "source_id": product.get("source_id"), "failed": sorted(set(failed))})
    if failures:
        raise RuntimeError(f"complete product contract failed for {len(failures)} rows: {failures[:10]}")
    return catalog, status_payload, runtime_payload


def run_scan(reason: str = "scheduled") -> bool:
    if not base.SCAN_LOCK.acquire(blocking=False):
        return False
    started_monotonic = time.monotonic()
    started_at = base.utc_now()
    with base.STATE_LOCK:
        base.SCAN_STATE.update(
            running=True,
            last_started_at=started_at,
            last_error=None,
            scan_count=int(base.SCAN_STATE.get("scan_count") or 0) + 1,
            trigger=reason,
            worker_script=WORKER_SCRIPT,
            merger_script=MERGER_SCRIPT,
            required_contract=REQUIRED_CONTRACT,
            required_normalization_contract=REQUIRED_NORMALIZATION,
        )
    base._persist_scan_state()
    run_root = base.RUNTIME_DIR / "runs" / started_at.replace(":", "-")
    shard_root = run_root / "shards"
    output_root = run_root / "output"
    shard_root.mkdir(parents=True, exist_ok=True)
    log_path = base.LOG_DIR / "latest-scan.log"
    success = False
    try:
        worker_path = base.SCRIPTS_DIR / WORKER_SCRIPT
        merger_path = base.SCRIPTS_DIR / MERGER_SCRIPT
        if not worker_path.is_file():
            raise RuntimeError(f"configured worker script is missing: {worker_path}")
        if not merger_path.is_file():
            raise RuntimeError(f"configured merger script is missing: {merger_path}")
        with log_path.open("w", encoding="utf-8") as log:
            log.write(
                f"DropFinder strict scan started {started_at}; trigger={reason}; "
                f"worker={WORKER_SCRIPT}; merger={MERGER_SCRIPT}; "
                f"comparison={REQUIRED_CONTRACT}; normalization={REQUIRED_NORMALIZATION}\n"
            )
            base._run_command(
                [
                    sys.executable,
                    str(worker_path),
                    "--shard",
                    "0",
                    "--shards",
                    "1",
                    "--workers",
                    str(base.SCAN_WORKERS),
                    "--output",
                    str(shard_root),
                ],
                log,
            )
            base._run_command(
                [
                    sys.executable,
                    str(merger_path),
                    "--input",
                    str(shard_root),
                    "--output",
                    str(output_root),
                    "--min-active",
                    str(base.MIN_ACTIVE),
                    "--min-products",
                    str(base.MIN_PRODUCTS),
                ],
                log,
            )

        catalog, status_payload, runtime_payload = _validate_output(output_root)
        status_payload["mode"] = "render_autonomous_service"
        status_payload["worker_script"] = WORKER_SCRIPT
        status_payload["merger_script"] = MERGER_SCRIPT
        runtime_payload.update(
            mode="render_autonomous_service",
            persistent_state="private_huggingface_dataset",
            scheduled_scan_interval_seconds=base.SCAN_INTERVAL,
            worker_script=WORKER_SCRIPT,
            merger_script=MERGER_SCRIPT,
        )
        base._write_json(output_root / "status.json", status_payload)
        base._write_json(output_root / "runtime.json", runtime_payload)
        base._publish_output(output_root)
        success = True
        with base.STATE_LOCK:
            base.SCAN_STATE["last_success_at"] = base.utc_now()
            base.SCAN_STATE["published_products"] = catalog.get("product_count")
    except Exception as exc:
        with base.STATE_LOCK:
            base.SCAN_STATE["last_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        with base.STATE_LOCK:
            base.SCAN_STATE.update(
                running=False,
                last_finished_at=base.utc_now(),
                last_duration_seconds=round(time.monotonic() - started_monotonic, 3),
            )
        base._persist_scan_state()
        base.SCAN_LOCK.release()
        runs_root = base.RUNTIME_DIR / "runs"
        for old in sorted(runs_root.glob("*"))[:-3] if runs_root.exists() else []:
            shutil.rmtree(old, ignore_errors=True)
    return success


base.run_scan = run_scan
_original_health = base.health


def health() -> dict[str, Any]:
    payload = _original_health()
    payload.update(
        worker_script=WORKER_SCRIPT,
        merger_script=MERGER_SCRIPT,
        required_contract=REQUIRED_CONTRACT,
        required_normalization_contract=REQUIRED_NORMALIZATION,
    )
    return payload


for route in base.app.router.routes:
    if getattr(route, "path", None) == "/health":
        route.endpoint = health
        break

app = base.app
