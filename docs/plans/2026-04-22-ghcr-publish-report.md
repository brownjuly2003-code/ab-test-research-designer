# GHCR Publish Report

Execution date: 2026-04-22

## Files Created Or Updated

- Created: `.github/workflows/docker-publish.yml`
- Created: `docs/plans/2026-04-22-ghcr-publish-report.md`
- Updated: `docs/DEPLOY.md`
- Updated: `README.md`
- Staged with the same task commit: `docs/plans/codex-tasks/2026-04-22-cx-ghcr-publish.md`

## Workflow Decision

- `verify-before-publish` was intentionally not added to the release workflow.
- Reason: the repository already runs the full verification stack on regular `push` / `pull_request` in `.github/workflows/test.yml`, while the GHCR workflow is meant to keep tag-based publishing latency reasonable on top of a multi-arch build.
- Tradeoff: a manually pushed tag can still trigger publish without rerunning the full suite in that workflow, so local `scripts/verify_all.cmd --with-e2e` remains part of the release checklist.

## Workflow Syntax Validation

- `actionlint .github/workflows/docker-publish.yml` passed.
- `python -c "import yaml; yaml.safe_load(open('.github/workflows/docker-publish.yml'))"` passed.

## Local Verification

- `scripts/verify_all.cmd --with-e2e` failed outside the GHCR scope during backend pytest:
  - `app/backend/tests/test_startup_seed.py::test_startup_seed_populates_demo_projects_with_analysis_and_export`
  - `app/backend/tests/test_startup_seed.py::test_startup_seed_is_idempotent_across_restarts`
- Failure summary: both tests expected three seeded demo projects after startup, but observed `0`.
- Evidence that this is pre-existing dirty-worktree state outside this task's file scope: `app/backend/app/config.py`, `app/backend/app/main.py`, untracked `app/backend/app/startup_seed.py`, untracked `app/backend/tests/test_startup_seed.py`, and untracked `docs/plans/codex-tasks/2026-04-22-cx-seed-hf-startup.md` were already present while this task only touched workflow/docs/report files.

## User Checklist For First Publish

1. Push a tag matching `v*`, for example `v1.1.0`.
2. Wait for the `Publish Docker image` workflow to finish.
3. Open https://github.com/brownjuly2003-code/ab-test-research-designer/pkgs/container/ab-test-research-designer.
4. Go to `Settings` and change package visibility to **Public**.
5. Verify anonymous pull from a clean machine:

```bash
docker pull ghcr.io/brownjuly2003-code/ab-test-research-designer:v1.1.0
```

## Known Risks

- The first publish can take roughly 8-15 minutes because the workflow builds both `linux/amd64` and `linux/arm64` without a warm cache.
- `cache-from/cache-to type=gha` improves repeat runs, but GitHub may evict the cache after about 7 days of inactivity.
- GHCR package visibility is private on the first push and must be switched to public once by hand.
