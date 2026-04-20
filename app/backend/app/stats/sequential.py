"""
Group sequential design utilities using O'Brien-Fleming style boundaries.

The implementation keeps the stats layer dependency-free and combines:
- Lan-DeMets alpha spending for cumulative alpha bookkeeping
- O'Brien-Fleming nominal z-boundaries for equally spaced looks
"""

import math

from app.backend.app.stats.binary import normal_ppf, standard_normal_cdf

_FINAL_BOUNDARY_ANCHORS = {
    0.01: {1: 2.5758, 2: 2.58, 4: 2.609, 8: 2.648, 16: 2.684},
    0.05: {1: 1.96, 2: 1.977, 4: 2.024, 8: 2.072, 16: 2.114},
    0.1: {1: 1.6449, 2: 1.678, 4: 1.733, 8: 1.786, 16: 1.83},
}


def _interpolate(value: float, points: list[tuple[float, float]]) -> float:
    if value <= points[0][0]:
        left_x, left_y = points[0]
        right_x, right_y = points[1]
        slope = (right_y - left_y) / (right_x - left_x)
        return left_y + slope * (value - left_x)

    for index in range(1, len(points)):
        left_x, left_y = points[index - 1]
        right_x, right_y = points[index]
        if value <= right_x:
            weight = (value - left_x) / (right_x - left_x)
            return left_y + (right_y - left_y) * weight

    left_x, left_y = points[-2]
    right_x, right_y = points[-1]
    slope = (right_y - left_y) / (right_x - left_x)
    return right_y + slope * (value - right_x)


def _interpolate_anchor_by_looks(n_looks: int, anchor_map: dict[int, float]) -> float:
    points = sorted((math.log2(looks), value) for looks, value in anchor_map.items())
    return _interpolate(math.log2(n_looks), points)


def _final_boundary_z(n_looks: int, alpha: float) -> float:
    adjustment_points: list[tuple[float, float]] = []
    for anchor_alpha, anchor_map in sorted(_FINAL_BOUNDARY_ANCHORS.items()):
        fixed_z = normal_ppf(1 - anchor_alpha / 2)
        obf_z = _interpolate_anchor_by_looks(n_looks, anchor_map)
        adjustment_points.append((anchor_alpha, obf_z - fixed_z))

    return normal_ppf(1 - alpha / 2) + _interpolate(alpha, adjustment_points)


def obrien_fleming_boundaries(
    n_looks: int,
    alpha: float = 0.05,
) -> list[dict]:
    if not 1 <= n_looks <= 10:
        raise ValueError(f"n_looks must be between 1 and 10, got {n_looks}")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")

    z_half_alpha = normal_ppf(1 - alpha / 2)
    final_boundary = _final_boundary_z(n_looks, alpha)
    boundaries: list[dict] = []
    cumulative_alpha_spent = 0.0

    for look in range(1, n_looks + 1):
        info_fraction = look / n_looks
        cumulative_spent = 2 * (1 - standard_normal_cdf(z_half_alpha / math.sqrt(info_fraction)))
        incremental_alpha = max(0.0, cumulative_spent - cumulative_alpha_spent)
        cumulative_alpha_spent = cumulative_spent
        z_boundary = final_boundary / math.sqrt(info_fraction)
        nominal_alpha = 2 * (1 - standard_normal_cdf(z_boundary))

        boundaries.append(
            {
                "look": look,
                "info_fraction": round(info_fraction, 4),
                "cumulative_alpha_spent": round(min(alpha, cumulative_spent), 6),
                "incremental_alpha": round(incremental_alpha, 6),
                "z_boundary": round(z_boundary, 4),
                "p_boundary": round(nominal_alpha, 6),
                "is_final": look == n_looks,
            }
        )

    return boundaries


def sequential_sample_size_inflation(
    n_looks: int,
    alpha: float = 0.05,
    power: float = 0.8,
) -> float:
    if not 1 <= n_looks <= 10:
        raise ValueError(f"n_looks must be between 1 and 10, got {n_looks}")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if not 0 < power < 1:
        raise ValueError("power must be between 0 and 1")
    if n_looks == 1:
        return 1.0

    inflation = {
        2: 1.013,
        3: 1.02,
        4: 1.025,
        5: 1.028,
        6: 1.03,
        7: 1.032,
        8: 1.033,
        9: 1.034,
        10: 1.035,
    }
    return inflation[n_looks]
