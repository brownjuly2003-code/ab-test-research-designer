# ADR 0001 — Practical-significance decision policy

**Status:** Accepted  
**Date:** 2026-07-23  
**Context:** audit F-07 (`audit_gpt_23_07_26.md`)

## Context

The live **Decision Readout** previously treated a statistically significant positive
treatment effect (with sequential / anytime-valid / Bayesian confirmation) as
`ship`. Design `mde_pct` only drove sample-size planning and information fraction —
not the final business decision. With large N, a trivial but significant lift could
therefore ship.

Observed post-hoc `power_achieved` is largely a re-expression of p-value / effect
estimate and is especially misleading for exact and resampling analyzers.

## Decision

1. **Separate statistical evidence from the business verdict.**
   - *Evidence* remains the existing frequentist / Bayesian / sequential / guardrail
     signals (no new test statistics).
   - *Policy* is a versioned rule set that maps evidence → `ship` | `no_ship` |
     `keep_running`.

2. **Policy version `practical_v1`.**
   - Default `minimum_worthwhile_effect` is the design absolute MDE:
     `baseline_value * mde_pct / 100` (same scale as `_expected_absolute_effect`).
   - Ship requires a statistical win **and** practical confirmation:
     CI lower bound of the effect (in analysis units) ≥ MWE.
   - If significant and positive but CI lower &lt; MWE:
     - CI upper &lt; MWE → proven trivial → `no_ship`
       (`below_practical_threshold_proven`).
     - CI still crosses MWE →
       incomplete sample → `keep_running` (`practical_threshold_uncertain`);
       planned sample complete → `no_ship`
       (`statistically_positive_but_below_practical_threshold`).
   - Guardrail breach, SRM, sequential peeking guards, and multi-arm loss rules are
     unchanged and still dominate.

3. **Backward compatibility.**
   - Live readout is re-synthesized on each request; historical *stored analysis*
     snapshots are not rewritten.
   - Response includes `policy.version`, thresholds, and evidence ids so consumers
     can see which rule applied.
   - Designs without usable `mde_pct` / baseline keep statistical-only ship and set
     `policy.require_practical_evidence = false` with reason
     `practical_threshold_unavailable`.

4. **Post-hoc power.**
   - Not used by the decision policy.
   - Decision UI surfaces planned power (from design) and practical-threshold
     evidence; observed `power_achieved` is left on raw analyzer cards as a
     descriptive field, not as ship evidence.

## Consequences

- Trivial-but-significant effects no longer ship under default designs that declare
  an MDE.
- Operators must set a meaningful `mde_pct` (or future explicit MWE override) for
  practical gating.
- Bayesian `P(δ > MWE)` is reserved for a later policy version (needs simulation
  beyond current `P(B>A)`).
