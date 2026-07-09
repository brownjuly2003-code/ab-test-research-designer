---
title: "P1.1 — Fixed-horizon peeking guard in the Decision Readout (audit 2026-07-02, finding A)"
---

# P1.1 — Fixed-horizon peeking guard in the Decision Readout (audit 2026-07-02, finding A)

## Problem

`decision_service._classify` gated wins/losses behind the O'Brien-Fleming boundary only for
sequential designs; for fixed-horizon (`n_looks=1`) it set `boundary_ok = True` unconditionally.
Any moment the operator pressed "Synthesize decision" was treated as "the planned single read":
on the seeded checkout demo (planned ~146.6k/arm, collected ~2k/arm = 1.4% of plan) a z-significant
readout produced **ship / high** while the always-valid (mSPRT) block in the same payload still
included zero. The product warns about peeking two blocks above — and committed it itself.

## Fix (no new statistics)

1. **`live_stats_service._build_sequential_block`** — the fixed-horizon branch now computes the
   planned sample size from the stored design (same `calculate_experiment_metrics` call the
   sequential branch already makes) and reports `planned_sample_size_per_variant` +
   `information_fraction` (`min(1, exposed / planned_total)`). Sizing unavailable (e.g. a legacy
   design without `std_dev`) → both stay `None`. No schema change: `LiveSequentialBlock` already
   carried both fields as optional.
2. **`decision_service`** — new rule: on a fixed-horizon read with a known fraction below
   `DECISION_FIXED_HORIZON_READ_FRACTION = 0.95`, a frequentist-significant result only counts as
   a win/loss when the comparison's `always_valid.is_significant` is `True` (the mSPRT view is the
   only signal in the payload whose guarantee survives early looks). Gated-out significant
   comparisons surface as `fixed_horizon_before_planned_read` (with the fraction) and the verdict
   falls to `keep_running` + `info_fraction_incomplete`. An anytime-valid-confirmed early call
   ships (or no-ships) with an `anytime_valid_confirmed` reason and confidence capped at
   **medium** — the sign is confirmed, but an early effect-size estimate is winner's-curse
   inflated. Fraction `None` (unknown plan) keeps the pre-guard behavior. The 0.95 tolerance
   absorbs read-time filters (dedup, identity resolution, bot exclusions) that legitimately shave
   a few percent off ingested exposures at an honest at-plan read.
3. **Demo seed** — `SAMPLE_PROJECTS` gained per-demo `metrics_overrides` so the showcase verdicts
   stay honest instead of gate-flipped: checkout (`mde_pct` 5→50, plans ~1,770/arm vs ~2,000
   seeded) and pricing (`mde_pct` 4.5→5.5, ~370/arm vs 400 seeded) become *planned* reads that
   ship legitimately; the ratio demo intentionally stays an early read that ships through the
   anytime-valid path (medium confidence); onboarding stays honestly inconclusive. Templates are
   untouched — only the seeded demo instances are retuned.
4. **Frontend** — the live sequential block shows "Fixed-horizon plan: X% of the planned sample
   collected (N/variant)" when the fraction is known; two new decision reason keys + the progress
   key added across all 7 locales.

## Monte-Carlo verification (scratchpad harness, hand-built payloads over the real z + mSPRT stats)

Binary, baseline 5%, mde 5% (planned 122,124/arm), alpha 0.05, seed 20260702:

| Scenario | OLD (no guard) | NEW (guard) |
|---|---|---|
| H0, 8 peeks up to 30% of plan (2,000 sims) — false-ship rate | **0.095** | **0.002** |
| Planned single read, H0 (500 sims) — verdict agreement / ship rate | 500/500 agree · 0.020 | 0.020 |
| Planned single read, H1 = MDE (500 sims) — agreement / ship rate (power) | 500/500 agree · 0.802 | 0.802 |
| True effect 3×MDE — NEW early-ship rate by 30% of plan (500 sims) | — | 0.912 |

Ship verdicts at the planned read are byte-identical (the guard is inert at fraction ≥ 0.95);
peeking false-ships collapse from ~2×alpha to ~0; strong effects still stop early through the
anytime-valid path.

## Tests

- `test_decision_service`: 5 new cases (early z-only read → keep_running with reason + fraction;
  early anytime-valid-confirmed ship / loss with medium confidence; the audit's 1.4% demo-numbers
  scenario verbatim; unknown-plan fallback). Planned-read ship/no-ship/guardrail scenarios now use
  honest designs (`mde_pct=20` → plan ≈ 3.8k/arm ≤ the 5k/arm ingested).
- `test_execution_live_stats`: fixed-horizon block carries planned size + fraction; sizing
  unavailable → both None; decision route test reads at its plan (`mde_pct=100` → ~199/arm).
- `test_startup_seed`: checkout asserts `information_fraction == 1.0` + ship/high; the ratio demo
  asserts ship/medium via `anytime_valid_confirmed`.
- Frontend: `LiveStatsSection` renders the fixed-horizon progress line (new vitest case).
