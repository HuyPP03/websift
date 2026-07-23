# syntax=docker/dockerfile:1
# Multi-stage: build wheel from package metadata, install as non-root runtime.
# Never bake secrets (API keys, MCP_BEARER_TOKEN) into the image.

FROM python:3.12-slim AS builder

WORKDIR /build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir --upgrade pip build

# Copy only packaging inputs (see .dockerignore).
COPY pyproject.toml README.md LICENSE ./
COPY websift ./websift
COPY server.py ./

RUN python -m build --wheel --outdir /build/dist

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Inside the container network namespace 0.0.0.0 is expected so published
    # ports reach the process; protect at the host/proxy and/or MCP_AUTH_MODE.
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8787 \
    MCP_TRANSPORT=streamable-http

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin websift

WORKDIR /app

COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir /tmp/websift-*.whl \
    && rm -f /tmp/websift-*.whl

USER websift

EXPOSE 8787

# TCP liveness: MCP streamable-http is not a plain GET health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os,socket; p=int(os.environ.get('MCP_PORT','8787')); s=socket.create_connection(('127.0.0.1',p),2); s.close()"

# Console entry from the installed package (not raw source tree).
CMD ["websift"]
