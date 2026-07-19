#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
OBSOLETE_BOOTSTRAP_GLOBS = ("source.part*.b64", "source.sha256")
REQUIRED_PACKAGING = (ROOT / "pyproject.toml",)


def module_path(module: str) -> Path:
    path = ROOT.joinpath(*module.split("."))
    package = path / "__init__.py"
    if package.is_file():
        return package
    return path.with_suffix(".py")


def first_party_imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((node.lineno, alias.name) for alias in node.names if alias.name == "app" or alias.name.startswith("app."))
        elif isinstance(node, ast.ImportFrom) and node.module and (node.module == "app" or node.module.startswith("app.")):
            imports.append((node.lineno, node.module))
    return imports


def verify() -> dict[str, object]:
    python_files = sorted(APP.rglob("*.py"))
    if not python_files:
        raise SystemExit("tracked app package is missing")

    missing_imports: list[dict[str, object]] = []
    for path in python_files:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
        for line, module in first_party_imports(path):
            if not module_path(module).is_file():
                missing_imports.append({"source": str(path.relative_to(ROOT)), "line": line, "module": module})
    if missing_imports:
        raise SystemExit(f"missing first-party imports: {json.dumps(missing_imports, sort_keys=True)}")

    missing_packaging = [str(path.relative_to(ROOT)) for path in REQUIRED_PACKAGING if not path.is_file()]
    if missing_packaging:
        raise SystemExit(f"missing packaging files: {missing_packaging}")

    bootstrap_dir = ROOT / "bootstrap"
    obsolete = sorted(
        str(path.relative_to(ROOT))
        for pattern in OBSOLETE_BOOTSTRAP_GLOBS
        for path in bootstrap_dir.glob(pattern)
    ) if bootstrap_dir.is_dir() else []
    if obsolete:
        raise SystemExit(f"obsolete incomplete bootstrap inputs remain tracked: {obsolete}")

    sys.path.insert(0, str(ROOT))
    imported = []
    for path in python_files:
        relative = path.relative_to(ROOT).with_suffix("")
        if relative.name == "__init__":
            module = ".".join(relative.parent.parts)
        else:
            module = ".".join(relative.parts)
        if module and module not in imported:
            importlib.import_module(module)
            imported.append(module)

    return {
        "schema_version": "dropfinder-tracked-source-boundary-v1",
        "python_files": [str(path.relative_to(ROOT)) for path in python_files],
        "imported_modules": imported,
        "missing_first_party_modules": [],
        "obsolete_bootstrap_inputs": [],
        "packaging_files": [str(path.relative_to(ROOT)) for path in REQUIRED_PACKAGING],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = verify()
    encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
