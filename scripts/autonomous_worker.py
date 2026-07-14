#!/usr/bin/env python3
"""Run real storefront retrieval workers on a deterministic GitHub Actions shard."""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cloud_scan as core  # type: ignore
import cloud_scan_v2 as aggregate  # type: ignore


def gate(products: list[dict]) -> tuple[bool, list[str], dict]:
    reasons: list[str] = []
    count = len(products)
    valid_urls = sum(bool(str(row.get("url") or "").strip()) for row in products)
    priced = sum(core.num(row.get("price")) is not None for row in products)
    if count == 0:
        reasons.append("no_qualifying_products")
    if count and valid_urls / count < 0.90:
        reasons.append("insufficient_product_urls")
    if count and priced == 0:
        reasons.append("no_priced_products")
    return not reasons, reasons, {
        "products": count,
        "url_coverage": round(valid_urls / count, 4) if count else 0,
        "priced_products": priced,
    }


def scan_source(source: tuple) -> tuple[list[dict], dict]:
    started = time.monotonic()
    products, status = aggregate.scan_all_routes(source)
    admitted, reasons, quality = gate(products)
    status = dict(status)
    status.update(
        admitted=admitted,
        status="healthy" if admitted else "quarantined",
        reason_codes=reasons,
        quality=quality,
        worker="cloud_scan_v2",
        duration_seconds=round(time.monotonic() - started, 3),
    )
    return products if admitted else [], status


def run(shard: int, shards: int, output: Path, workers: int) -> int:
    selected = [source for index, source in enumerate(core.SOURCES) if index % shards == shard]
    output.mkdir(parents=True, exist_ok=True)
    products: list[dict] = []
    statuses: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(selected) or 1))) as pool:
        futures = {pool.submit(scan_source, source): source[0] for source in selected}
        for future in as_completed(futures):
            source_id = futures[future]
            try:
                rows, status = future.result()
            except Exception as exc:
                rows = []
                status = {
                    "source_id": source_id,
                    "name": source_id,
                    "enabled": True,
                    "admitted": False,
                    "status": "quarantined",
                    "products": 0,
                    "reason_codes": ["worker_exception"],
                    "error": f"{type(exc).__name__}: {core.text(exc)[:500]}",
                    "quality": {"products": 0, "url_coverage": 0, "priced_products": 0},
                    "worker": "cloud_scan_v2",
                }
            products.extend(rows)
            statuses.append(status)
            print(json.dumps({"source": source_id, "status": status["status"], "products": len(rows)}), flush=True)
    payload = {
        "schema_version": "dropfinder-autonomous-shard-v1",
        "generated_at": core.now(),
        "shard": shard,
        "shards": shards,
        "products": core.dedupe(products),
        "sources": sorted(statuses, key=lambda row: str(row.get("source_id") or "")),
    }
    (output / f"shard-{shard}.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def self_test() -> int:
    good = [{"url": "https://example.test/p", "price": 10}]
    assert gate(good)[0]
    assert not gate([])[0]
    assert not gate([{"url": "https://example.test/p", "price": None}])[0]
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("scan-output"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.shards < 1 or not 0 <= args.shard < args.shards:
        parser.error("invalid shard configuration")
    return run(args.shard, args.shards, args.output, args.workers)


if __name__ == "__main__":
    raise SystemExit(main())
