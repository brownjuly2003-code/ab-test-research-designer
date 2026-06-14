from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.execution.bucketer import assign_variation
from app.backend.app.execution.experiment_assignment import (
    build_experiment_assignment,
    coverage_from_holdout,
    normalize_weights,
)


def _payload(*, variants_count=2, traffic_split=None, holdout_fraction=None, namespace=None) -> dict:
    setup = {
        "variants_count": variants_count,
        "traffic_split": traffic_split if traffic_split is not None else [50, 50],
        "randomization_unit": "user",
    }
    if namespace is not None:
        setup["namespace"] = namespace
    return {
        "setup": setup,
        "constraints": {"holdout_fraction": holdout_fraction},
    }


def test_normalize_weights_scales_to_unit_sum() -> None:
    assert normalize_weights([50, 50]) == [0.5, 0.5]
    thirds = normalize_weights([1, 1, 1])
    assert len(thirds) == 3
    assert abs(sum(thirds) - 1.0) < 1e-9
    assert all(abs(weight - 1 / 3) < 1e-9 for weight in thirds)


def test_normalize_weights_handles_uneven_split() -> None:
    assert normalize_weights([70, 30]) == [0.7, 0.3]


def test_normalize_weights_falls_back_to_equal_on_degenerate_input() -> None:
    assert normalize_weights([]) == []
    assert normalize_weights([0, 0]) == [0.5, 0.5]


def test_coverage_from_holdout_maps_and_clamps() -> None:
    assert coverage_from_holdout(None) == 1.0
    assert coverage_from_holdout(0.0) == 1.0
    assert abs(coverage_from_holdout(0.2) - 0.8) < 1e-9
    assert coverage_from_holdout(1.5) == 0.0
    assert coverage_from_holdout(-0.5) == 1.0


def test_build_assignment_is_deterministic_and_sticky() -> None:
    first = build_experiment_assignment("exp-abc", _payload(), "user-42")
    second = build_experiment_assignment("exp-abc", _payload(), "user-42")
    assert first == second
    assert first["seed"] == "exp-abc"
    assert first["experiment_id"] == "exp-abc"
    assert first["num_variations"] == 2
    assert first["weights"] == [0.5, 0.5]
    assert first["coverage"] == 1.0


def test_build_assignment_matches_raw_bucketer() -> None:
    # Binding must not diverge from the Phase A primitive for the same derived params.
    raw = assign_variation("exp-xyz", "user-7", num_variations=2, coverage=1.0, weights=[0.5, 0.5])
    bound = build_experiment_assignment("exp-xyz", _payload(), "user-7")
    assert bound["variation_index"] == raw["variation_index"]
    assert bound["hash"] == raw["hash"]
    assert bound["in_experiment"] == raw["in_experiment"]


def test_build_assignment_growthbook_block_is_compatible() -> None:
    result = build_experiment_assignment("exp-gb", _payload(), "user-13")
    gb = result["growthbook"]
    assert gb["key"] == "exp-gb"
    assert gb["hashAttribute"] == "id"
    assert gb["hashValue"] == "user-13"
    assert gb["hashUsed"] is True
    assert gb["bucket"] == result["hash"]
    assert gb["inExperiment"] == result["in_experiment"]
    if result["in_experiment"]:
        assert gb["variationId"] == result["variation_index"]


def test_holdout_excludes_a_share_and_maps_excluded_to_control() -> None:
    payload = _payload(holdout_fraction=0.5)
    in_count = 0
    sample = 4000
    for index in range(sample):
        result = build_experiment_assignment("exp-holdout", payload, f"u-{index}")
        if result["in_experiment"]:
            in_count += 1
            assert result["variation_index"] >= 0
        else:
            # Not-in-experiment users fall in the holdout tail -> control fallback (index 0).
            assert result["variation_index"] == -1
            assert result["growthbook"]["variationId"] == 0
            assert result["growthbook"]["inExperiment"] is False
    # coverage = 1 - 0.5 = 0.5; in-experiment share should sit near half.
    assert 0.45 <= in_count / sample <= 0.55


def test_uneven_weights_shift_distribution() -> None:
    payload = _payload(traffic_split=[80, 20])
    counts = {0: 0, 1: 0}
    sample = 4000
    for index in range(sample):
        result = build_experiment_assignment("exp-weighted", payload, f"w-{index}")
        counts[result["variation_index"]] += 1
    assert counts[0] > counts[1]
    assert 0.75 <= counts[0] / sample <= 0.85


def test_namespace_excludes_users_outside_the_slot() -> None:
    # This experiment owns the first half of the "checkout" namespace.
    payload = _payload(namespace={"id": "checkout", "range_start": 0.0, "range_end": 0.5})
    included = 0
    sample = 4000
    for index in range(sample):
        result = build_experiment_assignment("exp-ns", payload, f"u-{index}")
        if result["in_experiment"]:
            included += 1
            assert result["namespace_excluded"] is False
            assert result["variation_index"] >= 0
        else:
            assert result["namespace_excluded"] is True
            assert result["variation_index"] == -1
            assert result["growthbook"]["inExperiment"] is False
    # ~half the traffic lands in the [0, 0.5) namespace slot.
    assert 0.45 <= included / sample <= 0.55


def test_namespace_slots_are_mutually_exclusive() -> None:
    # Two experiments share a namespace but reserve disjoint halves -> no shared users.
    first = _payload(namespace={"id": "layer", "range_start": 0.0, "range_end": 0.5})
    second = _payload(namespace={"id": "layer", "range_start": 0.5, "range_end": 1.0})
    overlap = 0
    for index in range(4000):
        user = f"u-{index}"
        a = build_experiment_assignment("exp-a", first, user)
        b = build_experiment_assignment("exp-b", second, user)
        if a["in_experiment"] and b["in_experiment"]:
            overlap += 1
    assert overlap == 0


def test_namespace_excluded_user_stays_in_when_sticky() -> None:
    # An already-exposed user is exempt from namespace exclusion (once in, stay in).
    payload = _payload(namespace={"id": "checkout", "range_start": 0.0, "range_end": 0.5})
    # Find a user the namespace would exclude.
    excluded_user = next(
        f"u-{i}"
        for i in range(4000)
        if build_experiment_assignment("exp-ns", payload, f"u-{i}")["namespace_excluded"]
    )
    sticky = build_experiment_assignment("exp-ns", payload, excluded_user, sticky_variation_index=1)
    assert sticky["in_experiment"] is True
    assert sticky["variation_index"] == 1
    assert sticky["sticky"] is True
    assert sticky["namespace_excluded"] is False
