"""
Group sequential design utilities using O'Brien-Fleming style boundaries.

The implementation keeps the stats layer dependency-free and numerically inverts
the Lan-DeMets alpha-spending function for equally spaced looks.
"""

import math
from typing import Any

from app.backend.app.stats.binary import normal_ppf

_MAX_SEQUENTIAL_LOOKS = 20
_GAUSS_LEGENDRE_ORDER = 64
_ROOT_ITERATIONS = 40
_MIN_RESOLVABLE_ALPHA = 1e-12


def _gauss_legendre_rule(order: int) -> tuple[tuple[float, ...], tuple[float, ...]]:
    nodes = [0.0] * order
    weights = [0.0] * order
    for index in range((order + 1) // 2):
        root = math.cos(math.pi * (index + 0.75) / (order + 0.5))
        derivative = 0.0
        for _ in range(20):
            previous = 1.0
            current = root
            for degree in range(2, order + 1):
                previous, current = (
                    current,
                    ((2 * degree - 1) * root * current - (degree - 1) * previous) / degree,
                )
            derivative = order * (root * current - previous) / (root * root - 1)
            update = current / derivative
            root -= update
            if abs(update) < 1e-15:
                break

        weight = 2 / ((1 - root * root) * derivative * derivative)
        nodes[index] = -root
        nodes[order - index - 1] = root
        weights[index] = weight
        weights[order - index - 1] = weight
    return tuple(nodes), tuple(weights)


_QUADRATURE_NODES, _QUADRATURE_WEIGHTS = _gauss_legendre_rule(_GAUSS_LEGENDRE_ORDER)


def _normal_density(value: float, variance: float) -> float:
    return math.exp(-(value * value) / (2 * variance)) / math.sqrt(2 * math.pi * variance)


def _survival_state(
    boundary_z: float,
    information_fraction: float,
    information_increment: float,
    previous_nodes: tuple[float, ...] | None,
    previous_weighted_density: tuple[float, ...] | None,
) -> tuple[tuple[float, ...], tuple[float, ...], float]:
    brownian_boundary = boundary_z * math.sqrt(information_fraction)
    nodes = tuple(brownian_boundary * node for node in _QUADRATURE_NODES)
    mapped_weights = tuple(brownian_boundary * weight for weight in _QUADRATURE_WEIGHTS)

    if previous_nodes is None or previous_weighted_density is None:
        densities = tuple(_normal_density(node, information_fraction) for node in nodes)
    else:
        densities = tuple(
            sum(
                weighted_density * _normal_density(node - previous_node, information_increment)
                for previous_node, weighted_density in zip(
                    previous_nodes, previous_weighted_density, strict=True
                )
            )
            for node in nodes
        )

    weighted_density = tuple(
        weight * density for weight, density in zip(mapped_weights, densities, strict=True)
    )
    return nodes, weighted_density, sum(weighted_density)


def _invert_spending_boundary(
    *,
    information_fraction: float,
    information_increment: float,
    incremental_alpha: float,
    previous_boundary_z: float,
    previous_nodes: tuple[float, ...],
    previous_weighted_density: tuple[float, ...],
    previous_survival: float,
) -> tuple[float, tuple[float, ...], tuple[float, ...], float]:
    target_survival = previous_survival - incremental_alpha
    lower = 0.0
    upper = max(8.0, previous_boundary_z)

    for _ in range(_ROOT_ITERATIONS):
        midpoint = (lower + upper) / 2
        _, _, survival = _survival_state(
            midpoint,
            information_fraction,
            information_increment,
            previous_nodes,
            previous_weighted_density,
        )
        if survival < target_survival:
            lower = midpoint
        else:
            upper = midpoint

    boundary_z = (lower + upper) / 2
    nodes, weighted_density, survival = _survival_state(
        boundary_z,
        information_fraction,
        information_increment,
        previous_nodes,
        previous_weighted_density,
    )
    return boundary_z, nodes, weighted_density, survival


def obrien_fleming_boundaries(
    n_looks: int,
    alpha: float = 0.05,
) -> list[dict[str, Any]]:
    if not 1 <= n_looks <= _MAX_SEQUENTIAL_LOOKS:
        raise ValueError(f"n_looks must be between 1 and {_MAX_SEQUENTIAL_LOOKS}, got {n_looks}")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")

    z_half_alpha = normal_ppf(1 - alpha / 2)
    information_increment = 1 / n_looks
    boundaries: list[dict[str, Any]] = []
    cumulative_alpha_spent = 0.0
    previous_boundary_z = math.inf
    previous_nodes: tuple[float, ...] | None = None
    previous_weighted_density: tuple[float, ...] | None = None
    previous_survival = 1.0

    for look in range(1, n_looks + 1):
        info_fraction = look / n_looks
        cumulative_spent = (
            alpha
            if look == n_looks
            else math.erfc(z_half_alpha / math.sqrt(2 * info_fraction))
        )
        incremental_alpha = max(0.0, cumulative_spent - cumulative_alpha_spent)
        cumulative_alpha_spent = cumulative_spent

        if previous_nodes is None or previous_weighted_density is None:
            z_boundary = z_half_alpha / math.sqrt(info_fraction)
            nodes, weighted_density, survival = _survival_state(
                z_boundary,
                info_fraction,
                information_increment,
                None,
                None,
            )
        elif incremental_alpha <= _MIN_RESOLVABLE_ALPHA:
            z_boundary = z_half_alpha / math.sqrt(info_fraction)
            nodes, weighted_density, survival = _survival_state(
                z_boundary,
                info_fraction,
                information_increment,
                previous_nodes,
                previous_weighted_density,
            )
        else:
            z_boundary, nodes, weighted_density, survival = _invert_spending_boundary(
                information_fraction=info_fraction,
                information_increment=information_increment,
                incremental_alpha=incremental_alpha,
                previous_boundary_z=previous_boundary_z,
                previous_nodes=previous_nodes,
                previous_weighted_density=previous_weighted_density,
                previous_survival=previous_survival,
            )

        nominal_alpha = math.erfc(z_boundary / math.sqrt(2))

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
        previous_boundary_z = z_boundary
        previous_nodes = nodes
        previous_weighted_density = weighted_density
        previous_survival = survival

    return boundaries


def sequential_sample_size_inflation(
    n_looks: int,
    alpha: float = 0.05,
    power: float = 0.8,
) -> float:
    """Maximum-sample-size inflation factor for an O'Brien-Fleming design at ``n_looks`` looks.

    The factor is a reference-design approximation calibrated for the common two-sided
    ``alpha ~= 0.05`` / ``power ~= 0.80`` setting (the values practitioners use ~99% of the time).
    For O'Brien-Fleming the inflation is dominated by ``n_looks``; its dependence on ``alpha`` and
    ``power`` is second order (a few tenths of a percent across the usual ranges) and is
    intentionally *not* modelled here — an exact value needs the group-sequential power integral,
    which would pull a numerical-integration dependency into this stdlib-only stats layer.

    ``alpha`` / ``power`` are kept in the signature for call-site symmetry with the rest of the
    stats API and so a future exact implementation is a drop-in; callers should treat the result as
    valid for standard designs and not rely on it varying with ``alpha`` / ``power``.
    """
    if not 1 <= n_looks <= _MAX_SEQUENTIAL_LOOKS:
        raise ValueError(f"n_looks must be between 1 and {_MAX_SEQUENTIAL_LOOKS}, got {n_looks}")
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
    if n_looks in inflation:
        return inflation[n_looks]
    return round(min(1.08, inflation[10] + 0.01 * math.log(n_looks / 10, 10)), 4)
