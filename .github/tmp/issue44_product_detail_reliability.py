from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


v4 = "scripts/autonomous_worker_v4.py"
replace_once(
    v4,
    '''from multi_product.runtime import install_multi_product_runtime, runtime_self_test
from vendor_expansion import apply_registry, load_registry
''',
    '''from multi_product.runtime import install_multi_product_runtime, runtime_self_test
from product_detail_reliability import install as install_product_detail_reliability
from product_detail_reliability import self_test as product_detail_reliability_self_test
from vendor_expansion import apply_registry, load_registry
''',
)
replace_once(
    v4,
    '''    state = install_multi_product_runtime(reliability)
    if getattr(worker, "_listing_card_provenance_gate_installed", False):
        return state
''',
    '''    state = install_multi_product_runtime(reliability)
    install_product_detail_reliability(reliability)
    if getattr(worker, "_listing_card_provenance_gate_installed", False):
        return state
''',
)
replace_once(
    v4,
    '''    runtime_self_test(reliability)
    fallback_transport_self_test(reliability)
''',
    '''    runtime_self_test(reliability)
    fallback_transport_self_test(reliability)
    product_detail_reliability_self_test(reliability)
''',
)

merge = "scripts/autonomous_merge.py"
replace_once(
    merge,
    '''    "duration_seconds",
    "retry_attempt",
)
''',
    '''    "duration_seconds",
    "retry_attempt",
    "retry_attempts",
    "verification_rejections",
)
''',
)
replace_once(
    merge,
    '''_MAX_VERIFICATION_FAILURES = 100_000
''',
    '''_MAX_VERIFICATION_FAILURES = 100_000
_MAX_VERIFICATION_RECORDS = 24
''',
)
replace_once(
    merge,
    '''def _public_route_result(route: dict[str, Any]) -> dict[str, Any]:
''',
    '''def _public_verification_records(value: Any) -> list[dict[str, Any]]:
    """Retain a bounded, non-secret product verification failure ledger."""
    if not isinstance(value, list):
        return []
    records: list[dict[str, Any]] = []
    for item in value:
        if len(records) >= _MAX_VERIFICATION_RECORDS:
            break
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason") or "")
        if not _VERIFICATION_REASON.fullmatch(reason):
            continue
        try:
            attempts = max(1, min(int(item.get("attempts") or 1), 10))
        except (TypeError, ValueError):
            attempts = 1
        record = {
            "product_id": str(item.get("product_id") or "")[:160],
            "url": str(item.get("url") or "")[:500],
            "reason": reason,
            "attempts": attempts,
            "retryable": bool(item.get("retryable")),
        }
        records.append(record)
    return records


def _public_route_result(route: dict[str, Any]) -> dict[str, Any]:
''',
)
replace_once(
    merge,
    '''    error = route.get("error")
    if error not in (None, ""):
        public["error"] = str(error)[:_ERROR_LIMIT]
    return public
''',
    '''    records = _public_verification_records(route.get("verification_failure_records"))
    if records:
        public["verification_failure_records"] = records
    rejection_reasons = _public_verification_reasons(route.get("verification_rejection_reasons"))
    if rejection_reasons:
        public["verification_rejection_reasons"] = rejection_reasons
        public["verification_rejections"] = min(sum(rejection_reasons.values()), _MAX_VERIFICATION_FAILURES)
    error = route.get("error")
    if error not in (None, ""):
        public["error"] = str(error)[:_ERROR_LIMIT]
    return public
''',
)
replace_once(
    merge,
    '''    return {
        "source_id": row.get("source_id"),
        "name": row.get("name"),
        "enabled": True,
        "status": "healthy",
''',
    '''    source_status = str(row.get("status") or "")
    public_status = "degraded" if verification_failures > 0 or source_status == "degraded" else "healthy"

    return {
        "source_id": row.get("source_id"),
        "name": row.get("name"),
        "enabled": True,
        "status": public_status,
''',
)
replace_once(
    merge,
    '''        assert source["status"] == "healthy"
        assert source["routes_attempted"] == 2
''',
    '''        assert source["status"] == "degraded"
        assert source["routes_attempted"] == 2
''',
)
