import math


def chi_square_srm(
    observed_counts: list[int],
    expected_fractions: list[float],
) -> tuple[float, float, bool]:
    if len(observed_counts) != len(expected_fractions):
        raise ValueError("observed_counts and expected_fractions must have same length")
    if len(observed_counts) < 2:
        raise ValueError("observed_counts must contain at least two variants")
    if any(count <= 0 for count in observed_counts):
        raise ValueError("observed_counts must contain positive counts")

    total = sum(observed_counts)
    if total == 0:
        raise ValueError("Total observed count must be > 0")

    expected_counts = [fraction * total for fraction in expected_fractions]
    chi_square = sum(
        ((observed - expected) ** 2) / expected
        for observed, expected in zip(observed_counts, expected_counts)
        if expected > 0
    )

    degrees_of_freedom = len(observed_counts) - 1
    p_value = max(0.0, min(1.0, 1 - chi_square_cdf(chi_square, degrees_of_freedom)))
    return chi_square, p_value, p_value < 0.001


def chi_square_cdf(x: float, degrees_of_freedom: int) -> float:
    if x <= 0:
        return 0.0
    return regularized_gamma_p(degrees_of_freedom / 2, x / 2)


def regularized_gamma_p(a: float, x: float) -> float:
    if x == 0:
        return 0.0
    if x < a + 1:
        return _gamma_series(a, x)
    return 1.0 - _gamma_continued_fraction(a, x)


def _gamma_series(a: float, x: float) -> float:
    ap = a
    delta = 1.0 / a
    total = delta
    for _ in range(200):
        ap += 1
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * 1e-10:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_continued_fraction(a: float, x: float) -> float:
    tiny = 1e-30
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 201):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-10:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
