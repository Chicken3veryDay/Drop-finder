"""Deterministic parsers for structured laboratory evidence."""
from __future__ import annotations

from html.parser import HTMLParser
import json
import re
from typing import Any

from .models import DocumentCandidate, ParsedLabRecord, ParseConfidence

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


def _line_location(text: str, offset: int) -> str:
    return f"text_line:{text.count(chr(10), 0, max(0, offset)) + 1}"


def _source_entry(location: str, raw: str) -> dict[str, Any]:
    return {"source_location": location, "raw": raw[:240]}


RESULT_ROLE = re.compile(r"\b(?:result|measured|measurement|value|potency)\b", re.I)
LIMIT_ROLE = re.compile(
    r"\b(?:loq|lod|action\s+limit|reporting\s+limit|detection\s+limit|"
    r"quantitation\s+limit|threshold|uncertainty|recovery|limit)\b",
    re.I,
)


def _metric_name(line: str) -> tuple[str, str] | None:
    if DIRECT_TOTAL_THC.search(line):
        return ("cannabinoid", "total_thc")
    for name, pattern in CANNABINOID_LABELS.items():
        if pattern.search(line):
            return ("cannabinoid", name)
    lower = line.lower()
    for terpene in TERPENE_NAMES:
        if terpene in lower:
            return ("terpene", terpene)
    return None


def _percentage_role(prefix: str) -> str:
    if RESULT_ROLE.search(prefix):
        return "result"
    if LIMIT_ROLE.search(prefix) or "±" in prefix or "+/-" in prefix:
        return "limit"
    return "unknown"


def _select_metric_percentage(line: str) -> tuple[float | None, str | None]:
    matches = list(re.finditer(PERCENT, line))
    if not matches:
        return None, None
    roles: list[str] = []
    previous_end = 0
    for match in matches:
        roles.append(_percentage_role(line[previous_end:match.start()]))
        previous_end = match.end()

    result_indexes = [index for index, role in enumerate(roles) if role == "result"]
    if len(result_indexes) == 1:
        value = _number(matches[result_indexes[0]].group(1))
        return value, None if value is not None else "ignored impossible measured percentage"
    if len(result_indexes) > 1:
        return None, "ignored ambiguous row with multiple result percentages"

    unknown_indexes = [index for index, role in enumerate(roles) if role == "unknown"]
    if len(matches) == 1:
        if roles[0] == "limit":
            return None, "ignored limit-only analyte row"
        value = _number(matches[0].group(1))
        return value, None if value is not None else "ignored impossible measured percentage"
    if len(unknown_indexes) == 1 and all(
        role == "limit" for index, role in enumerate(roles) if index != unknown_indexes[0]
    ):
        value = _number(matches[unknown_indexes[0]].group(1))
        return value, None if value is not None else "ignored impossible measured percentage"
    return None, "ignored ambiguous analyte row with unlabeled percentages"


def _extract_metrics(
    text: str,
) -> tuple[
    dict[str, float],
    dict[str, float],
    float | None,
    float | None,
    dict[str, dict[str, Any]],
    tuple[str, ...],
]:
    cannabinoids: dict[str, float] = {}
    terpenes: dict[str, float] = {}
    field_provenance: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    seen_warnings: set[str] = set()
    lines = [
        (re.sub(r"\s+", " ", line).strip(), line_number)
        for line_number, line in enumerate(text.splitlines(), start=1)
        if line.strip()
    ]
    expanded = [(line, f"text_line:{line_number}") for line, line_number in lines]
    for index in range(len(lines) - 1):
        next_line, next_number = lines[index + 1]
        if re.fullmatch(r"-?\d{1,3}(?:\.\d+)?\s*%", next_line):
            line, line_number = lines[index]
            expanded.append((f"{line} {next_line}", f"text_line:{line_number}-{next_number}"))
    for line, location in expanded:
        target = _metric_name(line)
        if target is None:
            continue
        value, warning = _select_metric_percentage(line)
        if warning:
            rendered = f"{warning} at {location}"
            if rendered not in seen_warnings:
                warnings.append(rendered)
                seen_warnings.add(rendered)
        if value is None:
            continue
        category, metric_name = target
        if category == "cannabinoid":
            cannabinoids.setdefault(metric_name, value)
            field_provenance.setdefault(
                f"cannabinoids.{metric_name}",
                _source_entry(location, line),
            )
        else:
            terpenes.setdefault(metric_name, value)
            field_provenance.setdefault(f"terpenes.{metric_name}", _source_entry(location, line))

    total_c: float | None = None
    for match in re.finditer(r"total cannabinoids?\s*[:#-]?\s*" + PERCENT, text, re.I):
        value = _number(match.group(1))
        if value is not None:
            total_c = value
            field_provenance["total_cannabinoids"] = _source_entry(_line_location(text, match.start()), match.group(0))
            break
    total_t: float | None = None
    for match in re.finditer(r"total terpenes?\s*[:#-]?\s*" + PERCENT, text, re.I):
        value = _number(match.group(1))
        if value is not None:
            total_t = value
            field_provenance["total_terpenes"] = _source_entry(_line_location(text, match.start()), match.group(0))
            break
    return cannabinoids, terpenes, total_c, total_t, field_provenance, tuple(warnings)

def _confidence(parser_id: str, has_metrics: bool) -> ParseConfidence:
    if not has_metrics:
        return "none"
    if parser_id == "structured_json_v1":
        return "high"
    if parser_id in {"structured_html_v1", "bounded_pdf_literal_text_v1"}:
        return "medium"
    return "low"


def parse_lab_text(text: str, candidate: DocumentCandidate, parser_id: str = "lab_text_v1") -> ParsedLabRecord:
    normalized = text.replace("\x00", "").replace("\r\n", "\n")[:2_000_000]
    fields: dict[str, str] = {}
    field_provenance: dict[str, dict[str, Any]] = {}
    for name, pattern in FIELD_PATTERNS.items():
        match = pattern.search(normalized)
        fields[name] = match.group(1).strip() if match else ""
        if match:
            field_provenance[name] = _source_entry(_line_location(normalized, match.start()), match.group(0))
    cannabinoids, terpenes, total_c, total_t, metric_provenance, metric_warnings = _extract_metrics(normalized)
    field_provenance.update(metric_provenance)
    limitations: list[str] = list(metric_warnings)
    impossible_values = [raw for raw in re.findall(PERCENT, normalized) if _number(raw) is None]
    if impossible_values:
        limitations.append(f"ignored {len(impossible_values)} impossible percentage value(s)")
    if not cannabinoids and not terpenes:
        limitations.append("no recognized cannabinoid or terpene percentage rows")
    has_metrics = bool(cannabinoids or terpenes or total_c is not None or total_t is not None)
    status = "parsed" if has_metrics else "partial"
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
        confidence=_confidence(parser_id, has_metrics),
        field_provenance=field_provenance,
        warnings=tuple(limitations),
        limitations=tuple(limitations),
        provenance={"source": "public_document", "parser_id": parser_id, "candidate": candidate.to_dict()},
    )


def _json_path(parent: str, key: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return f"{parent}.{key}"
    return f"{parent}[{json.dumps(key, ensure_ascii=False)}]"


def _structured_metric_target(label: Any) -> tuple[str, str] | None:
    raw = str(label or "").strip()
    if not raw:
        return None
    normalized = re.sub(r"[^a-z0-9]+", " ", raw.casefold()).strip()
    if re.search(r"\btotal cannabinoids?\b", normalized):
        return ("total", "total_cannabinoids")
    if re.search(r"\btotal terpenes?\b", normalized):
        return ("total", "total_terpenes")
    if DIRECT_TOTAL_THC.search(raw):
        return ("cannabinoid", "total_thc")
    for name, pattern in CANNABINOID_LABELS.items():
        if pattern.search(raw):
            return ("cannabinoid", name)
    for terpene in TERPENE_NAMES:
        terpene_label = re.sub(r"[^a-z0-9]+", " ", terpene.casefold()).strip()
        if terpene_label and re.search(rf"\b{re.escape(terpene_label)}\b", normalized):
            return ("terpene", terpene)
    return None


def _structured_percentage(value: Any, unit: Any, result_key: str) -> float | None:
    if isinstance(value, bool):
        return None
    raw = str(value or "").strip()
    unit_value = str(unit or "").strip().casefold()
    percentage_unit = unit_value in {"%", "percent", "percentage", "pct"}
    percentage_field = result_key.casefold() in {"percentage", "percent"}
    if "%" not in raw and not percentage_unit and not percentage_field:
        return None
    return _number(value)


def parse_structured_json(payload: str | bytes | dict[str, Any] | list[Any], candidate: DocumentCandidate) -> ParsedLabRecord:
    data = json.loads(payload) if isinstance(payload, (str, bytes, bytearray)) else payload
    if not isinstance(data, (dict, list)):
        raise TypeError("structured JSON root must be an object or array")

    label_keys = ("analyte", "compound", "cannabinoid", "terpene", "name", "label")
    result_keys = ("result", "value", "percentage", "percent")
    unit_keys = ("unit", "units")
    structured_values: dict[str, float] = {}
    structured_provenance: dict[str, dict[str, Any]] = {}
    structured_warnings: list[str] = []
    fallback_lines: list[str] = []

    def visit(value: Any, current_path: str) -> None:
        if isinstance(value, dict):
            label_key = next((key for key in label_keys if value.get(key) not in (None, "")), None)
            result_key = next((key for key in result_keys if value.get(key) not in (None, "")), None)
            unit_key = next((key for key in unit_keys if value.get(key) not in (None, "")), None)
            if label_key is not None and result_key is not None:
                target = _structured_metric_target(value[label_key])
                metric = _structured_percentage(
                    value[result_key],
                    value.get(unit_key) if unit_key else None,
                    result_key,
                )
                if target is not None and metric is not None:
                    kind, name = target
                    field = name if kind == "total" else f"{kind}s.{name}"
                    location = f"json_path:{_json_path(current_path, result_key)}"
                    raw = " ".join(
                        part for part in (
                            str(value[label_key]).strip(),
                            str(value[result_key]).strip(),
                            str(value.get(unit_key) or "").strip() if unit_key else "",
                        ) if part
                    )
                    if field not in structured_values:
                        structured_values[field] = metric
                        structured_provenance[field] = _source_entry(location, raw)
                    elif structured_values[field] != metric:
                        structured_warnings.append(
                            f"conflicting structured value for {field} at {location}; "
                            f"kept {structured_values[field]} from "
                            f"{structured_provenance[field]['source_location']}"
                        )
            for key in sorted(value, key=lambda item: str(item)):
                item = value[key]
                item_path = _json_path(current_path, str(key))
                if isinstance(item, (dict, list)):
                    visit(item, item_path)
                elif isinstance(item, (str, int, float)) and not isinstance(item, bool):
                    fallback_lines.append(f"{key}: {item}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{current_path}[{index}]")

    visit(data, "$")
    fallback = parse_lab_text("\n".join(fallback_lines), candidate, "lab_text_v1")
    cannabinoids = {
        field.removeprefix("cannabinoids."): value
        for field, value in structured_values.items()
        if field.startswith("cannabinoids.")
    }
    terpenes = {
        field.removeprefix("terpenes."): value
        for field, value in structured_values.items()
        if field.startswith("terpenes.")
    }
    total_cannabinoids = structured_values.get("total_cannabinoids")
    total_terpenes = structured_values.get("total_terpenes")
    has_metrics = bool(cannabinoids or terpenes or total_cannabinoids is not None or total_terpenes is not None)
    field_provenance = {
        key: value
        for key, value in fallback.field_provenance.items()
        if not key.startswith(("cannabinoids.", "terpenes."))
        and key not in {"total_cannabinoids", "total_terpenes"}
    }
    field_provenance.update(structured_provenance)
    fallback_warnings = [
        warning
        for warning in fallback.warnings
        if warning != "no recognized cannabinoid or terpene percentage rows"
    ]
    warnings = [*structured_warnings, *fallback_warnings]
    if not has_metrics:
        warnings.append("no recognized structured analyte/result rows")
    limitations = tuple(dict.fromkeys(warnings))
    return ParsedLabRecord(
        document_id=candidate.document_id,
        vendor_id=candidate.vendor_id,
        source_url=candidate.url,
        document_kind=candidate.document_kind,
        parse_status="parsed" if has_metrics else "partial",
        parser_id="structured_json_v2",
        report_title=candidate.title,
        laboratory=fallback.laboratory,
        report_date=fallback.report_date,
        sample_id=fallback.sample_id,
        batch_id=fallback.batch_id or candidate.batch_id,
        product_name=fallback.product_name,
        variant_label=candidate.variant_label,
        weight_grams=candidate.weight_grams,
        cannabinoids=cannabinoids,
        terpenes=terpenes,
        total_cannabinoids=total_cannabinoids,
        total_terpenes=total_terpenes,
        confidence="high" if has_metrics else "none",
        field_provenance=field_provenance,
        warnings=limitations,
        limitations=limitations,
        provenance={
            "source": "public_document",
            "parser_id": "structured_json_v2",
            "candidate": candidate.to_dict(),
        },
    )


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
            confidence="none",
            warnings=limitations,
            limitations=limitations,
            provenance={"source": "public_document", "parser_id": "bounded_pdf_literal_text_v1", "candidate": candidate.to_dict()},
        )
    parsed = parse_lab_text(text, candidate, "bounded_pdf_literal_text_v1")
    merged_limitations = tuple([*parsed.limitations, *limitations])
    return ParsedLabRecord(**{
        **parsed.to_dict(),
        "warnings": merged_limitations,
        "limitations": merged_limitations,
    })


def parse_document(payload: bytes, content_type: str, candidate: DocumentCandidate) -> ParsedLabRecord:
    media = (content_type or candidate.content_type_hint or "").split(";", 1)[0].lower()
    if media in {"application/json", "application/ld+json"}:
        try:
            return parse_structured_json(payload.decode("utf-8", "replace"), candidate)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            warning = str(exc)
            return ParsedLabRecord(
                candidate.document_id,
                candidate.vendor_id,
                candidate.url,
                candidate.document_kind,
                "invalid",
                "structured_json_v2",
                warnings=(warning,),
                limitations=(warning,),
            )
    if media == "application/pdf" or candidate.url.lower().split("?", 1)[0].endswith(".pdf"):
        return parse_pdf(payload, candidate)
    if media in {"text/html", "application/xhtml+xml"}:
        return parse_structured_html(payload.decode("utf-8", "replace"), candidate)
    if media in {"text/plain", "text/csv", "application/octet-stream", ""}:
        return parse_lab_text(payload.decode("utf-8", "replace"), candidate)
    warning = f"unsupported content type: {media}"
    return ParsedLabRecord(
        candidate.document_id,
        candidate.vendor_id,
        candidate.url,
        candidate.document_kind,
        "unsupported_format",
        "none",
        warnings=(warning,),
        limitations=(warning,),
    )
