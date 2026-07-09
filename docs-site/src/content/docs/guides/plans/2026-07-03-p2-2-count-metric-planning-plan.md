---
title: "P2.2 — Count / rate as a plannable metric type in the wizard"
---

# P2.2 — Count / rate as a plannable metric type in the wizard

## Goal

Close audit `audit_fable_02_07_2026.md` §4 Tier 1 п.4: a count / rate metric can be *analyzed*
post-hoc (the shipped exact Poisson rate test) but cannot be *planned* — the wizard only offers
binary / continuous / ratio. P2.1 already landed the sizing math and the service routing
(`metric_type="count"` → `calculate_poisson_rate_sample_size`, keyed on `exposure_per_user`), so
this increment is purely the last mile: expose count in the schema and the wizard, and derive the
duration from the per-user exposure. No new statistics.

## What P2.1 already shipped (consumed unchanged here)

- `stats/poisson_rate.calculate_poisson_rate_sample_size(baseline_rate, mde_pct, alpha, power,
  exposure_per_user, variants_count)` — returns `sample_size_per_variant` (users) and honest
  assumptions narrating the event / exposure budget.
- `services/calculations_service.calculate_experiment_metrics`: `metric_type == "count"` branch
  dispatches to the Poisson sizing, reading `payload.get("exposure_per_user") or 1.0`, and the shared
  duration/result assembly already turns `sample_size_per_variant` into an accrual duration.
- Service-level tests `test_count_metric_routes_to_poisson_rate_sizing` /
  `test_count_metric_honors_exposure_per_user`.

So `sample_size_per_variant = ceil(exposure_per_variant / exposure_per_user)` — the duration is
already "by exposure": `exposure_per_user` is the bridge from the event/exposure budget to a user
count, and the existing `estimate_experiment_duration_days` converts that user count to days at the
daily-traffic rate. The remaining work is to let a user *reach* that path.

## Design decisions

- **`metric_type` gains `"count"`** on both `CalculationRequest` and `MetricsConfig` (wizard preview
  `/calculate` and full `/analyze` plan identically), plus a new optional field
  `exposure_per_user: float | None = Field(default=None, gt=0)` on both. `None` → the service
  defaults it to `1.0` (the user *is* the exposure unit). `baseline_value` for count is the baseline
  **event rate per exposure unit** (events per user at unit exposure), validated `> 0` with a new
  i18n error `errors.schemas.count_baseline_positive`.
- **No `planned_test` selector for count.** Count has exactly one plan (the conditional Poisson rate
  test); `PLANNED_TESTS_BY_METRIC_TYPE` deliberately omits count so any explicit `planned_test` on a
  count metric 422s, while `planned_test=None` resolves to `poisson_rate` at the service. `std_dev`
  and CUPED do not apply (CUPED is gated to the `z_test` continuous plan; the Bayesian companion
  already excludes count).
- **Frontend follows the ratio precedent for i18n.** Ratio's own wizard strings (the `ratio`
  metric-type option, `numerator_metric_name` / `denominator_metric_name`) ship via the field-config
  `defaultValue` fallback, not `wizardDraft.*` locale keys. Count does the same — the option label
  "Count / rate" and the `exposure_per_user` label / help text fall back to English in non-English
  locales, exactly like ratio today. This keeps the locale bundles at key-parity and defers a proper
  wizard-label RU sweep to task 4.4 (which already owns that). The English tooltip lives in
  `FIELD_TOOLTIPS`.

## Tasks

- [x] 1. Backend schema: `metric_type += "count"` and `exposure_per_user` on `CalculationRequest`
      and `MetricsConfig`; count baseline validator; `routes/analysis._build_calculation_payload`
      passes `exposure_per_user`; `errors.schemas.count_baseline_positive` ×7 locales.
      → Verified: `/calculate` + `/design` count round-trip, 422 on baseline ≤ 0, exposure scaling.
- [x] 2. Contract regen: `generate_frontend_api_types.py` + `generate_api_docs.py`. → `--check` clean.
- [x] 3. Frontend: `field-config.ts` count option + `exposure_per_user` field (visible when count) +
      tooltip + baseline help text mentions count; `types.ts` `exposure_per_user`; `payload.ts`
      initial state / metric-type-switch reset (clear std_dev+CUPED for count like binary) /
      `buildApiPayload` numeric coercion / `buildCalculationPayload` pass-through; `canCompute` count
      branch; `validation.ts` count (and ratio) branches. → vitest + tsc green.
- [x] 4. Tests: backend HTTP (+5) + frontend count end-to-end (payload build, canCompute preview).
- [ ] 5. Full gate (ruff · mypy --strict from ROOT · backend pytest 982✓ · contract --check ×2 · locale ·
      tsc 0 · full vitest · vite build 490.75kB<500) → PR → full CI → merge → tracker + handoff updated.

## Done when

- A count experiment is planned end-to-end through the wizard (metric type Count / rate, baseline
  rate, exposure per user → sample size + duration), on both the live preview and the full analyze
  path, with the Poisson event/exposure budget shown in the assumptions.
- Non-positive count baseline 422s with a translated message. CI fully green, squash-merged to main.
