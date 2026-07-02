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

# Upper bound on the number of distinct strata post-stratification (F3b) will split the sample into.
# A good stratifier has few, well-populated levels (platform, country, new-vs-returning); too many
# sparse strata *increase* variance (Miratrix et al.), so this caps a pathological high-cardinality
# attribute (e.g. a mistakenly-ingested user id). Above the cap the stratified block is skipped.
MAX_STRATA = 50

# Reserved variation index for a holdout member — a user held back from the rollout (F5). The
# bucketer already returns -1 for "not in experiment", and the per-arm primary rollup excludes it
# (variation_index >= 0); the cumulative holdout read selects exactly this tail.
HOLDOUT_VARIATION_INDEX = -1

# Attribution horizon for late / out-of-order conversion detection (P4.2). A conversion is
# attributed to a user's exposure only when its event time (occurred_at) falls within
# [exposure, exposure + ATTRIBUTION_HORIZON_DAYS]; a conversion before the exposure is out-of-order
# (causally impossible) and one after the horizon is late. 14 days is a conservative default that
# covers most conversion cycles without attributing stale activity to the experiment.
ATTRIBUTION_HORIZON_DAYS = 14.0

# Bot / fraud filter (P4.4). A single user contributing more conversion events than this on the
# analyzed metric is treated as an automated / instrumentation artifact (a real human does not convert
# hundreds of times) and is excluded from the rollup as a rate-spike, alongside the manual deny-list.
# The threshold is deliberately high so ordinary traffic never trips it — it catches only egregious
# spikes; the count is always surfaced in the live-stats indicator so the exclusion is never silent.
BOT_CONVERSION_EVENT_THRESHOLD = 100

# Upper bound on the number of raw per-unit values accepted per arm by the post-hoc Mann–Whitney
# (rank-sum) analyzer. The Hodges–Lehmann confidence interval materializes all n_c·n_t pairwise
# differences, so this cap bounds that O(n_c·n_t) work; 1000 per arm (<= 1e6 pairs) is generous for a
# manual paste-in analyzer, and large live datasets belong to the streaming path, not this endpoint.
MAX_OBSERVED_SAMPLE_SIZE = 1000

# Upper bound on each dimension (rows = groups, columns = outcome levels) of the contingency table
# accepted by the post-hoc chi-square test of independence. The statistic is O(r·c); a real
# categorical breakdown has a handful of groups and levels, so 50 per side is generous while bounding
# request size and compute. The grand total is capped separately in the stats module.
MAX_CONTINGENCY_DIM = 50

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
# A fixed-horizon (n_looks=1) design promises a single read at the planned sample size; a decision
# synthesized before that point is peeking, so the frequentist significance alone may not confirm a
# win/loss — only the anytime-valid (mSPRT) view can. The read counts as "the planned read" from
# this fraction of the planned sample onward: read-time filters (dedup, identity resolution,
# bot/fraud exclusions) legitimately shave a few percent off the ingested exposures, so demanding
# exactly 1.0 would misclassify honest at-plan reads as peeking.
DECISION_FIXED_HORIZON_READ_FRACTION = 0.95
