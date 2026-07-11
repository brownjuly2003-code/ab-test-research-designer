"""F-04: a count project must survive the whole project-list contract.

Count planning was added to the wizard/calculate/design path (`MetricsConfig.metric_type`
accepts "count") but not to the list contract: `ProjectListItem` allowed only
binary/continuous/ratio, so one saved count project failed response validation and took
`GET /api/v1/projects` down with it — a 400 that blanked the sidebar for every other
project too. The list filter rejected `metric_type=count` with a 422.

These tests walk a count project through create → list → filter → load → update → archive,
and pin the mixed-workspace case that actually broke.
"""

from pathlib import Path
import sys
import uuid

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings
from app.backend.app.constants import METRIC_TYPES
from app.backend.app.main import create_app


def _count_payload(name: str) -> dict:
    return {
        "project": {
            "project_name": name,
            "domain": "media",
            "product_type": "web app",
            "platform": "web",
            "market": "US",
            "project_description": "We want more article reads per session.",
        },
        "hypothesis": {
            "change_description": "Surface related articles at the end of each read",
            "target_audience": "returning readers",
            "business_problem": "reads per session are flat",
            "hypothesis_statement": "If we recommend related articles, reads per session rise.",
            "what_to_validate": "impact on reads per session",
            "desired_result": "statistically meaningful uplift",
        },
        "setup": {
            "experiment_type": "ab",
            "randomization_unit": "user",
            "traffic_split": [50, 50],
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "variants_count": 2,
            "inclusion_criteria": "returning readers",
            "exclusion_criteria": "internal staff",
        },
        "metrics": {
            "primary_metric_name": "articles_read",
            "metric_type": "count",
            "baseline_value": 3.4,
            "expected_uplift_pct": 8,
            "mde_pct": 5,
            "exposure_per_user": 1.0,
            "alpha": 0.05,
            "power": 0.8,
            "secondary_metrics": [],
            "guardrail_metrics": [],
        },
        "constraints": {
            "seasonality_present": True,
            "active_campaigns_present": False,
            "returning_users_present": True,
            "interference_risk": "medium",
            "technical_constraints": "legacy event logging",
            "legal_or_ethics_constraints": "none",
            "known_risks": "tracking quality",
            "deadline_pressure": "medium",
            "long_test_possible": True,
        },
    }


def _binary_payload(name: str) -> dict:
    payload = _count_payload(name)
    payload["metrics"] = {
        "primary_metric_name": "purchase_conversion",
        "metric_type": "binary",
        "baseline_value": 0.042,
        "expected_uplift_pct": 8,
        "mde_pct": 5,
        "alpha": 0.05,
        "power": 0.8,
        "std_dev": None,
        "secondary_metrics": [],
        "guardrail_metrics": [],
    }
    return payload


def _isolated_db(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("AB_DB_PATH", str(temp_dir / f"{uuid.uuid4()}.sqlite3"))
    get_settings.cache_clear()


def test_count_project_walks_the_full_list_contract(monkeypatch) -> None:
    _isolated_db(monkeypatch)

    with TestClient(create_app()) as client:
        created = client.post("/api/v1/projects", json=_count_payload("Reads per session"))
        assert created.status_code == 200
        project_id = created.json()["id"]

        listed = client.get("/api/v1/projects")
        assert listed.status_code == 200, "a saved count project must not break the list response"
        items = listed.json()["projects"]
        assert [item["metric_type"] for item in items] == ["count"]

        filtered = client.get("/api/v1/projects", params={"metric_type": "count"})
        assert filtered.status_code == 200, "metric_type=count must be an accepted filter value"
        assert [item["id"] for item in filtered.json()["projects"]] == [project_id]

        other_family = client.get("/api/v1/projects", params={"metric_type": "binary"})
        assert other_family.status_code == 200
        assert other_family.json()["projects"] == []

        loaded = client.get(f"/api/v1/projects/{project_id}")
        assert loaded.status_code == 200
        assert loaded.json()["payload"]["metrics"]["metric_type"] == "count"

        updated = client.put(f"/api/v1/projects/{project_id}", json=_count_payload("Reads per session v2"))
        assert updated.status_code == 200
        assert updated.json()["payload"]["metrics"]["metric_type"] == "count"

        archived = client.post(f"/api/v1/projects/{project_id}/archive")
        assert archived.status_code == 200

        active = client.get("/api/v1/projects")
        assert active.status_code == 200
        assert active.json()["projects"] == []

        archived_list = client.get("/api/v1/projects", params={"status": "archived", "metric_type": "count"})
        assert archived_list.status_code == 200
        assert [item["id"] for item in archived_list.json()["projects"]] == [project_id]


def test_one_count_project_does_not_hide_the_rest_of_the_workspace(monkeypatch) -> None:
    """The reported defect: a mixed workspace 400s, so every project disappears at once."""
    _isolated_db(monkeypatch)

    with TestClient(create_app()) as client:
        binary = client.post("/api/v1/projects", json=_binary_payload("Checkout redesign"))
        assert binary.status_code == 200
        count = client.post("/api/v1/projects", json=_count_payload("Reads per session"))
        assert count.status_code == 200

        listed = client.get("/api/v1/projects")

        assert listed.status_code == 200
        returned = {item["id"]: item["metric_type"] for item in listed.json()["projects"]}
        assert returned == {binary.json()["id"]: "binary", count.json()["id"]: "count"}


def test_every_supported_metric_family_is_an_accepted_list_filter(monkeypatch) -> None:
    """Guards the drift itself: a new family in MetricType must reach the filter too."""
    _isolated_db(monkeypatch)

    with TestClient(create_app()) as client:
        for metric_type in METRIC_TYPES:
            response = client.get("/api/v1/projects", params={"metric_type": metric_type})
            assert response.status_code == 200, f"{metric_type} is planned but rejected as a filter"
