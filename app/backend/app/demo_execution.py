"""Deterministic execution data for the seeded demo workspace (Phase 5 / T5.1).

The startup seed (``startup_seed.seed_demo_workspace``) creates *design* demo projects but
ingests no exposures or conversions, so every live-stats execution block reads ``unavailable``
on the default demo path. This module fills that gap: for the three analyzed demo projects it
generates a small, deterministic, statistically coherent stream of exposures / conversions /
pre-period covariates / strata / holdout members / identity links / exclusions, then ingests it
through the ordinary ``repository.record_*`` methods so the public results view shows the live
surface — always-valid (mSPRT), sequential, decision-readout, guardrail, holdout, CUPED,
post-stratification, identity resolution, bot/fraud filter, and late / out-of-order events — with
no manual ingest.

Design notes:

* **Deterministic.** Each demo draws from its own ``random.Random(seed)``, so the seeded data is
  reproducible and tests can assert on the resulting block statuses. No wall-clock is read; event
  times hang off a fixed anchor (``_ANCHOR``).
* **Honest.** The numbers are obviously synthetic but coherent — a real uplift where one is shown,
  guardrails that are *not* breached, a covariate genuinely correlated with the outcome, and one
  demo left deliberately inconclusive (``keep_running``) so the demo is not all green.
* **Metric names come from the stored design,** never hardcoded, so the seed stays in sync with the
  templates.
* **Idempotent.** ``seed_demo_execution`` skips any demo that already carries exposures, and the
  repository's first-write-wins dedup makes a re-run a no-op even mid-stream.
* **No schema / API / contract / frontend change** — this is data only.

A *ratio* demo is intentionally absent: a ratio experiment cannot be analyzed yet
(``routes/analysis`` rejects ratio sizing), and the live-stats view only renders for analyzed
projects, so a ratio demo's block could not surface. It unlocks once ratio becomes analyzable
(Phase 3 T3.1).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from random import Random
from typing import TYPE_CHECKING, Any

from app.backend.app.constants import BOT_CONVERSION_EVENT_THRESHOLD
from app.backend.app.logging_utils import log_event

if TYPE_CHECKING:
    from app.backend.app.repository import ProjectRepository

logger = logging.getLogger(__name__)

# Template ids of the demos this module knows how to populate (keyed to startup_seed.SAMPLE_PROJECTS).
CHECKOUT_TEMPLATE_ID = "checkout_conversion"
PRICING_TEMPLATE_ID = "pricing_sensitivity"
ONBOARDING_TEMPLATE_ID = "onboarding_completion"

# Fixed anchor so every occurred_at window is stable across runs (the seed never reads the clock).
# Exposures land on the anchor; in-window conversions a few days later; "late" conversions past the
# 14-day attribution horizon; "out-of-order" conversions just before the exposure.
_ANCHOR = datetime(2026, 5, 1, 9, 0, 0, tzinfo=UTC)
_LATE_OFFSET = timedelta(days=20)  # > ATTRIBUTION_HORIZON_DAYS (14) -> classified late
_OUT_OF_ORDER_OFFSET = timedelta(days=-1)  # before the exposure -> causally impossible

# Per-demo PRNG seeds — distinct so the three streams are independent and each is reproducible.
_SEED_BY_TEMPLATE = {
    CHECKOUT_TEMPLATE_ID: 104_217,
    PRICING_TEMPLATE_ID: 204_519,
    ONBOARDING_TEMPLATE_ID: 304_023,
}


@dataclass
class ExecutionBatches:
    """Ready-to-ingest event batches for one demo experiment. Each list matches the item shape the
    corresponding ``repository.record_*`` method expects."""

    exposures: list[dict[str, Any]] = field(default_factory=list)
    conversions: list[dict[str, Any]] = field(default_factory=list)
    pre_period_values: list[dict[str, Any]] = field(default_factory=list)
    strata: list[dict[str, Any]] = field(default_factory=list)
    holdout: list[dict[str, Any]] = field(default_factory=list)
    identities: list[dict[str, Any]] = field(default_factory=list)
    exclusions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ExecutionSeedResult:
    seeded: list[str] = field(default_factory=list)  # template ids freshly given execution data
    skipped: list[str] = field(default_factory=list)  # template ids that already had exposures


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _in_window_time(rng: Random) -> str:
    """A conversion time 1–4 days after the exposure anchor (inside the attribution horizon)."""
    return _iso(_ANCHOR + timedelta(days=1.0 + rng.random() * 3.0))


def _guardrail_names(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """The first binary and first continuous guardrail metric names declared in the design."""
    guardrails = payload.get("metrics", {}).get("guardrail_metrics") or []
    binary = next((g["name"] for g in guardrails if g.get("metric_type") == "binary"), None)
    continuous = next((g["name"] for g in guardrails if g.get("metric_type") == "continuous"), None)
    return binary, continuous


# --- Per-demo builders -----------------------------------------------------------------------


def build_checkout_execution(payload: dict[str, Any], rng: Random) -> ExecutionBatches:
    """Flagship binary demo (``purchase_conversion``) — the full execution surface.

    A balanced 2×2000 split (SRM healthy) with a clear, significant uplift so always-valid crosses
    and the decision reads *ship*; two guardrails that hold (ok); a held-back group for the
    cumulative read; a device stratum; a handful of anonymous→canonical identity links (which would
    have inflated the treated arm without resolution); a manual deny-list plus one rate-spike bot;
    and a few late / out-of-order conversions as an honest data-quality signal.
    """
    metrics = payload["metrics"]
    primary = metrics["primary_metric_name"]
    binary_guardrail, continuous_guardrail = _guardrail_names(payload)

    batches = ExecutionBatches()
    n_per_arm = 2000
    exposure_at = _iso(_ANCHOR)

    # Base conversion rates: control near the design baseline (0.042), treatment a clear lift.
    base_rate = {0: 0.043, 1: 0.062}
    # Device heterogeneity so post-stratification has signal (ios converts a touch higher).
    device_lift = {"ios": 0.007, "android": -0.004}

    # Treatment users reserved for forced data-quality timing (guaranteed counts, independent of rng).
    late_uids = {f"ckt-t-{i:04d}" for i in range(0, 12)}  # 12 late conversions
    out_of_order_uids = {f"ckt-t-{i:04d}" for i in range(12, 15)}  # 3 out-of-order conversions
    # Treatment users that also arrive first under an anonymous id (resolved away in the rollup).
    identity_uids = {f"ckt-t-{i:04d}" for i in range(20, 80)}  # 60 anonymous→canonical links
    # Control users placed on the manual deny-list (internal QA traffic).
    manual_excluded_uids = {f"ckt-c-{i:04d}" for i in range(100, 108)}  # 8 manual exclusions

    for arm in (0, 1):
        prefix = "ckt-c" if arm == 0 else "ckt-t"
        for i in range(n_per_arm):
            uid = f"{prefix}-{i:04d}"
            device = "ios" if rng.random() < 0.4 else "android"
            batches.exposures.append(
                {"user_id": uid, "variation_index": arm, "occurred_at": exposure_at}
            )
            batches.strata.append({"user_id": uid, "stratum": device})

            # Primary conversion. Reserved treatment users are forced converters with off-window
            # timing; everyone else converts per the arm/device rate inside the window.
            if uid in late_uids:
                batches.conversions.append(
                    {"user_id": uid, "metric": primary, "value": 1.0, "occurred_at": _iso(_ANCHOR + _LATE_OFFSET)}
                )
            elif uid in out_of_order_uids:
                batches.conversions.append(
                    {"user_id": uid, "metric": primary, "value": 1.0, "occurred_at": _iso(_ANCHOR + _OUT_OF_ORDER_OFFSET)}
                )
            elif rng.random() < base_rate[arm] + device_lift[device]:
                batches.conversions.append(
                    {"user_id": uid, "metric": primary, "value": 1.0, "occurred_at": _in_window_time(rng)}
                )

            # Binary guardrail (e.g. payment error rate): ~2.4% in both arms -> no breach.
            if binary_guardrail and rng.random() < 0.024 + (0.001 if arm == 1 else 0.0):
                batches.conversions.append(
                    {"user_id": uid, "metric": binary_guardrail, "value": 1.0, "occurred_at": exposure_at}
                )
            # Continuous guardrail (e.g. refund value): ~8% carry a value ~N(18, 6.5), equal arms -> ok.
            if continuous_guardrail and rng.random() < 0.08:
                refund = max(0.0, rng.gauss(18.0, 6.5))
                batches.conversions.append(
                    {"user_id": uid, "metric": continuous_guardrail, "value": round(refund, 2), "occurred_at": exposure_at}
                )

            # Anonymous→canonical link: an earlier anonymous exposure that folds onto this user.
            if uid in identity_uids:
                anon = f"ckt-anon-{i:04d}"
                batches.exposures.append(
                    {"user_id": anon, "variation_index": arm, "occurred_at": _iso(_ANCHOR - timedelta(hours=2))}
                )
                batches.identities.append({"anonymous_id": anon, "canonical_id": uid})

            if uid in manual_excluded_uids:
                batches.exclusions.append({"user_id": uid, "exclusion_reason": "internal_qa"})

    # One rate-spike bot in the treatment arm: more than the threshold conversion events on the
    # primary metric, so the rollup drops it automatically (its events never touch the rate).
    bot_uid = "ckt-bot-1"
    batches.exposures.append({"user_id": bot_uid, "variation_index": 1, "occurred_at": exposure_at})
    for k in range(BOT_CONVERSION_EVENT_THRESHOLD + 30):
        batches.conversions.append(
            {"user_id": bot_uid, "metric": primary, "value": 1.0, "occurred_at": exposure_at, "idempotency_key": f"ckt-bot-{k:04d}"}
        )

    # Holdout: a held-back group seeing the old experience (baseline rate). The live read pools the
    # treated arm against it for the cumulative effect.
    for i in range(400):
        uid = f"ckt-h-{i:04d}"
        batches.holdout.append({"user_id": uid})
        if rng.random() < 0.042:
            batches.conversions.append(
                {"user_id": uid, "metric": primary, "value": 1.0, "occurred_at": _in_window_time(rng)}
            )

    return batches


def build_pricing_execution(payload: dict[str, Any], rng: Random) -> ExecutionBatches:
    """Continuous demo (``avg_order_value``) — the variance-reduction toolkit.

    One outcome per exposed user with a real positive treatment effect; a pre-period covariate
    genuinely correlated with the outcome so CUPED reports a positive variance reduction; and a
    customer segment stratum so post-stratification has signal on a continuous metric.
    """
    metrics = payload["metrics"]
    primary = metrics["primary_metric_name"]
    base = float(metrics["baseline_value"])
    binary_guardrail, _ = _guardrail_names(payload)

    # 400/arm keeps the live read fast (the multi-covariate CUPED rollup is intentionally heavy) while
    # leaving the effect, the variance reduction, and both strata comfortably resolvable.
    batches = ExecutionBatches()
    n_per_arm = 400
    exposure_at = _iso(_ANCHOR)

    arm_effect = {0: 0.0, 1: 3.0}  # treatment lifts AOV by ~3.0
    segment_effect = {"new": 0.0, "returning": 5.0}  # returning users spend more
    # Guardrail (purchase conversion) holds: treatment is no worse than control under the design's
    # default increase-is-bad direction, so the guardrail reads "ok" rather than a noisy "warning".
    guardrail_rate = {0: 0.045, 1: 0.033}

    for arm in (0, 1):
        prefix = "prc-c" if arm == 0 else "prc-t"
        for i in range(n_per_arm):
            uid = f"{prefix}-{i:04d}"
            segment = "new" if rng.random() < 0.55 else "returning"
            pre = rng.gauss(base, 12.0)  # pre-period covariate X
            batches.exposures.append(
                {"user_id": uid, "variation_index": arm, "occurred_at": exposure_at}
            )
            batches.pre_period_values.append({"user_id": uid, "value": round(pre, 4)})
            batches.strata.append({"user_id": uid, "stratum": segment})
            # Outcome correlated with the covariate (rho ~ 0.55) plus arm and segment effects.
            outcome = (
                base
                + 0.55 * (pre - base)
                + arm_effect[arm]
                + segment_effect[segment]
                + rng.gauss(0.0, 10.0)
            )
            batches.conversions.append(
                {"user_id": uid, "metric": primary, "value": round(max(0.0, outcome), 2), "occurred_at": _in_window_time(rng)}
            )
            # Binary guardrail (e.g. purchase conversion): treatment <= control -> ok.
            if binary_guardrail and rng.random() < guardrail_rate[arm]:
                batches.conversions.append(
                    {"user_id": uid, "metric": binary_guardrail, "value": 1.0, "occurred_at": exposure_at}
                )

    return batches


def build_onboarding_execution(payload: dict[str, Any], rng: Random) -> ExecutionBatches:
    """Binary demo (``onboarding_completion_rate``) left deliberately inconclusive.

    A small, non-significant difference at a modest sample so always-valid keeps accruing and the
    decision reads *keep running* — an honest "still monitoring, no verdict yet" state so the demo
    is not uniformly green.
    """
    metrics = payload["metrics"]
    primary = metrics["primary_metric_name"]

    batches = ExecutionBatches()
    n_per_arm = 1200
    exposure_at = _iso(_ANCHOR)
    rate = {0: 0.340, 1: 0.355}  # ~0.015 difference -> z ~ 0.8, not significant

    for arm in (0, 1):
        prefix = "onb-c" if arm == 0 else "onb-t"
        for i in range(n_per_arm):
            uid = f"{prefix}-{i:04d}"
            batches.exposures.append(
                {"user_id": uid, "variation_index": arm, "occurred_at": exposure_at}
            )
            if rng.random() < rate[arm]:
                batches.conversions.append(
                    {"user_id": uid, "metric": primary, "value": 1.0, "occurred_at": _in_window_time(rng)}
                )

    return batches


_BUILDERS: dict[str, Callable[[dict[str, Any], Random], ExecutionBatches]] = {
    CHECKOUT_TEMPLATE_ID: build_checkout_execution,
    PRICING_TEMPLATE_ID: build_pricing_execution,
    ONBOARDING_TEMPLATE_ID: build_onboarding_execution,
}


def _ingest(repository: ProjectRepository, experiment_id: str, batches: ExecutionBatches) -> None:
    """Push one demo's batches through the ordinary record_* methods (one transaction each)."""
    if batches.exposures:
        repository.record_exposures(experiment_id, batches.exposures)
    if batches.holdout:
        repository.record_holdout(experiment_id, batches.holdout)
    if batches.identities:
        repository.record_identities(experiment_id, batches.identities)
    if batches.conversions:
        repository.record_conversions(experiment_id, batches.conversions)
    if batches.pre_period_values:
        repository.record_pre_period_values(experiment_id, batches.pre_period_values)
    if batches.strata:
        repository.record_strata(experiment_id, batches.strata)
    if batches.exclusions:
        repository.record_exclusions(experiment_id, batches.exclusions)


def seed_demo_execution(
    repository: ProjectRepository, demo_projects: list[tuple[str, str]]
) -> ExecutionSeedResult:
    """Ingest deterministic execution data for the known demo projects.

    ``demo_projects`` is a list of ``(template_id, project_id)`` pairs. A demo is seeded only when a
    builder is registered for its template and it carries no exposures yet (first run), so this is
    safe to call on every startup and on the upgrade path where the design projects already exist
    (e.g. restored from a snapshot) but have no execution data.
    """
    result = ExecutionSeedResult()
    for template_id, project_id in demo_projects:
        builder = _BUILDERS.get(template_id)
        if builder is None:
            continue
        summary = repository.get_ingestion_summary(project_id)
        if summary is None:
            continue  # project disappeared between resolution and seeding
        if summary["exposures_total"] > 0:
            result.skipped.append(template_id)
            continue
        project = repository.get_project(project_id, include_archived=True)
        if project is None:
            continue
        batches = builder(project["payload"], Random(_SEED_BY_TEMPLATE[template_id]))
        _ingest(repository, project_id, batches)
        result.seeded.append(template_id)

    log_event(
        logger,
        logging.INFO,
        "demo-seed-execution: completed",
        seeded=",".join(result.seeded) or "none",
        skipped=",".join(result.skipped) or "none",
    )
    return result
