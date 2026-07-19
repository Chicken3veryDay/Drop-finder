"""Vendor-configured discovery of public COA and terpene documents."""
from __future__ import annotations

from html.parser import HTMLParser
import json
import re
from typing import Any
from urllib.parse import unquote, urlsplit

from .models import DocumentCandidate, Provenance
from .urls import UnsafeUrl, canonicalize_url

DOCUMENT_WORDS = re.compile(r"\b(coa|certificate(?:s)? of analysis|lab(?:oratory)? (?:report|result|test)|terpene|potency|full[- ]panel)\b", re.I)
PDF_WORDS = re.compile(r"\.pdf(?:$|[?#])", re.I)
BATCH_WORDS = re.compile(r"\b(?:batch|lot|sample)\s*(?:id|no\.?|number|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})", re.I)
WEIGHT = re.compile(r"(?<!\d)(0\.5|1|2|3\.5|4|7|8|14|16|28|32)\s*(?:g|grams?)\b", re.I)
DOCUMENT_CONTAINER = re.compile(r"(?:documents?|attachments?|coas?|labs?|reports?|certificates?|potency|terpenes?)", re.I)
STRONG_URL_KEYS = {"document_url", "coa_url", "lab_url", "report_url", "certificate_url", "pdf", "download"}
GENERIC_URL_KEYS = {"url", "href"}


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


def _filename_label(url: str) -> str:
    path = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    stem = re.sub(r"\.[a-z0-9]{2,5}$", "", path, flags=re.I)
    stem = re.sub(r"(?:[_-](?:1600x|\d{2,4}x\d{2,4}))+$", "", stem, flags=re.I)
    return re.sub(r"[_-]+", " ", stem).strip()


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
    for index, (href, label, attrs) in enumerate(parser.links):
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
        candidate_title = label.strip() or attrs.get("title", "").strip() or attrs.get("aria-label", "").strip() or _filename_label(target)
        candidate_context = f"{candidate_title} {context}"
        batch_match = BATCH_WORDS.search(candidate_context)
        weight_match = WEIGHT.search(candidate_context)
        source_path = f"html_anchor:{index + 1}"
        candidates.append(DocumentCandidate(
            vendor_id=vendor_id,
            url=target,
            document_kind=_kind(candidate_context),  # type: ignore[arg-type]
            title=candidate_title,
            product_url=page_url if product_id else "",
            product_id=product_id,
            batch_id=batch_match.group(1) if batch_match else "",
            weight_grams=float(weight_match.group(1)) if weight_match else None,
            content_type_hint="application/pdf" if PDF_WORDS.search(target) else "",
            source_path=source_path,
            provenance=Provenance(page_url, "html_anchor", observed_at, notes=source_path),
        ))
    return sorted(candidates, key=lambda row: (row.document_kind, row.url, row.document_id))


def _path(parent: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]"
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return f"{parent}.{key}"
    return f"{parent}[{json.dumps(key)}]"


def _first(value: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        item = value.get(key)
        if item not in (None, ""):
            return str(item)
    return ""


def _document_context(obj: dict[str, Any], container_key: str, inherited: bool) -> tuple[bool, str]:
    explicit_type = _first(obj, ("document_type", "type", "kind", "category"))
    local_label = _first(obj, ("label", "title", "name"))
    container_cue = bool(DOCUMENT_CONTAINER.search(container_key))
    type_cue = bool(DOCUMENT_WORDS.search(explicit_type))
    label_cue = bool(DOCUMENT_WORDS.search(local_label))
    return inherited or container_cue or type_cue or label_cue, " ".join((container_key, explicit_type, local_label)).strip()


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

    def visit(
        value: Any,
        *,
        inherited: dict[str, Any],
        path: str,
        container_key: str,
        inherited_document_context: bool,
    ) -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(
                    item,
                    inherited=dict(inherited),
                    path=_path(path, index),
                    container_key=container_key,
                    inherited_document_context=inherited_document_context,
                )
            return
        if not isinstance(value, dict):
            return

        context = dict(inherited)
        direct = {
            "product_id": _first(value, ("product_id", "productId", "handle")),
            "variant_id": _first(value, ("variant_id", "variantId")),
            "variant_label": _first(value, ("variant_label", "variantLabel", "variant")),
            "batch_id": _first(value, ("batch_id", "batch", "lot")),
            "title": _first(value, ("title", "name", "label")),
            "weight_grams": value.get("weight_grams") if value.get("weight_grams") not in (None, "") else value.get("grams"),
        }
        for key, item in direct.items():
            if item not in (None, ""):
                context[key] = item

        document_context, local_cues = _document_context(value, container_key, inherited_document_context)
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key not in STRONG_URL_KEYS | GENERIC_URL_KEYS or not isinstance(item, str):
                continue
            try:
                target = canonicalize_url(item, base_url=source_url, allowed_hosts=allowed_hosts)
            except UnsafeUrl:
                continue
            strong = normalized_key in STRONG_URL_KEYS
            url_has_document_cue = bool(PDF_WORDS.search(target) or DOCUMENT_WORDS.search(target))
            container_has_document_cue = bool(DOCUMENT_CONTAINER.search(container_key))
            explicit_type_cue = bool(DOCUMENT_WORDS.search(_first(value, ("document_type", "type", "kind", "category"))))
            if not strong and not (
                document_context
                and (container_has_document_cue or explicit_type_cue or url_has_document_cue)
            ):
                continue
            source_path = _path(path, str(key))
            title = str(context.get("title") or "") or _filename_label(target)
            variant_label = str(context.get("variant_label") or "")
            candidate_context = " ".join((normalized_key, local_cues, title, target))
            candidate = DocumentCandidate(
                vendor_id=vendor_id,
                url=target,
                document_kind=_kind(candidate_context),  # type: ignore[arg-type]
                title=title,
                product_id=str(context.get("product_id") or ""),
                variant_id=str(context.get("variant_id") or ""),
                variant_label=variant_label,
                weight_grams=_weight_grams(context.get("weight_grams"), f"{variant_label} {title}"),
                batch_id=str(context.get("batch_id") or ""),
                content_type_hint="application/pdf" if PDF_WORDS.search(target) else "",
                source_path=source_path,
                provenance=Provenance(source_url, "structured_json", observed_at, notes=source_path),
            )
            association_key = _association_key(candidate)
            if association_key in seen_associations:
                continue
            seen_associations.add(association_key)
            results.append(candidate)

        for key, item in value.items():
            if isinstance(item, (dict, list)):
                visit(
                    item,
                    inherited=context,
                    path=_path(path, str(key)),
                    container_key=str(key),
                    inherited_document_context=document_context,
                )

    visit(data, inherited={}, path="$", container_key="", inherited_document_context=False)
    return sorted(
        results,
        key=lambda row: (
            row.document_kind,
            row.url,
            row.document_id,
            row.variant_label.strip().lower(),
            row.weight_grams if row.weight_grams is not None else -1.0,
            row.source_path,
        ),
    )
