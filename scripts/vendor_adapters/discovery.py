"""Vendor-configured discovery of public COA and terpene documents."""
from __future__ import annotations

from html.parser import HTMLParser
import json
import re
from typing import Any, Iterable

from .models import DocumentCandidate, Provenance
from .urls import UnsafeUrl, canonicalize_url

DOCUMENT_WORDS = re.compile(r"\b(coa|certificate(?:s)? of analysis|lab(?:oratory)? (?:report|result|test)|terpene|potency|full[- ]panel)\b", re.I)
DOCUMENT_CONTAINER_WORDS = re.compile(r"(?:^|_)(?:documents?|attachments?|coas?|lab_reports?|lab_results?|terpene_reports?|certificates?)(?:$|_)", re.I)
PDF_WORDS = re.compile(r"\.pdf(?:$|[?#])", re.I)
BATCH_WORDS = re.compile(r"\b(?:batch|lot|sample)\s*(?:id|no\.?|number|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})", re.I)
WEIGHT = re.compile(r"(?<!\d)(0\.5|1|2|3\.5|4|7|8|14|16|28|32)\s*(?:g|grams?)\b", re.I)
STRONG_DOCUMENT_URL_KEYS = {
    "coa_url", "lab_url", "document_url", "report_url", "certificate_url",
    "terpene_url", "pdf", "download_url", "document_download",
}
GENERIC_URL_KEYS = {"url", "href", "download"}


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


def _weight_grams(value: Any, context: str) -> float | None:
    try:
        if value not in (None, ""):
            return round(float(value), 4)
    except (TypeError, ValueError):
        pass
    match = WEIGHT.search(context)
    return float(match.group(1)) if match else None


def _association_key(candidate: DocumentCandidate) -> tuple[str, str, str]:
    """Keep mapping-relevant edges distinct without redefining physical document identity."""
    weight = "" if candidate.weight_grams is None else f"{candidate.weight_grams:.4f}"
    return (
        candidate.document_id,
        candidate.variant_label.strip().lower(),
        weight,
    )


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


def _first(value: dict[str, Any], keys: tuple[str, ...]) -> Any:
    return next((value.get(key) for key in keys if value.get(key) not in (None, "")), None)


def _path(parent: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]"
    return f"{parent}.{key}" if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) else f"{parent}[{json.dumps(key)}]"


def _walk_with_context(
    value: Any,
    *,
    inherited: dict[str, Any] | None = None,
    path: str = "$",
    key_hint: str = "",
) -> Iterable[tuple[dict[str, Any], dict[str, Any], str, bool]]:
    context = dict(inherited or {})
    if isinstance(value, dict):
        local_product_id = _first(value, ("product_id", "productId", "handle"))
        local_variant_id = _first(value, ("variant_id", "variantId"))
        local_variant_label = _first(value, ("variant_label", "variantLabel", "variant"))
        local_batch_id = _first(value, ("batch_id", "batch", "lot"))
        local_title = _first(value, ("title", "name", "label"))
        local_weight = _first(value, ("weight_grams", "grams"))
        local_product_url = _first(value, ("product_url", "productUrl"))
        for name, item in (
            ("product_id", local_product_id),
            ("variant_id", local_variant_id),
            ("variant_label", local_variant_label),
            ("batch_id", local_batch_id),
            ("title", local_title),
            ("weight_grams", local_weight),
            ("product_url", local_product_url),
        ):
            if item not in (None, ""):
                context[name] = item

        type_cue = " ".join(str(value.get(key) or "") for key in ("type", "kind", "document_type", "report_type"))
        key_is_document_container = bool(DOCUMENT_CONTAINER_WORDS.search(key_hint))
        explicit_schema_cue = bool(DOCUMENT_WORDS.search(type_cue))
        schema_document_context = key_is_document_container or explicit_schema_cue or bool(context.get("_document_context"))
        local_kind = _kind(" ".join((key_hint, type_cue, str(local_title or ""))))
        if local_kind != "unknown":
            context["document_kind"] = local_kind
        context["_document_context"] = schema_document_context
        yield value, context, path, schema_document_context

        for key, item in value.items():
            if isinstance(item, (dict, list)):
                yield from _walk_with_context(
                    item,
                    inherited=context,
                    path=_path(path, str(key)),
                    key_hint=str(key),
                )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, (dict, list)):
                yield from _walk_with_context(
                    item,
                    inherited=context,
                    path=_path(path, index),
                    key_hint=key_hint,
                )


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
    seen_associations: set[tuple[str, str, str]] = set()
    for obj, context, object_path, schema_document_context in _walk_with_context(data):
        product_id = str(context.get("product_id") or "")
        variant_id = str(context.get("variant_id") or "")
        variant_label = str(context.get("variant_label") or "")
        batch_id = str(context.get("batch_id") or "")
        title = str(context.get("title") or "")
        weight_grams = _weight_grams(context.get("weight_grams"), f"{variant_label} {title}")
        product_url = str(context.get("product_url") or "")

        direct_generic_product_url = obj.get("url") if not schema_document_context else None
        if not product_url and isinstance(direct_generic_product_url, str):
            product_url = direct_generic_product_url

        for key, value in obj.items():
            normalized_key = str(key).lower()
            if not isinstance(value, str):
                continue
            strong = normalized_key in STRONG_DOCUMENT_URL_KEYS
            generic = normalized_key in GENERIC_URL_KEYS and schema_document_context
            if not (strong or generic):
                continue
            local_evidence = " ".join((normalized_key, title, value, str(obj.get("type") or obj.get("kind") or "")))
            document_kind = _kind(local_evidence)
            if document_kind == "unknown":
                document_kind = str(context.get("document_kind") or "unknown")
            if document_kind == "unknown" and not PDF_WORDS.search(value):
                continue
            try:
                target = canonicalize_url(value, base_url=source_url, allowed_hosts=allowed_hosts)
            except UnsafeUrl:
                continue
            candidate = DocumentCandidate(
                vendor_id=vendor_id,
                url=target,
                document_kind=document_kind,  # type: ignore[arg-type]
                title=title,
                product_url=product_url,
                product_id=product_id,
                variant_id=variant_id,
                variant_label=variant_label,
                weight_grams=weight_grams,
                batch_id=batch_id,
                content_type_hint="application/pdf" if PDF_WORDS.search(target) else "",
                provenance=Provenance(
                    source_url,
                    "structured_json",
                    observed_at,
                    notes=f"json_path:{_path(object_path, str(key))}",
                ),
            )
            association_key = _association_key(candidate)
            if association_key in seen_associations:
                continue
            seen_associations.add(association_key)
            results.append(candidate)
    return sorted(
        results,
        key=lambda row: (
            row.document_kind,
            row.url,
            row.document_id,
            row.variant_label.strip().lower(),
            row.weight_grams if row.weight_grams is not None else -1.0,
        ),
    )
