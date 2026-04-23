# Locales FR / ZH / AR Report

## Coverage

- Frontend leaf-key count: `en=913`, `fr=913`, `zh=913`, `ar=913`
- Backend leaf-key count: `en=235`, `fr=235`, `zh=235`, `ar=235`
- Placeholder mismatch check: `0` mismatches for `fr`, `zh`, and `ar` versus `en` in both frontend and backend
- Note: the active `en.json` baseline on `2026-04-23` already contains `913` frontend leaf keys, so the older CX spec number `887` is stale for the current tree

## Angle Markers

- No `<angle>` review markers remain in `app/frontend/src/i18n/{fr,zh,ar}.json`
- No `<angle>` review markers remain in `app/backend/app/i18n/{fr,zh,ar}.json`

## RTL Audit

- Replaced with logical properties:
- `app/frontend/src/styles/layout.css`: `left` -> `inset-inline-start`
- `app/frontend/src/styles/components.css`: `padding-left` -> `padding-inline-start`
- `app/frontend/src/components/Accordion.module.css`: `text-align: left` -> `start`
- `app/frontend/src/components/EmptyState.module.css`: `text-align: left` -> `start`
- `app/frontend/src/components/MetricCard.module.css`: `margin-left` -> `margin-inline-start`
- `app/frontend/src/components/SidebarPanel.module.css`: `left` / `padding-left` -> `inset-inline-start` / `padding-inline-start`
- `app/frontend/src/components/ToastSystem.module.css`: `right` / `border-left` -> `inset-inline-end` / `border-inline-start`
- `app/frontend/src/components/ResultsPanel.module.css`: `border-left*` -> `border-inline-start*`
- `app/frontend/src/components/WizardDraftStep.module.css`: `margin-left` -> `margin-inline-start`
- `app/frontend/src/components/results/WarningsSection.module.css`: `border-left*` -> `border-inline-start*`

### Left As Physical Coordinates

- `app/frontend/src/components/ForestPlot.tsx`: kept `left/right` inline positioning because they encode chart coordinates, not page direction
- `app/frontend/src/components/ComparisonDashboard/DistributionView.tsx`
- `app/frontend/src/components/SequentialBoundaryChart.tsx`
- `app/frontend/src/components/PowerCurveChart.tsx`
- `app/frontend/src/components/PosteriorPlot.tsx`

These remaining `left/right` hits are Recharts margin values or plot-coordinate positioning and were intentionally not converted to logical properties.

## A11y

- `npm run test -- src/i18n.test.tsx src/test/a11y-locales.test.tsx src/test/a11y-rtl.test.tsx` passed
- `src/test/a11y-rtl.test.tsx` confirms `document.documentElement.lang === "ar"` and `document.documentElement.dir === "rtl"`
- `axe` reported `0` critical/serious violations in the targeted `de`, `es`, and `ar+rtl` switcher renders
- Vitest/jsdom still prints the known `HTMLCanvasElement.getContext()` warning during axe runs; it does not fail the suite
