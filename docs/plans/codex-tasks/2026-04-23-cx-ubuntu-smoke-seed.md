# CX Task: Finish making the Ubuntu Tests workflow fully green (smoke seed + comparison screenshot)

## Goal

Your earlier research pass (`docs/plans/2026-04-23-vitest-ubuntu-research.md`,
commit `e9c05c23`) fixed the vitest deadlock and the Playwright locator race.
After that, five more layered issues surfaced on Ubuntu CI. I patched the
easy ones but the last one is not clearing cleanly. Close the loop: drive
`Tests` workflow to a fully green run on `main`, then confirm
`update-metrics-badges` commits live numbers.

## Current state

- **Main** HEAD `2134bc70` (may be ahead when you start).
- **Green:** `verify (windows-latest)`, `docker`, lighthouse preconditions.
  Windows runs the full suite (vitest + e2e + smoke) without issue.
- **Red:** `verify (ubuntu-latest, --with-e2e --with-coverage
  --artifacts-dir .ci-artifacts)` on the smoke step:

  ```
  Smoke screenshot: archive/smoke-runs/20260423-031807/smoke-failure.png
  Smoke DOM dump:  archive/smoke-runs/20260423-031807/smoke-failure.html
  Traceback (most recent call last):
      raise RuntimeError("Smoke expected at least two comparison-ready
                          project checkboxes.")
  RuntimeError: Smoke expected at least two comparison-ready project
                checkboxes.
  ```
  Run id `24814745094`.

- **Layered fixes already on main (do not redo):**
  - `f95e5a6b` — pin `playwright==1.58.0` in `app/backend/requirements.txt`;
    add a `Install Playwright browser (python)` step:
    `python -m playwright install chromium`.
  - `ffadd775` — drop the hard-coded `"npm.cmd"` in
    `scripts/run_local_smoke.py`; use the `NPM_EXECUTABLE` pattern already
    in `scripts/verify_all.py` and `scripts/run_frontend_e2e.py`.
  - `2134bc70` — set `AB_SEED_DEMO_ON_STARTUP=true` in the smoke backend
    `process_env` so `startup_seed.seed_demo_workspace` is supposed to
    pre-populate projects. This did **not** fix the failure — either the
    env var is parsed wrong, the seed hook is silently skipped, or the
    smoke flow looks at a different store.

## Deliverables

1. **Diagnose why the seed is still empty at smoke time.**
   - `app/backend/app/startup_seed.py:seed_demo_workspace` is the seeder;
     `app/backend/app/main.py:84-88` is the startup wiring under the
     `seed_demo_on_startup` setting.
   - `app/backend/app/config.py:177` parses the env var via
     `_read_bool_env("AB_SEED_DEMO_ON_STARTUP", False)`. Confirm the
     parser accepts the string `"true"` — if it only recognises
     `"1"` / `"yes"`, change the value passed by smoke to whatever the
     parser expects, or make the parser tolerant (preferred: accept
     common truthy strings). Do not break the HF startup path that
     already works.
   - Check that the seed hook is invoked **before** the smoke test hits
     the UI (race between backend boot and frontend polling).
   - Confirm the temp SQLite path `temp_db_path` used by smoke is the
     same one the running backend process uses — no path drift between
     `AB_DB_PATH` export and the smoke harness probing it.

2. **Fix.** One clear path. Possible shapes:
   - Adjust `AB_SEED_DEMO_ON_STARTUP` value in `run_local_smoke.py` to a
     form the parser accepts (e.g. `"1"`).
   - Make `_read_bool_env` accept `{"1","true","yes","on"}` case-
     insensitive; keep the default `False`.
   - Add an explicit readiness probe that waits for the seeded project
     count to reach 2 before the smoke flow starts the comparison
     screenshot step.
   - Or — if you decide the smoke path should not rely on the seed hook
     at all — have `run_local_smoke.py` POST two projects through
     `POST /api/v1/projects` itself before entering the browser flow.
     Document the choice in the task report.

3. **Capture smoke artifacts on failure.** Whatever the outcome here, the
   next failure on `main` should bring the dump along. Add a workflow
   step:
   ```yaml
   - name: Upload smoke failure dump
     if: failure() && matrix.os == 'ubuntu-latest'
     uses: actions/upload-artifact@v4
     with:
       name: smoke-failure
       path: archive/smoke-runs/
       if-no-files-found: ignore
   ```
   Place it under the `verify` job, right next to the existing
   `Upload verify metrics artifacts` step.

4. **Green proof.** A single push on `main` must conclude:
   - `verify (ubuntu-latest, ...)`: success.
   - `verify (windows-latest)`: success.
   - `docker`: success.
   - `lighthouse`: success.
   - `update-metrics-badges`: success, bot commit
     `chore: update badge metrics [skip ci]` lands and rewrites the four
     `badges/*.json` files.
   - shields.io URLs in `README.md` render non-placeholder values within
     ~5 minutes.

5. **Report** at `docs/plans/2026-04-23-ubuntu-smoke-fix-report.md`:
   - Which of the three suspects was the real root cause.
   - What changed.
   - Screenshot or curl of the final `badges/metrics.json` showing
     non-placeholder values.

## Acceptance

- One push on `main` shows a fully green `Tests` workflow plus the
  follow-up bot commit from `update-metrics-badges`.
- `badges/metrics.json` at the tip of `main` has real numbers (not
  `"lightgrey"` / `"n/a"`).
- `git grep '"npm.cmd"'` returns only the NPM_EXECUTABLE assignment
  lines, nothing new.
- `scripts/run_local_smoke.py` still runs green on Windows — do not
  break the existing platform.
- Final commit subject:
  `fix: drive ubuntu ci green by repairing smoke seed and uploading smoke dumps`.

## Notes

- `_read_bool_env` is in `app/backend/app/config.py`; check its exact
  logic before assuming how it parses `"true"`.
- `AB_SEED_DEMO_ON_STARTUP` is already set in `run_local_smoke.py:70-85`.
  If that value needs to change, change it there — not globally.
- You can reproduce locally on Windows: `python scripts/verify_all.py
  --skip-build` with `AB_SEED_DEMO_ON_STARTUP=true` exported; compare
  the seed-hook logs to the Ubuntu run.
- `timeout-minutes: 20` on the verify job is intentional — keep it.
- Do **not** disable smoke on Ubuntu as a workaround; the comparison-
  screenshot path is part of the v1.1.0 UX and must stay verified.
- Do **not** touch HF sync here (separate CX task
  `2026-04-22-cx-hf-sync-seed.md`).

## Out of scope

- Any new product feature or locale.
- Refactoring the smoke harness beyond the seed path.
- Package publishing, release tagging, HF sync.
