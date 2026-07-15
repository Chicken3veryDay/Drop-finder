from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def select_active_variant(
    variants: Iterable[dict[str, Any]],
    *,
    minimum_grams: Any = None,
    maximum_grams: Any = None,
) -> dict[str, Any] | None:
    """Select the shopper-active variant with the issue #6 tie-break contract.

    Only explicitly in-stock variants inside the optional inclusive weight
    bounds are eligible. Ordering is lowest price per gram, lower total price,
    lower weight, then stable variant ID.
    """

    lower = _decimal(minimum_grams)
    upper = _decimal(maximum_grams)
    eligible: list[tuple[Decimal, Decimal, Decimal, str, dict[str, Any]]] = []
    for variant in variants:
        if not isinstance(variant, dict) or variant.get("in_stock") is not True:
            continue
        grams = _decimal(variant.get("grams"))
        price = _decimal(variant.get("current_price"))
        ppg = _decimal(variant.get("price_per_gram"))
        variant_id = str(variant.get("variant_id") or "")
        if grams is None or price is None or ppg is None or not variant_id:
            continue
        if lower is not None and grams < lower:
            continue
        if upper is not None and grams > upper:
            continue
        eligible.append((ppg, price, grams, variant_id, variant))
    if not eligible:
        return None
    return min(eligible, key=lambda row: row[:4])[4]
