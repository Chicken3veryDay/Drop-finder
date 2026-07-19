from __future__ import annotations

import html
import math
import re
import unicodedata
import urllib.parse
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable

from .strict_json import json_safe_raw

SPACE = re.compile(r"\s+")
PUNCT_SPACE = re.compile(r"[\s\-_/|,:;·•]+")
GRAM_PATTERN = re.compile(
    r"(?<![\d.-])(?P<value>0\.5|1|2|3\.5|4|7|14|28|56|112)\s*(?:g|grams?)\b",
    re.I,
)
POUND_PATTERN = re.compile(
    r"(?<![\d.-])(?P<value>1/4|1/2|1|2|4)\s*(?:lb|lbs|pounds?)\b",
    re.I,
)
WORD_POUND_PATTERN = re.compile(r"\b(?P<value>quarter|half|one|two|four)\s+pounds?\b", re.I)
OUNCE_PATTERN = re.compile(
    r"(?<![\d.-])(?P<value>1/8|1/4|1/2|1|2|4)\s*(?:st|nd|rd|th)?\s*(?:oz|ounces?)\b",
    re.I,
)
BARE_FRACTION_OUNCE_PATTERN = re.compile(r"(?<![\d.-])(?P<value>1/8|1/4|1/2)\s*(?:th|st|nd|rd)?\b", re.I)
WORD_WEIGHT_PATTERN = re.compile(
    r"\b(?P<value>eighth|quarter|half\s+ounce|half[- ]?oz|ounce|one\s+ounce|two\s+ounces?|four\s+ounces?|zip)\b(?!\s*(?:lb|lbs|pounds?)\b)",
    re.I,
)
PERCENT_PATTERN = re.compile(r"(?<!\d)(?P<value>\d{1,3}(?:\.\d+)?)\s*%")
ND_PATTERN = re.compile(r"\b(?:nd|n/?d|non[- ]?detect(?:ed|able)?|below\s+(?:loq|lod))\b", re.I)
NEGATIVE_STOCK_PATTERN = re.compile(
    r"\b(?:out\s+of\s+stock|outofstock|sold\s+out|unavailable|not(?:\s+\w+){0,2}\s+(?:available|in\s+stock))\b"
)
POSITIVE_STOCK_PATTERN = re.compile(r"\b(?:in\s+stock|instock|available(?:\s+for\s+order)?)\b")

TRAILING_NAME_PATTERNS = [
    re.compile(
        r"\s*[|\-–—_:]+\s*(?:0\.5|1|2|3\.5|4|7|14|28|56|112)\s*(?:g|grams?)\s*$|"
        r"\s*[|\-–—_:]+\s*(?:1/8|1/4|1/2|1|2|4)\s*(?:oz|ounces?)?\s*$|"
        r"\s*[|\-–—_:]+\s*(?:eighth|quarter|half\s+ounce|half[- ]?oz|ounce|one\s+ounce|two\s+ounces?|four\s+ounces?|zip)\s*$",
        re.I,
    ),
    re.compile(r"\s*[|\-–—_:]+\s*(?:premium\s+)?(?:high\s+)?thc-?a\s+(?:hemp\s+)?flower\s*$", re.I),
    re.compile(r"\s*\((?:indoor|outdoor|greenhouse|mixed\s+light)\)\s*$", re.I),
    re.compile(r"\s*[|\-–—_:]+\s*(?:indoor|outdoor|greenhouse|mixed\s+light)\s*$", re.I),
    re.compile(r"\s*[|\-–—_:]+\s*(?:smalls|minis|small\s+buds|premium\s+buds|whole\s+flower)\s*$", re.I),
    re.compile(r"\s+thc-?a\s+(?:hemp\s+)?flower\s*$", re.I),
    re.compile(r"\s+(?:hemp\s+)?flower\s*$", re.I),
]
MARKETING_SUFFIX = re.compile(
    r"\s*[|\-–—_:]+\s*(?:limited\s+drop|new\s+drop|best\s+seller|staff\s+pick|exotic|premium|sale)\s*$",
    re.I,
)

LINEAGE_MAP = {
    "indica": "indica",
    "indica dominant": "indica_leaning_hybrid",
    "indica-dominant": "indica_leaning_hybrid",
    "indica leaning": "indica_leaning_hybrid",
    "indica-leaning": "indica_leaning_hybrid",
    "indica leaning hybrid": "indica_leaning_hybrid",
    "indica-leaning hybrid": "indica_leaning_hybrid",
    "hybrid": "hybrid",
    "balanced hybrid": "hybrid",
    "sativa dominant": "sativa_leaning_hybrid",
    "sativa-dominant": "sativa_leaning_hybrid",
    "sativa leaning": "sativa_leaning_hybrid",
    "sativa-leaning": "sativa_leaning_hybrid",
    "sativa leaning hybrid": "sativa_leaning_hybrid",
    "sativa-leaning hybrid": "sativa_leaning_hybrid",
    "sativa": "sativa",
    "unknown": "unknown",
}

ENVIRONMENTS = {
    "indoor": "indoor",
    "outdoor": "outdoor",
    "greenhouse": "greenhouse",
    "green house": "greenhouse",
    "mixed light": "greenhouse",
    "mixed-light": "greenhouse",
    "sun grown": "outdoor",
    "sun-grown": "outdoor",
}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = unicodedata.normalize("NFKC", text)
    return SPACE.sub(" ", text).strip()


def normalized_search(value: Any) -> str:
    text = clean_text(value).casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = PUNCT_SPACE.sub(" ", text)
    return SPACE.sub(" ", text).strip()


def safe_decimal(value: Any, *, minimum: Decimal | None = None, maximum: Decimal | None = None) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "").replace("$", "")
        if not value:
            return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not number.is_finite():
        return None
    if minimum is not None and number < minimum:
        return None
    if maximum is not None and number > maximum:
        return None
    return number


def decimal_number(value: Decimal | None, places: str = "0.0001") -> float | None:
    if value is None:
        return None
    return float(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))


def percentage(value: Any) -> Decimal | None:
    if isinstance(value, str):
        match = PERCENT_PATTERN.search(value)
        if match:
            value = match.group("value")
    return safe_decimal(value, minimum=Decimal("0"), maximum=Decimal("100"))


def delta9_value(value: Any) -> tuple[Decimal | None, str]:
    if isinstance(value, str) and ND_PATTERN.search(value):
        return Decimal("0"), "non_detect_normalized_zero"
    parsed = percentage(value)
    return parsed, "measured" if parsed is not None else "missing"


def _snap_commercial_weight(value: Decimal) -> Decimal:
    standards = (
        Decimal("0.5"), Decimal("1"), Decimal("2"), Decimal("3.5"),
        Decimal("4"), Decimal("7"), Decimal("14"), Decimal("28"),
        Decimal("56"), Decimal("112"), Decimal("224"), Decimal("448"),
        Decimal("896"), Decimal("1792"),
    )
    closest = min(standards, key=lambda candidate: abs(candidate - value))
    tolerance = max(Decimal("0.02"), closest * Decimal("0.02"))
    return closest if abs(closest - value) <= tolerance else value


def _weight_from_label(text: str) -> tuple[Decimal | None, str]:
    match = GRAM_PATTERN.search(text)
    if match:
        return Decimal(match.group("value")), clean_text(match.group(0))
    match = POUND_PATTERN.search(text)
    if match:
        return {
            "1/4": Decimal("112"),
            "1/2": Decimal("224"),
            "1": Decimal("448"),
            "2": Decimal("896"),
            "4": Decimal("1792"),
        }[match.group("value")], clean_text(match.group(0))
    match = WORD_POUND_PATTERN.search(text)
    if match:
        return {
            "quarter": Decimal("112"),
            "half": Decimal("224"),
            "one": Decimal("448"),
            "two": Decimal("896"),
            "four": Decimal("1792"),
        }[normalized_search(match.group("value"))], clean_text(match.group(0))
    match = OUNCE_PATTERN.search(text) or BARE_FRACTION_OUNCE_PATTERN.search(text)
    if match:
        return {
            "1/8": Decimal("3.5"),
            "1/4": Decimal("7"),
            "1/2": Decimal("14"),
            "1": Decimal("28"),
            "2": Decimal("56"),
            "4": Decimal("112"),
        }[match.group("value")], clean_text(match.group(0))
    match = WORD_WEIGHT_PATTERN.search(text)
    if match:
        return {
            "eighth": Decimal("3.5"),
            "quarter": Decimal("7"),
            "half ounce": Decimal("14"),
            "half oz": Decimal("14"),
            "ounce": Decimal("28"),
            "one ounce": Decimal("28"),
            "two ounces": Decimal("56"),
            "two ounce": Decimal("56"),
            "four ounces": Decimal("112"),
            "four ounce": Decimal("112"),
            "zip": Decimal("28"),
        }.get(normalized_search(match.group("value"))), clean_text(match.group(0))
    return None, ""


def normalize_weight(value: Any, label: Any = None) -> tuple[Decimal | None, str]:
    direct = safe_decimal(value, minimum=Decimal("0.05"), maximum=Decimal("5000"))
    supplied_label = clean_text(label)
    source_label = supplied_label or clean_text(value)
    label_weight, matched_label = _weight_from_label(supplied_label) if supplied_label else (None, "")

    # Direct numeric values are not self-authenticating package-weight
    # evidence. Require a source label with an explicit unit or recognized
    # weight term, then require that evidence to agree with the normalized
    # numeric value. This prevents inherited Tier/count/potency numbers and
    # unitless legacy grams from producing shopper-visible price-per-gram data.
    if direct is not None:
        snapped = _snap_commercial_weight(direct)
        if label_weight is None or label_weight != snapped:
            return None, source_label
        return label_weight, matched_label

    return label_weight, matched_label or source_label


def canonical_url(value: Any, *, keep_variant: bool = False) -> str:
    raw = clean_text(value)
    if not raw:
        return ""
    try:
        parsed = urllib.parse.urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    query: list[tuple[str, str]] = []
    if keep_variant:
        query = [
            (key, val)
            for key, val in urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
            if key.casefold() in {"variant", "attribute_pa_size", "attribute_size", "variation_id"}
        ]
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, urllib.parse.urlencode(sorted(query)), "")
    )


def canonical_product_url(value: Any) -> str:
    return canonical_url(value, keep_variant=False)


def canonical_variant_url(value: Any) -> str:
    return canonical_url(value, keep_variant=True)


def canonical_strain_name(source_title: Any, variant_label: Any = None) -> str:
    title = clean_text(source_title)
    variant = clean_text(variant_label)
    if variant and normalized_search(title).endswith(normalized_search(variant)):
        escaped = re.escape(variant)
        title = re.sub(rf"\s*(?:[|\-–—_:]+\s*)?{escaped}\s*$", "", title, flags=re.I).strip()
    previous = None
    while title and title != previous:
        previous = title
        for pattern in TRAILING_NAME_PATTERNS:
            title = pattern.sub("", title).strip(" |-_–—:")
        title = MARKETING_SUFFIX.sub("", title).strip(" |-_–—:")
    return title or clean_text(source_title)


def lineage(value: Any, *fallback_text: Any) -> tuple[str, dict[str, Any]]:
    explicit = normalized_search(value)
    if explicit in LINEAGE_MAP:
        return LINEAGE_MAP[explicit], {"source": "explicit", "raw": clean_text(value)}
    combined = normalized_search(" ".join(clean_text(item) for item in fallback_text if item not in (None, "")))
    ordered = [
        (r"\bindica (?:dominant|leaning)(?: hybrid)?\b", "indica_leaning_hybrid"),
        (r"\bsativa (?:dominant|leaning)(?: hybrid)?\b", "sativa_leaning_hybrid"),
        (r"\bindica leaning hybrid\b", "indica_leaning_hybrid"),
        (r"\bsativa leaning hybrid\b", "sativa_leaning_hybrid"),
        (r"\bbalanced hybrid\b", "hybrid"),
        (r"\bhybrid\b", "hybrid"),
        (r"\bindica\b", "indica"),
        (r"\bsativa\b", "sativa"),
    ]
    for pattern, result in ordered:
        if re.search(pattern, combined):
            return result, {"source": "conservative_text", "raw": combined}
    return "unknown", {"source": "unavailable", "raw": ""}


def environment(value: Any, *fallback_text: Any) -> tuple[str, dict[str, Any]]:
    explicit = normalized_search(value)
    if explicit in ENVIRONMENTS:
        return ENVIRONMENTS[explicit], {"source": "explicit", "raw": clean_text(value)}
    combined = normalized_search(" ".join(clean_text(item) for item in fallback_text if item not in (None, "")))
    for token, result in ENVIRONMENTS.items():
        if re.search(rf"\b{re.escape(token)}\b", combined):
            return result, {"source": "conservative_text", "raw": token}
    return "unknown", {"source": "unavailable", "raw": ""}


def effects(value: Any) -> tuple[list[str], dict[str, Any]]:
    raw_items: Iterable[Any]
    if isinstance(value, (list, tuple, set)):
        raw_items = value
    elif isinstance(value, str):
        raw_items = re.split(r"[,;/|•]+", value)
    else:
        raw_items = []
    seen: set[str] = set()
    result: list[str] = []
    for item in raw_items:
        text = clean_text(item).strip(" .")
        key = normalized_search(text)
        if not key or key in seen or len(text) > 80:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= 12:
            break
    return result, {"source": "source_exposed" if result else "unavailable", "raw": clean_text(value)}


def rating(score: Any, count: Any) -> tuple[float | None, int | None, dict[str, Any]]:
    parsed_score = safe_decimal(score, minimum=Decimal("0"), maximum=Decimal("5"))
    parsed_count = safe_decimal(count, minimum=Decimal("1"), maximum=Decimal("100000000"))
    if parsed_score is None or parsed_count is None or parsed_count != parsed_count.to_integral_value():
        return None, None, {
            "source": "unavailable",
            "raw_score": json_safe_raw(score),
            "raw_count": json_safe_raw(count),
        }
    return (
        float(parsed_score.quantize(Decimal("0.01"))),
        int(parsed_count),
        {
            "source": "source_exposed",
            "raw_score": json_safe_raw(score),
            "raw_count": json_safe_raw(count),
        },
    )

def explicit_stock(value: Any) -> tuple[bool | None, str]:
    if isinstance(value, bool):
        return value, "explicit_boolean"
    text = normalized_search(value)
    if not text:
        return None, "missing"
    if text == "false" or NEGATIVE_STOCK_PATTERN.search(text):
        return False, "explicit_source_state"
    if text == "true" or POSITIVE_STOCK_PATTERN.search(text):
        return True, "explicit_source_state"
    return None, "unknown"


def finite_float(value: Any) -> float | None:
    parsed = safe_decimal(value)
    if parsed is None or not math.isfinite(float(parsed)):
        return None
    return float(parsed)
