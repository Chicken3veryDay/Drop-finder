from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / "cloud_pages"
OUT = Path(os.environ.get("AUDIT_REPORT", "/tmp/scraper-path-audit.json"))
UA = "DropFinderPathAudit/1.0 (+https://github.com/Chicken3veryDay/Drop-finder)"
TIMEOUT = 18
MAX_BYTES = 1_000_000


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_local_path(value: str) -> str | None:
    raw = str(value or "").strip()
    if not raw or raw.startswith(("http://", "https://", "data:", "blob:")):
        return None
    parsed = urllib.parse.urlsplit(raw)
    path = parsed.path.lstrip("./").lstrip("/")
    if path.startswith("Drop-finder/"):
        path = path[len("Drop-finder/"):]
    if not path or ".." in Path(path).parts:
        return None
    return path


def collect_path_fields(value: Any, prefix: str = "$") -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}"
            if key in {"path", "src", "href", "script", "stylesheet", "manifest", "compact_index", "vendors", "rejections"} and isinstance(child, str):
                local = normalized_local_path(child)
                if local:
                    found.append({"json_path": child_prefix, "reference": child, "local_path": local})
            found.extend(collect_path_fields(child, child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(collect_path_fields(child, f"{prefix}[{index}]"))
    return found


def probe(url: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json,text/html,application/xml;q=.8,*/*;q=.1",
            "Accept-Encoding": "identity",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            raw = response.read(MAX_BYTES + 1)
            return {
                "ok": 200 <= int(getattr(response, "status", 200)) < 400,
                "status": int(getattr(response, "status", 200)),
                "final_url": str(response.geturl()),
                "content_type": str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower(),
                "bytes": len(raw),
                "truncated": len(raw) > MAX_BYTES,
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": int(exc.code),
            "final_url": str(exc.geturl()),
            "content_type": str(exc.headers.get("Content-Type") or "").split(";", 1)[0].lower(),
            "error": f"HTTP {exc.code}",
        }
    except Exception as exc:
        return {"ok": False, "status": None, "final_url": url, "error": f"{type(exc).__name__}: {exc}"}


def alternate_candidates(route: dict[str, Any], healthy_urls: list[str]) -> list[str]:
    source_type = str(route.get("source_type") or "")
    url = str(route.get("url") or "")
    if not url:
        return []
    parsed = urllib.parse.urlsplit(url)
    origin = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")
    candidates: list[str] = []
    if source_type == "woo" or "/wp-json/wc/" in parsed.path:
        candidates.extend([
            f"{origin}/wp-json/wc/store/v1/products?per_page=100",
            f"{origin}/wp-json/wc/store/v1/products?per_page=100&search=flower",
            f"{origin}/wp-json/wc/store/v1/products?per_page=100&search=thca",
        ])
    if source_type == "shopify" or "/products.json" in parsed.path:
        collection_path = parsed.path.split("/products.json", 1)[0].rstrip("/")
        if collection_path:
            candidates.extend([
                f"{origin}{collection_path}",
                f"{origin}{collection_path}/products.json?limit=250",
            ])
        candidates.append(f"{origin}/products.json?limit=250")
    if source_type.startswith("html"):
        candidates.extend([f"{origin}/", f"{origin}/shop/", f"{origin}/collections/thca-flower", f"{origin}/product-category/thca-flower/"])
    candidates.extend(healthy_urls)
    deduped: list[str] = []
    for candidate in candidates:
        if candidate and candidate != url and candidate not in deduped:
            deduped.append(candidate)
    return deduped[:8]


def main() -> int:
    status = load(PAGES / "data" / "status.json")
    release = load(ROOT / "deployment" / "release.json")
    manifest = load(PAGES / "data" / "catalog-v4" / "manifest.json")
    index = load(PAGES / "data" / "catalog-v4" / "index.json")
    shell = load(PAGES / "app-shell.json")

    route_failures: list[dict[str, Any]] = []
    source_summaries: list[dict[str, Any]] = []
    configured_route_ids: set[str] = set()
    observed_route_ids: set[str] = set()

    for source in status.get("sources", []):
        healthy_urls = [
            str(item.get("url"))
            for item in source.get("route_results", [])
            if item.get("status") == "healthy" and item.get("url")
        ]
        source_failures: list[dict[str, Any]] = []
        for route in source.get("route_results", []):
            route_id = str(route.get("route_id") or "")
            if route_id:
                observed_route_ids.add(route_id)
                if not route_id.endswith("-product-verification"):
                    configured_route_ids.add(route_id)
            if route.get("status") == "healthy":
                continue
            record = {
                "source_id": source.get("source_id"),
                "source_name": source.get("name"),
                "route_id": route_id,
                "source_type": route.get("source_type"),
                "status": route.get("status"),
                "http_status": route.get("http_status"),
                "error": route.get("error"),
                "url": route.get("url"),
                "recorded_retry_attempt": route.get("retry_attempt"),
            }
            if route.get("url"):
                record["current_probe"] = probe(str(route["url"]))
                candidates = []
                for candidate in alternate_candidates(route, healthy_urls):
                    result = probe(candidate)
                    if result.get("ok"):
                        candidates.append({"url": candidate, "probe": result})
                record["working_candidates"] = candidates
            source_failures.append(record)
            route_failures.append(record)
        source_summaries.append({
            "source_id": source.get("source_id"),
            "name": source.get("name"),
            "status": source.get("status"),
            "enabled": source.get("enabled"),
            "active_route": source.get("active_route"),
            "products": source.get("products"),
            "healthy_routes": source.get("healthy_routes"),
            "non_healthy_routes": source.get("non_healthy_routes"),
            "failures": source_failures,
        })

    reference_documents = {
        "release": release,
        "manifest": manifest,
        "index": index,
        "app_shell": shell,
    }
    references: list[dict[str, Any]] = []
    for document_name, document in reference_documents.items():
        for ref in collect_path_fields(document, document_name):
            target = PAGES / ref["local_path"]
            ref["exists"] = target.is_file()
            ref["size"] = target.stat().st_size if target.is_file() else None
            references.append(ref)

    for path in sorted(release.get("catalog_v4_hashes", {})):
        target = PAGES / path
        references.append({
            "json_path": "release.catalog_v4_hashes",
            "reference": path,
            "local_path": path,
            "exists": target.is_file(),
            "size": target.stat().st_size if target.is_file() else None,
        })

    missing_refs = [ref for ref in references if not ref["exists"]]
    empty_refs = [ref for ref in references if ref["exists"] and ref.get("size") == 0]
    duplicate_refs = [
        path for path, count in Counter(ref["local_path"] for ref in references).items() if count > 1
    ]

    generation_ids = {
        "release": release.get("generation_id"),
        "manifest": manifest.get("generation_id"),
        "index": index.get("generation_id"),
    }
    generation_consistent = len({str(value) for value in generation_ids.values() if value}) == 1

    failures_by_status = Counter(str(item.get("http_status") or item.get("status") or "unknown") for item in route_failures)
    hard_missing = [
        item for item in route_failures
        if item.get("http_status") in {404, 410}
        or item.get("current_probe", {}).get("status") in {404, 410}
    ]
    blocked = [
        item for item in route_failures
        if item.get("http_status") in {401, 403, 429}
        or item.get("current_probe", {}).get("status") in {401, 403, 429}
    ]
    recovered_now = [item for item in route_failures if item.get("current_probe", {}).get("ok")]
    replacement_ready = [item for item in route_failures if item.get("working_candidates")]

    report = {
        "schema_version": "dropfinder-scraper-path-audit-v1",
        "source_commit": os.environ.get("SOURCE_COMMIT"),
        "release_generation": release.get("generation_id"),
        "status_generated_at": status.get("generated_at"),
        "counts": {
            "sources": len(status.get("sources", [])),
            "healthy_sources": status.get("healthy_sources"),
            "healthy_routes": status.get("healthy_routes"),
            "non_healthy_routes": status.get("non_healthy_routes"),
            "route_failure_records": len(route_failures),
            "hard_missing_routes": len(hard_missing),
            "blocked_routes": len(blocked),
            "recovered_routes": len(recovered_now),
            "replacement_ready_routes": len(replacement_ready),
            "path_references": len(references),
            "missing_path_references": len(missing_refs),
            "empty_path_references": len(empty_refs),
        },
        "generation_ids": generation_ids,
        "generation_consistent": generation_consistent,
        "failures_by_status": dict(sorted(failures_by_status.items())),
        "hard_missing_routes": hard_missing,
        "blocked_routes": blocked,
        "recovered_routes": recovered_now,
        "replacement_ready_routes": replacement_ready,
        "all_route_failures": route_failures,
        "source_summaries": source_summaries,
        "missing_path_references": missing_refs,
        "empty_path_references": empty_refs,
        "duplicate_reference_paths": duplicate_refs,
        "complete_data_graph": not missing_refs and not empty_refs and generation_consistent,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], sort_keys=True))
    print(json.dumps({"generation_consistent": generation_consistent, "complete_data_graph": report["complete_data_graph"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
