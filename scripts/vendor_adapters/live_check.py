"""Low-impact public route probes for vendor profile maintenance."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .fetch import fetch_public_document


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_live_checks(profiles_path: str | Path, *, workers: int = 4, timeout: float = 8.0, max_bytes: int = 512_000) -> dict[str, Any]:
    payload = json.loads(Path(profiles_path).read_text(encoding="utf-8"))
    jobs: list[tuple[str, str, set[str], str]] = []
    for profile in payload.get("vendors", []):
        vendor_id = str(profile["vendor_id"])
        hosts = set(str(item) for item in profile.get("allowed_document_hosts", []))
        jobs.append((vendor_id, str(profile["category_url"]), hosts, "category"))
        for lab_url in profile.get("lab_index_urls", []):
            jobs.append((vendor_id, str(lab_url), hosts, "lab_index"))
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        future_map = {
            pool.submit(fetch_public_document, url, allowed_hosts=hosts, timeout=timeout, max_bytes=max_bytes): (vendor_id, url, kind)
            for vendor_id, url, hosts, kind in jobs
        }
        for future in as_completed(future_map):
            vendor_id, url, kind = future_map[future]
            try:
                result = future.result()
                rows.append({
                    "vendor_id": vendor_id,
                    "kind": kind,
                    "url": url,
                    "final_url": result.final_url,
                    "status": result.status,
                    "content_type": result.content_type,
                    "bytes": len(result.body),
                    "ok": 200 <= result.status < 400 and not result.error,
                    "error": result.error,
                    "redirect_chain": list(result.redirect_chain),
                })
            except Exception as exc:  # a live maintenance report must preserve failure evidence
                rows.append({"vendor_id": vendor_id, "kind": kind, "url": url, "ok": False, "status": 0, "error": f"{type(exc).__name__}: {exc}"})
    rows.sort(key=lambda row: (row["vendor_id"], row["kind"], row["url"]))
    return {
        "schema_version": "dropfinder-vendor-live-check-v1",
        "generated_at": now(),
        "probe_count": len(rows),
        "success_count": sum(1 for row in rows if row.get("ok")),
        "failure_count": sum(1 for row in rows if not row.get("ok")),
        "checks": rows,
        "limitations": [
            "GET-only public probes; no checkout, account, identity submission, gate interaction, or bypass.",
            "A failed probe can be caused by WAF, rate limiting, routing, or site changes and does not prove the vendor is offline.",
        ],
    }
