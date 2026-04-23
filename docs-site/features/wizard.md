# Wizard flow

![Wizard overview](../assets/screenshots/wizard-overview.png)

The wizard keeps experiment setup, metric design, and delivery constraints in one flow so the same payload can drive calculation, design guidance, reports, and saved-project history.

## Steps in the flow

1. Project context: name, domain, platform, market, and business framing.
2. Hypothesis: change description, audience, expected outcome, and what must be validated.
3. Traffic setup: experiment type, randomization unit, traffic split, daily traffic, and variant count.
4. Metrics: primary metric type, baseline, MDE, alpha, power, optional CUPED inputs, guardrails, and secondary metrics.
5. Constraints: seasonality, campaigns, interference risk, deadline pressure, `n_looks`, and analysis mode.
6. Review: a deterministic summary before the run, with the payload normalized exactly as it will hit the API.

![Review step](../assets/screenshots/review-step.png)

## What makes it practical

- Draft restore and autosave keep the current plan in the browser session.
- JSON import/export lets you move a payload between machines or attach it to a review.
- The same saved payload can later power project history, comparison, exports, and reruns.
