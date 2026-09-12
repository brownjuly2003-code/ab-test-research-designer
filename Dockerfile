# Base images pinned to multi-arch manifest digests (audit F-10); Dependabot
# keeps them fresh via .github/dependabot.yml.
FROM node:24-alpine@sha256:d32cdf619f63fe0471182d08996dd516c6275bb5fd31ae06e55a570bd9e1ad43 AS frontend-build

WORKDIR /workspace/app/frontend

ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci

COPY app/frontend ./
RUN npm run build


FROM python:3.14-slim@sha256:d3400aa122fa42cf0af0dbe8ec3091b047eac5c8f7e3539f7135e86d855dc015 AS runtime

# Stamped by CI or the Compose caller. An omitted value fails closed when the
# build information is validated below.
ARG GIT_SHA
ENV AB_BUILD_SHA=${GIT_SHA}
LABEL org.opencontainers.image.revision=${GIT_SHA}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
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

COPY pyproject.toml /app/pyproject.toml
COPY app /app/app
RUN pip install --no-cache-dir --no-deps .
COPY --from=frontend-build /workspace/app/frontend/dist /app/app/frontend/dist

# Release builds stamp the exact kernel sources so the runtime never needs
# either the repository metadata or a git executable.
RUN python -c "import os; from pathlib import Path; from app.backend.app.evidence.stats_kernel import write_stats_kernel_build_info; write_stats_kernel_build_info(backend_root=Path('/app/app/backend'), git_commit=os.environ['AB_BUILD_SHA'])"

# Run unprivileged. UID 1000 matches the user Hugging Face Spaces runs containers
# as, so the same image works there without a second ownership pass. Only /app/data
# is writable; the code tree stays root-owned and read-only to the app user.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /app/data \
    && chown -R app:app /app/data

USER app
WORKDIR /app/data

EXPOSE 8008

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import os, urllib.request; port=os.environ.get('PORT') or os.environ.get('AB_PORT') or '8008'; urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3)" || exit 1

CMD ["sh", "-c", "exec python -m uvicorn app.backend.app.main:app --host \"${AB_HOST:-0.0.0.0}\" --port \"${PORT:-${AB_PORT:-8008}}\""]
