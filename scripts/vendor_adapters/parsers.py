"""Deterministic parsers for structured laboratory evidence."""
from __future__ import annotations

from html.parser import HTMLParser
import json
import re
from typing import Any, Iterable

from .models import DocumentCandidate, ParsedLabRecord

PERCENT = r"(?<![\d.])(-?\d{1,3}(?:\.\d+)?)(?![\d.])\s*%"
CANNABINOID_LABELS = {
    "thca": re.compile(r"\b(?:delta[- ]?9[- ]?)?thc[- ]?a\b", re.I),
    "delta_9_thc": re.compile(r"\b(?:delta[- ]?9[- ]?)?thc\b(?![- ]?a)", re.I),
    "cbd": re.compile(r"\bcbd\b(?![- ]?a)", re.I),
    "cbda": re.compile(r"\bcbd[- ]?a\b", re.I),
    "cbg": re.compile(r"\bcbg\b(?![- ]?a)", re.I),
    "cbga": re.compile(r"\bcbg[- ]?a\b", re.I),
    "cbn": re.compile(r"\bcbn\b", re.I),
}
DIRECT_TOTAL_THC = re.compile(r"\b(?:direct\s+)?total\s+(?:delta[- ]?9\s+)?thc\b", re.I)
TERPENE_NAMES = (
    "beta-caryophyllene", "caryophyllene", "limonene", "linalool", "myrcene",
    "alpha-pinene", "beta-pinene", "pinene", "humulene", "terpinolene", "ocimene",
    "bisabolol", "nerolidol", "camphene", "eucalyptol", "geraniol",
)
FIELD_PATTERNS = {
    "laboratory": re.compile(r"(?:laboratory|lab(?:oratory)? name)\s*(?::|#|-)??\s*(?:\n\s*)?([^\n|]{2,100})", re.I),
    "report_date": re.compile(r"(?:report|test|received|completed) date\s*(?::|#|-)??\s*(?:\n\s*)?([^\n|]{4,40})", re.I),
    "sample_id": re.compile(r"(?:sample id|sample #)\s*(?::|#|-)??\s*(?:\n\s*)?([A-Z0-9._/-]{3,80})", re.I),
    "batch_id": re.compile(r"(?:batch|lot)(?: id| #| number| no\.)?\s*(?::|#|-)??\s*(?:\n\s*)?([A-Z0-9._/-]{2,80})", re.I),
    "product_name": re.compile(r"(?:product|sample name|strain)\s*(?::|#|-)??\s*(?:\n\s*)?([^\n|]{2,120})", re.I),
}


def _number(value: Any) -> float | None:
    try:
        result = float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return round(result, 6) if 0.0 <= result <= 100.0 else None


def _extract_metrics(text: str) -> tuple[dict[str, float], dict[str, float], float | None, float | None]:
    cannabinoids: dict[str, float] = {}
    terpenes: dict[str, float] = {}
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    expanded = list(lines)
    for index in range(len(lines) - 1):
        if re.fullmatch(r"-?\d{1,3}(?:\.\d+)?\s*%", lines[index + 1]):
            expanded.append(f"{lines[index]} {lines[index + 1]}")
    for line in expanded:
        if not line:
            continue
        values = re.findall(PERCENT, line)
        if not values:
            continue
        value = _number(values[-1])
        if value is None:
            continue
        if DIRECT_TOTAL_THC.search(line):
            cannabinoids.setdefault("total_thc", value)
        else:
            for name, pattern in CANNABINOID_LABELS.items():
                if pattern.search(line):
                    cannabinoids.setdefault(name, value)
                    break
        lower = line.lower()
        for terpene in TERPENE_NAMES:
            if terpene in lower:
                terpenes.setdefault(terpene, value)
                break
    total_c = next((_number(m.group(1)) for m in re.finditer(r"total cannabinoids?\s*[:#-]?\s*" + PERCENT, text, re.I)), None)
    total_t = next((_number(m.group(1)) for m in re.finditer(r"total terpenes?\s*[:#-]?\s*" + PERCENT, text, re.I)), None)
    return cannabinoids, terpenes, total_c, total_t


def parse_lab_text(text: str, candidate: DocumentCandidate, parser_id: str = "lab_text_v1") -> ParsedLabRecord:
    normalized = text.replace("\x00", "").replace("\r\n", "\n")[:2_000_000]
    fields: dict[str, str] = {}
    for name, pattern in FIELD_PATTERNS.items():
        match = pattern.search(normalized)
        fields[name] = match.group(1).strip() if match else ""
    cannabinoids, terpenes, total_c, total_t = _extract_metrics(normalized)
    limitations: list[str] = []
    impossible_values = [raw for raw in re.findall(PERCENT, normalized) if _number(raw) is None]
    if impossible_values:
        limitations.append(f"ignored {len(impossible_values)} impossible percentage value(s)")
    if not cannabinoids and not terpenes:
        limitations.append("no recognized cannabinoid or terpene percentage rows")
    status = "parsed" if cannabinoids or terpenes else "partial"
    return ParsedLabRecord(
        document_id=candidate.document_id,
        vendor_id=candidate.vendor_id,
        source_url=candidate.url,
        document_kind=candidate.document_kind,
        parse_status=status,  # type: ignore[arg-type]
        parser_id=parser_id,
        report_title=candidate.title,
        laboratory=fields["laboratory"],
        report_date=fields["report_date"],
        sample_id=fields["sample_id"],
        batch_id=fields["batch_id"] or candidate.batch_id,
        product_name=fields["product_name"],
        variant_label=candidate.variant_label,
        weight_grams=candidate.weight_grams,
        cannabinoids=cannabinoids,
        terpenes=terpenes,
        total_cannabinoids=total_c,
        total_terpenes=total_t,
        limitations=tuple(limitations),
        provenance={"source": "public_document", "candidate": candidate.to_dict()},
    )


def _walk(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def parse_structured_json(payload: str | bytes | dict[str, Any] | list[Any], candidate: DocumentCandidate) -> ParsedLabRecord:
    data = json.loads(payload) if isinstance(payload, (str, bytes, bytearray)) else payload
    flattened: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            label = next((value.get(key) for key in ("analyte", "compound", "cannabinoid", "terpene", "name", "label") if value.get(key) not in (None, "")), None)
            result = next((value.get(key) for key in ("result", "value", "percentage", "percent") if value.get(key) not in (None, "")), None)
            if label is not None and result is not None:
                flattened.append(f"{label}: {result}")
            for key, item in value.items():
                if isinstance(item, (str, int, float)):
                    flattened.append(f"{key}: {item}")
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(data)
    return parse_lab_text("\n".join(flattened), candidate, "structured_json_v1")


class _TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = re.sub(r"\s+", " ", data).strip()
        if value:
            self.parts.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"p", "div", "tr", "td", "th", "li", "br", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")


def parse_structured_html(payload: str, candidate: DocumentCandidate) -> ParsedLabRecord:
    parser = _TextHTMLParser()
    parser.feed(payload[:4_000_000])
    return parse_lab_text(" ".join(parser.parts).replace(" \n ", "\n"), candidate, "structured_html_v1")


def extract_text_pdf(payload: bytes) -> tuple[str, tuple[str, ...]]:
    """Extract literal Tj/TJ strings from bounded, unencrypted, text PDFs.

    This intentionally supports only visible uncompressed text operators. Compressed,
    encrypted, image-only, or malformed PDFs are reported as unsupported rather than
    passed to OCR or guessed from binary noise.
    """
    if not payload.startswith(b"%PDF-"):
        return "", ("not a PDF header",)
    if b"/Encrypt" in payload:
        return "", ("encrypted PDF is unsupported",)
    if b"/Filter" in payload and b"/FlateDecode" in payload:
        return "", ("compressed PDF text streams require a dedicated vetted parser",)
    chunks: list[str] = []
    for raw in re.findall(rb"\((?:\\.|[^\\)])*\)\s*Tj", payload[:12_000_000]):
        literal = raw.rsplit(b")", 1)[0][1:]
        literal = re.sub(rb"\\([\\()])", rb"\1", literal)
        chunks.append(literal.decode("latin-1", "replace"))
    for array in re.findall(rb"\[(.*?)\]\s*TJ", payload[:12_000_000], re.S):
        for literal in re.findall(rb"\((?:\\.|[^\\)])*\)", array):
            value = re.sub(rb"\\([\\()])", rb"\1", literal[1:-1])
            chunks.append(value.decode("latin-1", "replace"))
    text = "\n".join(chunks).strip()
    return (text, ()) if text else ("", ("no extractable text operators; document may be scanned or compressed",))


def parse_pdf(payload: bytes, candidate: DocumentCandidate) -> ParsedLabRecord:
    text, limitations = extract_text_pdf(payload)
    if not text:
        return ParsedLabRecord(
            document_id=candidate.document_id,
            vendor_id=candidate.vendor_id,
            source_url=candidate.url,
            document_kind=candidate.document_kind,
            parse_status="unsupported_scanned" if any("scanned" in item for item in limitations) else "unsupported_format",
            parser_id="bounded_pdf_literal_text_v1",
            report_title=candidate.title,
            limitations=limitations,
            provenance={"source": "public_document", "candidate": candidate.to_dict()},
        )
    parsed = parse_lab_text(text, candidate, "bounded_pdf_literal_text_v1")
    return ParsedLabRecord(**{**parsed.to_dict(), "limitations": tuple([*parsed.limitations, *limitations])})


def parse_document(payload: bytes, content_type: str, candidate: DocumentCandidate) -> ParsedLabRecord:
    media = (content_type or candidate.content_type_hint or "").split(";", 1)[0].lower()
    if media in {"application/json", "application/ld+json"}:
        try:
            return parse_structured_json(payload.decode("utf-8", "replace"), candidate)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            return ParsedLabRecord(candidate.document_id, candidate.vendor_id, candidate.url, candidate.document_kind, "invalid", "structured_json_v1", limitations=(str(exc),))
    if media == "application/pdf" or candidate.url.lower().split("?", 1)[0].endswith(".pdf"):
        return parse_pdf(payload, candidate)
    if media in {"text/html", "application/xhtml+xml"}:
        return parse_structured_html(payload.decode("utf-8", "replace"), candidate)
    if media in {"text/plain", "text/csv", "application/octet-stream", ""}:
        return parse_lab_text(payload.decode("utf-8", "replace"), candidate)
    return ParsedLabRecord(candidate.document_id, candidate.vendor_id, candidate.url, candidate.document_kind, "unsupported_format", "none", limitations=(f"unsupported content type: {media}",))
