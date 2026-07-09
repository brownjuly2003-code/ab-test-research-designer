---
title: "T1 — Post-hoc ratio analyzer (`POST /api/v1/results/ratio`)"
---

# T1 — Post-hoc ratio analyzer (`POST /api/v1/results/ratio`)

Closes the last real gap of the 2026-07-02 audit (§4 Tier 2 item 6): ratio plans previously
dead-ended in a disclaimer ("analyzed on the live path only") — the post-hoc form could only offer
conscious approximations (continuous / count). Now the ratio itself is analyzable post-hoc.

## Shape

- **No new math.** The delta method (Deng, Knoblich & Lu, KDD 2018) is already implemented and
  live-verified in `stats/ratio.py` (`compare_ratios`), and the response assembly already exists as
  `build_ratio_results_response` (shared with the live executor). What is new is the *input path*:
  raw per-user (numerator, denominator) pairs → per-arm sufficient statistics → the same functions.
  Post-hoc and live readouts therefore agree by construction (pinned by a test).
- **Why raw pairs, not summaries:** the delta-method variance needs the within-user
  numerator/denominator covariance, which marginal summaries (means/stds) cannot carry. Same reason
  the live path aggregates `sum_xy` per user.
- **Backend:** `RatioArm` (paired-by-index `numerators`/`denominators`, min 2 users) +
  `RatioResultsRequest` (control + treatment arms, alpha) → `analyze_ratio_results` →
  existing `ResultsResponse`. Degenerate comparisons (zero denominator mean, zero pooled variance)
  raise `ValueError` → HTTP 400, mirroring survival/omnibus. Malformed arms (length mismatch,
  non-finite) → 422 at the schema.
- **Frontend:** new `RatioResultsSection` (pattern: `PairedResultsSection` — textarea per array),
  lazy-loaded accordion in the post-hoc stage right after Observed results. The 1.3 ratio
  disclaimer now points at the section instead of declaring a dead end.
- **Bundle:** main chunk had crossed the 500 kB warning limit on main (500.67 kB after the survival
  accordion landed); `CategoricalResultsSection` and `PairedResultsSection` are code-split along
  with the new section → index 491.05 kB.

## Verification

- Freeze before implementation (`scratchpad/verify_ratio_posthoc.py`, not committed): independent
  numpy/scipy delta-method computation on hand-pinned pairs vs `compare_ratios` — agreement ≤1e-10.
  Strong pin (z = 8.7443, CI [0.079005, 0.124654]), weak pin (z = 1.0158, p = 0.309704, not
  significant), degenerate pins.
- 12 new backend tests (`test_ratio_results.py`): frozen numbers, live-path agreement by
  construction, degenerate 400s, schema 422s, Accept-Language localization round-trip.
- 3 new frontend tests (`RatioResultsSection.test.tsx`).
- Live uvicorn round-trip: `/health` 200; freeze numbers reproduced end-to-end; RU degenerate 400
  with localized detail.
