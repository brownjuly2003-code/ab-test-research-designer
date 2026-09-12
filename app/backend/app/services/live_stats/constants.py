"""Shared constants for live stats Bayesian and anytime-valid rounding."""
_BAYESIAN_SIMULATIONS = 10000
_BAYESIAN_SEED = 42
# Continuous P(treatment > control) is a Monte-Carlo estimate. With 10k draws its
# standard error is sqrt(p(1-p)/N) <= sqrt(0.25/10000) = 0.005, so anything past
# the third decimal is simulation noise, not signal. Binary comparisons use the
# deterministic beta-posterior calculation instead.
_BAYESIAN_PROBABILITY_DECIMALS = 3

_ALWAYS_VALID_DECIMALS = 6
