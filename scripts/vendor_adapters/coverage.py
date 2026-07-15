"""Coverage verification against the canonical scripts/cloud_scan.py SOURCES list."""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from .registry import validate_profiles


def source_ids_from_python(path: str | Path) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "SOURCES" for target in node.targets):
            value = ast.literal_eval(node.value)
            return {str(row[0]) for row in value}
    raise ValueError("SOURCES assignment not found")


def verify_coverage(profiles_path: str | Path, sources_path: str | Path, research_dir: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(profiles_path).read_text(encoding="utf-8"))
    source_ids = source_ids_from_python(sources_path)
    profile_ids = {str(item.get("vendor_id")) for item in payload.get("vendors", []) if isinstance(item, dict)}
    research_ids = {path.stem for path in Path(research_dir).glob("*.md")}
    errors = validate_profiles(payload)
    missing_profiles = sorted(source_ids - profile_ids)
    stale_profiles = sorted(profile_ids - source_ids)
    missing_research = sorted(source_ids - research_ids)
    errors.extend(f"missing profile: {item}" for item in missing_profiles)
    errors.extend(f"stale profile: {item}" for item in stale_profiles)
    errors.extend(f"missing research report: {item}" for item in missing_research)
    return {
        "ok": not errors,
        "source_count": len(source_ids),
        "profile_count": len(profile_ids),
        "research_count": len(research_ids & source_ids),
        "missing_profiles": missing_profiles,
        "stale_profiles": stale_profiles,
        "missing_research": missing_research,
        "errors": errors,
    }
