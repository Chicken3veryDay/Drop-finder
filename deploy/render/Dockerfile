FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=10000 \
    DROPFINDER_RUNTIME_DIR=/app/runtime \
    DROPFINDER_WEB_DIR=/app/web \
    DROPFINDER_SCRIPTS_DIR=/app/scripts \
    DROPFINDER_HOSTING_MODE=render_autonomous_service \
    DROPFINDER_ASGI_APP=render_space_app:app \
    DROPFINDER_WORKER_SCRIPT=autonomous_worker_v6.py \
    DROPFINDER_MERGER_SCRIPT=autonomous_merge_complete.py \
    DROPFINDER_REQUIRED_COMPARISON_CONTRACT=exact_price_weight_ppg_thca_stock_image_v1 \
    DROPFINDER_SCAN_INTERVAL_SECONDS=10800 \
    DROPFINDER_SCAN_STALE_AFTER_SECONDS=14400 \
    DROPFINDER_SCAN_WORKERS=2 \
    DROPFINDER_MIN_ACTIVE_SOURCES=4 \
    DROPFINDER_MIN_PRODUCTS=25

RUN useradd --create-home --uid 1000 --shell /bin/bash user \
    && python -m pip install --no-cache-dir \
       'fastapi>=0.115,<1' \
       'uvicorn[standard]>=0.34,<1' \
       'huggingface_hub>=0.34,<2'

WORKDIR /app

COPY --chown=user:user deploy/huggingface-space/space_app.py /app/space_app.py
COPY --chown=user:user deploy/render/render_space_app.py /app/render_space_app.py
COPY --chown=user:user deploy/huggingface-space/hf_state.py /app/hf_state.py
COPY --chown=user:user deploy/huggingface-space/hf_supervisor.py /app/hf_supervisor.py
COPY --chown=user:user scripts/cloud_scan.py /app/scripts/cloud_scan.py
COPY --chown=user:user scripts/cloud_scan_v2.py /app/scripts/cloud_scan_v2.py
COPY --chown=user:user scripts/autonomous_worker.py /app/scripts/autonomous_worker.py
COPY --chown=user:user scripts/autonomous_worker_v2.py /app/scripts/autonomous_worker_v2.py
COPY --chown=user:user scripts/autonomous_worker_v4.py /app/scripts/autonomous_worker_v4.py
COPY --chown=user:user scripts/autonomous_worker_v5.py /app/scripts/autonomous_worker_v5.py
COPY --chown=user:user scripts/autonomous_worker_v6.py /app/scripts/autonomous_worker_v6.py
COPY --chown=user:user scripts/autonomous_merge.py /app/scripts/autonomous_merge.py
COPY --chown=user:user scripts/autonomous_merge_complete.py /app/scripts/autonomous_merge_complete.py
COPY --chown=user:user cloud_pages/ /app/web/
COPY --chown=user:user deploy/huggingface-space/operator.js /app/web/operator.js

RUN python - <<'PY'
from pathlib import Path

index = Path('/app/web/index.html')
html = index.read_text(encoding='utf-8')
marker = '<script src="operator.js"></script>'
if marker not in html:
    if '</body>' not in html:
        raise SystemExit('web index is missing </body>')
    html = html.replace('</body>', marker + '\n</body>', 1)
    index.write_text(html, encoding='utf-8')
PY

RUN mkdir -p /app/runtime/data /app/runtime/logs /app/runtime/runs \
    && chown -R user:user /app/runtime \
    && python -m py_compile \
       /app/space_app.py \
       /app/render_space_app.py \
       /app/hf_state.py \
       /app/hf_supervisor.py \
       /app/scripts/*.py \
    && python /app/scripts/autonomous_worker_v6.py --self-test \
    && python /app/scripts/autonomous_merge_complete.py --self-test

USER user
EXPOSE 10000
CMD ["python", "/app/hf_supervisor.py"]
