from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

CANNABIS_FLOWER = "cannabis_flower"
CANNABIS_VAPE = "cannabis_vape"
PSILOCYBIN_MUSHROOM = "psilocybin_mushroom"
PSILOCYBIN_VAPE = "psilocybin_vape"

SUPPORTED_PRODUCT_TYPES = (
    CANNABIS_FLOWER,
    CANNABIS_VAPE,
    PSILOCYBIN_MUSHROOM,
    PSILOCYBIN_VAPE,
)
ENABLED_PRODUCT_TYPES = SUPPORTED_PRODUCT_TYPES
CONTROLLED_PRODUCT_TYPES = frozenset((PSILOCYBIN_MUSHROOM, PSILOCYBIN_VAPE))

SPACE = re.compile(r"\s+")
THCA = re.compile(r"\b(?:thca|thc-a|high\s+thca|type\s+[i1])\b", re.I)
CANNABIS = re.compile(
    r"\b(?:cannabis|hemp|marijuana|thca|thc-a|delta[- ]?9|delta[- ]?8|"
    r"live\s+resin|live\s+rosin|distillate|cannabinoid)\b",
    re.I,
)
FLOWER = re.compile(r"\b(?:flower|buds?|smalls|minis|popcorn|shake|trim)\b", re.I)
VAPE = re.compile(
    r"\b(?:vapes?|cartridges?|carts?|disposables?|all[- ]?in[- ]?one|"
    r"510(?:\s+thread(?:ed)?)?|pods?|vape\s+pens?)\b",
    re.I,
)
PSILOCYBIN = re.compile(
    r"\b(?:psilocybin|psilocin|magic\s+mushrooms?|psychedelic\s+mushrooms?|"
    r"psilocybe(?:\s+(?:cubensis|natalensis|cyanescens|semilanceata|azurescens))?)\b",
    re.I,
)
MUSHROOM = re.compile(r"\b(?:mushrooms?|shrooms?|fruiting\s+bodies|caps?\s+and\s+stems?)\b", re.I)
AMANITA = re.compile(r"\b(?:amanita|muscaria|muscimol|ibotenic)\b", re.I)
ACCESSORY = re.compile(
    r"\b(?:battery|charger|empty\s+cart|replacement\s+coil|atomizer|glass|"
    r"grinder|tray|apparel|shirt|hoodie|hat|poster|gift\s*card|subscription|"
    r"wholesale|display\s+case|storage\s+jar)\b",
    re.I,
)
MIXED_OFFER = re.compile(
    r"\b(?:bundles?|samplers?(?![-\s]+sized\b)|sample\s+packs?|variety\s+packs?|"
    r"stash\s+kits?|mystery\s+(?:box(?:es)?|bags?|packs?)|"
    r"mix(?:\s*&\s*|[-\s]+and[-\s]+|[-\s]+)match)\b",
    re.I,
)
FLOWER_FORM_EXCLUDE = re.compile(
    r"\b(?:pre[- ]?rolls?|prerolls?|joints?|blunts?|cones?|vapes?|cartridges?|"
    r"carts?|disposables?|gumm(?:y|ies)|edibles?|tinctures?|capsules?|beverages?|"
    r"concentrates?|rosin|resin|badder|budder|crumble|isolate|dabs?|wax|seeds?|clones?)\b",
    re.I,
)


@dataclass(frozen=True)
class ProductClassification:
    primary_type: str
    type_tags: tuple[str, ...]
    evidence: dict[str, bool | str | tuple[str, ...]]
    permits_public_purchase_link: bool


def normalized_text(*values: object) -> str:
    return SPACE.sub(" ", " ".join(str(value or "") for value in values)).strip()


def is_mixed_offer(*values: object) -> bool:
    return bool(MIXED_OFFER.search(normalized_text(*values)))


def _ordered_tags(tags: Iterable[str]) -> tuple[str, ...]:
    found = set(tags)
    return tuple(product_type for product_type in SUPPORTED_PRODUCT_TYPES if product_type in found)


def classify_product(
    *,
    name: object,
    description: object = "",
    url: object = "",
    route_hint: object = "",
) -> ProductClassification | None:
    text = normalized_text(name, description, url, route_hint)
    if not text or ACCESSORY.search(text) or is_mixed_offer(name, description, url):
        return None

    has_thca = bool(THCA.search(text))
    has_cannabis = bool(CANNABIS.search(text))
    has_flower = bool(FLOWER.search(text))
    has_vape = bool(VAPE.search(text))
    has_psilocybin = bool(PSILOCYBIN.search(text))
    has_mushroom = bool(MUSHROOM.search(text))
    has_amanita = bool(AMANITA.search(text))

    tags: list[str] = []
    if has_thca and has_flower and not FLOWER_FORM_EXCLUDE.search(text):
        tags.append(CANNABIS_FLOWER)
    if has_cannabis and has_vape:
        tags.append(CANNABIS_VAPE)
    if has_psilocybin and has_mushroom and not has_vape and not has_amanita:
        tags.append(PSILOCYBIN_MUSHROOM)
    if has_psilocybin and has_vape and not has_amanita:
        tags.append(PSILOCYBIN_VAPE)

    ordered = _ordered_tags(tags)
    if not ordered:
        return None

    primary = next(
        product_type
        for product_type in (
            PSILOCYBIN_VAPE,
            PSILOCYBIN_MUSHROOM,
            CANNABIS_VAPE,
            CANNABIS_FLOWER,
        )
        if product_type in ordered
    )
    evidence: dict[str, bool | str | tuple[str, ...]] = {
        "primary_type": primary,
        "type_tags": ordered,
        "explicit_thca": has_thca,
        "explicit_cannabis": has_cannabis,
        "explicit_flower": has_flower,
        "explicit_vape": has_vape,
        "explicit_psilocybin": has_psilocybin,
        "explicit_mushroom": has_mushroom,
        "amanita_signal": has_amanita,
    }
    return ProductClassification(
        primary_type=primary,
        type_tags=ordered,
        evidence=evidence,
        permits_public_purchase_link=primary not in CONTROLLED_PRODUCT_TYPES,
    )


def validates_classification(classification: ProductClassification) -> bool:
    evidence = classification.evidence
    primary = classification.primary_type
    if primary not in SUPPORTED_PRODUCT_TYPES or primary not in classification.type_tags:
        return False
    if primary == CANNABIS_FLOWER:
        return bool(evidence.get("explicit_thca") and evidence.get("explicit_flower"))
    if primary == CANNABIS_VAPE:
        return bool(evidence.get("explicit_cannabis") and evidence.get("explicit_vape"))
    if primary == PSILOCYBIN_MUSHROOM:
        return bool(
            evidence.get("explicit_psilocybin")
            and evidence.get("explicit_mushroom")
            and not evidence.get("explicit_vape")
            and not evidence.get("amanita_signal")
        )
    if primary == PSILOCYBIN_VAPE:
        return bool(
            evidence.get("explicit_psilocybin")
            and evidence.get("explicit_vape")
            and not evidence.get("amanita_signal")
        )
    return False
