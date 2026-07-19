from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

root = Path.cwd()
app = root / "app"
files = sorted(app.rglob("*.py")) if app.exists() else []


def module_name(path: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def exists(name: str) -> bool:
    target = root.joinpath(*name.split("."))
    return target.with_suffix(".py").is_file() or (target / "__init__.py").is_file()


edges = []
parse_failures = []
for path in files:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception as exc:
        parse_failures.append({"path": str(path.relative_to(root)), "error": f"{type(exc).__name__}: {exc}"})
        continue
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        for name in names:
            if name == "app" or name.startswith("app."):
                edges.append({"source": str(path.relative_to(root)), "line": getattr(node, "lineno", 0), "module": name})

missing = {}
for edge in edges:
    if not exists(edge["module"]):
        missing.setdefault(edge["module"], []).append(edge)

compile_run = subprocess.run(
    [sys.executable, "-m", "compileall", "-q", "app"],
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
) if app.exists() else None
registry_run = subprocess.run(
    [sys.executable, "-c", "import app.adapters.registry"],
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
) if (root / "app/adapters/registry.py").is_file() else None

parts = sorted(str(path.relative_to(root)) for path in (root / "bootstrap").glob("source.part*.b64")) if (root / "bootstrap").exists() else []
status = (root / "PROJECT_STATUS.md").read_text(encoding="utf-8") if (root / "PROJECT_STATUS.md").is_file() else ""
release = json.loads((root / "release/source-build.json").read_text(encoding="utf-8")) if (root / "release/source-build.json").is_file() else {}
packaging = [name for name in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "requirements-dev.txt") if (root / name).is_file()]
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()

report = {
    "head": head,
    "app_python_files": len(files),
    "app_modules": len({module_name(path) for path in files if module_name(path)}),
    "first_party_import_edges": len(edges),
    "missing_first_party_modules": missing,
    "parse_failures": parse_failures,
    "compileall_returncode": compile_run.returncode if compile_run else None,
    "compileall_output": compile_run.stdout[-4000:] if compile_run else "app directory absent",
    "registry_import_returncode": registry_run.returncode if registry_run else None,
    "registry_import_output": registry_run.stdout[-4000:] if registry_run else "registry module absent",
    "bootstrap_parts": parts,
    "source_checksum_exists": (root / "bootstrap/source.sha256").is_file(),
    "bootstrap_workflow_exists": (root / ".github/workflows/bootstrap-dropfinder.yml").is_file(),
    "packaging_files": packaging,
    "status_claims_external_archive": "exists outside this repository" in status,
    "status_claims_incomplete_bootstrap": "incomplete bootstrap" in status,
    "release_source_build": release,
}
Path("/tmp/issue4-source-boundary.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

lines = [
    "# Issue 4 source-boundary audit",
    "",
    f"- Commit: `{head}`",
    f"- Python files under app: {len(files)}",
    f"- First-party import edges: {len(edges)}",
    f"- Missing first-party modules: {len(missing)}",
    f"- compileall return code: {report['compileall_returncode']}",
    f"- registry import return code: {report['registry_import_returncode']}",
    f"- Bootstrap parts: {len(parts)}",
    f"- Bootstrap checksum exists: {report['source_checksum_exists']}",
    f"- Bootstrap workflow exists: {report['bootstrap_workflow_exists']}",
    f"- Packaging files: {', '.join(packaging) if packaging else 'none'}",
    "",
    "## Missing first-party modules",
]
for module, module_edges in sorted(missing.items()):
    locations = ", ".join(f"{edge['source']}:{edge['line']}" for edge in module_edges)
    lines.append(f"- `{module}` from {locations}")
if not missing:
    lines.append("- none")
lines.extend(["", "## Registry import output", "```text", report["registry_import_output"].strip(), "```"])
Path("/tmp/issue4-source-boundary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(Path("/tmp/issue4-source-boundary.md").read_text(encoding="utf-8"))
