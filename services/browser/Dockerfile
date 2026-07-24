FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY pyproject.toml ./
COPY browser_service ./browser_service
RUN pip wheel --wheel-dir /wheels .

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BROWSER_HOST=0.0.0.0 \
    BROWSER_PORT=8790
RUN groupadd --system browser && useradd --system --gid browser --create-home browser
COPY --from=builder /wheels /wheels
RUN mkdir -p /home/browser/.cache && \
    pip install --no-cache-dir /wheels/*.whl && \
    playwright install-deps firefox && \
    python -m camoufox fetch && \
    cp -r /root/.cache/camoufox /home/browser/.cache/camoufox && \
    rm -rf /wheels && \
    chown -R browser:browser /home/browser/.cache
USER browser
WORKDIR /home/browser
EXPOSE 8790
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8790/healthz', timeout=3)"
ENTRYPOINT ["websift-browser"]
