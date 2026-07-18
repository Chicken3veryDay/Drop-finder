"""Bounded transport validation for autonomous-worker fallback category routes."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})


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
                    normalized_type = str(content_type or "").split(";", 1)[0].strip().lower()
                    result.update(http_status=http_status, content_type=normalized_type)
                    if http_status != 200:
                        retryable = http_status in reliability.RETRYABLE_HTTP
                        result.update(
                            status="retryable_error" if retryable else "error",
                            error_category="http_status",
                            retryable=retryable,
                            error=f"unexpected_http_status:{http_status}",
                        )
                    elif normalized_type not in HTML_CONTENT_TYPES:
                        result.update(
                            status="error",
                            error_category="unexpected_content_type",
                            retryable=False,
                            error=f"unexpected_content_type:{normalized_type or 'unknown'}",
                        )
                    else:
                        candidates = worker.card_candidates(payload, route)
                        extracted: list[dict] = []
                        conversion_errors = 0
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
                                        conversion_errors += 1
                                        row = None
                                    if row:
                                        extracted.append(row)
                        terminal_rows = worker.core.dedupe(extracted)
                        result.update(
                            status="healthy" if terminal_rows else "empty",
                            error_category=None,
                            retryable=False,
                            candidates=len(candidates),
                            conversion_errors=conversion_errors,
                            products=len(terminal_rows),
                        )
                except Exception as exc:
                    failure = worker.aggregate.classify_route_failure(exc)
                    result.update(
                        status="retryable_error" if failure["retryable"] else "error",
                        error=f"{type(exc).__name__}: {worker.core.text(exc)[:300]}",
                        **failure,
                    )
                result["duration_seconds"] = round(time.monotonic() - started, 3)
                attempts.append(result)
                if result.get("status") != "retryable_error":
                    break
            rows.extend(terminal_rows)
        return worker.core.dedupe(rows), attempts

    worker.fallback_scan = resilient_fallback_scan
    return resilient_fallback_scan


def self_test(reliability) -> int:
    """Exercise transport decisions without network access or retry sleeps."""
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
        worker.candidate_to_row = lambda candidate, source_id, vendor: {
            "source_id": source_id,
            "url": candidate["url"],
            "variant": "",
        }
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

        transport_responses = iter([
            TimeoutError("timed out"),
            ("<a>ok</a>", "application/xhtml+xml; charset=utf-8", 200),
        ])

        def fetch_after_timeout(target):
            response = next(transport_responses)
            if isinstance(response, Exception):
                raise response
            return response

        worker.core.fetch = fetch_after_timeout
        rows, attempts = scan(("fixture", "Fixture", []))
        assert len(rows) == 1
        assert [row["status"] for row in attempts] == ["retryable_error", "healthy"]
        assert attempts[0]["error_category"] == "transport_timeout"

        worker.core.fetch = lambda target: (_ for _ in ()).throw(ValueError("invalid fixture"))
        rows, attempts = scan(("fixture", "Fixture", []))
        assert not rows and len(attempts) == 1
        assert attempts[0]["status"] == "error"
        assert attempts[0]["error_category"] == "processing_error"

        worker.core.fetch = lambda target: ("not html", "application/json", 200)
        rows, attempts = scan(("fixture", "Fixture", []))
        assert not rows and len(attempts) == 1
        assert attempts[0]["error_category"] == "unexpected_content_type"

        worker.core.fetch = lambda target: ("blocked", "text/html", 403)
        rows, attempts = scan(("fixture", "Fixture", []))
        assert not rows and len(attempts) == 3
        assert all(row["retryable"] is True for row in attempts)

        worker.core.fetch = lambda target: ("missing", "text/html", 404)
        rows, attempts = scan(("fixture", "Fixture", []))
        assert not rows and len(attempts) == 1
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
