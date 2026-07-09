---
title: "P3.2 — Omnibus analyzers for >2 groups (Welch's ANOVA + Kruskal–Wallis)"
---

# P3.2 — Omnibus analyzers for >2 groups (Welch's ANOVA + Kruskal–Wallis)

Audit finding §4 Tier 1 п.3: multi-variant experiments (A/B/C/…) could be *planned* but the post-hoc
analyzers only compared arms *pairwise* — there was no omnibus "do the groups differ at all?" test.
This slice adds the two standard continuous omnibus tests as a new standalone "multiple groups"
section — one raw-input form feeding two analyzers, mirroring the Categorical (chi-square) precedent
that is itself the omnibus for a contingency table.

## Design decisions

- **New standalone section**, not a toggle inside `ObservedResultsSection`. The observed-results
  toggle offers alternative *two-arm* tests on the same summary/ranked data; an omnibus needs a
  fundamentally different input (a list of ≥ 2 per-group value arrays), so it gets its own
  request/response/endpoint/section — exactly as Categorical and Paired did.
- **One input form for both** analyzers via `test_type ∈ {welch_anova, kruskal_wallis}`: a list of
  groups, each ≥ 2 numeric values.
- **Welch's ANOVA, not classic Fisher ANOVA.** Equal-variance ANOVA is routinely violated across
  experiment arms; Welch's heteroscedastic version holds its nominal level under unequal variances
  and is the safer default. (Note: Welch does NOT reduce to classic ANOVA for k ≥ 3 — its correction
  term is non-zero — so the reference is statsmodels, not `f_oneway`.)
- **Dedicated `OmnibusResultsResponse`** with per-group summaries (means/SDs for Welch,
  medians/mean-ranks for Kruskal–Wallis): a single F/H over ≥ 3 arms otherwise says "something
  differs" without saying which arm, so the summaries make the verdict actionable.
- **stdlib-only, pure functions** in `app/stats/omnibus.py`; response assembled in the service layer.
  Reuses `srm.chi_square_cdf` and a new public `student_t.f_sf` (F-distribution survival via the same
  regularized-incomplete-beta continued fraction the Student-t CDF already uses) — no new special fn.

## Statistics (frozen against scipy 1.17.1 / statsmodels 0.14.6 BEFORE coding)

Verification script `scratchpad/verify_omnibus_vs_scipy.py`. Groups G1/G2/G3 (n = 8/9/7,
heteroscedastic). My hand implementation matched the references to 1e-9.

- **Welch's ANOVA** = `F* = [Σ w_i(x̄_i − x̄*)²/(k−1)] / [1 + 2(k−2)/(k²−1)·S]`, `w_i = n_i/s_i²`,
  `x̄* = Σ w_i x̄_i / W`, `S = Σ (1 − w_i/W)²/(n_i − 1)`; reference `F(k−1, df₂)`,
  `df₂ = (k²−1)/(3S)`. Effect size = descriptive `η² = SS_between/SS_total` on the raw data.
  Reference: `statsmodels.stats.oneway.anova_oneway(use_var="unequal", welch_correction=True)`.
  Frozen: F = 20.6233997113, p = 0.0000860564, df₂ = 13.2250716024, η² = 0.6577832702.
- **Kruskal–Wallis** = pooled midranks; `H = 12/(N(N+1))·Σ R_i²/n_i − 3(N+1)` divided by the tie
  correction `1 − Σ(t_j³−t_j)/(N³−N)`; reference `χ²` on `k−1` df. Effect size `ε² = H/(N−1)`
  (Tomczak & Tomczak 2014). Reference: `scipy.stats.kruskal`.
  Frozen: H = 15.3558529156, p = 0.0004629338, ε² = 0.6676457789; tie case H = 5.4051724138,
  p = 0.0670319299.
- **`f_sf(f, df1, df2)`** = `I_{df2/(df1·f+df2)}(df2/2, df1/2)`; matches `scipy.stats.f.sf` to ~1e-7
  (the incomplete-beta continued-fraction tolerance). Frozen spot checks at (5,2,10)=0.03125,
  (0.5,2,8)=0.6242950770, (1,3,3.5)=0.4883109229, (10,4,20)=0.0001298357.

Degenerate handling: Welch returns `None` (→ 400) when any group has < 2 observations or zero
within-group variance (its weight is infinite); Kruskal–Wallis returns `None` (→ 400) when every
observation is tied (the tie correction collapses to zero).

## Files

Backend:
- `app/stats/omnibus.py` — NEW: `welch_anova_test`, `kruskal_wallis_test` + helpers, sourced docstring.
- `app/stats/student_t.py` — NEW public `f_sf` (F survival, reuses `_betainc_regularized`).
- `app/constants.py` — NEW `MAX_OMNIBUS_GROUPS = 50`.
- `app/schemas/api.py` — NEW `OmnibusResultsRequest` / `OmnibusResultsResponse` / `OmnibusGroupSummary`.
- `app/services/results_service.py` — NEW `analyze_omnibus_results` dispatch + i18n interpretations.
- `app/routes/analysis.py` — NEW `POST /api/v1/results/omnibus`.
- i18n `app/i18n/{7}.json` — `errors.schemas.omnibus_*` + `welch_anova_degenerate` /
  `kruskal_wallis_degenerate`, `results.interpretation.welch_anova` / `kruskal_wallis`,
  `results.effect_size.eta_squared` / `epsilon_squared`, `results.omnibus.verdict_*`.

Frontend:
- `components/results/OmnibusResultsSection.tsx` — NEW (mirrors Categorical/Paired) + `parseGroups`.
- `components/ResultsPanel.tsx` — mount accordion; **lazy-loaded** (own chunk) to keep index.js < 500 kB.
- `lib/generated/api-contract.ts` + `docs/API.md` — contract regen (auto-discovered from OpenAPI).
- `public/locales/{7}.json` — `results.omnibusResults.*` + `results.panel.accordion.omnibusResults`.

Tests:
- `tests/test_omnibus.py` — NEW: stats frozen vs scipy/statsmodels + edge/degenerate guards; `f_sf`
  vs scipy; service rounding + RU-locale; HTTP round-trip per test_type + 422/400 validation.
- `components/results/__tests__/OmnibusResultsSection.test.tsx` — NEW (+ `parseGroups` units).

## Verify

Focused stats suite reproducing frozen scipy/statsmodels numbers · mypy `--strict` (79 files) ·
contract `--check` (regen) · full backend pytest (1028) · full vitest (61/354) · tsc · locale ·
vite build (index 496.49 kB < 500). Live uvicorn curl for both test_types (EN + RU) and the 422/400
guards.
