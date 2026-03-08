FROM node:22-alpine AS frontend-build

WORKDIR /workspace/app/frontend

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

WORKDIR /app

COPY app/backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY app /app/app
COPY --from=frontend-build /workspace/app/frontend/dist /app/app/frontend/dist

RUN mkdir -p /app/data

EXPOSE 8008

CMD ["python", "-m", "uvicorn", "app.backend.app.main:app", "--host", "0.0.0.0", "--port", "8008"]
