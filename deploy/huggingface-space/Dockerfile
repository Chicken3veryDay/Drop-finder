FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=7860 \
    DROPFINDER_RUNTIME_DIR=/app/runtime \
    DROPFINDER_WEB_DIR=/app/web \
    DROPFINDER_SCRIPTS_DIR=/app/scripts \
    DROPFINDER_SCAN_INTERVAL_SECONDS=10800 \
    DROPFINDER_SCAN_STALE_AFTER_SECONDS=14400 \
    DROPFINDER_SCAN_WORKERS=3 \
    DROPFINDER_MIN_ACTIVE_SOURCES=5 \
    DROPFINDER_MIN_PRODUCTS=25

RUN useradd --create-home --uid 1000 --shell /bin/bash user \
    && python -m pip install --no-cache-dir \
       'fastapi>=0.115,<1' \
       'uvicorn[standard]>=0.34,<1' \
       'huggingface_hub>=0.34,<2'

WORKDIR /app
COPY --chown=user:user space_app.py hf_state.py hf_supervisor.py /app/
COPY --chown=user:user scripts/ /app/scripts/
COPY --chown=user:user web/ /app/web/
RUN mkdir -p /app/runtime/data /app/runtime/logs /app/runtime/scan-results \
    && chown -R user:user /app/runtime

USER user
EXPOSE 7860
CMD ["python", "/app/hf_supervisor.py"]
