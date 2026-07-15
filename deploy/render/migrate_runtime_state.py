from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNTIME_DIR = Path(os.getenv("DROPFINDER_RUNTIME_DIR", "/app/runtime")).resolve()
DATA_DIR = RUNTIME_DIR / "data"
SCRIPTS_DIR = Path(os.getenv("DROPFINDER_SCRIPTS_DIR", "/app/scripts")).resolve()
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from catalog_normalization import (  # type: ignore
    NORMALIZATION_CONTRACT,
    normalize_product,
    normalization_failures,
)

COMPARISON_CONTRACT = os.getenv(
    "DROPFINDER_REQUIRED_COMPARISON_CONTRACT",
    "exact_price_weight_ppg_thca_stock_image_v1",
).strip()
NORMALIZATION_REQUIRED = os.getenv(
    "DROPFINDER_REQUIRED_NORMALIZATION_CONTRACT",
    NORMALIZATION_CONTRACT,
).strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".migration.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def migrate() -> dict[str, Any]:
    catalog_path = DATA_DIR / "catalog.json"
    status_path = DATA_DIR / "status.json"
    runtime_path = DATA_DIR / "runtime.json"
    catalog = read_json(catalog_path, {})
    status = read_json(status_path, {})
    runtime = read_json(runtime_path, {})
    products = catalog.get("products") if isinstance(catalog, dict) else None
    if not isinstance(products, list) or not products:
        return {
            "status": "no_catalog",
            "migrated_products": 0,
            "normalization_contract": NORMALIZATION_REQUIRED,
        }
    if catalog.get("comparison_contract") != COMPARISON_CONTRACT:
        raise RuntimeError(
            f"persisted catalog comparison contract is not eligible for migration: {catalog.get('comparison_contract')}"
        )

    normalized: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for product in products:
        if not isinstance(product, dict):
            failures.append({"id": None, "failed": ["non_object_product"]})
            continue
        row = normalize_product(product)
        failed = normalization_failures(row)
        if product.get("comparison_complete") is not True:
            failed.append("comparison_complete")
        if product.get("comparison_contract") != COMPARISON_CONTRACT:
            failed.append("comparison_contract")
        if failed:
            failures.append({
                "id": product.get("id"),
                "source_id": product.get("source_id"),
                "raw_name": product.get("name"),
                "failed": sorted(set(failed)),
            })
        else:
            normalized.append(row)
    if failures:
        raise RuntimeError(f"persisted catalog normalization migration failed for {len(failures)} rows: {failures[:10]}")
    if len(normalized) != len(products):
        raise RuntimeError("persisted catalog normalization changed product count")

    migrated_at = utc_now()
    catalog.update(
        products=normalized,
        product_count=len(normalized),
        normalization_contract=NORMALIZATION_REQUIRED,
        normalization_migrated_at=migrated_at,
    )
    status = dict(status) if isinstance(status, dict) else {}
    services = dict(status.get("services") or {})
    services["final_normalizer"] = "healthy"
    status.update(
        normalization_contract=NORMALIZATION_REQUIRED,
        normalization_migrated_at=migrated_at,
        complete_products=len(normalized),
        product_count=len(normalized),
        services=services,
    )
    runtime = dict(runtime) if isinstance(runtime, dict) else {}
    runtime.update(
        normalization_contract=NORMALIZATION_REQUIRED,
        normalization_migrated_at=migrated_at,
        complete_products=len(normalized),
        products=len(normalized),
    )

    write_json(catalog_path, catalog)
    write_json(status_path, status)
    write_json(runtime_path, runtime)
    receipt = {
        "schema_version": "dropfinder-runtime-normalization-migration-v1",
        "status": "healthy",
        "migrated_at": migrated_at,
        "migrated_products": len(normalized),
        "comparison_contract": COMPARISON_CONTRACT,
        "normalization_contract": NORMALIZATION_REQUIRED,
        "field_failure_count": 0,
    }
    write_json(RUNTIME_DIR / "normalization-migration.json", receipt)
    return receipt


def main() -> int:
    receipt = migrate()
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
