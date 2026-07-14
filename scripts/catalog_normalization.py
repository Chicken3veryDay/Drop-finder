#!/usr/bin/env python3
"""Source-independent final normalization for every published DropFinder product."""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any

NORMALIZATION_CONTRACT = "dropfinder-product-normalization-v1"

_SPACE = re.compile(r"\s+")
_SEPARATORS = re.compile(r"\s*(?:\||•|·|_|—|–)\s*")
_THCA = re.compile(r"\b(?:thca|thc-a|high\s+thca)\b", re.I)
_VENDOR_JOIN = r"(?:\s*(?:\||•|·|_|—|–|-|:)+\s*)?"
_WEIGHT_VALUE = r"(?:\d+(?:\.\d+)?\s*\+?\s*(?:g|grams?|oz|ounces?|lb|lbs|pounds?)|1/(?:8|4|2)(?:th)?\s*(?:oz|ounces?)?)"
_LABELLED_WEIGHT = re.compile(
    rf"\b(?:weight|size|package|amount|quantity|option)\s*[:=\-]?\s*{_WEIGHT_VALUE}\b",
    re.I,
)
_WEIGHT = re.compile(rf"(?<![\d.]){_WEIGHT_VALUE}\b", re.I)
_WEIGHT_IN_NAME = re.compile(
    r"(?<![\d.])(?:\d+(?:\.\d+)?\s*\+?\s*(?:g|grams?|oz|ounces?|lb|lbs|pounds?)|1/(?:8|4|2)(?:th)?\s*(?:oz|ounces?)?)\b",
    re.I,
)
_LABEL_IN_NAME = re.compile(r"\b(?:weight|size|package|amount|quantity|option)\s*:", re.I)
_PRODUCT_TYPE = re.compile(r"\b(?:hemp\s+flower|flower|buds?)\b", re.I)
_EDGE_FILLER = re.compile(r"^(?:of|the|and|with|for|by|from)\b|\b(?:of|the|and|with|for|by|from)$", re.I)
_PUNCTUATION = re.compile(r"^[\s,:;\-+./]+|[\s,:;\-+./]+$")
_DUPLICATE_WORD = re.compile(r"\b([a-z0-9']+)\s+\1\b", re.I)

_FORM_PATTERNS = (
    ("Minis", re.compile(r"\b(?:minis?|mini\s+buds?)\b", re.I)),
    ("Smalls", re.compile(r"\b(?:smalls?|small\s+buds?)\b", re.I)),
    ("Popcorn", re.compile(r"\bpopcorn(?:\s+buds?)?\b", re.I)),
    ("Shake", re.compile(r"\bshake\b", re.I)),
    ("Trim", re.compile(r"\btrim\b", re.I)),
)
_CULTIVATION_PATTERNS = (
    ("Indoor", re.compile(r"\bindoor\b", re.I)),
    ("Greenhouse", re.compile(r"\bgreenhouse\b", re.I)),
    ("Outdoor", re.compile(r"\boutdoor\b", re.I)),
    ("Light Assist", re.compile(r"\blight[- ]?assist(?:ed)?\b", re.I)),
)
_ACRONYMS = {
    "cbd": "CBD",
    "cbg": "CBG",
    "gmo": "GMO",
    "mac": "MAC",
    "og": "OG",
    "rso": "RSO",
    "sour d": "Sour D",
}
_SMALL_WORDS = {"a", "an", "and", "at", "by", "for", "in", "of", "on", "the", "to", "with"}


def _text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = unicodedata.normalize("NFKC", text).replace("\u00a0", " ")
    return _SPACE.sub(" ", text).strip()


def positive(value: object) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def format_grams(value: object) -> str | None:
    grams = positive(value)
    if grams is None:
        return None
    rounded = round(grams, 3)
    text = f"{rounded:.3f}".rstrip("0").rstrip(".")
    return f"{text} g"


def _extract_label(raw: str, patterns: tuple[tuple[str, re.Pattern[str]], ...]) -> str | None:
    for label, pattern in patterns:
        if pattern.search(raw):
            return label
    return None


def _remove_vendor(text: str, vendor: str) -> str:
    vendor = _text(vendor)
    if not vendor:
        return text
    escaped = re.escape(vendor)
    text = re.sub(rf"{_VENDOR_JOIN}{escaped}\s*$", "", text, flags=re.I)
    return re.sub(rf"\b{escaped}\b", "", text, flags=re.I)


def _remove_patterns(text: str, patterns: tuple[tuple[str, re.Pattern[str]], ...]) -> str:
    for _, pattern in patterns:
        text = pattern.sub(" ", text)
    return text


def _smart_title(text: str) -> str:
    words = text.split()
    result: list[str] = []
    for index, word in enumerate(words):
        lower = word.lower()
        stripped = re.sub(r"[^a-z0-9]", "", lower)
        if lower in _ACRONYMS:
            result.append(_ACRONYMS[lower])
        elif stripped in _ACRONYMS:
            result.append(word.replace(stripped, _ACRONYMS[stripped]))
        elif lower in _SMALL_WORDS and index not in {0, len(words) - 1}:
            result.append(lower)
        elif word.isupper() and 1 < len(stripped) <= 4 and stripped not in {"grams", "gram"}:
            result.append(word)
        elif "'" in word:
            result.append("'".join(part[:1].upper() + part[1:].lower() for part in word.split("'")))
        else:
            result.append(word[:1].upper() + word[1:].lower())
    return " ".join(result)


def canonical_name(raw_name: object, vendor: object = "") -> tuple[str, str, str | None]:
    raw = _text(raw_name)
    form = _extract_label(raw, _FORM_PATTERNS)
    cultivation = _extract_label(raw, _CULTIVATION_PATTERNS)

    text = _remove_vendor(raw, _text(vendor))
    text = _SEPARATORS.sub(" ", text)
    text = _LABELLED_WEIGHT.sub(" ", text)
    text = _WEIGHT.sub(" ", text)
    text = _THCA.sub(" ", text)
    text = _remove_patterns(text, _FORM_PATTERNS)
    text = _remove_patterns(text, _CULTIVATION_PATTERNS)
    text = re.sub(r"\b(?:weight|size|package|amount|quantity|option)\b\s*[:=\-]?", " ", text, flags=re.I)
    text = re.sub(r"\b(?:grams?\s+of)\b", " ", text, flags=re.I)
    text = _SPACE.sub(" ", text)
    text = _PUNCTUATION.sub("", text)
    while _EDGE_FILLER.search(text):
        text = _EDGE_FILLER.sub("", text).strip()
    while _DUPLICATE_WORD.search(text):
        text = _DUPLICATE_WORD.sub(r"\1", text)

    tokens_without_type = _PRODUCT_TYPE.sub(" ", text)
    tokens_without_type = _SPACE.sub(" ", tokens_without_type).strip()
    if tokens_without_type and len(tokens_without_type.split()) >= 1:
        text = tokens_without_type
    text = _PUNCTUATION.sub("", _SPACE.sub(" ", text)).strip()

    if not text:
        text = "Flower"
    title = _smart_title(text)
    suffixes: list[str] = []
    if cultivation and cultivation.lower() not in title.lower():
        suffixes.append(cultivation)
    if form:
        # "Minis" and "small buds" are competing source labels for the same
        # visible form. Prefer the more specific source term instead of showing
        # both human inventions on one product.
        suffixes.append(form)
    if suffixes:
        title = f"{title} {' '.join(suffixes)}"
    title = _SPACE.sub(" ", title).strip()
    return title, form or "Flower", cultivation


def search_text(product: dict[str, Any]) -> str:
    values = (
        product.get("display_name"),
        product.get("raw_name"),
        product.get("vendor"),
        product.get("source_id"),
        product.get("flower_form"),
        product.get("cultivation"),
        product.get("package_label"),
        product.get("thca"),
    )
    return _SPACE.sub(" ", " ".join(_text(value) for value in values if value not in (None, ""))).lower()


def normalize_product(product: dict[str, Any]) -> dict[str, Any]:
    row = dict(product)
    raw_name = _text(row.get("raw_name") or row.get("name"))
    raw_variant = _text(row.get("raw_variant") or row.get("variant"))
    display_name, flower_form, cultivation = canonical_name(raw_name, row.get("vendor"))
    package_label = format_grams(row.get("grams"))

    row.update(
        raw_name=raw_name,
        raw_variant=raw_variant,
        name=display_name,
        display_name=display_name,
        variant=package_label or "",
        package_grams=round(float(row["grams"]), 3) if positive(row.get("grams")) is not None else None,
        package_label=package_label,
        flower_form=flower_form,
        cultivation=cultivation,
        normalization_contract=NORMALIZATION_CONTRACT,
        name_normalization_version=NORMALIZATION_CONTRACT,
    )
    row["search_text"] = search_text(row)
    return row


def normalization_failures(product: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    name = _text(product.get("name"))
    vendor = _text(product.get("vendor"))
    package_label = format_grams(product.get("grams"))
    if product.get("normalization_contract") != NORMALIZATION_CONTRACT:
        failures.append("normalization_contract")
    if not _text(product.get("raw_name")):
        failures.append("raw_name")
    if not name or name != _text(product.get("display_name")):
        failures.append("display_name")
    if _THCA.search(name):
        failures.append("thca_token_in_name")
    if _WEIGHT_IN_NAME.search(name):
        failures.append("weight_in_name")
    if _LABEL_IN_NAME.search(name):
        failures.append("weight_label_in_name")
    if any(character in name for character in ("|", "_", "•", "·")):
        failures.append("source_separator_in_name")
    if vendor and vendor.lower() in name.lower():
        failures.append("vendor_in_name")
    if package_label is None or product.get("package_label") != package_label:
        failures.append("package_label")
    if product.get("variant") != package_label:
        failures.append("variant_label")
    if positive(product.get("package_grams")) != positive(product.get("grams")):
        failures.append("package_grams")
    if not _text(product.get("search_text")):
        failures.append("search_text")
    return failures


def self_test() -> int:
    examples = {
        "THCA Flower MINIS _ 29+ Grams of Small Buds | Black Tie CBD": ("Flower Minis", "Minis", None),
        "Bolo Runtz THCa Weight: 28g": ("Bolo Runtz", "Flower", None),
        "GMO THCa Weight: 14g": ("GMO", "Flower", None),
        "Punch Breath THCA 28 GRAMS SMALLS": ("Punch Breath Smalls", "Smalls", None),
        "Double Lemon Cherry THCA 3.5 GRAMS": ("Double Lemon Cherry", "Flower", None),
        "Rainbow Cadillac size: 7.0g": ("Rainbow Cadillac", "Flower", None),
        "Secret Cookies THCa Indoor Weight: 3.5g": ("Secret Cookies Indoor", "Flower", "Indoor"),
        "MAC 1 Cap's Cut THCA 28 GRAMS": ("MAC 1 Cap's Cut", "Flower", None),
    }
    for raw, expected in examples.items():
        vendor = "Black Tie CBD" if "Black Tie CBD" in raw else "Fixture"
        actual = canonical_name(raw, vendor)
        assert actual == expected, (raw, actual, expected)

    fixture = normalize_product({
        "id": "fixture",
        "source_id": "green_unicorn_farms",
        "vendor": "Green Unicorn Farms",
        "name": "Bolo Runtz THCa Weight: 28g",
        "variant": "Weight: 28g",
        "grams": 28,
        "thca": 27.2,
    })
    assert fixture["name"] == "Bolo Runtz"
    assert fixture["variant"] == "28 g"
    assert fixture["package_label"] == "28 g"
    assert fixture["raw_name"] == "Bolo Runtz THCa Weight: 28g"
    assert normalization_failures(fixture) == []
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.input or not args.output:
        parser.error("--input and --output are required")
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    products = payload.get("products") if isinstance(payload, dict) else None
    if not isinstance(products, list):
        raise SystemExit("input must contain a products array")
    normalized = [normalize_product(row) for row in products if isinstance(row, dict)]
    payload["normalization_contract"] = NORMALIZATION_CONTRACT
    payload["products"] = normalized
    payload["product_count"] = len(normalized)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
