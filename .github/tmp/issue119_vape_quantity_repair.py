from pathlib import Path


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "scripts/multi_product/normalization.py",
    '''    volume_ml = _first_decimal(ML, text)
    if primary_type in (CANNABIS_FLOWER, PSILOCYBIN_MUSHROOM):
        volume_ml = None
    if primary_type in (CANNABIS_VAPE, PSILOCYBIN_VAPE):
        grams = None
    return {
        "grams": float(grams.quantize(Decimal("0.0001"))) if grams else None,
        "volume_ml": float(volume_ml.quantize(Decimal("0.0001"))) if volume_ml else None,
        "quantity_unit": "g" if grams else "ml" if volume_ml else None,
    }
''',
    '''    volume_ml = _first_decimal(ML, text)
    if primary_type in (CANNABIS_FLOWER, PSILOCYBIN_MUSHROOM):
        volume_ml = None
    elif primary_type in (CANNABIS_VAPE, PSILOCYBIN_VAPE) and volume_ml:
        # Prefer explicit source volume when both units are present. Mass-only
        # labels remain intact so publication can reject them explicitly.
        grams = None
    quantity_value = grams if grams else volume_ml
    return {
        "grams": float(grams.quantize(Decimal("0.0001"))) if grams else None,
        "volume_ml": float(volume_ml.quantize(Decimal("0.0001"))) if volume_ml else None,
        "quantity_value": float(quantity_value.quantize(Decimal("0.0001"))) if quantity_value else None,
        "quantity_unit": "g" if grams else "ml" if volume_ml else None,
    }
''',
    "vape quantity normalization",
)

replace_once(
    "scripts/multi_product/publication.py",
    "import argparse\nimport json\nimport urllib.parse\n",
    "import argparse\nimport json\nimport math\nimport urllib.parse\n",
    "publication math import",
)

replace_once(
    "scripts/multi_product/publication.py",
    '''def reject_reason(product: dict[str, Any]) -> str | None:
''',
    '''def _positive_number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _vape_quantity_reject_reason(product: dict[str, Any]) -> str | None:
    unit = str(product.get("quantity_unit") or "")
    grams = _positive_number(product.get("grams"))
    volume_ml = _positive_number(product.get("volume_ml"))
    quantity_value = _positive_number(product.get("quantity_value"))
    metric = str(product.get("comparison_metric") or "")
    comparison = _positive_number(product.get("comparison_price"))
    price_per_ml = _positive_number(product.get("price_per_ml"))
    current_price = _positive_number(product.get("price"))

    if unit == "g" or grams is not None:
        return "unsupported_vape_mass_quantity"
    if unit != "ml" or volume_ml is None:
        return "missing_vape_volume"
    if quantity_value is not None and abs(quantity_value - volume_ml) > 0.0001:
        return "inconsistent_vape_quantity"
    if metric != "price_per_ml" or comparison is None or price_per_ml is None:
        return "missing_vape_comparison_price"
    expected = current_price / volume_ml if current_price is not None else None
    if (
        abs(comparison - price_per_ml) > 0.0001
        or expected is None
        or abs(price_per_ml - expected) > 0.0001
    ):
        return "inconsistent_vape_comparison_price"
    return None


def reject_reason(product: dict[str, Any]) -> str | None:
''',
    "vape quantity validator",
)

replace_once(
    "scripts/multi_product/publication.py",
    '''    elif primary == CANNABIS_VAPE:
        if not evidence.get("explicit_cannabis"):
            return "missing_product_level_cannabis_evidence"
        if not evidence.get("explicit_vape"):
            return "missing_product_level_vape_evidence"
''',
    '''    elif primary == CANNABIS_VAPE:
        if not evidence.get("explicit_cannabis"):
            return "missing_product_level_cannabis_evidence"
        if not evidence.get("explicit_vape"):
            return "missing_product_level_vape_evidence"
        quantity_reason = _vape_quantity_reject_reason(product)
        if quantity_reason:
            return quantity_reason
''',
    "cannabis vape publication invariant",
)

replace_once(
    "scripts/multi_product/publication.py",
    '''    elif primary == PSILOCYBIN_VAPE:
        if not evidence.get("explicit_psilocybin"):
            return "missing_product_level_psilocybin_evidence"
        if not evidence.get("explicit_vape"):
            return "missing_product_level_vape_evidence"
        if evidence.get("amanita_signal"):
            return "amanita_not_psilocybin"
''',
    '''    elif primary == PSILOCYBIN_VAPE:
        if not evidence.get("explicit_psilocybin"):
            return "missing_product_level_psilocybin_evidence"
        if not evidence.get("explicit_vape"):
            return "missing_product_level_vape_evidence"
        if evidence.get("amanita_signal"):
            return "amanita_not_psilocybin"
        quantity_reason = _vape_quantity_reject_reason(product)
        if quantity_reason:
            return quantity_reason
''',
    "psilocybin vape publication invariant",
)
