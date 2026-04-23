# CX Task: Research-first diagnosis and fix for two Ubuntu-only CI hangs in AB_TEST

## Goal

Two independent Linux-specific CI failures started surfacing on the
Ubuntu runner after a recent round of frontend additions (v1.1.0 post-
release wave: multi-project comparison, webhooks, de/es locales,
property-based tests). They were invisible before because an earlier
`api-contract.ts` drift was failing the pipeline before it could reach
them. Now that drift is fixed, both hangs block every green run on
`main`. Windows CI and local development (both platforms) work.

The task is: (1) **research both symptoms as the first step**, do not
start editing code or running speculative patches until the research
produces a concrete cause-and-fix hypothesis; (2) apply the fix; (3)
remove the current workarounds; (4) re-enable the dynamic-badges
pipeline that was disabled during triage.

**Scope.** Two separate hangs, both Linux-only:

1. **Vitest unit suite deadlocks** after `WizardReviewStep.test.tsx`
   (plain `npm run test:unit`, vitest 1.x, Node 22, Ubuntu runner).
   `--testTimeout=30000 --hookTimeout=30000 --bail=1 --reporter=verbose`
   all failed to surface a named failing test; the process just sits
   idle. Current workaround: `--skip-frontend-unit` on the Ubuntu
   matrix. The full suite still runs green on the Windows matrix.
2. **Playwright e2e `locator.click: Test timeout of 45000ms exceeded`**
   in the `e2e-smoke-imports-the-demo` test on Ubuntu. Surfaces even
   with `--skip-frontend-unit` set (run id `24811054759`, commit
   `88d67b11`).

## Research — do this first, before touching code

Both hangs smell like a known tooling interaction. Dig the following
sources and write a short research note (see Deliverables §1) before
opening any patch branch:

- **vitest issues.** Search the `vitest-dev/vitest` repo for:
  - `jsdom` + `vitest-axe` + `hang` / `deadlock` / `freeze`.
  - `Node 22` or `node:22` hang reports on Linux runners.
  - `pool: 'forks'` vs `pool: 'threads'` Linux flakiness.
  - `--isolate` / `poolOptions` workarounds.
  - Any CHANGELOG entry in `1.x` patch releases touching
    worker-pool or jsdom teardown.
- **vitest-axe issues.** Search `chaances/vitest-axe` (or the current
  canonical home) for issues on Linux runner hangs, axe runner leaks,
  or jsdom+async handler teardown. Note versions that have shipped
  fixes.
- **Playwright issues.** Search `microsoft/playwright` for
  `locator.click` timing out on Ubuntu GitHub runners when the app is
  served from a locally-started backend, especially with the specific
  chromium-headless-shell v1208 build captured in the install log.
  Note the standard fixes: `test.use({ viewport })`, `page.waitFor*`
  primitives, headless flags, `CHROMIUM_FLAGS` env, `ipc=host` in
  Docker, etc.
- **GitHub Actions runner Ubuntu image changes** in the last 60 days
  that could affect jsdom / chromium behaviour (seccomp, AppArmor,
  Node binary swap). Look at `actions/runner-images` issue tracker.
- **The existing tests in this repo** that were added during the
  v1.1.0 wave. These are the most likely triggers for hang #1:
  - `app/frontend/src/test/a11y-locales.test.tsx`
  - `app/frontend/src/test/a11y-webhooks.test.tsx`
  Read them before deciding on a fix, but do not rewrite them
  blindly — the research should produce a concrete reason they
  would deadlock on Linux and not on Windows.
- **The e2e smoke flow.** Read `scripts/run_frontend_e2e.py`,
  `app/frontend/e2e/*` (or wherever the smoke tests live), and
  identify the selector that `locator.click` is waiting on in the
  `imports-the-demo` scenario. Hypothesise whether it is a
  server-readiness race, a hidden element, a missing `await`, or a
  Linux font/layout difference.

Budget the research at ~45–90 minutes. If after that window neither
hypothesis is concrete, write what you have into the research note
and stop — we will ask for a second pass before moving to code.

## Context

- **Repo.** `D:\AB_TEST\`, `main`, HEAD at or ahead of `88d67b11`. Do
  not rebase.
- **Workaround in place right now.**
  - Ubuntu verify job matrix arg: `--with-e2e --skip-frontend-unit`.
  - Windows verify job matrix arg: `""` (full suite — runs the vitest
    unit tests that Linux skips).
  - `update-metrics-badges` workflow job: `if: false` (disabled).
  - `Upload verify metrics artifacts` step: removed from the workflow.
  - `--with-coverage` / `--artifacts-dir` flags: still present on
    `scripts/verify_all.{py,cmd}` but not used by the Ubuntu matrix
    any more.
  - `badges/{metrics,tests,coverage,lighthouse}.json`: committed as
    static placeholders (last real values: 236 backend tests, 92%
    backend coverage, lighthouse n/a).
- **Relevant recent commits (newest first).**
  - `88d67b11` — add `--skip-frontend-unit` and route Ubuntu through it.
  - `ff26c2c8` — revert coverage pipeline on Ubuntu to restore CI.
  - `93a33a65` — attempt 2 at surfacing the vitest hang
    (`--reporter=verbose --bail=1`). Cancelled.
  - `82083f20` — attempt 1 (`--testTimeout=30000 --hookTimeout=30000`).
    Did not help.
  - `51ee07b6` — drop `vitest --reporter=junit --outputFile=...` path
    (also hangs; writes 0-byte XML locally on Windows git-bash).
  - `6e02ea70` — `timeout-minutes: 20` on the verify job so hangs
    surface instead of burning the 6-hour ceiling.
  - `efaa23cf` — `pypdf==6.9.2` pin (unrelated, earlier failure).
  - `1757bc36` — regen `api-contract.ts` under pinned fastapi
    0.128.0; this is the commit that **uncovered** the two hangs by
    letting the pipeline reach frontend tests.
- **Last visible test line before hang #1** (run `24803637727`,
  Ubuntu, commit `51ee07b6`):
  ```
  ✓ src/components/WizardReviewStep.test.tsx (1 test) 78ms
  ```
  ~18 minutes of silence follow until job timeout.
- **Hang #2 log line** (run `24811054759`, commit `88d67b11`):
  ```
  Error: locator.click: Test timeout of 45000ms exceeded.
  test-results/playwright/e2e-smoke-imports-the-demo-6ab29-etes-
    the-browser-smoke-flow-retry1/test-failed-1.png
  ```
- **Environment pins.**
  - `fastapi==0.128.0`, `pydantic==2.12.5`, `pypdf==6.9.2`,
    `pytest==8.4.2`, `pytest-cov==5.0.0`, `hypothesis==6.152.1`.
  - Node 22, `actions/setup-node@v4`.
  - vitest version: read from `app/frontend/package.json`.
  - Playwright: chromium-headless-shell v1208 at install time.
  - GitHub Actions runner image tag: `ubuntu-latest` (currently the
    Ubuntu 24.04 image, but verify in the run log — image version is
    printed during `Set up job`).

## Deliverables

1. **Research note** at `docs/plans/2026-04-23-vitest-ubuntu-research.md`
   with sections:
   - Symptoms (paste the two log signatures).
   - Sources consulted (URLs, versions checked).
   - Hypothesis for hang #1 (vitest unit) with evidence.
   - Hypothesis for hang #2 (Playwright click) with evidence.
   - Proposed fix path for each, ranked by confidence.
   - Rejected options and why.

2. **Fix for hang #1** (vitest unit deadlock). Possible shapes,
   document whichever you pick:
   - Patch or split `a11y-locales.test.tsx` / `a11y-webhooks.test.tsx`
     (stop leaking axe runners, teardown i18n listeners, etc.).
   - Pin a vitest / jsdom / vitest-axe combination that does not
     deadlock (no `^` ranges).
   - Change `app/frontend/vite.config.ts` (explicit `pool`,
     `poolOptions`, `isolate`).
   - Do not quarantine tests without justification.

3. **Fix for hang #2** (Playwright click timeout). Possible shapes:
   - Adjust the selector / waiting strategy in the `imports-the-demo`
     e2e scenario (prefer `expect(locator).toBeVisible({ timeout })`
     over bare `click`).
   - Adjust `run_frontend_e2e.py` so it does not race the backend
     start (readiness probe instead of sleep).
   - Headed/headless flags or chromium launch args for the Linux
     runner.
   - `--trace on-first-retry` or `--video=retain-on-failure` for
     future diagnosis, but fix the underlying race.

4. **Workaround removal.** In the same branch or a follow-up commit:
   - Remove `--skip-frontend-unit` from the Ubuntu matrix in
     `.github/workflows/test.yml`.
   - Remove the flag from `scripts/verify_all.py` (argparse entry +
     delegation line) and `scripts/verify_all.cmd` (if added there).
     If the flag is not added to the `.cmd` wrapper it can stay out.
   - Restore `matrix[ubuntu].verify_args =
     "--with-e2e --with-coverage --artifacts-dir .ci-artifacts"`.
   - Restore the `Upload verify metrics artifacts` step (see the
     `ff26c2c8` revert diff for the exact YAML we removed).
   - Flip `update-metrics-badges.if` back to
     `github.ref == 'refs/heads/main' && github.event_name == 'push'`.
   - Keep `timeout-minutes: 20` on the verify job.

5. **Green proof.** A single push on `main` must produce:
   - Both `verify (ubuntu-latest, ...)` and `verify (windows-latest)`
     concluding `success`.
   - `lighthouse` green.
   - `update-metrics-badges` running and committing a real
     `chore: update badge metrics [skip ci]` commit (OK to revert the
     four `badges/*.json` to their placeholder content before the
     push so the bot commit is non-empty).
   - shields.io URLs in `README.md` rendering real values within
     ~5 minutes of the bot commit landing.

## Acceptance

- `docs/plans/2026-04-23-vitest-ubuntu-research.md` exists and names
  a concrete root cause for each hang (not just a "try X and see").
- `git grep skip-frontend-unit` is empty.
- `.github/workflows/test.yml` carries the restored
  `update-metrics-badges.if` and the restored
  `Upload verify metrics artifacts` step.
- A push on `main` shows a fully green `Tests` workflow with a
  subsequent `github-actions[bot]` commit from
  `update-metrics-badges`.
- Final commit subject:
  `docs: diagnose and fix the two ubuntu ci hangs, re-enable dynamic badges`
  (single commit is OK; split is also OK if the research note goes
  first).

## Notes

- Research agent instructions: use a subagent with WebSearch + GitHub
  issue search. Budget ≤90 minutes. If stuck, report partial findings
  rather than grind.
- Do not upgrade React, React-i18next, axe-core, or any runtime
  library as part of the fix unless the research explicitly ties one
  of them to the hang. A version bump that silently changes UX
  behaviour is out of scope.
- The `timeout-minutes: 20` safety net should remain after the fix.
- If the real root cause cannot be fully fixed in one pass (e.g., an
  upstream vitest bug with no released patch), ship the research note
  + the best-available mitigation + an upstream issue link; do not
  silently re-disable the suite.
- Keep `timeout-minutes: 20` on the `verify` job.
- The GHCR package visibility (public vs private) is not part of this
  task — the repo owner will flip that once through the GitHub UI.

## Out of scope

- HF Space sync (separate CX task
  `2026-04-22-cx-hf-sync-seed.md`).
- Frontend junit reporter back in the badges pipeline — separate
  follow-up if needed.
- Any new product feature, locale, or UI change.
- History rewrites / force-push. Append new commits only.
