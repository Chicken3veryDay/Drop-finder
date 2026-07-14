#!/usr/bin/env python3
"""Complete-data worker: expand embedded product-page variants after v4 enrichment."""
from __future__ import annotations

import concurrent.futures
import html
import json
import re
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import autonomous_worker_v4 as v4  # type: ignore

worker = v4.worker
core = v4.core
_original_scan_source = worker.scan_source

_DATA_PRODUCT_VARIATIONS = re.compile(
    r"data-product_variations\s*=\s*([\"'])(.*?)\1",
    re.I | re.S,
)


def canonical_product_url(value: object) -> str:
    raw = str(value or "").strip()
    try:
        parsed = urllib.parse.urlsplit(raw)
    except ValueError:
        return raw
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _decode_variation_payload(raw: str) -> list[dict]:
    value = html.unescape(raw).strip()
    if not value or value.lower() in {"false", "null", "[]"}:
        return []
    candidates = [value]
    if "\\\"" in value:
        candidates.append(value.replace("\\\"", '"'))
    for candidate in candidates:
        try:
            decoded = json.loads(candidate)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(decoded, list):
            return [row for row in decoded if isinstance(row, dict)]
    return []


def embedded_variations(payload: str) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for match in _DATA_PRODUCT_VARIATIONS.finditer(payload):
        for row in _decode_variation_payload(match.group(2)):
            key = str(row.get("variation_id") or row.get("id") or json.dumps(row.get("attributes") or {}, sort_keys=True))
            if key and key not in seen:
                rows.append(row)
                seen.add(key)
    return rows


def _variant_label(attributes: object) -> str:
    if not isinstance(attributes, dict):
        return ""
    values: list[str] = []
    for key, raw in attributes.items():
        value = core.text(raw).replace("-", " ")
        if not value:
            continue
        label = core.text(str(key).replace("attribute_", "").replace("pa_", "").replace("_", " "))
        values.append(f"{label}: {value}" if label else value)
    return " · ".join(values)


def _variation_image(variation: dict, fallback: str) -> str:
    image = variation.get("image") if isinstance(variation.get("image"), dict) else {}
    for key in ("full_src", "src", "url", "gallery_thumbnail_src"):
        value = str(image.get(key) or "").strip()
        if value:
            return value
    return fallback


def _variation_price(variation: dict) -> float | None:
    for key in ("display_price", "display_regular_price", "price"):
        value = v4._finite_positive(variation.get(key))
        if value is not None:
            return round(value, 4)
    return None


def _variation_stock(variation: dict) -> object:
    if variation.get("is_in_stock") is not None:
        return bool(variation.get("is_in_stock"))
    availability = core.text(variation.get("availability_html")).lower()
    if "out of stock" in availability or "sold out" in availability:
        return False
    if "in stock" in availability:
        return True
    return ""


def _variation_url(product_url: str, variation: dict) -> str:
    try:
        parsed = urllib.parse.urlsplit(product_url)
    except ValueError:
        return product_url
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    attributes = variation.get("attributes") if isinstance(variation.get("attributes"), dict) else {}
    for key, value in attributes.items():
        if value not in (None, ""):
            query[str(key)] = str(value)
    variation_id = variation.get("variation_id") or variation.get("id")
    if variation_id:
        query["variation_id"] = str(variation_id)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), ""))


def rows_from_embedded_variations(parent: dict, payload: str) -> list[dict]:
    variations = embedded_variations(payload)
    if not variations:
        return []
    base_url = canonical_product_url(parent.get("url"))
    route = ("html", base_url, "product_detail_embedded_variations")
    page_potencies = v4._thca_values(payload)
    page_potency = page_potencies[0] if len(page_potencies) == 1 else None
    rows: list[dict] = []
    for variation in variations:
        if variation.get("variation_is_visible") is False or variation.get("variation_is_active") is False:
            continue
        label = _variant_label(variation.get("attributes"))
        if not label:
            continue
        price = _variation_price(variation)
        target = _variation_url(base_url, variation)
        row = core.record(
            parent.get("source_id"),
            parent.get("vendor"),
            route,
            core.text(f"{parent.get('name', '')} {label}"),
            target,
            payload,
            price,
            _variation_stock(variation),
            _variation_image(variation, str(parent.get("image") or "")),
            label,
        )
        if not row:
            continue
        row["parent_id"] = parent.get("id")
        row["variant_id"] = variation.get("variation_id") or variation.get("id")
        row["price_source"] = "woo_embedded_variation"
        row["stock_source"] = "woo_embedded_variation"
        row["classification_evidence"] = parent.get("classification_evidence") or v4.worker.evidence_payload(
            core.text(f"{parent.get('name', '')} {label} {base_url}"),
            "product_page_embedded_variation",
        )
        if page_potency is not None:
            row["thca"] = page_potency
            row["thca_source"] = "product_page"
        rows.append(row)
    return core.dedupe(rows)


def _fetch_product_page(url: str) -> tuple[str, str, int]:
    try:
        return core.fetch(url)
    except Exception:
        return "", "", 0


def complete_scan_source(source: tuple) -> tuple[list[dict], dict]:
    products, status = _original_scan_source(source)
    if not products:
        return products, status

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in products:
        groups[canonical_product_url(row.get("url"))].append(row)

    fetched: dict[str, tuple[str, str, int]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(groups))) as executor:
        futures = {executor.submit(_fetch_product_page, url): url for url in groups if url.startswith(("http://", "https://"))}
        for future in concurrent.futures.as_completed(futures):
            fetched[futures[future]] = future.result()

    final_rows: list[dict] = []
    expanded_groups = 0
    for url, group in groups.items():
        payload, content_type, http_status = fetched.get(url, ("", "", 0))
        expanded: list[dict] = []
        if http_status == 200 and content_type in {"text/html", "application/xhtml+xml"}:
            expanded = rows_from_embedded_variations(group[0], payload)
        if expanded:
            final_rows.extend(expanded)
            expanded_groups += 1
        else:
            final_rows.extend(group)

    final_rows = core.dedupe(final_rows)
    status = dict(status)
    quality = dict(status.get("quality") or {})
    quality.update(
        embedded_variation_products=sum(row.get("price_source") == "woo_embedded_variation" for row in final_rows),
        embedded_variation_groups=expanded_groups,
        exact_pricing=sum(row.get("pricing_confidence") in {"exact_variant", "exact_title"} for row in final_rows),
        potency_products=sum(v4._finite_positive(row.get("thca")) is not None for row in final_rows),
        known_stock=sum(row.get("availability") in {"in_stock", "out_of_stock"} for row in final_rows),
    )
    status.update(products=len(final_rows), quality=quality, worker="autonomous_worker_v5_complete_html_variants")
    return final_rows, status


worker.scan_source = complete_scan_source


def self_test() -> int:
    v4.self_test()
    fixture = """
    <form class="variations_form cart" data-product_variations="[{&quot;variation_id&quot;:101,&quot;display_price&quot;:49.99,&quot;is_in_stock&quot;:true,&quot;variation_is_visible&quot;:true,&quot;variation_is_active&quot;:true,&quot;attributes&quot;:{&quot;attribute_weight&quot;:&quot;7g&quot;},&quot;image&quot;:{&quot;full_src&quot;:&quot;https://example.test/flower.jpg&quot;}}]">
    </form>
    <div>Laboratory result: 28.6% THCA</div>
    """
    parent = {
        "id": "parent",
        "source_id": "fixture",
        "vendor": "Fixture",
        "name": "Blue Dream THCA Flower",
        "url": "https://example.test/product/blue-dream",
        "image": "",
        "classification_evidence": {"explicit_thca": True, "explicit_flower": True},
    }
    rows = rows_from_embedded_variations(parent, fixture)
    assert len(rows) == 1
    row = rows[0]
    assert row["grams"] == 7.0
    assert row["price"] == 49.99
    assert row["price_per_gram"] == round(49.99 / 7, 4)
    assert row["thca"] == 28.6
    assert row["availability"] == "in_stock"
    assert row["variant_id"] == 101
    assert row["pricing_confidence"] == "exact_variant"
    assert canonical_product_url("https://x.test/product/a?variant=2") == "https://x.test/product/a"
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    return worker.main()


if __name__ == "__main__":
    raise SystemExit(main())
