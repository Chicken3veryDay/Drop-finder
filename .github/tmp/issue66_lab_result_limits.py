from pathlib import Path
import re

path = Path("scripts/vendor_adapters/parsers.py")
text = path.read_text(encoding="utf-8")

start = text.index("def _extract_metrics(")
end = text.index("\ndef _confidence(", start)
replacement = r'''RESULT_ROLE = re.compile(r"\b(?:result|measured|measurement|value|potency)\b", re.I)
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
'''
text = text[:start] + replacement + text[end:]
old = "    cannabinoids, terpenes, total_c, total_t, metric_provenance = _extract_metrics(normalized)\n    field_provenance.update(metric_provenance)\n    limitations: list[str] = []\n"
new = "    cannabinoids, terpenes, total_c, total_t, metric_provenance, metric_warnings = _extract_metrics(normalized)\n    field_provenance.update(metric_provenance)\n    limitations: list[str] = list(metric_warnings)\n"
if text.count(old) != 1:
    raise SystemExit(f"parse_lab_text anchor count: {text.count(old)}")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
