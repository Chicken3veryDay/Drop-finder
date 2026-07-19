from pathlib import Path

path = Path("scripts/vendor_adapters/parsers.py")
text = path.read_text(encoding="utf-8")
text = text.replace("from typing import Any, Iterable\n", "from typing import Any\n")
start = text.find("def _walk(value: Any)")
end = text.find("class _TextHTMLParser", start)
if start < 0 or end < 0:
    raise SystemExit("structured JSON parser boundary not found")
replacement = '''def _json_path(parent: str, key: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return f"{parent}.{key}"
    return f"{parent}[{json.dumps(key, ensure_ascii=False)}]"


def _structured_metric_target(label: Any) -> tuple[str, str] | None:
    raw = str(label or "").strip()
    if not raw:
        return None
    normalized = re.sub(r"[^a-z0-9]+", " ", raw.casefold()).strip()
    if re.search(r"\\btotal cannabinoids?\\b", normalized):
        return ("total", "total_cannabinoids")
    if re.search(r"\\btotal terpenes?\\b", normalized):
        return ("total", "total_terpenes")
    if DIRECT_TOTAL_THC.search(raw):
        return ("cannabinoid", "total_thc")
    for name, pattern in CANNABINOID_LABELS.items():
        if pattern.search(raw):
            return ("cannabinoid", name)
    for terpene in TERPENE_NAMES:
        terpene_label = re.sub(r"[^a-z0-9]+", " ", terpene.casefold()).strip()
        if terpene_label and re.search(rf"\\b{re.escape(terpene_label)}\\b", normalized):
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
    fallback = parse_lab_text("\\n".join(fallback_lines), candidate, "lab_text_v1")
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


'''
text = text[:start] + replacement + text[end:]
text = text.replace('                "structured_json_v1",\n', '                "structured_json_v2",\n', 1)
path.write_text(text, encoding="utf-8")
