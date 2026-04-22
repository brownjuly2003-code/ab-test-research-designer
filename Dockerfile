FROM node:22-alpine AS frontend-build

WORKDIR /workspace/app/frontend

ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci

COPY app/frontend ./
RUN npm run build


FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV AB_HOST=0.0.0.0
ENV AB_PORT=8008
ENV AB_SERVE_FRONTEND_DIST=true
ENV AB_FRONTEND_DIST_PATH=/app/app/frontend/dist
ENV AB_DB_PATH=/app/data/projects.sqlite3
ENV AB_SQLITE_BUSY_TIMEOUT_MS=5000
ENV AB_SQLITE_JOURNAL_MODE=WAL
ENV AB_SQLITE_SYNCHRONOUS=NORMAL
ENV AB_LOG_LEVEL=INFO
ENV AB_LOG_FORMAT=plain

WORKDIR /app

COPY app/backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY app /app/app
COPY --from=frontend-build /workspace/app/frontend/dist /app/app/frontend/dist

RUN mkdir -p /app/data

EXPOSE 8008

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8008/health', timeout=3)" || exit 1

CMD ["sh", "-c", "exec python -m uvicorn app.backend.app.main:app --host \"${AB_HOST:-0.0.0.0}\" --port \"${PORT:-${AB_PORT:-8008}}\""]
