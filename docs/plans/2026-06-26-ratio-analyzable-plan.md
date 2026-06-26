# Ratio metrics: analyzable + delta-method sizing + demo (Phase 3 T3.1, 2026-06-26)

Workstream (2) of Юля's chosen next steps (handoff #20). The ratio live-stats block (F2 delta
method) only renders for an **analyzed** project, but `routes/analysis._build_calculation_payload`
rejected ratio sizing with a 422 — so a ratio experiment could never be analyzed and its live block
never surfaced, and no ratio demo could exist. This makes ratio a first-class, analyzable metric and
adds a ratio demo.

## Approach — delta-method sizing reduces to the continuous formula

A ratio metric `R = E[Y]/E[X]` is sized by the **delta method**: the per-user linearized value
`Y - R*X` is the analysis unit, with mean `R` (the baseline ratio) and a per-user standard deviation
`σ_L`. The two-sample sample-size formula is then exactly the **continuous** one with
`baseline = R`, `std_dev = σ_L`. So ratio sizing reuses the verified continuous math (no new
statistic) and — crucially — produces a *normal* `calculation_result`, leaving the report builder,
the frontend `CalculationsSection`, and the decision service **unchanged**. This is a far smaller
blast radius than threading "optional sizing" through the whole report/UI stack, and it makes ratio
fully first-class (sizing **and** the existing live delta-method analysis).

Verified parity: a ratio payload and the equivalent continuous payload produce an identical planned
sample size (`test_ratio_calculation_reduces_to_continuous_delta_method`).

## Changes

**Backend**
- `schemas/api.py` — `CalculationRequest.metric_type` accepts `"ratio"`; its validator requires a
  positive baseline ratio and a positive `std_dev` for ratio (ratio-specific i18n messages).
- `services/calculations_service.py` — ratio branch reduces to `calculate_continuous_sample_size`
  (baseline `R`, `std_dev` `σ_L`), then restamps `metric_type="ratio"` and the lead assumption to
  name the delta-method linearization. CUPED stays continuous-only; the bayesian path already routes
  non-binary through the continuous formula; sequential is metric-agnostic.
- `routes/analysis.py` — `_build_calculation_payload` no longer blanket-rejects ratio; it raises a
  clear 422 only when a ratio metric is missing `std_dev` (otherwise sizing proceeds like continuous).
- `app/backend/app/i18n/*.json` (7 locales) — `errors.schemas.ratio_baseline_positive` /
  `ratio_std_positive`.

**Demo (data + template)**
- `templates/ad_ctr_ratio.yaml` — new built-in ratio template (Feed Ad Click-Through Ratio:
  `ad_ctr = ad_clicks / ad_impressions`, `R=0.05`, `σ_L=0.09`).
- `startup_seed.py` — adds the ratio demo to `SAMPLE_PROJECTS` (now 4 demo projects). It flows
  through the ordinary analyze path automatically (now that ratio is analyzable).
- `demo_execution.py` — `build_ad_ctr_execution` seeds 1200 users/arm with a per-user variable number
  of impressions (the denominator differs per user — the point of a ratio) and a binomial number of
  clicks at the arm's true rate (control 0.046 → treatment 0.062), so the live ratio comparison
  reads significant, the always-valid view crosses, and the decision reads **ship**.

**Frontend**
- `lib/field-config.ts` — the `std_dev` field is shown for ratio (not just continuous); the
  `baseline_value` / `std_dev` tooltips explain the ratio meaning (baseline ratio R; per-user
  linearized std).
- `hooks/useCalculationPreview.ts` — `canCompute` allows ratio once `R>0` and `std_dev>0`.
- `lib/payload.ts` — `buildCalculationPayload` no longer throws for ratio; it sizes ratio like a
  continuous metric.
- `lib/generated/api-contract.ts` — regenerated (CalculateRequest `metric_type` now includes ratio).

## Verification
- New tests: calculator ratio↔continuous parity + std_dev requirement (`test_calculations.py`);
  `/api/v1/design` sizes ratio (200) and rejects ratio-without-std_dev (422) (`test_api_routes.py`);
  ratio demo builder shape + determinism (`test_demo_execution.py`); the seeded ratio demo's live
  block is significant on the demo path (`test_startup_seed.py`); ratio preview path
  (`useCalculationPreview.test.tsx`).
- Updated stale counts: built-in templates 10→11, demo projects 3→4.
- Gate (serial, Windows): ruff ✓ · mypy `--strict` 67 ✓ · backend suite ✓ · tsc ✓ · targeted vitest ✓
  · vite build 493.59 kB < 500 ✓ · contract `--check` ✓ · locale-content 14 clean ✓.
- End-to-end (seeded demo, SQLite): ratio R control 0.0445 vs treatment 0.0628, p≈0, frequentist +
  always-valid significant, SRM ok, decision = ship, ratio read ~6 ms (fast after the live-read
  indexing work).
