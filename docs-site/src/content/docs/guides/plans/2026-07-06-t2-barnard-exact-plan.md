---
title: "T2 — Barnard's unconditional exact test (`metric_type=\"barnard_exact\"`)"
---

# T2 — Barnard's unconditional exact test (`metric_type="barnard_exact"`)

Un-defers the 5.3 deferral on explicit request. The 5.3 module was designed for exactly this
addition ("one ``T`` statistic + a dispatch branch"); the shared nuisance-supremum machinery,
the size cap and the exact-card response assembly are all reused unchanged.

## Shape

- **Stats** (`stats/unconditional_exact.py`): `_pooled_wald_z` (Barnard's ordering statistic) +
  `_barnard_two_sided_p_value` + `barnard_exact_test`. Two-sided convention differs from Boschloo's:
  the nuisance-supremum is taken over the ``|Z| >= |Z_obs|`` set directly (scipy's Barnard
  convention), not the doubled smaller one-sided supremum (scipy's Boschloo convention). Module
  docstring updated — the "why not Barnard" deferral note is now the Boschloo-vs-Barnard comparison.
- **Service/schema:** `barnard_exact` joins the `ResultsRequest.metric_type` literal, dispatches to
  `_analyze_barnard_exact` (same `MAX_UNCONDITIONAL_EXACT_TOTAL=200` cap → 400 above it; same
  `_binary_exact_response` card: Newcombe CI, mid-p OR CI, descriptive power).
- **Frontend:** one registry row in `observedResultsShared.ts` (the registry was built so an
  analyzer is a single entry) + the explicit binary-form unions. The hint honestly says Barnard does
  **not** dominate Fisher (unlike Boschloo) and recommends Boschloo unless Barnard's ordering is
  specifically needed. i18n ×7 both stacks; contract + API.md regenerated.

## Verification

- Freeze re-run before implementation (`scratchpad/verify_barnard_boschloo_gtest.py`, restored from
  the 5.3 wip commit `dae0c7a1`): stdlib reference vs `scipy.stats.barnard_exact` max diff 2.4e-10
  across beats-Fisher, asymmetric, zero-cell, empty-margin and all-success tables; worst-case at the
  cap 0.11 s.
- Discriminating pin: asymmetric 2/8 vs 11/25 → Barnard 0.371643 vs Boschloo 0.379091 — proof the
  two orderings are genuinely different analyzers, not aliases (frozen in both stats and HTTP tests).
- +13 backend tests (stats: scipy pins, ordering divergence, arm-swap symmetry, empty margin,
  ordering statistic, MC type-I control; HTTP: round-trip, RU localization, 422/400) and +2 frontend
  registry tests; existing registry expectations extended.
- Live uvicorn round-trip: frozen p-values reproduced end-to-end, RU interpretation, 400 at the cap.
