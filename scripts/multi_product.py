"""Type-aware product admission for DropFinder's flower, vape, and mushroom sections.

The existing autonomous worker remains the transport and evidence engine. This
module installs a narrow compatibility layer that admits only products with
explicit form evidence, preserves the strict exclusions for unrelated forms,
and expands existing public storefront routes without bypassing access controls.
"""
from __future__ import annotations

import hashlib
import re
import urllib.parse
from typing import Any, MutableMapping

CANNABIS_FLOWER = "cannabis_flower"
CANNABIS_VAPE = "cannabis_vape"
MUSHROOM = "mushroom"
MUSHROOM_VAPE = "mushroom_vape"
SUPPORTED_PRODUCT_TYPES = {
    CANNABIS_FLOWER,
    CANNABIS_VAPE,
    MUSHROOM,
    MUSHROOM_VAPE,
}

VAPE = re.compile(
    r"\b(?:vapes?|cartridges?|carts?|disposables?|all[- ]?in[- ]?one|510(?:[- ]thread)?)\b",
    re.I,
)
MUSHROOM_SIGNAL = re.compile(
    r"\b(?:mushrooms?|amanita|muscaria|psilocybin|functional\s+mushroom|lion'?s\s+mane|cordyceps|reishi)\b",
    re.I,
)
PSILOCYBIN = re.compile(r"\b(?:psilocybin|psilocin|magic\s+mushrooms?)\b", re.I)
CANNABIS_SIGNAL = re.compile(
    r"\b(?:thca|thc-a|high\s+thca|hemp|delta[- ]?9|cannabinoids?)\b",
    re.I,
)
VOLUME = re.compile(r"(?<!\d)(\d+(?:\.\d+)?)\s*m[lL]\b")

# Vapes and mushrooms are classified below instead of being rejected by form.
# Everything else in the historical strict-flower exclusion remains excluded.
GENERAL_HARD_EXCLUDE = re.compile(
    r"\b(?:pre[- ]?rolls?|prerolls?|joints?|blunts?|cones?|gumm(?:y|ies)|edibles?|"
    r"tinctures?|capsules?|beverages?|drinks?|seltzers?|concentrates?|rosin|badder|"
    r"budder|crumble|isolate|dabs?|seeds?|clones?|incense|topicals?|salves?|balms?|"
    r"creams?|lotions?|apparel|shirts?|hoodies?|hats?|posters?|fertilizer|accessories?|"
    r"grinders?|trays?|glass|pets?|gift\s*cards?|subscriptions?|samplers?|"
    r"mystery\s*(?:box|bag|pack)s?|wholesale|bundles?|hash\s*holes?)\b",
    re.I,
)

MERGE_FORBIDDEN = GENERAL_HARD_EXCLUDE
PLACEHOLDER = re.compile(
    r"^(?:product|flower|strain|vape|mushroom|indica|sativa|hybrid|"
    r"indica[, /]+hybrid[, /]+sativa|unknown|untitled)$",
    re.I,
)
ALT_CANNABINOID = re.compile(
    r"\b(?:cbd|cbg|type\s*[34]|delta[- ]?8|hhc|thc[- ]?p|thc[- ]?o|nicotine)\b",
    re.I,
)

STOREWIDE_ROUTES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "black_tie_cbd": (("shopify", "https://www.blacktiecbd.net/products.json?limit=250", "storewide"),),
    "crysp": (("woo", "https://crysp.co/wp-json/wc/store/v1/products?per_page=100", "storewide"),),
    "green_unicorn_farms": (("woo", "https://greenunicornfarms.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),),
    "hello_mary": (("woo", "https://shophellomary.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),),
    "holy_city_farms": (("woo", "https://holycityfarms.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),),
    "lucky_elk": (("shopify", "https://luckyelk.com/products.json?limit=250", "storewide"),),
    "pure_roots_botanicals": (("woo", "https://purerootsbotanicals.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),),
    "sherlocks_glass": (("woo", "https://sherlocksglass.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),),
    "smoky_mountain_cbd": (("woo", "https://www.smokymountaincbd.com/wp-json/wc/store/v1/products?per_page=100", "storewide"),),
}


def classify_text(value: str, *, core: Any | None = None) -> str | None:
    """Return a supported primary type only when the form is explicit."""
    normalized = str(value or "")
    if GENERAL_HARD_EXCLUDE.search(normalized):
        return None
    mushroom = bool(MUSHROOM_SIGNAL.search(normalized))
    vape = bool(VAPE.search(normalized))
    if mushroom and vape:
        return MUSHROOM_VAPE
    if mushroom:
        return MUSHROOM
    if vape and CANNABIS_SIGNAL.search(normalized):
        return CANNABIS_VAPE
    if core is not None and core.THCA.search(normalized) and core.FLOWER.search(normalized):
        return CANNABIS_FLOWER
    return None


def _append_storewide_routes(core: Any) -> None:
    expanded = []
    for source_id, vendor, routes in core.SOURCES:
        known = {route[1] for route in routes}
        additions = [route for route in STOREWIDE_ROUTES.get(source_id, ()) if route[1] not in known]
        expanded.append((source_id, vendor, [*routes, *additions]))
    core.SOURCES[:] = expanded


def _install_core(core: Any) -> None:
    core.HARD_EXCLUDE = GENERAL_HARD_EXCLUDE
    _append_storewide_routes(core)

    def record(
        source_id: str,
        vendor: str,
        route: tuple,
        name: Any,
        target: Any,
        desc: Any = "",
        price: Any = None,
        stock: Any = "",
        image: Any = "",
        variant: Any = "",
    ) -> dict | None:
        clean_name = core.text(name)
        clean_desc = core.text(desc)
        target_url = core.url(target, route[1])
        path = ""
        try:
            path = urllib.parse.unquote(urllib.parse.urlsplit(target_url).path).replace("-", " ").replace("_", " ")
        except ValueError:
            pass
        combined = f"{clean_name} {clean_desc} {path}"
        product_type = classify_text(combined, core=core)
        # Preserve the old category-route fallback only for explicit flower form.
        if product_type is None and core.FLOWER.search(combined) and "thca" in route[1].lower():
            product_type = CANNABIS_FLOWER
        if not clean_name or not target_url or product_type is None:
            return None

        ambiguous = core.AMBIGUOUS_FORM.search(combined)
        if product_type == CANNABIS_FLOWER and ambiguous and core.FORM_CONTEXT.search(combined) and not core.EXPLICIT_FLOWER.search(clean_name):
            return None

        current_price = core.num(price)
        quantity = core.grams(combined)
        quantity_unit = "g"
        if product_type in {CANNABIS_VAPE, MUSHROOM_VAPE}:
            volume = VOLUME.search(combined)
            if volume:
                quantity = core.num(volume.group(1))
                quantity_unit = "ml"
        potencies = [core.num(value) for value in core.POTENCY.findall(combined)]
        potency = max((value for value in potencies if value and value <= 100), default=None)
        public_purchase_allowed = not bool(PSILOCYBIN.search(combined))
        return {
            "id": hashlib.sha256(f"{source_id}|{target_url}|{variant}".encode()).hexdigest()[:24],
            "source_id": source_id,
            "vendor": vendor,
            "name": clean_name,
            "url": target_url,
            "image": core.url(image, route[1]) if image else "",
            "price": current_price,
            # Catalog v4 currently consumes grams/price_per_gram. For vape rows,
            # this numeric slot represents the explicitly labeled package volume.
            "grams": quantity,
            "quantity": quantity,
            "quantity_unit": quantity_unit,
            "price_per_gram": round(current_price / quantity, 4) if current_price and quantity else None,
            "price_per_unit": round(current_price / quantity, 4) if current_price and quantity else None,
            "thca": potency,
            "availability": core.availability(stock),
            "variant": core.text(variant),
            "source_type": route[0],
            "route_url": route[1],
            "collected_at": core.now(),
            "product_type": product_type,
            "type_tags": [product_type],
            "public_purchase_allowed": public_purchase_allowed,
        }

    def product_links(payload: str, route: tuple) -> list[str]:
        base = urllib.parse.urlsplit(route[1])
        seen: list[str] = []
        for href, label in core.ANCHOR.findall(payload):
            target = core.url(href, route[1])
            parsed = urllib.parse.urlsplit(target)
            clean_label = core.text(label)
            path = parsed.path.lower()
            if not target or parsed.netloc != base.netloc.lower() or target == core.url(route[1], route[1]):
                continue
            if not any(marker in path for marker in ("/product/", "/products/", "/shop/", "/l/national/products/", "/cbd-hemp-flower/")):
                continue
            signal = f"{clean_label} {path.replace('-', ' ')}"
            if classify_text(signal, core=core) is None:
                continue
            if target not in seen:
                seen.append(target)
            if len(seen) >= 24:
                break
        return seen

    core.record = record
    core.product_links = product_links


def install(reliability: Any) -> None:
    """Patch the proven worker in place without changing its transport layer."""
    worker = reliability.worker
    core = worker.core
    _install_core(core)

    def product_type(value: str) -> str | None:
        return classify_text(core.text(value), core=core)

    def has_product_evidence(value: str) -> bool:
        return product_type(value) is not None

    def evidence_payload(value: str, source: str) -> dict[str, Any]:
        normalized = core.text(value)
        classified = product_type(normalized)
        return {
            "explicit_thca": bool(core.THCA.search(normalized)),
            "explicit_flower": bool(core.FLOWER.search(normalized)),
            "explicit_vape": bool(VAPE.search(normalized)),
            "explicit_mushroom": bool(MUSHROOM_SIGNAL.search(normalized)),
            "controlled_psilocybin_signal": bool(PSILOCYBIN.search(normalized)),
            "product_type": classified,
            "evidence_source": source,
            "evidence_sha256": hashlib.sha256(normalized.lower().encode("utf-8")).hexdigest(),
        }

    def decorate(product: dict | None, evidence: str, source: str) -> dict | None:
        if not product:
            return None
        row = dict(product)
        classified = str(row.get("product_type") or product_type(evidence) or "")
        if classified not in SUPPORTED_PRODUCT_TYPES:
            return None
        row["product_type"] = classified
        row["type_tags"] = list(dict.fromkeys([classified, *(row.get("type_tags") or [])]))
        row["classification_evidence"] = evidence_payload(evidence, source)
        if classified in {MUSHROOM, MUSHROOM_VAPE} and PSILOCYBIN.search(evidence):
            row["public_purchase_allowed"] = False
        return row

    def gate(products: list[dict]) -> tuple[bool, list[str], dict[str, Any]]:
        reasons: list[str] = []
        count = len(products)
        valid_urls = sum(bool(str(row.get("url") or "").strip()) for row in products)
        priced = sum(core.num(row.get("price")) is not None for row in products)
        evidenced = 0
        by_type: dict[str, int] = {}
        for row in products:
            row_type = str(row.get("product_type") or "")
            evidence = row.get("classification_evidence") if isinstance(row.get("classification_evidence"), dict) else {}
            if row_type in SUPPORTED_PRODUCT_TYPES and evidence.get("product_type") == row_type:
                evidenced += 1
                by_type[row_type] = by_type.get(row_type, 0) + 1
        if count == 0:
            reasons.append("no_qualifying_products")
        if count and valid_urls / count < 0.90:
            reasons.append("insufficient_product_urls")
        if count and priced == 0:
            reasons.append("no_priced_products")
        if count and evidenced != count:
            reasons.append("missing_product_level_evidence")
        return not reasons, reasons, {
            "products": count,
            "url_coverage": round(valid_urls / count, 4) if count else 0,
            "priced_products": priced,
            "evidenced_products": evidenced,
            "products_by_type": dict(sorted(by_type.items())),
        }

    worker.has_product_evidence = has_product_evidence
    worker.evidence_payload = evidence_payload
    worker.decorate = decorate
    worker.gate = gate


def install_merge(namespace: MutableMapping[str, Any]) -> None:
    """Install the matching final-sanitizer policy into autonomous_merge."""
    namespace["FORBIDDEN"] = MERGE_FORBIDDEN
    thca = namespace["THCA"]
    flower = namespace["FLOWER"]
    ambiguous_hash = namespace["AMBIGUOUS_HASH"]

    def reject_reason(product: dict) -> str | None:
        name = str(product.get("name") or "").strip()
        url = str(product.get("url") or "").strip()
        text = namespace["product_text"](product)
        evidence = product.get("classification_evidence") if isinstance(product.get("classification_evidence"), dict) else {}
        classified = str(product.get("product_type") or evidence.get("product_type") or classify_text(text) or "")
        explicit_thca = bool(evidence.get("explicit_thca")) or bool(thca.search(text))
        explicit_flower = bool(evidence.get("explicit_flower")) or bool(flower.search(text))
        explicit_vape = bool(evidence.get("explicit_vape")) or bool(VAPE.search(text))
        explicit_mushroom = bool(evidence.get("explicit_mushroom")) or bool(MUSHROOM_SIGNAL.search(text))

        if not name:
            return "missing_name"
        if not url.startswith(("http://", "https://")):
            return "missing_or_invalid_url"
        if MERGE_FORBIDDEN.search(text):
            return "forbidden_product_form"
        if PLACEHOLDER.fullmatch(name):
            return "generic_or_fragment_title"
        if classified not in SUPPORTED_PRODUCT_TYPES:
            return "unsupported_or_ambiguous_product_type"
        if classified == CANNABIS_FLOWER:
            if ambiguous_hash.search(text) and not explicit_flower:
                return "ambiguous_hash_without_flower_evidence"
            if ALT_CANNABINOID.search(text) and not explicit_thca:
                return "alternate_cannabinoid_without_thca"
            if not explicit_thca:
                return "missing_product_level_thca_evidence"
            if not explicit_flower:
                return "missing_product_level_flower_evidence"
        elif classified == CANNABIS_VAPE:
            if ALT_CANNABINOID.search(text) and not explicit_thca:
                return "alternate_cannabinoid_without_thca"
            if not explicit_thca:
                return "missing_product_level_thca_evidence"
            if not explicit_vape:
                return "missing_product_level_vape_evidence"
        elif classified in {MUSHROOM, MUSHROOM_VAPE}:
            if not explicit_mushroom:
                return "missing_product_level_mushroom_evidence"
            if classified == MUSHROOM_VAPE and not explicit_vape:
                return "missing_product_level_vape_evidence"
        if product.get("availability") == "out_of_stock" and product.get("price") in (None, "") and not product.get("image"):
            return "out_of_stock_placeholder_without_product_data"
        product["product_type"] = classified
        product.setdefault("type_tags", [classified])
        if classified in {MUSHROOM, MUSHROOM_VAPE} and bool(evidence.get("controlled_psilocybin_signal")):
            product["public_purchase_allowed"] = False
        return None

    namespace["reject_reason"] = reject_reason


def self_test() -> int:
    class Core:
        THCA = re.compile(r"\b(?:thca|thc-a|high\s+thca)\b", re.I)
        FLOWER = re.compile(r"\b(?:flower|buds?)\b", re.I)

    assert classify_text("Blue Dream THCA flower", core=Core) == CANNABIS_FLOWER
    assert classify_text("THCA live resin disposable vape", core=Core) == CANNABIS_VAPE
    assert classify_text("Amanita mushroom caps 7g", core=Core) == MUSHROOM
    assert classify_text("Psilocybin mushroom vape 1ml", core=Core) == MUSHROOM_VAPE
    assert classify_text("Nicotine disposable vape", core=Core) is None
    assert classify_text("THCA gummies", core=Core) is None
    return 0
