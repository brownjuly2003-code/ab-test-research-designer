---
title: "P3.3 — Wilson / Newcombe intervals for binary + mid-p CI for Fisher's odds ratio"
---

# P3.3 — Wilson / Newcombe intervals for binary + mid-p CI for Fisher's odds ratio

Audit finding §4 Tier 2 п.5: the binary risk-difference interval was the Wald interval, which
mis-covers at small `n` or extreme rates — exactly the regime the platform's Fisher's-exact analyzer
targets. And Fisher's odds ratio was reported with no interval at all (only a point estimate, with the
risk-difference CI left on the normal approximation). This slice is a **quality** upgrade (not new
breadth): swap the Wald difference interval for Newcombe's hybrid-score method, and complete the exact
family with a mid-p conditional exact confidence interval for the odds ratio.

## Design decisions

- **Only the interval estimate changes; the test decision does not.** The binary p-value / verdict stay
  on the pooled two-proportion z-test; the Fisher p-value stays the exact conditional test. Newcombe
  replaces only the reported risk-difference CI. Score interval ≠ Wald test, so at the very margin a
  Newcombe CI can disagree with the z-test's significance call — accepted, standard, and the
  interpretation prose reports the interval descriptively (it never couples "excludes zero" to the
  verdict).
- **Newcombe for both the binary z-test path and the Fisher path.** Fisher is used precisely when `n`
  is small / a cell is rare, which is where the score interval most outperforms Wald, so both share the
  helper. Fisher's `power_achieved` stays the large-sample normal approximation (already framed as
  descriptive).
- **mid-p, not the strict Cornfield exact CI, for the odds ratio.** mid-p counts only half the
  probability of the observed table, removing the discreteness-driven over-coverage; it is the natural
  less-conservative completion of the exact family that already powers the p-value. Surfaced as two new
  optional response fields plus one appended interpretation sentence.
- **Additive schema.** `effect_size_ci_lower` / `effect_size_ci_upper` on `ResultsResponse`, both
  `float | None`. `effect_size_ci_upper = None` means unbounded above (+∞); both `None` for every
  non-Fisher analyzer and when no estimable interval exists. No other analyzer touched.

## Statistics (frozen against statsmodels 0.14.6 / scipy 1.17.1 BEFORE coding)

Verification script `scratchpad/verify_wilson_newcombe_midp.py`. The stdlib implementation reproduces
each oracle: Wilson / Newcombe to 1e-9 vs statsmodels, mid-p to ~1e-4 (rel) vs an independent
`scipy.stats.nchypergeom_fisher` bisection. statsmodels / scipy are cross-checked locally, not project
dependencies, so the numbers are frozen into the tests.

- **Wilson score interval** (single proportion), `stats/binary.wilson_score_interval`:
  `center = (p̂ + z²/2n)/(1 + z²/n)`, `half = z/(1+z²/n)·√(p̂(1−p̂)/n + z²/4n²)`.
  Reference `statsmodels.stats.proportion.proportion_confint(method="wilson")`. Source: Wilson (1927).
  Frozen 95 %: 48/80 → (0.4904546501, 0.7003817240); 0/20 → (0.0, 0.1611251581);
  1/100 → (0.0017674321, 0.0544861962); 531/1000 → (0.5000102484, 0.5617524926).
- **Newcombe difference** (`p1 − p2`), `stats/binary.newcombe_difference_interval` — MOVER on the two
  Wilson intervals `(l_i, u_i)`:
  `lower = (p̂1−p̂2) − √((p̂1−l1)² + (u2−p̂2)²)`, `upper = (p̂1−p̂2) + √((u1−p̂1)² + (p̂2−l2)²)`.
  Reference `confint_proportions_2indep(method="newcomb", compare="diff")`. Source: Newcombe (1998)
  method 10. Published worked example 56/70 vs 48/80 (0.8 vs 0.6) → (0.0524314724, 0.3338726540),
  reproducing Altman "Statistics with Confidence". Antisymmetric under group swap.
- **mid-p conditional OR CI**, `stats/fisher_exact.fisher_exact_odds_ratio_midp_ci` — the control-success
  cell `a` follows Fisher's noncentral hypergeometric law with odds ratio `ψ`; solve
  `P_{ψ_L}(A>a) + ½P_{ψ_L}(A=a) = α/2` (lower) and `P_{ψ_U}(A<a) + ½P_{ψ_U}(A=a) = α/2` (upper) by
  log-odds bisection. Reference: independent `scipy.stats.nchypergeom_fisher` bisection. Sources:
  Agresti CDA §3.5 (mid-p); Vollset (1993); Fay (2010, `exact2x2`). Frozen 95 %:
  [[3,1],[1,3]] → (0.310055, 308.556772); [[8,2],[1,5]] → (1.342002, 526.395203);
  [[10,40],[2,48]] → (1.344810, 41.618450); boundary [[10,0],[3,5]] → (2.358171, +∞). Each mid-p
  interval sits strictly inside the corresponding strict Cornfield exact interval.

Edge behaviour: `lower = 0.0` when the observed cell sits at the low edge of its support;
`upper = None` (+∞) at the high edge (the standard empty-off-diagonal case). Returns `None` for a
degenerate margin (empty success/failure column) or when the conditional support exceeds
`MAX_FISHER_EXACT_CI_SUPPORT = 20_000` (large-sample regime — the exact CI is skipped, not enumerated
at length; the p-value stays exact over the same support).

## Files

Backend:
- `app/stats/binary.py` — NEW `wilson_score_interval`, `newcombe_difference_interval` (sourced docstrings).
- `app/stats/fisher_exact.py` — NEW `fisher_exact_odds_ratio_midp_ci` + `MAX_FISHER_EXACT_CI_SUPPORT`.
- `app/services/results_service.py` — `_analyze_binary` / `_analyze_fisher_exact` use Newcombe; Fisher
  adds the mid-p OR CI and appends the interpretation sentence.
- `app/schemas/api.py` — `ResultsResponse` gains `effect_size_ci_lower` / `effect_size_ci_upper`.
- i18n `app/i18n/{en,ru,de,es,fr,zh,ar}.json` — NEW `results.fisher_exact.odds_ratio_midp_ci` (×7).

Frontend:
- `app/frontend/src/lib/generated/api-contract.ts` — regenerated (2 fields on `ResultsResponse`).
- `app/frontend/src/lib/types.ts` — `ResultsAnalysisResponse` gains the two fields.
- `app/frontend/src/components/results/internal/ObservedResultsView.tsx` — the effect-size card shows
  the odds-ratio interval `[lower, upper]` (∞ when unbounded), reusing the existing `ciLabel` key.

Tests:
- `app/backend/tests/test_binary_intervals.py` — NEW: Wilson & Newcombe vs frozen references + structure.
- `app/backend/tests/test_fisher_exact.py` — NEW mid-p block (frozen refs, brackets sample OR, inside the
  strict exact interval, unbounded edge, reciprocal-under-swap, degenerate/too-wide → None, invalid alpha).
- `app/backend/tests/test_results_service.py` — binary Newcombe interval integration + Fisher OR-CI fields
  and interpretation prose (bounded & unbounded cases).
- `app/frontend/src/components/results/__tests__/ObservedResultsSection.test.tsx` — the Fisher card renders
  the mid-p interval.

## Verify

- Focused backend suites + full gate (ruff scoped to `app/backend/app scripts`, mypy `--strict`, full
  pytest, contract `--check`, locale, full vitest, vite build < 500 kB).
- CIs cross-checked against published examples (Newcombe 1998 / Altman 56-70 vs 48-80; Wilson 1927) and
  independent scipy/statsmodels oracles frozen into the tests.
