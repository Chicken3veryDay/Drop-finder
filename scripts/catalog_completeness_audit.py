#!/usr/bin/env python3
"""Audit the live DropFinder catalog for complete, trustworthy comparison data."""
from __future__ import annotations

import argparse
import concurrent.futures
import html
import json
import math
import re
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UA = "DropFinder-Completeness-Audit/1.0"
TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")
THCA_PATTERNS = (
    re.compile(r"\b(?:thca|thc-a)\b\s*(?:content|potency|total|percentage|percent|%)?\s*[:=\-]?\s*(\d{1,2}(?:\.\d+)?)\s*%", re.I),
    re.compile(r"(\d{1,2}(?:\.\d+)?)\s*%\s*\b(?:thca|thc-a)\b", re.I),
    re.compile(r'"(?:thca|thc_a|thca_percent|thca_percentage)"\s*:\s*"?(\d{1,2}(?:\.\d+)?)', re.I),
)
WEIGHT = re.compile(
    r"(?<![\d.])(?:"
    r"(?P<ordinal>1/8|1/4|1/2)(?:st|nd|rd|th)(?:\s*(?:oz|ounces?))?"
    r"|(?P<fraction>1/8|1/4|1/2)\s*(?:oz|ounces?)"
    r"|(?P<number>\d+(?:\.\d+)?)\s*\+?\s*(?P<unit>g|grams?|oz|ounces?|lb|lbs|pounds?)"
    r"|(?P<word>eighth|quarter\s+(?:oz|ounces?)|half(?:\s+|-)??(?:oz|ounces?)|one\s+ounce|an\s+ounce|ounce|zip)"
    r")\b",
    re.I,
)
META_PRICE = re.compile(
    r"(?:product:price:amount|og:price:amount|priceCurrency|lowPrice|highPrice|\"price\")"
    r"[^\d]{0,80}(\d{1,4}(?:\.\d{1,2})?)",
    re.I,
)


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def number(value: object) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def positive(value: object) -> float | None:
    parsed = number(value)
    return parsed if parsed is not None and parsed > 0 else None


def fetch_json(url: str, timeout: int = 90) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def fetch_text(url: str, timeout: int = 25) -> tuple[str, int, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/json;q=.9,*/*;q=.1",
            "Accept-Encoding": "identity",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(5_000_001)
            if len(raw) > 5_000_000:
                raise ValueError("response exceeds 5 MB audit limit")
            charset = response.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, "replace"), int(getattr(response, "status", 200)), str(response.headers.get("Content-Type") or "")
    except urllib.error.HTTPError as exc:
        return exc.read(250_000).decode("utf-8", "replace"), int(exc.code), str(exc.headers.get("Content-Type") or "")


def text(value: object) -> str:
    return WS.sub(" ", TAG.sub(" ", html.unescape(str(value or "")))).strip()


def weight_candidates(value: object) -> list[float]:
    normalized = text(value)
    values: list[float] = []
    fraction_grams = {"1/8": 3.5437, "1/4": 7.0874, "1/2": 14.1748}
    word_grams = {
        "eighth": 3.5437,
        "quarter oz": 7.0874,
        "quarter ounce": 7.0874,
        "quarter ounces": 7.0874,
        "half oz": 14.1748,
        "half-oz": 14.1748,
        "half ounce": 14.1748,
        "half ounces": 14.1748,
        "one ounce": 28.3495,
        "an ounce": 28.3495,
        "ounce": 28.3495,
        "zip": 28.3495,
    }
    for match in WEIGHT.finditer(normalized):
        grams: float | None = None
        fraction = match.group("ordinal") or match.group("fraction")
        if fraction:
            grams = fraction_grams.get(fraction)
        elif match.group("word"):
            key = re.sub(r"\s+", " ", match.group("word").lower()).strip()
            grams = word_grams.get(key)
        else:
            n = positive(match.group("number"))
            unit = str(match.group("unit") or "").lower()
            if n is not None:
                if unit.startswith("g"):
                    grams = n
                elif unit.startswith("oz") or unit.startswith("ounce"):
                    grams = n * 28.3495
                elif unit.startswith("lb") or unit.startswith("pound"):
                    grams = n * 453.59237
        if grams is not None and 0.1 <= grams <= 1814.37:
            values.append(round(grams, 3))
    return sorted(set(values))


def potency_candidates(value: object) -> list[float]:
    results: list[float] = []
    for pattern in THCA_PATTERNS:
        for raw in pattern.findall(str(value or "")):
            n = positive(raw)
            if n is not None and 0 < n <= 100:
                results.append(round(n, 3))
    return sorted(set(results))


def page_probe(product: dict[str, Any]) -> dict[str, Any]:
    url = str(product.get("url") or "")
    result: dict[str, Any] = {
        "id": product.get("id"),
        "source_id": product.get("source_id"),
        "name": product.get("name"),
        "url": url,
    }
    if not url.startswith(("http://", "https://")):
        result.update(status="invalid_url")
        return result
    try:
        payload, status, content_type = fetch_text(url)
        result.update(http_status=status, content_type=content_type[:120])
        normalized = text(payload)
        result["page_thca_candidates"] = potency_candidates(payload)[:20]
        result["page_weight_candidates"] = weight_candidates(normalized)[:40]
        result["page_price_candidates"] = sorted({round(float(x), 2) for x in META_PRICE.findall(payload) if 0 < float(x) < 10000})[:40]
        result["recoverable_thca"] = bool(result["page_thca_candidates"])
        result["recoverable_weight"] = bool(result["page_weight_candidates"])
        result["recoverable_price"] = bool(result["page_price_candidates"])
        result["status"] = "fetched" if status == 200 else "http_error"
    except Exception as exc:
        result.update(status="error", error=f"{type(exc).__name__}: {exc}"[:500])
    return result


def product_issues(product: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    price = positive(product.get("price"))
    grams = positive(product.get("grams"))
    ppg = positive(product.get("price_per_gram"))
    thca = positive(product.get("thca"))
    if price is None:
        issues.append("missing_price")
    if grams is None:
        issues.append("missing_grams")
    if ppg is None:
        issues.append("missing_price_per_gram")
    if thca is None or thca > 100:
        issues.append("missing_thca")
    if product.get("availability") not in {"in_stock", "out_of_stock"}:
        issues.append("unknown_availability")
    if not str(product.get("image") or "").startswith(("http://", "https://")):
        issues.append("missing_image")
    if not str(product.get("url") or "").startswith(("http://", "https://")):
        issues.append("missing_url")
    if price is not None and grams is not None:
        calculated = round(price / grams, 4)
        if ppg is None or abs(calculated - ppg) > max(0.02, calculated * 0.01):
            issues.append("price_per_gram_mismatch")
    if product.get("pricing_confidence") not in {"exact_variant", "exact_title"}:
        issues.append("unpaired_price_weight")
    return sorted(set(issues))


def audit(catalog: dict[str, Any], inspect_pages: bool, max_pages: int) -> dict[str, Any]:
    products = catalog.get("products") if isinstance(catalog, dict) else []
    products = products if isinstance(products, list) else []
    issue_counts: Counter[str] = Counter()
    source_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incomplete: list[dict[str, Any]] = []
    for product in products:
        if not isinstance(product, dict):
            continue
        issues = product_issues(product)
        issue_counts.update(issues)
        source_id = str(product.get("source_id") or "unknown")
        source_rows[source_id].append(product)
        if issues:
            incomplete.append({
                "id": product.get("id"),
                "source_id": source_id,
                "vendor": product.get("vendor"),
                "name": product.get("name"),
                "variant": product.get("variant"),
                "url": product.get("url"),
                "price": product.get("price"),
                "grams": product.get("grams"),
                "price_per_gram": product.get("price_per_gram"),
                "thca": product.get("thca"),
                "availability": product.get("availability"),
                "pricing_confidence": product.get("pricing_confidence"),
                "issues": issues,
            })

    per_source: dict[str, Any] = {}
    for source_id, rows in sorted(source_rows.items()):
        source_issue_counts: Counter[str] = Counter()
        complete = 0
        for row in rows:
            issues = product_issues(row)
            source_issue_counts.update(issues)
            complete += not issues
        per_source[source_id] = {
            "products": len(rows),
            "complete_products": complete,
            "complete_ratio": round(complete / len(rows), 4) if rows else 0,
            "issue_counts": dict(source_issue_counts.most_common()),
        }

    probes: list[dict[str, Any]] = []
    if inspect_pages and incomplete:
        # Probe a balanced sample from every source first, then fill remaining slots.
        chosen: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        originals = {str(row.get("id")): row for row in products if isinstance(row, dict)}
        for row in incomplete:
            by_source[row["source_id"]].append(row)
        for source_id in sorted(by_source):
            for row in by_source[source_id][: min(8, len(by_source[source_id]))]:
                original = originals.get(str(row.get("id")))
                if original and str(original.get("id")) not in seen_ids:
                    chosen.append(original)
                    seen_ids.add(str(original.get("id")))
        for row in products:
            if len(chosen) >= max_pages:
                break
            if not isinstance(row, dict) or str(row.get("id")) in seen_ids or not product_issues(row):
                continue
            chosen.append(row)
            seen_ids.add(str(row.get("id")))
        chosen = chosen[:max_pages]
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(page_probe, row) for row in chosen]
            for future in concurrent.futures.as_completed(futures):
                probes.append(future.result())
        probes.sort(key=lambda row: (str(row.get("source_id")), str(row.get("name"))))

    recoverability: dict[str, Any] = {}
    if probes:
        for source_id in sorted({str(row.get("source_id")) for row in probes}):
            rows = [row for row in probes if str(row.get("source_id")) == source_id]
            recoverability[source_id] = {
                "probed": len(rows),
                "fetched": sum(row.get("status") == "fetched" for row in rows),
                "thca_recoverable": sum(bool(row.get("recoverable_thca")) for row in rows),
                "weight_recoverable": sum(bool(row.get("recoverable_weight")) for row in rows),
                "price_recoverable": sum(bool(row.get("recoverable_price")) for row in rows),
            }

    return {
        "schema_version": "dropfinder-catalog-completeness-audit-v2",
        "audited_at": now(),
        "catalog_generated_at": catalog.get("generated_at"),
        "product_count": len(products),
        "complete_product_count": len(products) - len(incomplete),
        "complete_ratio": round((len(products) - len(incomplete)) / len(products), 4) if products else 0,
        "incomplete_product_count": len(incomplete),
        "issue_counts": dict(issue_counts.most_common()),
        "per_source": per_source,
        "recoverability": recoverability,
        "incomplete_examples": incomplete[:250],
        "page_probes": probes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-url", default="https://dropfinder-os.onrender.com/api/catalog")
    parser.add_argument("--catalog-file", type=Path)
    parser.add_argument("--output", type=Path, default=Path("deployment/catalog-completeness-audit.json"))
    parser.add_argument("--inspect-pages", action="store_true")
    parser.add_argument("--max-pages", type=int, default=160)
    args = parser.parse_args()
    catalog = json.loads(args.catalog_file.read_text(encoding="utf-8")) if args.catalog_file else fetch_json(args.catalog_url)
    report = audit(catalog, args.inspect_pages, max(1, min(args.max_pages, 500)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("product_count", "complete_product_count", "complete_ratio", "issue_counts")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
