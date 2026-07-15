#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCRIPT_NAMES = (
    "cloud_scan.py",
    "cloud_scan_v2.py",
    "autonomous_worker.py",
    "autonomous_worker_v2.py",
    "autonomous_worker_v4.py",
    "autonomous_worker_v5.py",
    "autonomous_worker_v6.py",
    "autonomous_merge.py",
    "catalog_normalization.py",
    "autonomous_merge_complete.py",
)

DOCKERFILE = r'''FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=7860 \
    DROPFINDER_RUNTIME_DIR=/app/runtime \
    DROPFINDER_WEB_DIR=/app/web \
    DROPFINDER_SCRIPTS_DIR=/app/scripts \
    DROPFINDER_HOSTING_MODE=huggingface_autonomous_service \
    DROPFINDER_ASGI_APP=strict_space_app:app \
    DROPFINDER_STATE_MIGRATION_SCRIPT=/app/migrate_runtime_state.py \
    DROPFINDER_WORKER_SCRIPT=autonomous_worker_v6.py \
    DROPFINDER_MERGER_SCRIPT=autonomous_merge_complete.py \
    DROPFINDER_REQUIRED_COMPARISON_CONTRACT=exact_price_weight_ppg_thca_stock_image_v1 \
    DROPFINDER_REQUIRED_NORMALIZATION_CONTRACT=dropfinder-product-normalization-v1 \
    DROPFINDER_SCAN_INTERVAL_SECONDS=10800 \
    DROPFINDER_SCAN_STALE_AFTER_SECONDS=14400 \
    DROPFINDER_SCAN_WORKERS=3 \
    DROPFINDER_MIN_ACTIVE_SOURCES=4 \
    DROPFINDER_MIN_PRODUCTS=25

RUN useradd --create-home --uid 1000 --shell /bin/bash user \
    && python -m pip install --no-cache-dir \
       'fastapi>=0.115,<1' \
       'uvicorn[standard]>=0.34,<1' \
       'huggingface_hub>=0.34,<2'

WORKDIR /app
COPY --chown=user:user space_app.py strict_space_app.py migrate_runtime_state.py hf_state.py hf_supervisor.py /app/
COPY --chown=user:user scripts/ /app/scripts/
COPY --chown=user:user web/ /app/web/
RUN python - <<'PY'
from pathlib import Path
index = Path('/app/web/index.html')
html = index.read_text(encoding='utf-8')
marker = '<script src="operator.js"></script>'
if marker not in html:
    html = html.replace('</body>', marker + '\n</body>', 1)
    index.write_text(html, encoding='utf-8')
PY
RUN mkdir -p /app/runtime/data /app/runtime/logs /app/runtime/runs \
    && chown -R user:user /app/runtime \
    && python -m py_compile /app/*.py /app/scripts/*.py \
    && python /app/scripts/catalog_normalization.py --self-test \
    && python /app/scripts/autonomous_worker_v6.py --self-test \
    && python /app/scripts/autonomous_merge_complete.py --self-test
USER user
EXPOSE 7860
CMD ["python", "/app/hf_supervisor.py"]
'''


def copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def build(output: Path) -> None:
    if output.exists():
        shutil.rmtree(output)
    (output / "scripts").mkdir(parents=True)
    (output / "web").mkdir(parents=True)

    copy(ROOT / "deploy/huggingface-space/README.md", output / "README.md")
    copy(ROOT / "deploy/huggingface-space/space_app.py", output / "space_app.py")
    copy(ROOT / "deploy/huggingface-space/hf_state.py", output / "hf_state.py")
    copy(ROOT / "deploy/huggingface-space/hf_supervisor.py", output / "hf_supervisor.py")
    copy(ROOT / "deploy/render/migrate_runtime_state.py", output / "migrate_runtime_state.py")

    strict = (ROOT / "deploy/render/render_space_app.py").read_text(encoding="utf-8")
    strict = strict.replace(
        '"render_autonomous_service"',
        'os.getenv("DROPFINDER_HOSTING_MODE", "huggingface_autonomous_service")',
    )
    (output / "strict_space_app.py").write_text(strict, encoding="utf-8")

    for name in SCRIPT_NAMES:
        copy(ROOT / "scripts" / name, output / "scripts" / name)
    shutil.copytree(ROOT / "cloud_pages", output / "web", dirs_exist_ok=True)
    copy(ROOT / "deploy/huggingface-space/operator.js", output / "web/operator.js")
    (output / "Dockerfile").write_text(DOCKERFILE, encoding="utf-8")

    html = (output / "web/index.html").read_text(encoding="utf-8")
    required = (
        "content-visibility:auto",
        "requestIdleCallback",
        'loading="lazy"',
        "products on this page",
        "dropfinder-favorites",
    )
    missing = [item for item in required if item not in html]
    if missing:
        raise RuntimeError(f"bundle UI is missing required performance hooks: {missing}")
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    if len(scripts) != 1:
        raise RuntimeError(f"bundle expected one inline script, found {len(scripts)}")
    (output / "browser-app.js").write_text(scripts[0], encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/dropfinder-space"))
    args = parser.parse_args()
    build(args.output.resolve())
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
