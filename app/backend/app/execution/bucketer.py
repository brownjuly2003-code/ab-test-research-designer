"""Deterministic assignment / bucketing — port of the GrowthBook hashing spec (MIT).

The whole execution layer rests on this: a pure, infrastructure-free function that
maps ``(seed, user_id)`` to a stable variation. Staying byte-for-byte compatible with
GrowthBook's algorithm means their published MIT SDKs (JS/Python/Go/...) can act as the
client layer later (Phase B) without writing our own.

Reference: https://docs.growthbook.io/lib/build-your-own and
``growthbook/packages/sdk-js/src/util.ts``. Constants/behaviour are verified against the
upstream ``test/cases.json`` vectors in ``tests/test_bucketer.py``.

Caveat: ``fnv32a`` XORs each character's code point, matching JS ``charCodeAt`` for the
Basic Multilingual Plane (code points <= 0xFFFF). Astral-plane characters (emoji) would
diverge from a UTF-16 client; user ids and seeds are expected to be BMP text in the MVP.
"""

from __future__ import annotations

FNV_OFFSET_BASIS_32 = 0x811C9DC5
FNV_PRIME_32 = 0x01000193
UINT32_MASK = 0xFFFFFFFF


def fnv32a(text: str) -> int:
    """32-bit FNV-1a hash, matching GrowthBook's ``fnv32a`` (XOR on full char code)."""
    hval = FNV_OFFSET_BASIS_32
    for char in text:
        hval ^= ord(char)
        hval = (hval * FNV_PRIME_32) & UINT32_MASK
    return hval


def hash_to_unit(seed: str, value: str, hash_version: int = 2) -> float | None:
    """Map ``(seed, value)`` to a stable float in ``[0, 1)``.

    ``hash_version`` 1 is the original (biased) algorithm; 2 is the current unbiased
    double-hash. Any other version returns ``None`` (GrowthBook returns null), signalling
    "no deterministic hash available".
    """
    if hash_version == 1:
        return (fnv32a(value + seed) % 1000) / 1000
    if hash_version == 2:
        return (fnv32a(str(fnv32a(seed + value))) % 10000) / 10000
    return None


def in_namespace(
    user_id: str,
    namespace_id: str,
    range_start: float,
    range_end: float,
) -> bool:
    """Whether ``user_id`` falls inside this experiment's slot of a shared namespace.

    Byte-for-byte port of GrowthBook ``inNamespace``: hash ``user_id + "__" + namespace_id``
    to ``[0, 1)`` (version-1 style ``% 1000 / 1000``) and test ``range_start <= n < range_end``.
    Two experiments that share a ``namespace_id`` but reserve non-overlapping ``[start, end)``
    slots can never assign the same user — the basis for mutual exclusion. The hash is
    independent of the experiment seed, so namespace membership and variation are uncorrelated.
    """
    unit_interval = (fnv32a(f"{user_id}__{namespace_id}") % 1000) / 1000
    return range_start <= unit_interval < range_end


def get_equal_weights(num_variations: int) -> list[float]:
    if num_variations < 1:
        return []
    return [1 / num_variations] * num_variations


def _clamp_coverage(coverage: float) -> float:
    return max(0.0, min(1.0, coverage))


def get_bucket_ranges(
    num_variations: int,
    coverage: float = 1.0,
    weights: list[float] | None = None,
) -> list[tuple[float, float]]:
    """Convert weights + coverage into ``[start, end)`` ranges over ``[0, 1)``.

    Mirrors GrowthBook ``getBucketRanges``: coverage is clamped to ``[0, 1]``; weights
    default to equal and fall back to equal when their length mismatches the variation
    count or their sum is outside ``[0.99, 1.01]``. A range's start is the cumulative
    weight; its width is ``coverage * weight`` (so ``coverage < 1`` leaves an unassigned
    tail — free ramp-up).
    """
    clamped_coverage = _clamp_coverage(coverage)

    resolved_weights = weights if weights is not None else get_equal_weights(num_variations)
    if len(resolved_weights) != num_variations:
        resolved_weights = get_equal_weights(num_variations)
    total_weight = sum(resolved_weights)
    if total_weight < 0.99 or total_weight > 1.01:
        resolved_weights = get_equal_weights(num_variations)

    ranges: list[tuple[float, float]] = []
    cumulative = 0.0
    for weight in resolved_weights:
        start = cumulative
        cumulative += weight
        ranges.append((start, start + clamped_coverage * weight))
    return ranges


def choose_variation(unit_interval: float, ranges: list[tuple[float, float]]) -> int:
    """Return the index of the range containing ``unit_interval`` (``[lo, hi)``), else -1."""
    for index, (lower, upper) in enumerate(ranges):
        if lower <= unit_interval < upper:
            return index
    return -1


SAMPLE_ASSIGNMENT_LIMIT = 25


def preview_assignment_distribution(
    seed: str,
    num_variations: int,
    coverage: float = 1.0,
    weights: list[float] | None = None,
    sample_size: int = 1000,
    user_id_prefix: str = "user-",
    hash_version: int = 2,
) -> dict[str, object]:
    """Planning sanity-check: bucket ``sample_size`` synthetic users and report the
    resulting variation distribution and in-experiment share. Deterministic for a given
    ``(seed, prefix, sample_size)`` — pure, no IO. This is NOT live per-experiment
    assignment (that is Phase B); it lets a planner confirm bucketing is balanced and
    that ``coverage`` ramps as expected before wiring real traffic.
    """
    counts: dict[int, int] = {}
    samples: list[dict[str, object]] = []
    in_experiment = 0
    for index in range(sample_size):
        user_id = f"{user_id_prefix}{index}"
        result = assign_variation(seed, user_id, num_variations, coverage, weights, hash_version)
        variation = int(result["variation_index"])
        counts[variation] = counts.get(variation, 0) + 1
        if result["in_experiment"]:
            in_experiment += 1
        if len(samples) < SAMPLE_ASSIGNMENT_LIMIT:
            samples.append({"user_id": user_id, "variation_index": variation})

    distribution = [
        {"variation_index": variation, "count": count, "fraction": count / sample_size}
        for variation, count in sorted(counts.items())
    ]
    return {
        "sample_size": sample_size,
        "in_experiment_fraction": in_experiment / sample_size,
        "distribution": distribution,
        "sample_assignments": samples,
    }


def assign_variation(
    seed: str,
    user_id: str,
    num_variations: int,
    coverage: float = 1.0,
    weights: list[float] | None = None,
    hash_version: int = 2,
) -> dict[str, object]:
    """Deterministically assign ``user_id`` to a variation for an experiment ``seed``.

    Returns the variation index (-1 = not in experiment / outside coverage), the
    ``in_experiment`` flag, and the underlying hash for transparency.
    """
    unit_interval = hash_to_unit(seed, user_id, hash_version)
    if unit_interval is None:
        return {"variation_index": -1, "in_experiment": False, "hash": None}
    ranges = get_bucket_ranges(num_variations, coverage, weights)
    variation = choose_variation(unit_interval, ranges)
    return {
        "variation_index": variation,
        "in_experiment": variation >= 0,
        "hash": unit_interval,
    }
