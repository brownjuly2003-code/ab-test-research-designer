# 2026-04-21 A11y Audit Report

## Scope

- Repo: `D:\AB_TEST`
- Frontend gate: `app/frontend/src/test/a11y-wizard.test.tsx`, `app/frontend/src/test/a11y-results.test.tsx`, `app/frontend/src/test/a11y-sidebar.test.tsx`
- Target: WCAG 2.1 AA with `0 critical / 0 serious` axe violations across wizard, results, sidebar, and modal states

## Checked states

- Wizard: `Project`, `Hypothesis`, `Setup`, `Metrics`, `Constraints`, `Review`
- Results shell: `ResultsPanel` with seeded mock analysis data
- Results subsections: `PowerCurveSection`, `SensitivitySection`, `SrmCheckSection`, `ObservedResultsSection`, `AiAdviceSection`, `WarningsSection`, `RisksSection`, `ExperimentDesignSection`, `MetricsPlanSection`, `ComparisonSection`, `SequentialDesignSection`
- Sidebar and modals: `Projects` tab, `System` tab, `TemplateGallery` open, `ShortcutHelp` open, visible project filters, workspace backup controls

## Critical / serious violations fixed

- Rule: `nested-interactive`
  State: `PowerCurveSection`
  File: `app/frontend/src/components/results/PowerCurveSection.tsx:53`
  Change: moved `ChartExportMenu` outside the `role="img"` wrapper so export buttons are no longer nested inside the chart image region.

## Additional hardening applied

- `app/frontend/src/components/TemplateGallery.tsx` and `app/frontend/src/components/ShortcutHelp.tsx`: added focus trap behavior, Escape close handling, and focus return to the opener for dialog flows.
- `app/frontend/src/components/ProjectListFilters.tsx`: grouped filters in a `fieldset` with a hidden legend while keeping explicit label-to-control bindings.
- `app/frontend/src/components/ChartExport.tsx`: exposed a named export-control group and explicit button labels for SVG/PNG actions.
- `app/frontend/src/components/SliderInput.tsx`: added `aria-labelledby`, `aria-valuemin`, `aria-valuemax`, `aria-valuenow`, and `aria-valuetext` on slider controls.
- `app/frontend/src/components/ToastSystem.tsx`: non-error toast items expose polite `status` semantics, error toast items stay `alert`, and the stack keeps the existing live-region anchor used by the current toast lifecycle tests.
- `app/frontend/src/components/ErrorBoundary.tsx` and `app/frontend/src/components/ChartErrorBoundary.tsx`: made fallback alerts focusable and shifted focus to them after render failures.

## Rule exceptions

- None. No axe rules were skipped in the committed a11y tests.

## Verification

- `cd app/frontend && npm.cmd run test:unit` passed with `184` tests green.
- Added `24` accessibility cases covering wizard, results, sidebar, and modal states.
