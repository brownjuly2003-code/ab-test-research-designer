# Task 0.2: Backend modularization + security fix

**Phase:** 0 — Foundation  
**Priority:** Critical  
**Depends on:** nothing  
**Effort:** ~4h

---

## Context

Read these files before starting:
- `app/backend/app/main.py` (1057 lines) — ALL routes, middleware, auth, rate limiting in one file inside `create_app()` closure
- `app/backend/app/config.py` (184 lines) — settings
- `app/backend/app/repository.py` — used by route handlers
- `app/backend/tests/` — all test files (they use `TestClient(create_app())`)

Current structure: one giant `create_app()` function in `main.py` registers all 19 endpoints inline. This makes the file unmaintainable and hard to review.

---

## Goal

1. Split `main.py` into focused APIRouter modules — one per domain
2. Fix timing-unsafe token comparison (security bug — `==` operator is vulnerable to timing oracle attacks)
3. Keep `create_app()` as the composition root — all tests continue to work unchanged

---

## Steps

### Step 1: Create routes directory

Create `app/backend/app/routes/__init__.py` (empty).

### Step 2: Extract `routes/analysis.py`

Move these endpoints from `main.py` into `app/backend/app/routes/analysis.py`:
- `POST /api/v1/calculate`
- `POST /api/v1/design`
- `POST /api/v1/analyze`
- `POST /api/v1/llm/advice`
- `GET /api/v1/sensitivity` (will be added in Phase 2.1 — create placeholder for it now)

The router needs access to: `settings`, `repository`, `rate_limiter`, `auth_dependency`.
Pass these via a factory function:

```python
from fastapi import APIRouter

def create_analysis_router(settings, repository, rate_limiter, require_auth, require_write_auth) -> APIRouter:
    router = APIRouter()
    # move route handlers here
    return router
```

### Step 3: Extract `routes/projects.py`

Move these endpoints:
- `GET /api/v1/projects`
- `POST /api/v1/projects`
- `GET /api/v1/projects/{project_id}`
- `PUT /api/v1/projects/{project_id}`
- `DELETE /api/v1/projects/{project_id}` (archive)
- `GET /api/v1/projects/{project_id}/history`
- `GET /api/v1/projects/{project_id}/revisions`
- `POST /api/v1/projects/compare`
- `GET /api/v1/projects/{project_id}/snapshots/{run_id}`

Factory: `create_projects_router(settings, repository, rate_limiter, require_auth, require_write_auth) -> APIRouter`

### Step 4: Extract `routes/workspace.py`

Move these endpoints:
- `POST /api/v1/workspace/export`
- `POST /api/v1/workspace/import`
- `POST /api/v1/workspace/validate`

Factory: `create_workspace_router(settings, repository, rate_limiter, require_auth, require_write_auth) -> APIRouter`

### Step 5: Extract `routes/export.py`

Move these endpoints:
- `POST /api/v1/export/markdown`
- `POST /api/v1/export/html`
- `POST /api/v1/export/html-standalone` (placeholder for Phase 3.4)

Factory: `create_export_router(settings, repository, rate_limiter, require_auth) -> APIRouter`

### Step 6: Extract `routes/system.py`

Move these endpoints:
- `GET /health`
- `GET /readyz`
- `GET /api/v1/diagnostics`

Factory: `create_system_router(settings, repository, runtime_counters, start_time) -> APIRouter`

### Step 7: Fix timing-safe token comparison (SECURITY)

In `main.py`, find all places where API tokens are compared:
```python
# BEFORE (vulnerable):
if presented_token == settings.api_token:
if presented_token == settings.readonly_api_token:

# AFTER (timing-safe):
import hmac
if hmac.compare_digest(presented_token, settings.api_token):
if hmac.compare_digest(presented_token, settings.readonly_api_token):
```

Apply to ALL token comparison locations — typically in the auth dependency function and middleware.
Also check `repository.py` for any token/signature comparisons and apply the same fix.

### Step 8: Slim down `main.py`

After extraction, `main.py` should contain only:
1. `create_app()` factory — creates FastAPI instance, creates all dependencies, includes all routers
2. Middleware registration (CORS, rate limiter middleware, request ID / process time headers, security headers)
3. Exception handlers (400, 500 global handlers)
4. `if __name__ == "__main__": uvicorn.run(...)` block

Target: `main.py` ≤ 200 lines after extraction.

Include routers in `create_app()`:
```python
analysis_router = create_analysis_router(settings, repository, rate_limiter, require_auth, require_write_auth)
projects_router = create_projects_router(settings, repository, rate_limiter, require_auth, require_write_auth)
workspace_router = create_workspace_router(settings, repository, rate_limiter, require_auth, require_write_auth)
export_router = create_export_router(settings, repository, rate_limiter, require_auth)
system_router = create_system_router(settings, repository, runtime_counters, start_time)

app.include_router(analysis_router)
app.include_router(projects_router)
app.include_router(workspace_router)
app.include_router(export_router)
app.include_router(system_router)
```

---

## Verify

- [ ] `cd app/backend && python -m pytest tests/ -x -q` — all 100 tests pass
- [ ] `python -c "from app.main import create_app; app = create_app(); print(len(app.routes), 'routes')"` — same count as before
- [ ] `main.py` is ≤ 200 lines
- [ ] Each `routes/*.py` exists: `analysis.py`, `projects.py`, `workspace.py`, `export.py`, `system.py`
- [ ] `hmac.compare_digest` is used for all token comparisons — grep: `grep -r "== settings.api_token" app/backend/` returns nothing
- [ ] `python scripts/verify_all.py` exits 0 (or all checks that don't require e2e pass)

---

## Constraints

- Do NOT change any endpoint URLs, request schemas, or response schemas
- Do NOT change test files — they must pass without modification
- The `create_app()` factory pattern MUST be preserved (tests rely on it)
- Do NOT add new dependencies to `requirements.txt`
- Each route module MUST be independently importable (no circular imports)
- Keep all middleware in `main.py` — do not move it to route modules
