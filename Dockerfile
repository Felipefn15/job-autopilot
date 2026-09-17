FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DISPLAY=:99

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        novnc \
        tini \
        websockify \
        x11vnc \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data /ms-playwright \
    && chown -R appuser:appuser /data /ms-playwright

COPY --chown=appuser:appuser . /app
RUN chmod +x /app/scripts/container-entrypoint.sh /app/scripts/deploy_run.sh

USER appuser

EXPOSE 6080

ENTRYPOINT ["/usr/bin/tini", "--", "/app/scripts/container-entrypoint.sh"]
CMD ["/app/scripts/deploy_run.sh"]

