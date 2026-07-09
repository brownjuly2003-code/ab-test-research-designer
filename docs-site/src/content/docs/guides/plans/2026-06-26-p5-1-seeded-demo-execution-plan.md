---
title: "Plan — P5.1 Seeded demo execution data (Phase 5 / \"Подача-демо\" → 9.8)"
---

# Plan — P5.1 Seeded demo execution data (Phase 5 / "Подача-демо" → 9.8)

## Goal
On the **default demo path** (deployed Space with `AB_SEED_DEMO_ON_STARTUP=true`), the live
execution surface — always-valid (mSPRT), sequential, decision-readout, guardrail, holdout,
post-stratification, CUPED, identity resolution, bot/fraud filter, late/out-of-order events —
must be **visible without any manual ingest**. Today the startup seed creates only *design*
demo projects (no exposures/conversions), so every live-stats block reads `unavailable`.

## Constraint discovered (scoping)
`LiveStatsSection` + `DecisionReadoutSection` render only when the loaded project has an
**analysis report** (`ResultsPanel`: `displayedAnalysis?.report`). They are **not** admin-gated
— they sit in the public results view. A **ratio** experiment cannot be analyzed
(`routes/analysis._build_calculation_payload` raises 422 — ratio sizing is a separate sub-phase,
Phase 3 T3.1) and `CalculationsSection` requires non-optional `int` sizing fields, so a ratio
demo's live-stats **cannot surface in the UI** until ratio is analyzable.
→ **Ratio is out of scope here** (deferred to T3.1). This PR seeds the three *analyzed* demos,
surfacing **10 of 11** live-stats capability blocks on the real public path. Ratio block is the
one remaining; it unlocks once T3.1 makes ratio analyzable.

## Approach (no schema / no API / no contract / no frontend changes)
New module `app/backend/app/demo_execution.py`:
- Deterministic per-demo builders (`random.Random(fixed_seed)` — reproducible, test-assertable).
  Metric names are **read from the stored project payload**, not hardcoded, so the seed stays in
  sync with the templates.
- `seed_demo_execution(repository, demo_ids)` orchestrator: idempotent (skips a demo whose
  `get_ingestion_summary().exposures_total > 0`), ingests via existing `repository.record_*`.

`startup_seed.seed_demo_workspace` resolves the three demo project ids by name and calls
`seed_demo_execution` on them **every startup** (idempotent), so the upgrade path (demos already
exist from an old snapshot, but lack execution data) tops up correctly.

### Demo data (deterministic, statistically coherent, honest)
- **Demo - Checkout Conversion** (binary `purchase_conversion`, base 0.042) — flagship, full surface:
  - 2000+2000 balanced exposures (SRM ok) · clear uplift 0.043→0.062 (always-valid crosses,
    decision = **ship**, Bayesian P(B>A)≈1)
  - guardrail "Payment error rate" (binary) + "Refund value" (continuous): both arms ≈ equal → **ok**
  - holdout 400 (vi=−1) at baseline → pooled-treated-vs-holdout cumulative **+effect**
  - strata `device` ∈ {ios, android}, both arms populated → post-stratified estimate
  - 60 anonymous→canonical identity links → resolution **active** (no SRM inflation)
  - 8 manual deny-list (`internal_qa`) + 1 rate-spike bot (>100 conv events) → exclusions **active**
  - ~12 late + ~3 out-of-order conversions (occurred_at past 14-day horizon) → event-timing
- **Demo - Pricing Sensitivity** (continuous `avg_order_value`, base 45.0, std 12) — variance toolkit:
  - 1500+1500 exposures · one outcome per exposed user · treatment +≈3.0
  - pre-period covariate correlated ρ≈0.55 → **CUPED variance reduction** > 0
  - strata `segment` ∈ {new, returning} → post-stratified estimate on continuous
  - guardrail "Purchase conversion" (binary) ≈ equal → ok
- **Demo - Onboarding Completion** (binary `onboarding_completion_rate`, base 0.34) — honest variety:
  - 1200+1200 exposures · small effect 0.34→0.355 (z≈0.9, n.s.) → decision = **keep_running**,
    always-valid still accruing (shows the "monitoring, no verdict yet" state)

## Tests
- `test_startup_seed.py` — keep the 3-project + analysis + export contract; **add**: each seeded
  demo now carries execution data and `/live-stats` returns the expected block statuses
  end-to-end through the app.
- `test_demo_execution.py` (new) — builder determinism, idempotent re-seed (no double count),
  and the intended live-stats block statuses (checkout ship + guardrail ok + holdout available +
  stratified available + identity active + exclusions active + event-timing late>0; pricing CUPED
  reduction>0 + stratified available; onboarding keep_running).

## Verify
- Serial Windows gate: ruff · mypy --strict · backend pytest · contract `--check` · locale.
- Playwright: seed a local app, load a demo, confirm the live-stats blocks render (no console errors).
- Push → PR → full CI (incl. verify-postgres — the seed runs on PG too via backend-agnostic
  `record_*`) → merge by green CI (autonomy mandate). **Deploy held until "задеплой".**

## Out of scope (follow-ups)
- **Ratio block on the demo** → needs T3.1 (ratio analyzable: delta-method sizing or a sizing-free
  report with optional `CalculationsSection` ints). Then add a ratio demo + template.
- Phase 6 T6.1/T6.2 eval re-assessment (separate step this session).
