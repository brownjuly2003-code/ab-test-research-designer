from __future__ import annotations

import copy
import json
import logging
import math
from pathlib import Path
import sys

import yaml
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backend.app.config import get_settings
from app.backend.app.main import create_app


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO_ROOT / "app" / "backend" / "templates" / "checkout_conversion.yaml"
OUTPUT_PATH = REPO_ROOT / "docs" / "case-studies" / "checkout-redesign.json"
PRIOR_ALPHA = 1
PRIOR_BETA = 1

INTERIM_COUNTS = {
    "control": {"conversions": 1200, "users": 16000},
    "variant_a": {"conversions": 1272, "users": 16000},
    "variant_b": {"conversions": 1340, "users": 16000},
}


def _load_payload_template() -> dict:
    with TEMPLATE_PATH.open("r", encoding="utf-8") as handle:
        template = yaml.safe_load(handle)
    return copy.deepcopy(template["payload"])


def _build_experiment_payload() -> dict:
    payload = _load_payload_template()
    payload["project"]["project_name"] = "Checkout redesign case study"
    payload["project"]["project_description"] = (
        "Evaluate two checkout redesigns against the current flow."
    )
    payload["hypothesis"]["change_description"] = (
        "Test two shorter checkout redesigns against the current flow"
    )
    payload["hypothesis"]["target_audience"] = "all checkout visitors on web"
    payload["hypothesis"]["business_problem"] = "checkout abandonment suppresses completed orders"
    payload["hypothesis"]["hypothesis_statement"] = (
        "Reducing checkout friction can lift purchase conversion."
    )
    payload["hypothesis"]["what_to_validate"] = (
        "whether either redesign improves purchase conversion vs control"
    )
    payload["hypothesis"]["desired_result"] = (
        "ship the strongest redesign without harming guardrails"
    )
    payload["setup"]["traffic_split"] = [34, 33, 33]
    payload["setup"]["expected_daily_traffic"] = 80000
    payload["setup"]["audience_share_in_test"] = 0.5
    payload["setup"]["variants_count"] = 3
    payload["setup"]["inclusion_criteria"] = "all checkout visitors"
    payload["setup"]["exclusion_criteria"] = "internal staff and QA sessions"
    payload["metrics"]["baseline_value"] = 0.042
    payload["metrics"]["expected_uplift_pct"] = 10
    payload["metrics"]["mde_pct"] = 10
    payload["metrics"]["alpha"] = 0.05
    payload["metrics"]["power"] = 0.8
    payload["constraints"]["n_looks"] = 1
    payload["constraints"]["analysis_mode"] = "frequentist"
    payload["constraints"]["known_risks"] = "tracking quality"
    payload["additional_context"]["llm_context"] = (
        "README case study scenario for a checkout redesign."
    )
    return payload


def _build_calculation_payload(experiment_payload: dict) -> dict:
    return {
        "metric_type": experiment_payload["metrics"]["metric_type"],
        "baseline_value": experiment_payload["metrics"]["baseline_value"],
        "mde_pct": experiment_payload["metrics"]["mde_pct"],
        "alpha": experiment_payload["metrics"]["alpha"],
        "power": experiment_payload["metrics"]["power"],
        "expected_daily_traffic": experiment_payload["setup"]["expected_daily_traffic"],
        "audience_share_in_test": experiment_payload["setup"]["audience_share_in_test"],
        "traffic_split": experiment_payload["setup"]["traffic_split"],
        "variants_count": experiment_payload["setup"]["variants_count"],
        "seasonality_present": experiment_payload["constraints"]["seasonality_present"],
        "active_campaigns_present": experiment_payload["constraints"]["active_campaigns_present"],
        "long_test_possible": experiment_payload["constraints"]["long_test_possible"],
        "n_looks": experiment_payload["constraints"]["n_looks"],
        "analysis_mode": experiment_payload["constraints"]["analysis_mode"],
        "credibility": experiment_payload["constraints"]["credibility"],
    }


def _post_or_raise(client: TestClient, path: str, payload: dict, label: str) -> dict:
    response = client.post(path, json=payload)
    if response.status_code != 200:
        raise RuntimeError(f"{label} failed with {response.status_code}: {response.text}")
    return response.json()


def _posterior_parameters(conversions: int, users: int) -> dict[str, int]:
    return {
        "alpha": PRIOR_ALPHA + conversions,
        "beta": PRIOR_BETA + users - conversions,
    }


def _log_beta(x: int, y: int) -> float:
    return math.lgamma(x) + math.lgamma(y) - math.lgamma(x + y)


def _probability_beta_greater(alpha_x: int, beta_x: int, alpha_y: int, beta_y: int) -> float:
    total = 0.0
    for index in range(alpha_x):
        log_term = (
            _log_beta(alpha_y + index, beta_x + beta_y)
            - math.log(beta_x + index)
            - _log_beta(1 + index, beta_x)
            - _log_beta(alpha_y, beta_y)
        )
        total += math.exp(log_term)
    return min(1.0, max(0.0, total))


def _render_markdown(case_study: dict) -> str:
    calculation = case_study["outputs"]["calculate"]
    design = case_study["outputs"]["design"]
    interim = case_study["outputs"]["interim"]
    variant_a = interim["variants"]["variant_a"]
    variant_b = interim["variants"]["variant_b"]

    return "\n".join(
        [
            "## Case study: Checkout redesign",
            "",
            "Retailer testing two checkout variants against control to lift conversion from a 4.2% baseline.",
            "",
            "**Setup** - 80k daily visitors, 50% share into test, 3 variants (34/33/33), alpha = 0.05, power = 0.80, two-sided, relative MDE = 10%.",
            "",
            "**Sizing (from `POST /api/v1/calculate`).**",
            "",
            "| Metric | Value |",
            "| --- | --- |",
            f"| Per-variant sample | {calculation['results']['sample_size_per_variant']:,} users |",
            f"| Total sample | {calculation['results']['total_sample_size']:,} users |",
            f"| Required duration | {calculation['results']['estimated_duration_days']} days |",
            f"| Bonferroni adjustment | {interim['bonferroni_short_note']} |",
            "",
            "**Design guidance (from `POST /api/v1/design`).**",
            f"- Primary risk: {design['risks']['statistical'][0]}",
            f"- Key recommendation: {design['recommendations']['before_launch'][0]}",
            f"- Guardrail to monitor: {design['metrics_plan']['guardrail'][0]}",
            "",
            "**Interim check.**",
            (
                f"An early snapshot came in after {interim['totals']['elapsed_test_days']:.1f} test-days, "
                f"{interim['totals']['total_users']:,} visitors, and {interim['totals']['total_conversions']:,} conversions "
                f"({interim['totals']['observed_fraction_of_planned_sample_pct']:.1f}% of the planned per-variant sample):"
            ),
            f"- P(variant A > control) = {variant_a['bayesian_probability_beats_control_pct']:.1f}%",
            f"- P(variant B > control) = {variant_b['bayesian_probability_beats_control_pct']:.1f}%",
            "Variant A is still ambiguous; variant B is the only treatment with a decisive early signal.",
            "",
            "**Decision.**",
            (
                "Stop spending exposure on variant A, keep variant B against control until the planned read is complete, "
                "and ship B only if payment error rate and refund value stay in range. The value here is that sizing, "
                "multivariant correction, design risks, and the Bayesian interim view all come from the same backend run."
            ),
            "",
            "Full inputs and outputs: [docs/case-studies/checkout-redesign.json](docs/case-studies/checkout-redesign.json). "
            "Rerun with `python scripts/generate_case_study_numbers.py`.",
            "",
        ]
    )


def main() -> int:
    logging.getLogger("app.backend.app.main").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    experiment_payload = _build_experiment_payload()
    calculation_payload = _build_calculation_payload(experiment_payload)
    get_settings.cache_clear()

    try:
        with TestClient(create_app()) as client:
            calculation = _post_or_raise(
                client,
                "/api/v1/calculate",
                calculation_payload,
                "POST /api/v1/calculate",
            )
            design = _post_or_raise(
                client,
                "/api/v1/design",
                experiment_payload,
                "POST /api/v1/design",
            )
            variant_a_results = _post_or_raise(
                client,
                "/api/v1/results",
                {
                    "metric_type": "binary",
                    "binary": {
                        "control_conversions": INTERIM_COUNTS["control"]["conversions"],
                        "control_users": INTERIM_COUNTS["control"]["users"],
                        "treatment_conversions": INTERIM_COUNTS["variant_a"]["conversions"],
                        "treatment_users": INTERIM_COUNTS["variant_a"]["users"],
                        "alpha": experiment_payload["metrics"]["alpha"],
                    },
                },
                "POST /api/v1/results for variant A",
            )
            variant_b_results = _post_or_raise(
                client,
                "/api/v1/results",
                {
                    "metric_type": "binary",
                    "binary": {
                        "control_conversions": INTERIM_COUNTS["control"]["conversions"],
                        "control_users": INTERIM_COUNTS["control"]["users"],
                        "treatment_conversions": INTERIM_COUNTS["variant_b"]["conversions"],
                        "treatment_users": INTERIM_COUNTS["variant_b"]["users"],
                        "alpha": experiment_payload["metrics"]["alpha"],
                    },
                },
                "POST /api/v1/results for variant B",
            )
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        get_settings.cache_clear()

    control_posterior = _posterior_parameters(**INTERIM_COUNTS["control"])
    variant_a_posterior = _posterior_parameters(**INTERIM_COUNTS["variant_a"])
    variant_b_posterior = _posterior_parameters(**INTERIM_COUNTS["variant_b"])
    total_users = sum(arm["users"] for arm in INTERIM_COUNTS.values())
    total_conversions = sum(arm["conversions"] for arm in INTERIM_COUNTS.values())
    per_variant_plan = calculation["results"]["sample_size_per_variant"]
    case_study = {
        "case_study": "checkout-redesign",
        "inputs": {
            "prior": {
                "name": "Beta(1,1)",
                "alpha": PRIOR_ALPHA,
                "beta": PRIOR_BETA,
                "description": "Uniform conjugate prior for conversion rates.",
            },
            "experiment_payload": experiment_payload,
            "calculation_payload": calculation_payload,
            "interim_observations": INTERIM_COUNTS,
        },
        "outputs": {
            "calculate": calculation,
            "design": design,
            "interim": {
                "totals": {
                    "total_users": total_users,
                    "total_conversions": total_conversions,
                    "elapsed_test_days": round(
                        total_users / calculation["results"]["effective_daily_traffic"],
                        4,
                    ),
                    "planned_duration_days": calculation["results"]["estimated_duration_days"],
                    "observed_fraction_of_planned_sample_pct": round(
                        INTERIM_COUNTS["control"]["users"] / per_variant_plan * 100,
                        4,
                    ),
                },
                "bonferroni_short_note": (
                    "2 treatment-vs-control comparisons, adjusted alpha 0.025"
                ),
                "variants": {
                    "control": {
                        "observed": INTERIM_COUNTS["control"],
                        "posterior": control_posterior,
                    },
                    "variant_a": {
                        "observed": INTERIM_COUNTS["variant_a"],
                        "posterior": variant_a_posterior,
                        "frequentist_results": variant_a_results,
                        "bayesian_probability_beats_control": _probability_beta_greater(
                            variant_a_posterior["alpha"],
                            variant_a_posterior["beta"],
                            control_posterior["alpha"],
                            control_posterior["beta"],
                        ),
                        "bayesian_probability_beats_control_pct": round(
                            _probability_beta_greater(
                                variant_a_posterior["alpha"],
                                variant_a_posterior["beta"],
                                control_posterior["alpha"],
                                control_posterior["beta"],
                            )
                            * 100,
                            4,
                        ),
                    },
                    "variant_b": {
                        "observed": INTERIM_COUNTS["variant_b"],
                        "posterior": variant_b_posterior,
                        "frequentist_results": variant_b_results,
                        "bayesian_probability_beats_control": _probability_beta_greater(
                            variant_b_posterior["alpha"],
                            variant_b_posterior["beta"],
                            control_posterior["alpha"],
                            control_posterior["beta"],
                        ),
                        "bayesian_probability_beats_control_pct": round(
                            _probability_beta_greater(
                                variant_b_posterior["alpha"],
                                variant_b_posterior["beta"],
                                control_posterior["alpha"],
                                control_posterior["beta"],
                            )
                            * 100,
                            4,
                        ),
                    },
                },
            },
        },
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(case_study, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(_render_markdown(case_study), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
