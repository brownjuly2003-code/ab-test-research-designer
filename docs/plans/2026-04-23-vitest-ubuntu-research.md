# 2026-04-23 Vitest Ubuntu Research Note

## Symptoms

### Hang #1: Vitest unit suite stalls on Ubuntu

Observed in GitHub Actions run `24803637727` after:

```text
✓ src/components/WizardReviewStep.test.tsx (1 test) 78ms
```

The job then sat idle until the 20-minute timeout. The Ubuntu job log later showed orphaned `vitest` worker processes and `esbuild` still alive when GitHub Actions cleaned the job up.

Run URL:
`https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/24803637727`

### Hang #2: Playwright click timeout on Ubuntu

Observed in GitHub Actions run `24811054759`:

```text
Error: locator.click: Test timeout of 45000ms exceeded.
```

The failing step was not a generic early click. The failed locator was:

```text
app/frontend/src/test/e2e-smoke.spec.ts:52
await page.getByRole("button", { name: "Export Markdown" }).click();
```

Run URL:
`https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/24811054759`

## Sources Consulted

- Local version checks from `app/frontend/package.json` on April 23, 2026:
  - `vitest@^3.2.4`
  - `jsdom@^28.1.0`
  - `vitest-axe@^0.1.0`
  - `@playwright/test@^1.58.2`
- Vitest issue `#835` (`jsdom loading issue if threads false`):
  `https://github.com/vitest-dev/vitest/issues/835`
- Vitest issue `#8133` (`Terminating Worker Thread error since Vitest 3.2.0`):
  `https://github.com/vitest-dev/vitest/issues/8133`
- Vitest `v1.6.0` release notes:
  `https://github.com/vitest-dev/vitest/releases/tag/v1.6.0`
- GitHub Actions runner image release `Ubuntu 24.04 (20260420)`:
  `https://github.com/actions/runner-images/releases/tag/ubuntu24/20260420.95`
- Playwright actionability docs:
  `https://playwright.dev/docs/actionability`
- Playwright issue `#12193` (`Weird issues with unreliable test results, passes and fails arbitrarily`):
  `https://github.com/microsoft/playwright/issues/12193`

## Hypothesis For Hang #1 (Vitest Unit) With Evidence

### Final diagnosis

The Ubuntu hang was not caused by `vitest-axe`, `jsdom`, `Node 22`, or the Ubuntu 24.04 runner image directly.

The concrete root cause was a render loop in `app/frontend/src/components/SidebarPanel.tsx`:

- `compareCandidates` was recomputed as a fresh array on every render.
- A `useEffect` depended on that fresh array.
- The effect always called `setSelectedComparisonProjectIds(current.filter(...))`.
- Even when `current` was already `[]`, `current.filter(...)` returned a new empty array reference.
- React treated that as a state change and re-rendered again.
- Under Vitest/jsdom `act(...)`, the first render of `SidebarPanel` never settled on Linux, so the worker looked like a deadlock.

### Evidence chain

1. The full Ubuntu suite previously appeared to stop after `WizardReviewStep.test.tsx`, but a local Linux reproduction narrowed the unfinished files to:
   - `src/App.test.tsx`
   - `src/test/a11y-api-keys.test.tsx`
   - `src/test/a11y-sidebar.test.tsx`
2. A minimal Linux probe that only imported `SidebarPanel` completed quickly.
3. A minimal Linux probe that only rendered `SidebarPanel` without `axe` still hung.
4. A staged probe printed `STAGE: before render` and then hung inside `renderIntoDocument(<SidebarPanel />)`, before `flushEffects()` and before `unmount()`.
5. A temporary patch in the Linux container that stopped the `selectedComparisonProjectIds` effect from writing the same selection again immediately removed the hang.
6. After that temporary patch:
   - `a11y-sidebar.test.tsx` ran to completion and surfaced real accessibility failures instead of hanging.
   - `a11y-api-keys.test.tsx` passed.
   - `App.test.tsx` ran to completion and surfaced one separate stale-UI regression instead of hanging.
   - the full Linux `npm run test:unit` completed green.

### Why the upstream/tooling hypotheses were rejected

- `pool: "threads"` vs `pool: "forks"` was tested on isolated Linux runs and both still hung before the local code fix.
- The Ubuntu runner image changed on April 21, 2026, but the same hang reproduced in a local Linux Playwright container, so the runner image was not sufficient to explain it.
- The task brief mentioned Vitest `1.x`, but the current repo was already on `vitest 3.2.4`, so the `1.x` release notes were informative background, not a direct match.

## Hypothesis For Hang #2 (Playwright Click) With Evidence

### Final diagnosis

The Playwright failure was a stale smoke test, not a backend-readiness race.

`SensitivityOverview.tsx` now puts report export actions inside a hidden menu:

- the visible control is `Export`
- `Export Markdown` and `Export HTML` live inside `#report-export-menu`
- the menu is hidden until `exportMenuOpen` becomes `true`

The smoke spec still clicked `Export Markdown` and `Export HTML` directly without opening the menu first.

### Evidence chain

1. The failing GH Actions line was the direct click on `Export Markdown`, after the app had already:
   - loaded successfully
   - finished analysis
   - rendered `Deterministic experiment design`
2. The current component code in `SensitivityOverview.tsx` shows:
   - a dedicated `Export` button
   - submenu buttons hidden behind `display: exportMenuOpen ? "grid" : "none"`
3. After updating the smoke spec to:
   - click `Export`
   - wait for `Export Markdown` / `Export HTML` to become visible
   - then click the submenu entry
   the Playwright smoke run passed locally through `scripts/run_frontend_e2e.py`.

## Proposed Fix Path For Each, Ranked By Confidence

### Hang #1 (Vitest unit)

1. High confidence: make the `SidebarPanel` comparison-selection effect idempotent and stop using invalid listbox semantics that surfaced once the hang was removed.
2. Medium confidence: restore the per-project `Compare` button that the store logic still supported but the sidebar UI no longer rendered.
3. Low confidence / not needed: change Vitest pool settings or pin different Vitest versions.

### Hang #2 (Playwright click)

1. High confidence: update `e2e-smoke.spec.ts` to open the `Export` menu first and assert submenu visibility before clicking.
2. Low confidence / not needed: alter backend startup timing in `run_frontend_e2e.py`.
3. Low confidence / not needed: change Chromium flags or headless settings.

## Rejected Options And Why

- `vitest-axe` quarantine or test deletion: rejected because the render loop reproduced without `axe`.
- Global Vitest pool/config changes: rejected because isolated Linux runs still hung in both `threads` and `forks` before the local component fix.
- Blaming Node 22 or Ubuntu 24.04 image alone: rejected because the same render loop reproduced in a local Linux container.
- Playwright readiness sleeps: rejected because the failing click happened after analysis output was already visible.
- Re-disabling frontend unit tests on Ubuntu: rejected because the root cause was local and fixable.
