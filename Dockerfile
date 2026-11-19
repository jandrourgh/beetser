# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Frontend build
# ---------------------------------------------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Python wheels (keeps compilers out of the runtime image)
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS python-build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        python3-dev \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY backend/ /build/backend/
RUN pip wheel --wheel-dir /wheels /build/backend

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="Beetser" \
      org.opencontainers.image.description="Self-hosted beets frontend with watched origins, MusicBrainz tagging and a review queue" \
      org.opencontainers.image.source="https://github.com/wabasi/beetser" \
      org.opencontainers.image.url="https://github.com/wabasi/beetser" \
      org.opencontainers.image.documentation="https://github.com/wabasi/beetser/tree/main/docs" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="0.1.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BEETSER_DATA_DIR=/config \
    BEETSER_STATIC_DIR=/app/static \
    BEETSER_HOST=0.0.0.0 \
    BEETSER_PORT=8080

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        libchromaprint-tools \
        gosu \
        tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=python-build /wheels /wheels
RUN pip install --no-index --find-links=/wheels beetser \
    && rm -rf /wheels

COPY --from=frontend /src/frontend/dist /app/static
COPY LICENSE THIRD_PARTY_NOTICES.md /app/licenses/
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
    && chmod -R a+r /app/licenses \
    && useradd --uid 1000 --create-home --shell /usr/sbin/nologin beetser \
    && mkdir -p /config /music /app/static \
    && chown -R beetser:beetser /config /music /app

WORKDIR /app
VOLUME ["/config"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/system/health', timeout=4)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["python", "-m", "beetser"]
