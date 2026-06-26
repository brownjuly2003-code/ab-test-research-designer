"""Unit tests for the deterministic demo execution data builders (Phase 5 / T5.1).

These are fast, DB-free checks of the generators: determinism (a fixed seed reproduces the same
stream) and the structural invariants the seed relies on (balanced arms, forced data-quality
timing, identity links, exclusions, holdout, per-user continuous outcomes). The end-to-end proof
that this data lights up the live-stats blocks lives in ``test_startup_seed.py``.
"""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.demo_execution import (  # noqa: E402
    CHECKOUT_TEMPLATE_ID,
    ONBOARDING_TEMPLATE_ID,
    PRICING_TEMPLATE_ID,
    _ANCHOR,
    _LATE_OFFSET,
    _OUT_OF_ORDER_OFFSET,
    _SEED_BY_TEMPLATE,
    build_checkout_execution,
    build_onboarding_execution,
    build_pricing_execution,
)
from app.backend.app.constants import BOT_CONVERSION_EVENT_THRESHOLD  # noqa: E402
from app.backend.app.services.template_service import load_built_in_templates  # noqa: E402

# random.Random is deterministic across runs/platforms, so the builders are reproducible.
from random import Random  # noqa: E402


def _payload(template_id: str) -> dict:
    templates = {template["id"]: template for template in load_built_in_templates()}
    return templates[template_id]["payload"]


def _rng(template_id: str) -> Random:
    return Random(_SEED_BY_TEMPLATE[template_id])


@pytest.mark.parametrize(
    "template_id,builder",
    [
        (CHECKOUT_TEMPLATE_ID, build_checkout_execution),
        (PRICING_TEMPLATE_ID, build_pricing_execution),
        (ONBOARDING_TEMPLATE_ID, build_onboarding_execution),
    ],
)
def test_builders_are_deterministic(template_id, builder) -> None:
    first = builder(_payload(template_id), _rng(template_id))
    second = builder(_payload(template_id), _rng(template_id))
    assert first == second


def test_checkout_builder_shape() -> None:
    payload = _payload(CHECKOUT_TEMPLATE_ID)
    primary = payload["metrics"]["primary_metric_name"]
    batches = build_checkout_execution(payload, _rng(CHECKOUT_TEMPLATE_ID))

    # Balanced arms: exactly 2000 real users each (anonymous shadows + the bot are extra exposures).
    real_arm_exposures = [
        e for e in batches.exposures
        if not e["user_id"].startswith("ckt-anon-") and e["user_id"] != "ckt-bot-1"
    ]
    control = [e for e in real_arm_exposures if e["variation_index"] == 0]
    treatment = [e for e in real_arm_exposures if e["variation_index"] == 1]
    assert len(control) == 2000
    assert len(treatment) == 2000

    # 60 anonymous -> canonical links, each backed by an earlier anonymous exposure that folds in.
    assert len(batches.identities) == 60
    anon_ids = {e["user_id"] for e in batches.exposures if e["user_id"].startswith("ckt-anon-")}
    assert len(anon_ids) == 60
    assert {link["anonymous_id"] for link in batches.identities} == anon_ids

    # Manual deny-list: 8 internal-QA exclusions.
    assert len(batches.exclusions) == 8
    assert {x["exclusion_reason"] for x in batches.exclusions} == {"internal_qa"}

    # One rate-spike bot whose conversion volume exceeds the auto-exclusion threshold.
    bot_conversions = [c for c in batches.conversions if c["user_id"] == "ckt-bot-1"]
    assert len(bot_conversions) > BOT_CONVERSION_EVENT_THRESHOLD

    # Holdout: 400 held-back members.
    assert len(batches.holdout) == 400

    # Exactly 12 late and 3 out-of-order primary conversions (forced off-window timing).
    primary_conversions = [c for c in batches.conversions if c["metric"] == primary]
    late_iso = (_ANCHOR + _LATE_OFFSET).isoformat()
    ooo_iso = (_ANCHOR + _OUT_OF_ORDER_OFFSET).isoformat()
    assert sum(1 for c in primary_conversions if c["occurred_at"] == late_iso) == 12
    assert sum(1 for c in primary_conversions if c["occurred_at"] == ooo_iso) == 3

    # A device stratum is attached to every real exposed user, over exactly two strata.
    assert len(batches.strata) == len(real_arm_exposures)
    assert {s["stratum"] for s in batches.strata} == {"ios", "android"}


def test_pricing_builder_shape() -> None:
    payload = _payload(PRICING_TEMPLATE_ID)
    primary = payload["metrics"]["primary_metric_name"]
    batches = build_pricing_execution(payload, _rng(PRICING_TEMPLATE_ID))

    # 400/arm, one pre-period covariate and one outcome per exposed user (continuous mean is over
    # all exposed users, so every user must carry a value).
    assert len(batches.exposures) == 800
    assert len(batches.pre_period_values) == 800
    primary_conversions = [c for c in batches.conversions if c["metric"] == primary]
    assert len(primary_conversions) == 800

    # Two customer segments, both populated, drive post-stratification.
    assert {s["stratum"] for s in batches.strata} == {"new", "returning"}

    # No holdout / identity / exclusion surface on the pricing demo (those live on checkout).
    assert batches.holdout == []
    assert batches.identities == []
    assert batches.exclusions == []


def test_onboarding_builder_is_minimal() -> None:
    payload = _payload(ONBOARDING_TEMPLATE_ID)
    batches = build_onboarding_execution(payload, _rng(ONBOARDING_TEMPLATE_ID))

    # 1200/arm exposures, primary conversions only — a clean second always-valid example.
    assert len(batches.exposures) == 2400
    assert {e["variation_index"] for e in batches.exposures} == {0, 1}
    assert batches.pre_period_values == []
    assert batches.strata == []
    assert batches.holdout == []
    assert batches.identities == []
    assert batches.exclusions == []
