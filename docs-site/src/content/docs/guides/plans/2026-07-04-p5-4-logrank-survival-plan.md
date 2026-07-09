---
title: "P5.4 — Two-arm log-rank test + Kaplan-Meier estimator (survival / time-to-event)"
---

# P5.4 — Two-arm log-rank test + Kaplan-Meier estimator (survival / time-to-event)

Audit ref: `audit_fable_02_07_2026.md` §4 Tier 3 item 9 + P5 table row 5.4 ("Log-rank / survival —
F5 xhigh, только если появится спрос"). Model: Opus 4.8. Date: 2026-07-04.

This is the **scoped core** of the survival class — the single largest separate class flagged by the
audit. It closes the breadth item honestly with a well-bounded increment, NOT an unbounded survival
suite. New input shape (per-subject event time + censoring flag, two arms) → **new section**, mirroring
the 3.1 paired and 3.2 omnibus precedents (each added a whole new section for a new input shape), not a
toggle on an existing analyzer.

## 1. Freeze (BEFORE production code)

Reference oracle: `scratchpad/verify_logrank_km.py` — a fully independent from-scratch implementation
of KM + Greenwood + log-rank, cross-checked against:

* the **Freireich et al. (1963) leukemia remission dataset** (6-MP vs placebo, 21 patients per arm) —
  the canonical log-rank textbook example (Klein & Moeschberger "Survival Analysis"; Collett).
* **scipy.stats.chi2.sf(x, 1)** for the p-value (independent chi-square tail).
* lifelines was attempted in a throwaway target dir but the install hit a network reset; the published
  Freireich number + scipy + the by-hand small example are the three independent confirmations instead.

**Frozen numbers** (copied verbatim into `tests/test_survival.py`):

Freireich log-rank (arm 1 = 6-MP treatment, arm 2 = placebo):
* O1 = 9, E1 = 19.2505009480, O2 = 21, E2 = 10.7494990520, V = 6.2569605737
* **chi-square = 16.7929409892** (published ≈ 16.79)
* **p = 4.168809e-05** (scipy chi2.sf, 1 df; published ≈ 4.2e-5)

Freireich Kaplan-Meier, 6-MP (treatment) arm survival S(t):
* S(6)=0.857143, S(7)=0.806723, S(10)=0.752941, S(13)=0.690196, S(16)=0.627451, S(22)=0.537815,
  S(23)=0.448179 (matches Klein & Moeschberger exactly); SE(6)=0.076360 (Greenwood).

Small hand-computable example — arm1 `[(1,event),(3,cens),(5,event)]`, arm2 `[(2,event),(4,cens),(6,event)]`:
* O1=2, E1=1.4, V=0.74, **chi-square = 0.4864864865**, p = 0.4854988026
* KM arm1: S(1)=0.666667 (Greenwood var=0.074074, SE=0.272166), S(5)=0 (variance undefined at S=0)

Degenerate: both arms fully censored → no events → V=0 → chi-square undefined → service 400.

## 2. Scope + explicit deferrals

**In scope (this PR):**
1. Kaplan-Meier survival estimator per arm: S(t)=Π(1−dᵢ/nᵢ) over event times, Greenwood variance for
   pointwise CIs; return step points (time, survival, at_risk n, n_events, CI) per arm.
2. Two-arm log-rank (Mantel-Cox) test: pooled ordered event times, hypergeometric risk-set
   expectation/variance, χ²=(O₁−E₁)²/V ~ chi-square 1 df; report χ², p, O/E per arm.

**Explicitly deferred (documented, NOT this PR)** — mirrors how 2.1/3.x scoped assumptions:
* Cox proportional-hazards regression
* Parametric survival (Weibull / exponential)
* >2-arm log-rank / trend tests
* Sample-size / power FOR survival endpoints (planning side — a separate sizing task)
* Weighted log-rank (Gehan-Wilcoxon / Fleming-Harrington)
* Competing risks
* Median survival CIs, restricted mean survival time, hazard-ratio estimation

## 3. Design

* **Backend** `app/backend/app/stats/survival.py` — stdlib-only, pure functions:
  `kaplan_meier_estimate(times, events)` → list of step points; `log_rank_test(t1,e1,t2,e2, alpha)`
  → dict or `None` (None when V=0 / no events). Reuses `srm.chi_square_cdf` for the χ²(1) tail
  (existing chi-square tail — no second implementation). Greenwood needs only `math`.
* **Schemas** `SurvivalArm` (parallel arrays `durations: list[float]` ≥0 + `events_observed: list[bool]`
  of equal length), `SurvivalResultsRequest` (control_arm + treatment_arm + alpha),
  `SurvivalResultsResponse` (log-rank χ²/df/p/verdict + O/E per arm + `SurvivalCurvePoint[]` per arm).
  Validation: equal-length arrays, non-empty, non-negative finite times, cap total N with an i18n
  over-cap message (`MAX_SURVIVAL_TOTAL`, mirroring the omnibus cap). Single arm / mismatched length →
  422 (pydantic). Degenerate all-censored → V=0 → service raises ValueError → 400.
* **Service** `analyze_survival_results` → interpretation + verdict (curves differ / no evidence of
  difference) via `translate()`, ×7 locales (backend has no EN fallback).
* **Route** `POST /api/v1/results/survival` in `routes/analysis.py`, `Depends(require_auth)`.
* **Frontend** new `SurvivalResultsSection.tsx` + accordion in `ResultsPanel` **posthoc stage**
  (alongside observed/categorical/paired/omnibus). **Lazy-loaded** as its own chunk (bundle ~497 kB,
  tiny headroom). Renders log-rank χ²/p/verdict cards + a Kaplan-Meier step-curve chart for the two
  arms via `recharts` `<Line type="stepAfter">` (already a dependency; SequentialBoundaryChart pattern),
  `role="img"` + `aria-label` for a11y ≥0.9. Parallel-array paste form (durations + 0/1 censor flags).
* **Contract** regen `api-contract.ts`; verify `API.md` via `--check`.
* i18n ×7 both stacks; ru reads as natural Russian survival terminology (кривая выживаемости
  Каплана–Майера, лог-ранговый критерий, цензурирование).

## 4. Verify plan

* Unit tests `test_survival.py`: KM points + Greenwood vs frozen Freireich; log-rank χ²/p vs frozen
  16.7929/4.169e-5; small censored example (O/E/V/χ² + KM S(1)); degeneracy (all-censored → None →
  400; single arm / mismatched → 422). Schema validation. HTTP round-trip (200 + 422 + 400 + over-cap).
* Frontend `SurvivalResultsSection.test.tsx`: renders χ²/p, renders KM curve, i18n presence.
* Full local gate serially (Win): ruff · mypy --strict from ROOT · backend pytest · tsc · vitest
  (throttle maxThreads=2) · vite build <500 · contract --check · api docs --check · locale content.
* LIVE verify against running uvicorn with the Freireich payload → confirm χ²≈16.79 / p / KM points.
