"""Cox proportional-hazards model for the treatment effect — a hazard ratio with its Wald inference.

Scope (deliberate): the A/B-relevant Cox model with a **single binary covariate**, the treatment
indicator. That makes the partial likelihood one-dimensional, so the fit is a scalar Newton-Raphson
— no matrix algebra, no feature framework — while delivering exactly what the log-rank test cannot:
an **effect size**. The log-rank family (``stats.survival``) answers "do the survival curves
differ?"; the Cox hazard ratio answers "by how much" — ``HR = h_treatment(t) / h_control(t)``, the
constant multiplicative effect on the hazard under the proportional-hazards assumption
(``HR < 1``: treatment reduces the event hazard; ``HR > 1``: increases it).

Ties are handled with the **Efron (1977) approximation** (more accurate than Breslow, and the
default in lifelines / R's ``coxph``). For an event time with death set ``D`` (``|D| = d``), risk
set ``R`` and binary covariate ``x``:

    S0  = Σ_{i∈R} e^{βx_i}      S1 = Σ_{i∈R} x_i e^{βx_i}     (S2 ≡ S1 because x² = x)
    s0d = Σ_{i∈D} e^{βx_i}      s1d = Σ_{i∈D} x_i e^{βx_i}
    denom_l = S0 − (l/d)·s0d,   num_l = S1 − (l/d)·s1d,       l = 0..d−1

    score U(β)      = Σ_{i∈D} x_i − Σ_l num_l / denom_l
    information I(β) = Σ_l [ num_l/denom_l − (num_l/denom_l)² ]

Newton-Raphson from ``β = 0`` (each step ``β += U/I``) converges in a handful of iterations —
the one-dimensional Efron partial log-likelihood is strictly concave wherever both arms remain in
the risk sets. Inference is Wald: ``SE = 1/√I(β̂)``, ``z = β̂/SE``, two-sided p from the normal,
``CI(HR) = exp(β̂ ± z_crit·SE)``. At ``β = 0`` the score statistic ``U²/I`` is the log-rank
statistic up to tie-handling — the family-consistency the tests pin.

Source (verified against the literature at implementation time, not from memory): Cox, "Regression
models and life-tables" (JRSS-B, 1972); Efron, "The efficiency of Cox's likelihood function for
censored data" (JASA, 1977); Therneau & Grambsch, *Modeling Survival Data* ch. 3. Cross-checked
numerically against BOTH ``statsmodels 0.14.6`` ``PHReg(ties="efron")`` (agreement ≤1e-10) and
``lifelines 0.30.3`` ``CoxPHFitter`` (≤3e-7) in ``scratchpad/verify_cox_ph.py`` before this module
was written; the frozen Freireich numbers (β = −1.5721251488, SE = 0.4123967177, HR = 0.207604)
are reproduced by the unit tests. Neither library is a runtime dependency; this module is
stdlib-only and holds pure functions — the response shape is assembled in the service layer.

Explicitly OUT OF SCOPE (documented deferrals): multi-covariate Cox (adjustment / stratification),
time-varying covariates, Breslow ties, baseline-hazard / survival-function estimation,
proportional-hazards diagnostics (Schoenfeld residuals).
"""

import math
from statistics import NormalDist

from app.backend.app.stats.survival import MAX_SURVIVAL_TOTAL, _validate_arm

_STANDARD_NORMAL = NormalDist()

# Newton-Raphson iteration cap. The 1-D Efron partial log-likelihood is strictly concave with a
# bounded maximizer whenever both arms contribute events, so convergence takes ~5 iterations; the cap
# only guards quasi-separated data (one arm's events all precede the other's), where |β̂| → ∞ and the
# fit is declared undefined instead of returning a huge unstable estimate.
_MAX_ITERATIONS = 50
_SCORE_TOLERANCE = 1e-12
# |β| beyond this is numerically indistinguishable from monotone likelihood (quasi-separation):
# HR = e^±30 ≈ 10^±13 carries no usable inference and the Wald SE is meaningless.
_BETA_DIVERGENCE_BOUND = 30.0


def cox_ph_treatment_effect(
    durations_control: list[float],
    events_control: list[bool],
    durations_treatment: list[float],
    events_treatment: list[bool],
    alpha: float = 0.05,
) -> dict[str, float | int | bool] | None:
    """Cox proportional-hazards fit of the treatment indicator: hazard ratio + Wald inference.

    Arms mirror :func:`stats.survival.log_rank_test` (control first). Returns the log hazard ratio
    ``β̂`` (treatment vs control), its standard error, the hazard ratio with its Wald confidence
    interval, the Wald chi-square (``z²``, 1 df) and two-sided p-value, plus per-arm ``n`` / event
    counts. Returns ``None`` when the fit is undefined: no events at all, events in only one arm's
    risk experience (monotone likelihood — the MLE diverges), or a vanishing information.
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    _validate_arm(durations_control, events_control)
    _validate_arm(durations_treatment, events_treatment)
    total = len(durations_control) + len(durations_treatment)
    if total > MAX_SURVIVAL_TOTAL:
        raise ValueError(f"survival total observations exceed the {MAX_SURVIVAL_TOTAL} cap")

    times = [*durations_control, *durations_treatment]
    events = [*events_control, *events_treatment]
    x = [0.0] * len(durations_control) + [1.0] * len(durations_treatment)
    n = len(times)

    event_times = sorted({times[i] for i in range(n) if events[i]})
    if not event_times:
        return None

    # Pre-index the death and risk sets once; they do not depend on β.
    deaths_at = {
        t: [i for i in range(n) if times[i] == t and events[i]] for t in event_times
    }
    risk_at = {t: [i for i in range(n) if times[i] >= t] for t in event_times}

    beta = 0.0
    information = 0.0
    for _ in range(_MAX_ITERATIONS):
        score = 0.0
        information = 0.0
        for t in event_times:
            deaths = deaths_at[t]
            risk = risk_at[t]
            d = len(deaths)
            exp_beta = math.exp(beta)
            treated_risk = sum(1 for i in risk if x[i] == 1.0)
            s0 = (len(risk) - treated_risk) + treated_risk * exp_beta
            s1 = treated_risk * exp_beta
            treated_deaths = sum(1 for i in deaths if x[i] == 1.0)
            s0d = (d - treated_deaths) + treated_deaths * exp_beta
            s1d = treated_deaths * exp_beta
            score += treated_deaths
            for tie_index in range(d):
                fraction = tie_index / d
                denominator = s0 - fraction * s0d
                numerator = s1 - fraction * s1d
                ratio = numerator / denominator
                score -= ratio
                information += ratio - ratio * ratio
        if information <= 0:
            return None
        step = score / information
        beta += step
        if not math.isfinite(beta) or abs(beta) > _BETA_DIVERGENCE_BOUND:
            # Monotone likelihood (e.g. every event in one arm): the MLE diverges.
            return None
        if abs(score) < _SCORE_TOLERANCE and abs(step) < 1e-10:
            break

    standard_error = 1.0 / math.sqrt(information)
    z_statistic = beta / standard_error
    p_value = 2.0 * (1.0 - _STANDARD_NORMAL.cdf(abs(z_statistic)))
    p_value = min(1.0, max(0.0, p_value))
    z_critical = _STANDARD_NORMAL.inv_cdf(1.0 - alpha / 2.0)
    return {
        "log_hazard_ratio": beta,
        "standard_error": standard_error,
        "hazard_ratio": math.exp(beta),
        "hr_ci_lower": math.exp(beta - z_critical * standard_error),
        "hr_ci_upper": math.exp(beta + z_critical * standard_error),
        "z_statistic": z_statistic,
        "wald_chi_square": z_statistic * z_statistic,
        "df": 1,
        "p_value": p_value,
        "is_significant": p_value < alpha,
        "alpha": alpha,
        "n_control": len(durations_control),
        "n_treatment": len(durations_treatment),
        "events_control": sum(1 for e in events_control if e),
        "events_treatment": sum(1 for e in events_treatment if e),
    }
