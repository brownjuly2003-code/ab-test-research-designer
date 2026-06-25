"""Phase B — bind the deterministic bucketer to a saved experiment.

Phase A gave us a pure ``(seed, user_id) -> variation`` function. This module derives the
bucketing parameters (seed, number of variations, weights, coverage) from a *stored*
experiment design and returns the assignment for a concrete user, alongside a
GrowthBook-compatible result block so an off-the-shelf MIT GrowthBook SDK can act as the
client layer (or reproduce the same assignment locally) without us writing our own SDK.

Parameter mapping (experiment design -> bucketer):
- ``seed``      = the experiment id. GrowthBook defaults an experiment's hash seed to its
                  ``key``; using the stable experiment id keeps us byte-for-byte reproducible.
- ``weights``   = ``setup.traffic_split`` normalised to sum 1.0 (the split is stored as
                  relative integers, e.g. ``[50, 50]`` or ``[1, 1, 1]``).
- ``coverage``  = ``1 - constraints.holdout_fraction``. A holdout withholds that share of
                  traffic from the experiment, which is exactly GrowthBook's coverage tail.

Out of MVP scope (honest non-goals, see execution-layer plan §"НЕ-цели"): targeting
conditions / attribute-based eligibility (the request's ``attributes`` are accepted but not
yet evaluated), mutual-exclusion namespaces, and sticky-bucket persistence.
"""

from __future__ import annotations

from typing import Any

from app.backend.app.execution.bucketer import (
    assign_variation,
    get_equal_weights,
    in_namespace,
)
from app.backend.app.execution.targeting import evaluate_targeting

# GrowthBook's default hash attribute. We always hash the caller-supplied unit id, so the
# stored ``randomization_unit`` (free text like "user"/"session") is informational only.
DEFAULT_HASH_ATTRIBUTE = "id"


def normalize_weights(traffic_split: list[float] | list[int]) -> list[float]:
    """Normalise relative traffic split to weights that sum to 1.0.

    Falls back to equal weights when the split is empty or non-positive, mirroring how the
    bucketer itself defends against degenerate weights.
    """
    if not traffic_split:
        return []
    total = float(sum(traffic_split))
    if total <= 0:
        return get_equal_weights(len(traffic_split))
    return [float(weight) / total for weight in traffic_split]


def coverage_from_holdout(holdout_fraction: float | None) -> float:
    """Map a holdout fraction to experiment coverage (``1 - holdout``), clamped to [0, 1]."""
    if holdout_fraction is None:
        return 1.0
    return max(0.0, min(1.0, 1.0 - float(holdout_fraction)))


def build_experiment_assignment(
    experiment_id: str,
    payload: dict[str, Any],
    user_id: str,
    hash_version: int = 2,
    sticky_variation_index: int | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assign ``user_id`` to a variation for a stored experiment design.

    ``payload`` is the persisted ``ExperimentInput`` dict (``setup`` + ``constraints``).
    Returns native fields (``variation_index`` is ``-1`` when the user falls in the holdout
    tail) plus a ``growthbook`` block whose field names match GrowthBook's ``Result`` so an
    MIT SDK can consume it directly. Not-in-experiment users map to the control variation
    (index 0) with ``inExperiment = false`` in the GrowthBook block, matching GrowthBook's
    own fallback semantics.

    Sticky bucketing: when ``sticky_variation_index`` is supplied (the caller found a
    previously recorded exposure for this user), that stored variation is honoured instead
    of the fresh hash, so a user keeps their variation even if weights/coverage have since
    changed. The hash is still computed for transparency in the response.

    Mutual exclusion: when ``setup.namespace`` is set and the user falls outside this
    experiment's namespace slot, they are not in the experiment (``namespace_excluded``).
    A sticky (already-exposed) user is exempt — once in, they stay in.

    Targeting: when ``setup.targeting_rules`` are set and the request's ``attributes`` do
    not satisfy them, the user is not in the experiment (``targeting_excluded``). Targeting
    is evaluated before namespace (eligibility first); sticky users are exempt.
    """
    setup = payload.get("setup", {})
    constraints = payload.get("constraints", {})

    num_variations = int(setup["variants_count"])
    weights = normalize_weights(setup.get("traffic_split", []))
    coverage = coverage_from_holdout(constraints.get("holdout_fraction"))

    assignment = assign_variation(
        seed=experiment_id,
        user_id=user_id,
        num_variations=num_variations,
        coverage=coverage,
        weights=weights,
        hash_version=hash_version,
    )
    bucket = assignment["hash"]

    namespace = setup.get("namespace")
    targeting_rules = setup.get("targeting_rules") or []
    namespace_excluded = False
    targeting_excluded = False
    if sticky_variation_index is not None:
        # A recorded exposure means the user was in the experiment at this variation.
        variation_index = int(sticky_variation_index)
        in_experiment = True
        sticky = True
    elif targeting_rules and not evaluate_targeting(targeting_rules, attributes):
        # Fails attribute-based eligibility -> not in the experiment.
        variation_index = -1
        in_experiment = False
        sticky = False
        targeting_excluded = True
    elif namespace and not in_namespace(
        user_id, str(namespace["id"]), float(namespace["range_start"]), float(namespace["range_end"])
    ):
        # Outside this experiment's namespace slot -> mutually excluded.
        variation_index = -1
        in_experiment = False
        sticky = False
        namespace_excluded = True
    else:
        variation_index = int(assignment["variation_index"])
        in_experiment = bool(assignment["in_experiment"])
        sticky = False

    return {
        "experiment_id": experiment_id,
        "user_id": user_id,
        "seed": experiment_id,
        "variation_index": variation_index,
        "in_experiment": in_experiment,
        "hash": bucket,
        "num_variations": num_variations,
        "coverage": coverage,
        "weights": weights,
        "hash_version": hash_version,
        "sticky": sticky,
        "namespace_excluded": namespace_excluded,
        "targeting_excluded": targeting_excluded,
        "growthbook": {
            "key": experiment_id,
            "variationId": variation_index if in_experiment else 0,
            "inExperiment": in_experiment,
            "hashUsed": bucket is not None,
            "hashAttribute": DEFAULT_HASH_ATTRIBUTE,
            "hashValue": user_id,
            "bucket": bucket,
        },
    }
