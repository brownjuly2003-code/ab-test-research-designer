# Base images pinned to multi-arch manifest digests (audit F-10); Dependabot
# keeps them fresh via .github/dependabot.yml.
FROM node:22-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2 AS frontend-build

WORKDIR /workspace/app/frontend

ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci

COPY app/frontend ./
RUN npm run build


FROM python:3.13-slim@sha256:eb43ff125d8d58d7449dcba7d336c23bcac412f526d861db493b9994d8010280 AS runtime

# Stamped by CI (docker-publish passes the release commit); defaults to "unknown"
# for builds that pass nothing, e.g. the HF Space build — the deploy script stamps
# the Space variable AB_BUILD_SHA instead, which overrides this ENV at runtime.
ARG GIT_SHA=unknown
ENV AB_BUILD_SHA=${GIT_SHA}
LABEL org.opencontainers.image.revision=${GIT_SHA}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV AB_HOST=0.0.0.0
ENV AB_PORT=8008
ENV AB_SERVE_FRONTEND_DIST=true
ENV AB_FRONTEND_DIST_PATH=/app/app/frontend/dist
ENV AB_DB_PATH=/app/data/projects.sqlite3
ENV AB_SEED_DEMO_ON_STARTUP=false
ENV AB_SQLITE_BUSY_TIMEOUT_MS=5000
ENV AB_SQLITE_JOURNAL_MODE=WAL
ENV AB_SQLITE_SYNCHRONOUS=NORMAL
ENV AB_LOG_LEVEL=INFO
ENV AB_LOG_FORMAT=plain

WORKDIR /app

COPY app/backend/requirements.txt /tmp/requirements.txt
# requirements.txt is a uv-compiled lock with sha256 hashes; --require-hashes
# makes the hash check explicit rather than relying on pip's auto-enable.
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt

COPY app /app/app
COPY --from=frontend-build /workspace/app/frontend/dist /app/app/frontend/dist

# Run unprivileged. UID 1000 matches the user Hugging Face Spaces runs containers
# as, so the same image works there without a second ownership pass. Only /app/data
# is writable; the code tree stays root-owned and read-only to the app user.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /app/data \
    && chown -R app:app /app/data

USER app

EXPOSE 8008

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import os, urllib.request; port=os.environ.get('PORT') or os.environ.get('AB_PORT') or '8008'; urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3)" || exit 1

CMD ["sh", "-c", "exec python -m uvicorn app.backend.app.main:app --host \"${AB_HOST:-0.0.0.0}\" --port \"${PORT:-${AB_PORT:-8008}}\""]
