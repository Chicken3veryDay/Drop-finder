"""Bounded transport validation for autonomous-worker fallback category routes."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}


def install(reliability):
    """Patch fallback category retrieval to share the production retry policy."""
    worker = reliability.worker

    def resilient_fallback_scan(source: tuple) -> tuple[list[dict], list[dict]]:
        source_id, vendor, _ = source
        targets = worker.FALLBACK_HTML_ROUTES.get(source_id, [])
        rows: list[dict] = []
        attempts: list[dict] = []
        for index, target in enumerate(targets, 1):
            route = ("html", target, "thca_flower")
            route_id = f"{source_id}-fallback-{index}"
            terminal_rows: list[dict] = []
            for retry_attempt, delay in enumerate(reliability.RETRY_DELAYS, start=1):
                if delay:
                    time.sleep(delay)
                started = time.monotonic()
                result = {
                    "route_id": route_id,
                    "url": target,
                    "source_type": "html_card_product_detail",
                    "retry_attempt": retry_attempt,
                }
                try:
                    payload, content_type, http_status = worker.core.fetch(target)
                    result.update(http_status=http_status, content_type=content_type)
                    if http_status != 200:
                        result["status"] = "retryable_error" if http_status in reliability.RETRYABLE_HTTP else "error"
                        result["error"] = f"unexpected_http_status:{http_status}"
                    elif content_type not in HTML_CONTENT_TYPES:
                        result.update(status="error", error=f"unexpected_content_type:{content_type or 'unknown'}")
                    else:
                        candidates = worker.card_candidates(payload, route)
                        extracted: list[dict] = []
                        if candidates:
                            with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as pool:
                                futures = {
                                    pool.submit(worker.candidate_to_row, candidate, source_id, vendor): candidate
                                    for candidate in candidates
                                }
                                for future in as_completed(futures):
                                    try:
                                        row = future.result()
                                    except Exception:
                                        row = None
                                    if row:
                                        extracted.append(row)
                        terminal_rows = worker.core.dedupe(extracted)
                        result.update(
                            status="healthy" if terminal_rows else "empty",
                            candidates=len(candidates),
                            products=len(terminal_rows),
                        )
                except Exception as exc:
                    result.update(status="error", error=f"{type(exc).__name__}: {worker.core.text(exc)[:300]}")
                result["duration_seconds"] = round(time.monotonic() - started, 3)
                attempts.append(result)
                if result.get("status") != "retryable_error":
                    break
            rows.extend(terminal_rows)
        return worker.core.dedupe(rows), attempts

    worker.fallback_scan = resilient_fallback_scan
    return resilient_fallback_scan


def self_test(reliability) -> int:
    """Exercise transport decisions without network access or real retry sleeps."""
    worker = reliability.worker
    original_fetch = worker.core.fetch
    original_routes = dict(worker.FALLBACK_HTML_ROUTES)
    original_delays = reliability.RETRY_DELAYS
    original_cards = worker.card_candidates
    original_convert = worker.candidate_to_row
    try:
        reliability.RETRY_DELAYS = (0.0, 0.0, 0.0)
        worker.FALLBACK_HTML_ROUTES["fixture"] = ["https://example.test/category"]
        worker.card_candidates = lambda payload, route: [{"url": "https://example.test/products/a"}]
        worker.candidate_to_row = lambda candidate, source_id, vendor: {"source_id": source_id, "url": candidate["url"], "variant": ""}
        scan = install(reliability)

        responses = iter([
            ("processing", "text/html", 202),
            ("<a>ok</a>", "text/html", 200),
        ])
        worker.core.fetch = lambda target: next(responses)
        rows, attempts = scan(("fixture", "Fixture", []))
        assert len(rows) == 1
        assert [row["http_status"] for row in attempts] == [202, 200]
        assert [row["retry_attempt"] for row in attempts] == [1, 2]
        assert attempts[-1]["status"] == "healthy"

        worker.core.fetch = lambda target: ("processing", "text/html", 202)
        rows, attempts = scan(("fixture", "Fixture", []))
        assert not rows and len(attempts) == 3
        assert all(row["status"] == "retryable_error" for row in attempts)

        worker.core.fetch = lambda target: ("not html", "application/json", 200)
        rows, attempts = scan(("fixture", "Fixture", []))
        assert not rows and len(attempts) == 1
        assert attempts[0]["status"] == "error"
        assert attempts[0]["error"].startswith("unexpected_content_type:")

        worker.core.fetch = lambda target: ("missing", "text/html", 404)
        rows, attempts = scan(("fixture", "Fixture", []))
        assert not rows and len(attempts) == 1
        assert attempts[0]["http_status"] == 404
        assert attempts[0]["status"] == "error"
        return 0
    finally:
        worker.core.fetch = original_fetch
        worker.FALLBACK_HTML_ROUTES.clear()
        worker.FALLBACK_HTML_ROUTES.update(original_routes)
        reliability.RETRY_DELAYS = original_delays
        worker.card_candidates = original_cards
        worker.candidate_to_row = original_convert
        install(reliability)
