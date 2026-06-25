MAX_SUPPORTED_VARIANTS = 10

# Upper bound on the number of metric p-values accepted by the multiple-testing endpoint. A real
# experiment tracks a primary plus a battery of secondary and guardrail metrics; 100 is generous
# while still bounding request size.
MAX_SUPPORTED_METRICS = 100

# Eight weeks is the point after which the planner flags long-running experiments.
MAX_RECOMMENDED_DURATION_DAYS = 56

# Upper bound on the number of distinct pre-period covariates multi-covariate CUPED (F3a) regresses
# the outcome on. The normal-equations solve is O(k^3); a handful of covariates is the realistic
# regime, and the cap bounds pathological ingestion. If more distinct names are ingested the lowest
# (sorted) names up to this cap are used and the response flags the truncation.
MAX_CUPED_COVARIATES = 10

DEFAULT_CORS_METHODS = ("GET", "POST", "PUT", "DELETE", "OPTIONS")
DEFAULT_CORS_HEADERS = ("Accept", "Content-Type")

# --- Decision Readout (live ship / no-ship synthesis) ---------------------------------------
# Minimum Bayesian P(treatment > control) required to call a positive, frequentist-significant
# result a "ship". 0.95 mirrors the default 95% credibility the planner uses elsewhere.
DECISION_SHIP_PROBABILITY = 0.95
# At or above this P(B>A) — or once a sequential design has run its full course — a verdict is
# reported with "high" confidence rather than "medium".
DECISION_STRONG_PROBABILITY = 0.99
# Information fraction at/after which a group-sequential design is treated as complete (it has
# accrued its planned sample size, so a still-inconclusive result reads as "no detectable effect"
# rather than "keep collecting").
DECISION_INFO_FRACTION_COMPLETE = 1.0
