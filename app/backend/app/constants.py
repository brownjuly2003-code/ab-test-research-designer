MAX_SUPPORTED_VARIANTS = 10

# Eight weeks is the point after which the planner flags long-running experiments.
MAX_RECOMMENDED_DURATION_DAYS = 56

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
