# Demo Hosting Prep Report

Execution date: 2026-04-21

## Files Created Or Updated

- Created: `fly.toml`
- Created: `scripts/seed_demo_workspace.py`
- Created: `docs/RELEASE_NOTES_v1.0.0-github-draft.md`
- Created: `docs/plans/2026-04-22-demo-hosting-prep-report.md`
- Updated: `Dockerfile`
- Updated: `docs/DEPLOY.md`
- Updated: `README.md`
- Staged with the same task commit: `docs/plans/codex-tasks/2026-04-22-cx-demo-hosting-prep.md`

## Bug Fixes And Fly Compatibility Notes

- Docker runtime now respects `AB_HOST` and `AB_PORT` at container start. Before this change, the image always started uvicorn with hardcoded `0.0.0.0:8008`, which made the env vars ineffective.
- No backend patch was required for SQLite path handling. `app/backend/app/config.py` already reads `AB_DB_PATH`, and `app/backend/app/repository.py` already creates the parent directory before SQLite initialization, which is enough for a writable Fly volume mounted at `/data`.
- Demo seed data is implemented as a manual helper script instead of a Fly `release_command`. Fly release Machines do not mount persistent volumes, so a release-time seed would write to ephemeral storage rather than the SQLite volume.

## Verification Status

- `python -c "import tomllib; tomllib.load(open('fly.toml','rb'))"` passed.
- `docker build -t ab-test-research-designer:1.0.0 .` passed.
- `docker run --rm -p 18008:8008 -e AB_ENV=demo -e AB_WORKSPACE_DIR=/tmp/abtest -e AB_DB_PATH=/tmp/abtest/p.sqlite3 -v <temp-host-dir>:/tmp/abtest ab-test-research-designer:1.0.0` reached `GET /health -> 200`, returned `"environment":"demo"`, and created the SQLite file on the mounted path.
- `python scripts/seed_demo_workspace.py --idempotent` passed in a temporary demo workspace: first run created 3 sample projects, second run skipped the same 3 projects as expected.
- `scripts\verify_all.cmd --with-e2e` is currently blocked before the backend or Fly-specific checks run. It fails at the generated contract gate because `app/frontend/src/lib/generated/api-contract.ts` is already out of date relative to pre-existing API changes in the dirty worktree outside this task's file scope.

## User Deploy Checklist

1. Run `fly apps create <fly-app-name>`.
2. Update `app` in `fly.toml` or deploy with `fly deploy -a <fly-app-name>`.
3. Run `fly volumes create ab_test_data --region ams --size 1`.
4. Optional secure mode: `fly secrets set AB_API_TOKEN=... AB_READONLY_API_TOKEN=... AB_WORKSPACE_SIGNING_KEY=...`.
5. Run `fly deploy`.
6. Optional demo seed after the first deploy: `fly ssh console -C "python scripts/seed_demo_workspace.py --idempotent"`.
7. Replace `<fly-url-after-deploy>` and the release-note placeholders after the real deploy and Docker push.

## Known Risks

- Cold-start latency remains possible because `min_machines_running = 0` allows Fly to scale the demo down to zero.
- `[[vm]]` is pinned to `shared` CPU with `512` MB RAM; large exports or future feature growth may need a memory bump.
- SQLite on a Fly volume is acceptable for a single demo machine, but it does not scale horizontally; multi-machine hosting would require Postgres or LiteFS.
