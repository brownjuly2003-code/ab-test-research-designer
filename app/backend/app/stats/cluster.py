"""Cluster-randomized design effect (Kish / Donner & Klar) for sample-size inflation.

When the randomization unit is a cluster (store, region, classroom, ...) rather than an individual,
observations within a cluster are correlated, so the naive sample size — which assumes independent
units — is too small. The Kish design effect scales it up.

Sources (re-derived and confirmed against Monte Carlo in ``scratchpad/verify_cluster_design_effect.py``,
not taken on faith):

* L. Kish, *Survey Sampling* (1965): the design effect ``DEFF`` is the ratio of the variance of an
  estimator under the actual (clustered) design to its variance under simple random sampling.
* A. Donner & N. Klar, *Design and Analysis of Cluster Randomization Trials in Health Research*
  (2000), eq. (1.1): ``DEFF = 1 + (m - 1) * rho``.
* R. J. Hayes & L. H. Moulton, *Cluster Randomised Trials* (2009): the variance inflation factor
  ``DEFF = 1 + (m - 1) * rho``; worked figure ``rho = 0.02``, ``m = 100`` -> ``DEFF = 2.98``.
* S. Eldridge & S. Kerry, *A Practical Guide to Cluster Randomised Trials* (2012): the equal-cluster-
  size design effect used here, and the coefficient-of-variation correction for UNEQUAL cluster sizes
  (which inflates the true design effect further) — the latter is deliberately out of scope.

The runtime is stdlib-only; no new dependency is introduced.
"""

from math import ceil
from typing import Any

from app.backend.app.constants import MAX_SUPPORTED_VARIANTS


def cluster_design_effect(avg_cluster_size: float, icc: float) -> float:
    """Kish (1965) / Donner & Klar (2000) design effect ``DEFF = 1 + (m - 1) * ICC``.

    ``avg_cluster_size`` (``m``) is the average number of individuals per cluster and ``icc`` is the
    intraclass correlation coefficient in ``[0, 1]``. Two degeneracies fall out of the formula and are
    the strongest correctness checks: ``icc = 0`` gives ``DEFF = 1`` (independent observations, i.e.
    the exact simple-random-sampling case), and ``m = 1`` gives ``DEFF = 1`` for any ``icc`` (a single
    individual per "cluster" is not clustering).
    """
    if avg_cluster_size < 1:
        raise ValueError("avg_cluster_size must be >= 1")
    if not 0 <= icc <= 1:
        raise ValueError("icc must be between 0 and 1")
    return 1.0 + (avg_cluster_size - 1.0) * icc


def inflate_for_cluster_design(
    individual_sample_size_per_variant: int,
    avg_cluster_size: float,
    icc: float,
    variants_count: int = 2,
) -> dict[str, Any]:
    """Inflate an individual-level per-arm sample size for a cluster-randomized design.

    Given the individual-level per-arm sample size ``n_ind`` (from any of the existing sizers —
    binary z, continuous z, Mann-Whitney, TOST, Poisson rate; the design effect is a post-multiplier
    that is agnostic to which produced ``n_ind``), returns the cluster-adjusted plan:

    * ``design_effect`` = ``DEFF = 1 + (m - 1) * ICC``
    * ``sample_size_per_variant`` = ``ceil(n_ind * DEFF)`` (individuals per arm)
    * ``clusters_per_variant`` = ``ceil(n_ind * DEFF / m)`` (whole clusters per arm)

    ``icc = 0`` or ``m = 1`` return ``DEFF = 1`` and therefore ``sample_size_per_variant == n_ind``
    exactly (``ceil`` of an integer times ``1.0``), so the cluster path degenerates numerically to the
    non-cluster path — this is the guarantee the tests pin.
    """
    if individual_sample_size_per_variant < 1:
        raise ValueError("individual_sample_size_per_variant must be >= 1")
    if not 2 <= variants_count <= MAX_SUPPORTED_VARIANTS:
        raise ValueError(f"variants_count must be between 2 and {MAX_SUPPORTED_VARIANTS}")

    deff = cluster_design_effect(avg_cluster_size, icc)
    inflated = individual_sample_size_per_variant * deff
    sample_size_per_variant = ceil(inflated)
    clusters_per_variant = ceil(inflated / avg_cluster_size)

    return {
        "design_effect": deff,
        "avg_cluster_size": avg_cluster_size,
        "icc": icc,
        "individual_sample_size_per_variant": individual_sample_size_per_variant,
        "sample_size_per_variant": sample_size_per_variant,
        "total_sample_size": sample_size_per_variant * variants_count,
        "clusters_per_variant": clusters_per_variant,
    }
