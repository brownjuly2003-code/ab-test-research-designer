# Configuration

The backend reads its runtime settings from environment variables. The frontend also supports one build-time override for the API base URL.

## Application runtime

| Variable | Default | Purpose |
| --- | --- | --- |
| `AB_APP_NAME` | `AB Test Research Designer API` | Overrides the API service name reported by health endpoints. |
| `AB_APP_VERSION` | `1.1.0` | Overrides the runtime version string. |
| `AB_ENV` | `local` | Labels the current environment such as `local`, `demo`, or `production`. |
| `AB_HOST` | `127.0.0.1` | Backend bind host. Use `0.0.0.0` in containers. |
| `AB_PORT` | `8008` | Backend listen port. |
| `AB_DB_PATH` | absolute path to `<repo>/app/backend/data/projects.sqlite3` (computed from package location) | Override only with an **absolute** path. Bare relative paths break through `Path.as_posix()` → `sqlite:///app/...` resolving to absolute `/app/...`. |
| `AB_FRONTEND_DIST_PATH` | absolute path to `<repo>/app/frontend/dist` (computed from package location) | Override only with an absolute path. |
| `AB_SERVE_FRONTEND_DIST` | `true` | Enables same-origin serving of the built frontend. |

## CORS and frontend wiring

| Variable | Default | Purpose |
| --- | --- | --- |
| `AB_CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | Allowed frontend origins for dev or split-host deployments. |
| `AB_CORS_METHODS` | `GET,POST,PUT,DELETE,OPTIONS` | Allowed HTTP methods for CORS preflight. |
| `AB_CORS_HEADERS` | `Accept,Content-Type` | Allowed request headers for CORS preflight. |
| `VITE_API_BASE_URL` | empty in production, `http://127.0.0.1:8008` in dev | Optional frontend build-time API base override. Leave empty for same-origin deploys. |

## LLM adapter

| Variable | Default | Purpose |
| --- | --- | --- |
| `AB_LLM_BASE_URL` | `http://localhost:8001` | Base URL of the optional local LLM orchestrator. |
| `AB_LLM_TIMEOUT_SECONDS` | `60` | Request timeout for LLM calls. |
| `AB_LLM_MAX_ATTEMPTS` | `3` | Retry count for LLM calls. |
| `AB_LLM_INITIAL_BACKOFF_SECONDS` | `0.1` | Initial retry backoff. |
| `AB_LLM_BACKOFF_MULTIPLIER` | `2` | Backoff multiplier between attempts. |

## SQLite and logging

| Variable | Default | Purpose |
| --- | --- | --- |
| `AB_SQLITE_BUSY_TIMEOUT_MS` | `5000` | SQLite busy timeout. |
| `AB_SQLITE_JOURNAL_MODE` | `WAL` | SQLite journal mode. |
| `AB_SQLITE_SYNCHRONOUS` | `NORMAL` | SQLite synchronous mode. |
| `AB_LOG_LEVEL` | `INFO` | Runtime log verbosity. |
| `AB_LOG_FORMAT` | `plain` | Log format: `plain` or `json`. |

## Auth, backup signing, and admin flows

| Variable | Default | Purpose |
| --- | --- | --- |
| `AB_API_TOKEN` | unset | Shared write-capable token for protected API routes. |
| `AB_READONLY_API_TOKEN` | unset | Shared read-only token for safe `GET/HEAD/OPTIONS` access. |
| `AB_ADMIN_TOKEN` | unset | Enables database-backed API key management and webhook administration endpoints. |
| `AB_WORKSPACE_SIGNING_KEY` | unset | Adds HMAC signatures to workspace exports and requires signed imports on the same runtime. |

## Rate limiting and request guards

| Variable | Default | Purpose |
| --- | --- | --- |
| `AB_RATE_LIMIT_ENABLED` | `true` | Enables in-memory rate limiting on runtime routes. |
| `AB_RATE_LIMIT_REQUESTS` | `240` | Allowed requests per rate-limit window. |
| `AB_RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate-limit window size. |
| `AB_AUTH_FAILURE_LIMIT` | `20` | Failed-auth attempts allowed before throttling. |
| `AB_AUTH_FAILURE_WINDOW_SECONDS` | `60` | Window size for auth-failure throttling. |
| `AB_MAX_REQUEST_BODY_BYTES` | `1048576` | Default request-body limit for mutating routes. |
| `AB_MAX_WORKSPACE_BODY_BYTES` | `8388608` | Larger dedicated body limit for workspace import and validation flows. |

## Demo seeding

| Variable | Default | Purpose |
| --- | --- | --- |
| `AB_SEED_DEMO_ON_STARTUP` | `false` | Seeds the hosted demo workspace with sample projects after startup. |

For Hugging Face Spaces, set `AB_SEED_DEMO_ON_STARTUP=true` in the Space Settings UI instead of baking it into the image. The current demo seed creates checkout conversion, pricing sensitivity, and onboarding completion projects and records an initial export for the checkout example.

## Minimal examples

Local development (`AB_DB_PATH` left unset — backend uses the absolute default inside the package):

```bash
set AB_ENV=local
set AB_PORT=8008
```

Protected local runtime:

```bash
set AB_API_TOKEN=replace-with-write-token
set AB_READONLY_API_TOKEN=replace-with-readonly-token
set AB_ADMIN_TOKEN=replace-with-admin-token
```

Signed workspace backups:

```bash
set AB_WORKSPACE_SIGNING_KEY=replace-with-a-long-random-secret
```
