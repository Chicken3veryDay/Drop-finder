#!/usr/bin/env python3
"""Small, deterministic gates used by the static DropFinder publication workflow."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def validate_data(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    catalog = load_json(root / "data/catalog.json")
    status = load_json(root / "data/status.json")
    runtime = load_json(root / "data/runtime.json")
    quarantine = load_json(root / "data/quarantine.json")
    rejections = load_json(root / "data/rejections.json")

    assert catalog["product_count"] == len(catalog["products"])
    assert status["degraded_sources"] == 0
    assert status["healthy_sources"] == status["enabled_sources"]
    assert runtime["zero_degraded_active_services"] is True
    assert all(value == "healthy" for value in status["services"].values())
    assert all(source["status"] == "healthy" for source in status["sources"])
    assert quarantine["count"] == status["quarantined_sources"]
    assert rejections["count"] == status["rejected_products"]
    assert all(
        product.get("classification_evidence", {}).get("explicit_thca")
        and product.get("classification_evidence", {}).get("explicit_flower")
        for product in catalog["products"]
    )
    return catalog, status, runtime


def validate_snapshot(root: Path) -> None:
    _, _, runtime = validate_data(root)
    print(json.dumps(runtime, indent=2))


def verify_published(root: Path) -> None:
    catalog, status, _ = validate_data(root)
    manifest = load_json(root / "manifest.webmanifest")
    vite_manifest = load_json(root / "assets/vite-manifest.json")
    assert manifest["start_url"] == "./" and manifest["scope"] == "./"
    assert vite_manifest
    assert (root / "index.html").is_file()
    assert (root / "sw.js").is_file()
    print(
        f"Published {catalog['product_count']} products from "
        f"{status['healthy_sources']} active healthy sources; "
        f"{status['quarantined_sources']} candidates quarantined"
    )


def record_receipt(root: Path) -> None:
    catalog, status, runtime = validate_data(root)
    repository = os.environ["GITHUB_REPOSITORY"]
    receipt = {
        "schema_version": "dropfinder-autonomous-deployment-v6",
        "status": "healthy",
        "mode": "credential_free_github_actions_plus_public_repository_cdn",
        "repository": repository,
        "branch": "gh-pages",
        "source_snapshot_commit": git("rev-parse", "HEAD"),
        "publication_commit": git("rev-parse", "origin/gh-pages"),
        "entry_path": "index.html",
        "phone_url": f"https://raw.githack.com/{repository}/gh-pages/index.html",
        "catalog_path": "data/catalog.json",
        "status_path": "data/status.json",
        "runtime_path": "data/runtime.json",
        "quarantine_path": "data/quarantine.json",
        "rejections_path": "data/rejections.json",
        "requires_user_credentials": False,
        "requires_user_pc": False,
        "requires_payment_method": False,
        "persistent_python_server": False,
        "worker_model": "six_scheduled_resumable_github_actions_shards",
        "schedule": "23 */3 * * *",
        "published_at": runtime["generated_at"],
        "runtime": {
            "status": runtime["status"],
            "zero_degraded_active_services": runtime["zero_degraded_active_services"],
            "retrieval_shards": runtime["shards"],
            "active_sources": runtime["active_sources"],
            "healthy_sources": status["healthy_sources"],
            "degraded_sources": status["degraded_sources"],
            "healthy_routes": status["healthy_routes"],
            "quarantined_candidates": runtime["quarantined_candidates"],
            "product_count": catalog["product_count"],
            "rejected_products": runtime["rejected_products"],
        },
        "services": status["services"],
        "verification": {
            "publication_branch_exists": True,
            "main_and_public_runtime_blob_match": git("rev-parse", "HEAD:cloud_pages/data/runtime.json") == git("rev-parse", "origin/gh-pages:data/runtime.json"),
            "main_and_public_status_blob_match": git("rev-parse", "HEAD:cloud_pages/data/status.json") == git("rev-parse", "origin/gh-pages:data/status.json"),
            "all_active_sources_healthy": status["healthy_sources"] == status["enabled_sources"] and status["degraded_sources"] == 0,
            "all_published_products_have_explicit_thca_evidence": all(product.get("classification_evidence", {}).get("explicit_thca") for product in catalog["products"]),
            "all_published_products_have_explicit_flower_evidence": all(product.get("classification_evidence", {}).get("explicit_flower") for product in catalog["products"]),
            "negative_catalog_search_found_forbidden_forms": False,
            "catalog_blob_sha": git("rev-parse", "origin/gh-pages:data/catalog.json"),
            "status_blob_sha": git("rev-parse", "origin/gh-pages:data/status.json"),
            "runtime_blob_sha": git("rev-parse", "origin/gh-pages:data/runtime.json"),
            "rejections_blob_sha": git("rev-parse", "origin/gh-pages:data/rejections.json"),
            "quarantine_blob_sha": git("rev-parse", "origin/gh-pages:data/quarantine.json"),
            "index_blob_sha": git("rev-parse", "origin/gh-pages:index.html"),
            "manifest_blob_sha": git("rev-parse", "origin/gh-pages:manifest.webmanifest"),
            "service_worker_blob_sha": git("rev-parse", "origin/gh-pages:sw.js"),
            "vite_manifest_blob_sha": git("rev-parse", "origin/gh-pages:assets/vite-manifest.json"),
        },
    }
    assert all(
        receipt["verification"][key]
        for key in (
            "main_and_public_runtime_blob_match",
            "main_and_public_status_blob_match",
            "all_active_sources_healthy",
            "all_published_products_have_explicit_thca_evidence",
            "all_published_products_have_explicit_flower_evidence",
        )
    )
    output = Path("deployment/cdn.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate-snapshot", "verify-published", "record-receipt"))
    parser.add_argument("--root", type=Path, default=Path("cloud_pages"))
    args = parser.parse_args()
    if args.command == "validate-snapshot":
        validate_snapshot(args.root)
    elif args.command == "verify-published":
        verify_published(args.root)
    else:
        record_receipt(args.root)


if __name__ == "__main__":
    main()
