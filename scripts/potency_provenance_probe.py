#!/usr/bin/env python3
"""Find explicit THCA potency evidence in product pages and linked COA documents."""
from __future__ import annotations

import argparse
import concurrent.futures
import io
import json
import math
import re
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

UA = "DropFinder-Potency-Provenance-Probe/1.0"
LINK = re.compile(r"(?:href|src|data-src)\s*=\s*[\"']([^\"']+)[\"']", re.I)
TAG = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")
COA_HINT = re.compile(r"(?:\bcoa\b|certificate[-_ ]?of[-_ ]?analysis|lab[-_ ]?(?:report|result|test)|test[-_ ]?result|analysis|potency)", re.I)
THCA_PATTERNS = (
    re.compile(r"\b(?:total\s+)?(?:thca|thc-a|thca-a|delta[- ]?9[- ]?thca|d9[- ]?thca)\b\s*(?:content|potency|percentage|percent)?\s*[:=\-]?\s*(\d{1,2}(?:\.\d+)?)\s*%", re.I),
    re.compile(r"(\d{1,2}(?:\.\d+)?)\s*%\s*(?:total\s+)?(?:thca|thc-a|thca-a|delta[- ]?9[- ]?thca|d9[- ]?thca)\b", re.I),
    re.compile(r'\"(?:thca|thc_a|thca_percent|thca_percentage|delta9_thca)\"\s*:\s*\"?(\d{1,2}(?:\.\d+)?)', re.I),
)


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean(value: object) -> str:
    return SPACE.sub(" ", TAG.sub(" ", str(value or ""))).strip()


def positive(value: object) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and 0 < number <= 100 else None


def potencies(value: object) -> list[float]:
    results: list[float] = []
    raw = str(value or "")
    normalized = clean(raw)
    for candidate in (raw, normalized):
        for pattern in THCA_PATTERNS:
            for match in pattern.findall(candidate):
                number = positive(match)
                if number is not None:
                    results.append(round(number, 3))
    return sorted(set(results))


def fetch(url: str, limit: int = 8_000_000, timeout: int = 25) -> tuple[bytes, str, int]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/pdf,application/json,image/*;q=.8,*/*;q=.1",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(limit + 1)
        if len(body) > limit:
            raise ValueError("response exceeds probe limit")
        content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
        return body, content_type, int(getattr(response, "status", 200))


def decode(body: bytes, content_type: str) -> str:
    if content_type == "application/pdf":
        reader = PdfReader(io.BytesIO(body))
        return " ".join((page.extract_text() or "") for page in reader.pages[:12])
    return body.decode("utf-8", "replace")


def evidence_links(payload: str, page_url: str) -> list[str]:
    links: list[str] = []
    for raw in LINK.findall(payload):
        target = urllib.parse.urljoin(page_url, raw.replace("&amp;", "&"))
        try:
            parsed = urllib.parse.urlsplit(target)
        except ValueError:
            continue
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        path = urllib.parse.unquote(parsed.path).lower()
        if COA_HINT.search(target) or path.endswith(".pdf"):
            canonical = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path, parsed.query, ""))
            if canonical not in links:
                links.append(canonical)
        if len(links) >= 12:
            break
    return links


def inspect_product(product: dict[str, Any]) -> dict[str, Any]:
    result = {
        "id": product.get("id"),
        "source_id": product.get("source_id"),
        "name": product.get("name"),
        "url": product.get("url"),
        "catalog_thca": product.get("thca"),
    }
    url = str(product.get("url") or "")
    try:
        body, content_type, status = fetch(url)
        payload = decode(body, content_type)
        page_values = potencies(payload)
        links = evidence_links(payload, url)
        result.update(
            page_status=status,
            page_content_type=content_type,
            page_thca_candidates=page_values,
            evidence_links=links,
        )
    except Exception as exc:
        result.update(page_status=0, page_error=f"{type(exc).__name__}: {exc}"[:500])
        return result

    document_rows: list[dict[str, Any]] = []
    for link in result.get("evidence_links", [])[:4]:
        document: dict[str, Any] = {"url": link}
        try:
            body, content_type, status = fetch(link, limit=15_000_000, timeout=30)
            document.update(status=status, content_type=content_type)
            if content_type.startswith("image/"):
                document["result"] = "image_only_not_machine_verified"
            else:
                text = decode(body, content_type)
                document["thca_candidates"] = potencies(text)
                document["result"] = "parsed"
        except Exception as exc:
            document.update(status=0, error=f"{type(exc).__name__}: {exc}"[:500])
        document_rows.append(document)
    result["documents"] = document_rows
    page_candidates = result.get("page_thca_candidates") or []
    document_candidates = sorted({
        value
        for document in document_rows
        for value in document.get("thca_candidates", [])
    })
    result["document_thca_candidates"] = document_candidates
    combined = sorted(set(page_candidates) | set(document_candidates))
    result["verified_thca"] = combined[0] if len(combined) == 1 else None
    result["verified_source"] = (
        "product_page" if len(page_candidates) == 1 and not document_candidates
        else "linked_document" if len(document_candidates) == 1 and not page_candidates
        else "page_and_document_agree" if len(combined) == 1 and page_candidates and document_candidates
        else None
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-url", default="https://dropfinder-os.onrender.com/api/catalog")
    parser.add_argument("--output", type=Path, default=Path("deployment/potency-provenance-probe.json"))
    parser.add_argument("--max-products", type=int, default=350)
    args = parser.parse_args()

    body, _, _ = fetch(args.catalog_url)
    catalog = json.loads(body.decode("utf-8"))
    products = [row for row in catalog.get("products", []) if isinstance(row, dict)]
    # One representative per canonical product URL avoids probing each exact variant repeatedly.
    representatives: dict[str, dict[str, Any]] = {}
    for product in products:
        url = str(product.get("url") or "")
        try:
            parsed = urllib.parse.urlsplit(url)
            canonical = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path, "", ""))
        except ValueError:
            canonical = url
        representatives.setdefault(canonical, product)
    selected = list(representatives.values())[: max(1, min(args.max_products, 500))]

    rows: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=14) as executor:
        futures = [executor.submit(inspect_product, product) for product in selected]
        for future in concurrent.futures.as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: (str(row.get("source_id")), str(row.get("name"))))

    per_source: dict[str, Any] = {}
    sources = sorted({str(row.get("source_id") or "unknown") for row in rows})
    for source in sources:
        source_rows = [row for row in rows if str(row.get("source_id") or "unknown") == source]
        per_source[source] = {
            "probed_products": len(source_rows),
            "pages_fetched": sum(row.get("page_status") == 200 for row in source_rows),
            "products_with_page_thca": sum(len(row.get("page_thca_candidates") or []) == 1 for row in source_rows),
            "products_with_evidence_links": sum(bool(row.get("evidence_links")) for row in source_rows),
            "products_with_document_thca": sum(len(row.get("document_thca_candidates") or []) == 1 for row in source_rows),
            "products_with_single_verified_thca": sum(row.get("verified_thca") is not None for row in source_rows),
            "evidence_link_count": sum(len(row.get("evidence_links") or []) for row in source_rows),
        }

    report = {
        "schema_version": "dropfinder-potency-provenance-probe-v1",
        "probed_at": now(),
        "catalog_generated_at": catalog.get("generated_at"),
        "catalog_products": len(products),
        "unique_product_pages": len(representatives),
        "probed_product_pages": len(rows),
        "verified_product_pages": sum(row.get("verified_thca") is not None for row in rows),
        "per_source": per_source,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "catalog_products": report["catalog_products"],
        "probed_product_pages": report["probed_product_pages"],
        "verified_product_pages": report["verified_product_pages"],
        "sources": len(per_source),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
