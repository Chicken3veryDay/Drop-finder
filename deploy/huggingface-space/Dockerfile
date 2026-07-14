FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DROPFINDER_HOST=0.0.0.0 \
    DROPFINDER_PORT=7860 \
    DROPFINDER_PYTHON=/usr/local/bin/python \
    DROPFINDER_DB_PATH=/app/runtime/dropfinder.db \
    DROPFINDER_QUEUE_DIR=/app/runtime/queue \
    DROPFINDER_RELIABILITY_DB_PATH=/app/runtime/reliability.db \
    DROPFINDER_REQUIRE_SCHEDULER_READY=1 \
    DROPFINDER_WORKER_COUNT=1 \
    DROPFINDER_SCHEDULER_ENABLED=1 \
    DROPFINDER_RELIABILITY_SCHEDULER_ENABLED=1

RUN useradd --create-home --uid 1000 --shell /bin/bash user
WORKDIR /app

COPY dropfinder-runtime.tar.xz.b64 /tmp/dropfinder-runtime.tar.xz.b64
RUN base64 -d /tmp/dropfinder-runtime.tar.xz.b64 > /tmp/dropfinder-runtime.tar.xz \
    && rm /tmp/dropfinder-runtime.tar.xz.b64 \
    && tar -xJf /tmp/dropfinder-runtime.tar.xz -C /app \
    && rm /tmp/dropfinder-runtime.tar.xz \
    && python -m pip install --no-cache-dir -r requirements.txt 'huggingface_hub>=0.34,<2' \
    && python -m playwright install --with-deps chromium \
    && chmod -R a+rX "$PLAYWRIGHT_BROWSERS_PATH" \
    && mkdir -p /app/runtime /app/logs /opt/dropfinder-hosting \
    && chown -R user:user /app /opt/dropfinder-hosting \
    && chmod 0755 /app/run.sh \
    && rm -rf /var/lib/apt/lists/*

COPY --chown=user:user hf_state.py hf_supervisor.py /opt/dropfinder-hosting/

USER user
EXPOSE 7860
CMD ["python", "/opt/dropfinder-hosting/hf_supervisor.py"]
