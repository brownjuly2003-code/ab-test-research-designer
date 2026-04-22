# Seed HF Startup Report

## Files changed for this task

- `Dockerfile`
- `app/backend/app/config.py`
- `app/backend/app/main.py`
- `app/backend/app/startup_seed.py`
- `app/backend/tests/test_startup_seed.py`
- `docs/RUNBOOK.md`
- `docs/plans/codex-tasks/2026-04-22-cx-seed-hf-startup.md`
- `docs/plans/2026-04-22-seed-hf-startup-report.md`

## Notes on repo state

- `README.md` already contained the hosted-demo seeded paragraph on `HEAD`, so no additional README change was required for this task.
- Hugging Face Spaces currently injects runtime env vars from the Space Settings UI, not from README frontmatter, so `AB_SEED_DEMO_ON_STARTUP=true` must be configured there.
- The worktree already contained unrelated modified/untracked files before this task; they were not reverted or included in this task commit.

## New startup seed test

Scenarios covered:

1. startup with `AB_SEED_DEMO_ON_STARTUP=true` creates 3 demo projects, saves one analysis run for each, and records a markdown export for Checkout
2. repeated startup stays idempotent and does not duplicate the demo projects
3. startup with `AB_SEED_DEMO_ON_STARTUP=false` creates nothing

Command:

```bash
python -m pytest app/backend/tests/test_startup_seed.py -q
```

Result:

```text
...                                                                      [100%]
3 passed in 6.99s
```

## Full verification

Backend suite:

```bash
python -m pytest app/backend/tests -q
```

```text
236 passed in 144.42s (0:02:24)
```

Full pipeline:

```bash
cmd /c scripts\verify_all.cmd --with-e2e
```

Result:

```text
exit 0
[verify] generated api contracts
[verify] generated api docs
[verify] workspace backup roundtrip (checksum)
[verify] workspace backup roundtrip (signed)
[verify] backend tests
236 passed in 130.46s (0:02:10)
[verify] backend benchmark
payload=binary iterations=500 mean_ms=0.005 p95_ms=0.005 max_ms=0.038
```

## Docker smoke

Build:

```bash
docker build -t ab-test:seed-test .
```

Seeded run:

```bash
docker run --rm -e AB_SEED_DEMO_ON_STARTUP=true -p 18010:8008 ab-test:seed-test
```

Observed result:

```text
projects_count=3
2026-04-22T15:38:31.976008+00:00 INFO app.backend.app.startup_seed: demo-seed: completed analyzed_projects=3 created_projects=3 exported_projects=1 skipped_projects=0
```

Default run without flag:

```bash
docker run --rm -p 18011:8008 ab-test:seed-test
```

Observed result:

```text
projects_count=0
```

## HF deploy checklist

1. In Hugging Face Space Settings -> Variables and secrets, set `AB_SEED_DEMO_ON_STARTUP=true`.
2. If the Space should stay open-mode, leave `AB_API_TOKEN` unset. If secure mode is needed, also set `AB_API_TOKEN` and use `Authorization: Bearer ...` for verification calls.
3. Redeploy or restart the Space.
4. Verify the project list:

```bash
curl https://liovina-ab-test-research-designer.hf.space/api/v1/projects
```

5. Verify seeded history for the Checkout demo project:

```bash
curl https://liovina-ab-test-research-designer.hf.space/api/v1/projects/PROJECT_ID/history
```

6. If the Space is protected, repeat the same calls with:

```bash
curl https://liovina-ab-test-research-designer.hf.space/api/v1/projects \
  -H "Authorization: Bearer YOUR_AB_API_TOKEN"
```

7. For deploy/debug status, check the HF UI logs or inspect runtime stage with:

```python
from huggingface_hub import HfApi
print(HfApi().get_space_runtime(repo_id="liovina/ab-test-research-designer").stage)
```

## Known risks

- SQLite on the base Hugging Face Space tier is ephemeral, so every cold restart seeds the demo workspace again. This is expected behavior for the public demo.
- Startup seeding adds a small delay before the app is ready. In local Docker smoke it completed before the first readiness poll and logged one pass that created 3 projects, 3 analysis runs, and 1 export event.
- `git status --short` cannot be made empty after this task commit without also touching unrelated in-progress user changes already present in the repo. Those files were intentionally left alone.
