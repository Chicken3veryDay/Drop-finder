"""Vendor-configured discovery of public COA and terpene documents."""
from __future__ import annotations

from html.parser import HTMLParser
import json
import re
from typing import Any, Iterable

from .models import DocumentCandidate, Provenance
from .urls import UnsafeUrl, canonicalize_url

DOCUMENT_WORDS = re.compile(r"\b(coa|certificate(?:s)? of analysis|lab(?:oratory)? (?:report|result|test)|terpene|potency|full[- ]panel)\b", re.I)
PDF_WORDS = re.compile(r"\.pdf(?:$|[?#])", re.I)
BATCH_WORDS = re.compile(r"\b(?:batch|lot|sample)\s*(?:id|no\.?|number|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})", re.I)
WEIGHT = re.compile(r"(?<!\d)(0\.5|1|2|3\.5|4|7|8|14|16|28|32)\s*(?:g|grams?)\b", re.I)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, dict[str, str]]] = []
        self._href = ""
        self._attrs: dict[str, str] = {}
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._attrs = {str(k).lower(): str(v or "") for k, v in attrs}
            self._href = self._attrs.get("href", "")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append((self._href, " ".join(self._text).strip(), self._attrs))
            self._href = ""
            self._attrs = {}
            self._text = []


def _kind(text: str) -> str:
    lower = text.lower()
    if "terpene" in lower and any(token in lower for token in ("coa", "lab", "certificate", "panel")):
        return "combined_lab_report"
    if "terpene" in lower:
        return "terpene_report"
    if any(token in lower for token in ("coa", "certificate", "lab", "potency", "panel")):
        return "coa"
    return "unknown"


def discover_html_documents(
    payload: str,
    *,
    vendor_id: str,
    page_url: str,
    allowed_hosts: set[str],
    observed_at: str,
    product_id: str = "",
) -> list[DocumentCandidate]:
    parser = _LinkParser()
    parser.feed(payload)
    candidates: list[DocumentCandidate] = []
    seen: set[str] = set()
    for href, label, attrs in parser.links:
        context = " ".join([label, attrs.get("title", ""), attrs.get("aria-label", ""), href])
        if not (DOCUMENT_WORDS.search(context) or PDF_WORDS.search(href)):
            continue
        try:
            target = canonicalize_url(href, base_url=page_url, allowed_hosts=allowed_hosts)
        except UnsafeUrl:
            continue
        if target in seen:
            continue
        seen.add(target)
        batch = (BATCH_WORDS.search(context).group(1) if BATCH_WORDS.search(context) else "")
        weight = float(WEIGHT.search(context).group(1)) if WEIGHT.search(context) else None
        candidates.append(DocumentCandidate(
            vendor_id=vendor_id,
            url=target,
            document_kind=_kind(context),  # type: ignore[arg-type]
            title=label.strip(),
            product_url=page_url if product_id else "",
            product_id=product_id,
            batch_id=batch,
            weight_grams=weight,
            content_type_hint="application/pdf" if PDF_WORDS.search(target) else "",
            provenance=Provenance(page_url, "html_anchor", observed_at),
        ))
    return sorted(candidates, key=lambda row: (row.document_kind, row.url, row.document_id))


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def discover_json_documents(
    payload: str | bytes | dict[str, Any] | list[Any],
    *,
    vendor_id: str,
    source_url: str,
    allowed_hosts: set[str],
    observed_at: str,
) -> list[DocumentCandidate]:
    data = json.loads(payload) if isinstance(payload, (str, bytes, bytearray)) else payload
    results: list[DocumentCandidate] = []
    seen: set[str] = set()
    url_keys = {"url", "href", "document_url", "coa_url", "lab_url", "pdf", "download"}
    for obj in _walk(data):
        context = json.dumps(obj, sort_keys=True, default=str)[:12000]
        if not DOCUMENT_WORDS.search(context):
            continue
        product_id = str(obj.get("product_id") or obj.get("productId") or obj.get("handle") or "")
        variant_id = str(obj.get("variant_id") or obj.get("variantId") or "")
        batch_id = str(obj.get("batch_id") or obj.get("batch") or obj.get("lot") or "")
        title = str(obj.get("title") or obj.get("name") or obj.get("label") or "")
        for key, value in obj.items():
            if str(key).lower() not in url_keys or not isinstance(value, str):
                continue
            try:
                target = canonicalize_url(value, base_url=source_url, allowed_hosts=allowed_hosts)
            except UnsafeUrl:
                continue
            if target in seen:
                continue
            seen.add(target)
            results.append(DocumentCandidate(
                vendor_id=vendor_id,
                url=target,
                document_kind=_kind(f"{key} {title} {target}"),  # type: ignore[arg-type]
                title=title,
                product_id=product_id,
                variant_id=variant_id,
                batch_id=batch_id,
                content_type_hint="application/pdf" if PDF_WORDS.search(target) else "",
                provenance=Provenance(source_url, "structured_json", observed_at),
            ))
    return sorted(results, key=lambda row: (row.document_kind, row.url, row.document_id))
