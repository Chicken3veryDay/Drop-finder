from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from .classification import (
    CANNABIS_FLOWER,
    CANNABIS_VAPE,
    PSILOCYBIN_MUSHROOM,
    PSILOCYBIN_VAPE,
)

GRAM = re.compile(r"(?<!\d)(0\.25|0\.5|1|2|3\.5|4|7|14|28|56|112)\s*(?:g|grams?)\b", re.I)
OUNCE = re.compile(r"(?<!\d)(1/8|1/4|1/2|1|2|4)(?:st|nd|rd|th)?\s*(?:(?:oz|ounces?)\b)?", re.I)
WORD_WEIGHT = re.compile(r"\b(eighth|quarter|half\s+ounce|half[- ]?oz|ounce|one\s+ounce|zip)\b", re.I)
ML = re.compile(r"(?<!\d)(0\.25|0\.3|0\.5|0\.8|1|1\.5|2|3|5|10)\s*(?:ml|milliliters?)\b", re.I)
PSILOCYBIN_PERCENT = re.compile(r"\bpsilocybin\s*[:\-]?\s*(\d{1,2}(?:\.\d+)?)\s*%", re.I)
POTENCY_PERCENT = re.compile(r"\bpotency\s*[:\-]?\s*(\d{1,2}(?:\.\d+)?)\s*%", re.I)
PUFF_COUNT = re.compile(r"\b(\d{2,5})\s*(?:puffs?|draws?)\b", re.I)
SPECIES = re.compile(
    r"\b(psilocybe\s+(?:cubensis|natalensis|cyanescens|semilanceata|azurescens))\b",
    re.I,
)
TERPENES = (
    "myrcene",
    "limonene",
    "caryophyllene",
    "linalool",
    "pinene",
    "humulene",
    "terpinolene",
    "ocimene",
    "bisabolol",
)
TERPENE_TOTAL = re.compile(r"\btotal\s+terpenes?\s*[:\-]?\s*(\d{1,2}(?:\.\d+)?)\s*%", re.I)


def decimal_value(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
    return parsed if parsed.is_finite() and parsed > 0 else None


def _first_decimal(pattern: re.Pattern[str], text: str) -> Decimal | None:
    match = pattern.search(text)
    return decimal_value(match.group(1)) if match else None


def quantity_fields(text: str, primary_type: str) -> dict[str, float | str | None]:
    grams: Decimal | None = None
    volume_ml: Decimal | None = None
    gram_match = GRAM.search(text)
    if gram_match:
        grams = decimal_value(gram_match.group(1))
    else:
        ounce_match = OUNCE.search(text)
        if ounce_match:
            ounces = {
                "1/8": Decimal("0.125"),
                "1/4": Decimal("0.25"),
                "1/2": Decimal("0.5"),
            }.get(ounce_match.group(1), decimal_value(ounce_match.group(1)))
            grams = ounces * Decimal("28.3495") if ounces else None
        else:
            word_match = WORD_WEIGHT.search(text)
            if word_match:
                label = re.sub(r"\s+", " ", word_match.group(1).lower().replace("-", " ")).strip()
                grams = {
                    "eighth": Decimal("3.5437"),
                    "quarter": Decimal("7.0874"),
                    "half ounce": Decimal("14.1748"),
                    "half oz": Decimal("14.1748"),
                    "ounce": Decimal("28.3495"),
                    "one ounce": Decimal("28.3495"),
                    "zip": Decimal("28.3495"),
                }.get(label)
    volume_ml = _first_decimal(ML, text)
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


def comparison_price(price: Any, quantity: dict[str, float | str | None]) -> dict[str, float | str | None]:
    current = decimal_value(price)
    grams = decimal_value(quantity.get("grams"))
    volume_ml = decimal_value(quantity.get("volume_ml"))
    metric = None
    value = None
    if current and grams:
        metric = "price_per_gram"
        value = (current / grams).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    elif current and volume_ml:
        metric = "price_per_ml"
        value = (current / volume_ml).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return {
        "comparison_metric": metric,
        "comparison_price": float(value) if value else None,
        "price_per_gram": float(value) if metric == "price_per_gram" and value else None,
        "price_per_ml": float(value) if metric == "price_per_ml" and value else None,
    }


def type_specific_fields(text: str, primary_type: str) -> dict[str, Any]:
    normalized = " ".join(text.split())
    species_match = SPECIES.search(normalized)
    psilocybin = _first_decimal(PSILOCYBIN_PERCENT, normalized)
    potency = _first_decimal(POTENCY_PERCENT, normalized)
    puffs = PUFF_COUNT.search(normalized)
    device_type = None
    lowered = normalized.lower()
    for token, label in (
        ("disposable", "disposable"),
        ("cartridge", "cartridge"),
        (" cart ", "cartridge"),
        ("pod", "pod"),
        ("510", "510 cartridge"),
        ("all-in-one", "all-in-one"),
    ):
        if token in f" {lowered} ":
            device_type = label
            break
    return {
        "species": species_match.group(1).title() if species_match and primary_type == PSILOCYBIN_MUSHROOM else None,
        "psilocybin_percent": float(psilocybin) if psilocybin and primary_type in (PSILOCYBIN_MUSHROOM, PSILOCYBIN_VAPE) else None,
        "claimed_potency_percent": float(potency) if potency else None,
        "device_type": device_type if primary_type in (CANNABIS_VAPE, PSILOCYBIN_VAPE) else None,
        "puff_count": int(puffs.group(1)) if puffs and primary_type in (CANNABIS_VAPE, PSILOCYBIN_VAPE) else None,
        "terpenes": [terpene for terpene in TERPENES if re.search(rf"\b{re.escape(terpene)}\b", lowered)],
        "total_terpenes_percent": float(_first_decimal(TERPENE_TOTAL, normalized) or 0) or None,
    }
