from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.main import create_app
from app.backend.app.stats.srm import chi_square_cdf, chi_square_srm


def test_chi_square_srm_matches_known_reference() -> None:
    chi_square, p_value, is_srm = chi_square_srm(
        observed_counts=[4800, 5200],
        expected_fractions=[0.5, 0.5],
    )

    assert round(chi_square, 4) == 16.0
    assert abs(p_value - 0.0000633) < 0.00001
    assert is_srm is True


def test_chi_square_cdf_matches_known_threshold() -> None:
    p_value = 1 - chi_square_cdf(3.841, 1)

    assert abs(p_value - 0.05) < 0.001


def test_calculate_endpoint_flags_srm_warning_when_actual_counts_are_provided() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/calculate",
        json={
            "metric_type": "binary",
            "baseline_value": 0.042,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "traffic_split": [50, 50],
            "variants_count": 2,
            "actual_counts": [4800, 5200],
        },
    )

    assert response.status_code == 200
    codes = {warning["code"] for warning in response.json()["warnings"]}
    assert "SRM_DETECTED" in codes


def test_no_srm_equal_split() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/srm-check",
        json={
            "observed_counts": [5000, 5000],
            "expected_fractions": [0.5, 0.5],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_srm"] is False
    assert data["p_value"] > 0.001


def test_srm_detected_skewed() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/srm-check",
        json={
            "observed_counts": [4800, 5200],
            "expected_fractions": [0.5, 0.5],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_srm"] is True
    assert data["p_value"] < 0.001


def test_srm_three_variants() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/srm-check",
        json={
            "observed_counts": [3300, 3300, 3400],
            "expected_fractions": [0.333, 0.333, 0.334],
        },
    )

    assert response.status_code == 200
    assert response.json()["is_srm"] is False


def test_srm_fractions_must_sum_to_one() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/srm-check",
        json={
            "observed_counts": [5000, 5000],
            "expected_fractions": [0.6, 0.6],
        },
    )

    assert response.status_code == 422


def test_srm_mismatched_lengths() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/srm-check",
        json={
            "observed_counts": [5000, 5000, 5000],
            "expected_fractions": [0.5, 0.5],
        },
    )

    assert response.status_code == 422
