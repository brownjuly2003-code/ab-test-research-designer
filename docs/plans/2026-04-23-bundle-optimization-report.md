# Bundle Optimization Report

## Summary

- Frontend locales were moved from `app/frontend/src/i18n/*.json` to `app/frontend/public/locales/*.json`.
- `app/frontend/src/i18n/index.ts` now lazy-loads locale bundles over `/locales/{lng}.json`, preloads only the initial language, and keeps fallback to `en`.
- `app/frontend/vite.config.ts` now emits stable vendor chunks for React, i18n, and Zustand.
- Main bundle budget target is met with large margin: `247.88 kB gzip -> 122.18 kB gzip`.

## Bundle Sizes

### Before

- Main JS: `assets/index-*.js` -> `851.86 kB raw`, `247.88 kB gzip`
- `assets/CartesianChart-*.js` -> `355.69 kB raw`, `106.33 kB gzip`
- `assets/ComparisonDashboard-*.js` -> `39.20 kB raw`, `11.19 kB gzip`
- `assets/PosteriorPlot-*.js` -> `15.62 kB raw`, `5.76 kB gzip`
- `assets/PowerCurveChart-*.js` -> `3.97 kB raw`, `1.56 kB gzip`
- `assets/SequentialBoundaryChart-*.js` -> `2.08 kB raw`, `0.91 kB gzip`
- `assets/LineChart-*.js` -> `4.62 kB raw`, `1.93 kB gzip`
- `assets/WebhookManager-*.js` -> `10.14 kB raw`, `2.64 kB gzip`
- `assets/ApiKeyManager-*.js` -> `6.46 kB raw`, `2.08 kB gzip`

### After

- Main JS: `assets/index-CN1OTjcd.js` -> `445.73 kB raw`, `122.18 kB gzip`
- `assets/vendor-i18n-CbAhzFG_.js` -> `63.55 kB raw`, `21.08 kB gzip`
- `assets/vendor-react-DEzZDo-A.js` -> `3.66 kB raw`, `1.39 kB gzip`
- `assets/vendor-state-DbJSIkhz.js` -> `0.66 kB raw`, `0.41 kB gzip`
- `assets/CartesianChart-DCN3aMQR.js` -> `355.73 kB raw`, `106.36 kB gzip`
- `assets/ComparisonDashboard-CvXz6hS0.js` -> `39.31 kB raw`, `11.25 kB gzip`
- `assets/PosteriorPlot-H2LXTtxZ.js` -> `15.73 kB raw`, `5.81 kB gzip`
- `assets/PowerCurveChart-DMkPh0w1.js` -> `4.07 kB raw`, `1.61 kB gzip`
- `assets/SequentialBoundaryChart-Dzyn0bkt.js` -> `2.18 kB raw`, `0.97 kB gzip`
- `assets/LineChart-JjK_dXED.js` -> `4.63 kB raw`, `1.94 kB gzip`
- `assets/WebhookManager-CvGeAmWW.js` -> `10.25 kB raw`, `2.69 kB gzip`
- `assets/ApiKeyManager-TpwB5ndC.js` -> `6.57 kB raw`, `2.13 kB gzip`

## Verification

- `npm --prefix app/frontend exec tsc -- --noEmit -p .` -> pass
- `npm --prefix app/frontend run test:unit` -> pass
- `npm --prefix app/frontend run build` -> pass
- Static preview + Playwright locale check -> pass
  - initial locale requests: only `http://127.0.0.1:4173/locales/en.json`
  - after switching to French: `http://127.0.0.1:4173/locales/fr.json` loaded on demand

## Blockers Outside Task Scope

- `cmd /c scripts\verify_all.cmd --with-e2e` is blocked before frontend/e2e/smoke completion by unrelated dirty-tree backend changes:
  - `app/backend/app/repository.py`
  - `app/backend/app/config.py`
  - `app/backend/tests/test_config.py`
  - `app/backend/tests/test_postgres_backend.py`
- Current failure:
  - `AttributeError: type object 'ProjectRepository' has no attribute '_create_history_tables'`
- Because backend startup fails, these commands are also blocked for reasons outside this bundle task:
  - `python scripts/run_frontend_e2e.py --skip-build`
  - `python scripts/run_local_smoke.py --skip-build`
  - `python scripts/run_lighthouse_ci.py`

## Notes

- `app/backend/app/frontend_routes.py` did not need changes: it already serves arbitrary files from `dist`, so `/locales/*.json` works once Vite copies `public/locales` into `dist/locales`.
- To keep `vitest run` stable under normal parallelism, several long-running frontend tests were given larger per-test timeouts; no test behavior or assertions were relaxed.
