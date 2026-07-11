from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

try:
    from testcontainers.postgres import PostgresContainer
except ImportError:  # pragma: no cover - exercised when deps are not installed yet
    PostgresContainer = None

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings
from app.backend.app.main import create_app
from app.backend.app.repository import ProjectRepository, create_backend
from app.backend.app.repository._migrations import EXPECTED_POSTGRES_SCHEMA_VERSION


def test_create_backend_uses_sqlite_backend_for_sqlite_urls() -> None:
    expected_backend = SimpleNamespace(backend_name="sqlite", supports_snapshots=True)

    with patch("app.backend.app.repository.SQLiteBackend", return_value=expected_backend) as sqlite_backend:
        with patch("app.backend.app.repository.PostgresBackend") as postgres_backend:
            backend = create_backend(
                "sqlite:///D:/AB_TEST/app/backend/data/projects.sqlite3",
                busy_timeout_ms=7000,
                journal_mode="WAL",
                synchronous="NORMAL",
                workspace_signing_key="a" * 16,
                pool_size=12,
            )

    assert backend is expected_backend
    sqlite_backend.assert_called_once()
    postgres_backend.assert_not_called()


def test_create_backend_uses_postgres_backend_for_postgresql_urls() -> None:
    expected_backend = SimpleNamespace(backend_name="postgres", supports_snapshots=False)

    with patch("app.backend.app.repository.SQLiteBackend") as sqlite_backend:
        with patch("app.backend.app.repository.PostgresBackend", return_value=expected_backend) as postgres_backend:
            backend = create_backend(
                "postgresql://postgres:postgres@localhost:5432/abtest",
                busy_timeout_ms=7000,
                journal_mode="WAL",
                synchronous="NORMAL",
                workspace_signing_key="a" * 16,
                pool_size=12,
            )

    assert backend is expected_backend
    sqlite_backend.assert_not_called()
    postgres_backend.assert_called_once()


def test_project_repository_delegates_to_selected_backend() -> None:
    backend = SimpleNamespace(
        backend_name="postgres",
        supports_snapshots=False,
        schema_version=7,
        list_projects=lambda include_archived=False: [{"id": "project-1", "include_archived": include_archived}],
    )

    with patch("app.backend.app.repository.create_backend", return_value=backend) as create_backend_mock:
        repository = ProjectRepository(
            "postgresql://postgres:postgres@localhost:5432/abtest",
            pool_size=12,
        )

    assert repository.backend_name == "postgres"
    assert repository.supports_snapshots is False
    assert repository.schema_version == 7
    assert repository.list_projects(include_archived=True) == [{"id": "project-1", "include_archived": True}]
    create_backend_mock.assert_called_once()


def _require_docker() -> None:
    if sys.platform == "win32":
        pytest.skip("Linux containers unavailable on Windows GitHub runner")
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("Docker unavailable")


def _postgres_url(container: PostgresContainer) -> str:
    return container.get_connection_url().replace("+psycopg2", "")


def _payload(name: str, metric_type: str) -> dict:
    return {
        "project": {"project_name": name},
        "hypothesis": {
            "hypothesis_statement": f"{name} hypothesis",
            "change_description": f"{name} change",
        },
        "metrics": {"metric_type": metric_type},
    }


@pytest.fixture(scope="module")
def postgres_repository():
    if PostgresContainer is None:
        pytest.fail("testcontainers is required for Postgres backend tests")
    _require_docker()
    with PostgresContainer("postgres:16-alpine") as postgres:
        repository = ProjectRepository(_postgres_url(postgres), pool_size=4)
        yield repository
        close = getattr(repository, "close", None)
        if callable(close):
            close()


def test_postgres_backend_round_trips_project_reads_and_queries() -> None:
    if PostgresContainer is None:
        pytest.fail("testcontainers is required for Postgres backend tests")
    _require_docker()

    with PostgresContainer("postgres:16-alpine") as postgres:
        repository = ProjectRepository(_postgres_url(postgres), pool_size=4)

        binary_project = repository.create_project(_payload("Binary project", "binary"))
        continuous_project = repository.create_project(_payload("Continuous project", "continuous"))

        assert repository.backend_name == "postgres"
        assert repository.supports_snapshots is False
        assert repository.get_project(binary_project["id"])["project_name"] == "Binary project"
        assert repository.query_projects(metric_type="binary")["projects"][0]["id"] == binary_project["id"]
        assert {project["id"] for project in repository.list_projects(include_archived=True)} == {
            binary_project["id"],
            continuous_project["id"],
        }


def test_postgres_backend_handles_concurrent_writes() -> None:
    if PostgresContainer is None:
        pytest.fail("testcontainers is required for Postgres backend tests")
    _require_docker()

    with PostgresContainer("postgres:16-alpine") as postgres:
        repository = ProjectRepository(_postgres_url(postgres), pool_size=6)

        def create(index: int) -> str:
            created = repository.create_project(_payload(f"Project {index}", "binary"))
            return created["id"]

        with ThreadPoolExecutor(max_workers=4) as executor:
            project_ids = list(executor.map(create, range(8)))

        assert len(project_ids) == 8
        assert len(set(project_ids)) == 8
        assert repository.query_projects(limit=20)["total"] == 8


def test_postgres_backend_workspace_export_import_round_trip(postgres_repository) -> None:
    repo = postgres_repository
    a = repo.create_project(_payload("Workspace A", "binary"))
    b = repo.create_project(_payload("Workspace B", "continuous"))

    bundle = repo.export_workspace()
    assert {p["project_name"] for p in bundle["projects"]} >= {"Workspace A", "Workspace B"}

    repo.delete_project(a["id"])
    repo.delete_project(b["id"])

    result = repo.import_workspace(bundle)
    assert result["imported_projects"] >= 2
    imported_names = {p["project_name"] for p in repo.list_projects(include_archived=True)}
    assert {"Workspace A", "Workspace B"}.issubset(imported_names)


def test_postgres_backend_api_key_lifecycle(postgres_repository) -> None:
    repo = postgres_repository
    created = repo.create_api_key(name="ci-key", scope="readonly")
    plaintext = created["plaintext_key"]
    assert plaintext.startswith("abk_")

    listed = repo.list_api_keys()
    assert any(k["id"] == created["id"] for k in listed["keys"])

    authenticated = repo.authenticate_api_key(plaintext)
    assert authenticated is not None and authenticated["id"] == created["id"]

    revoked = repo.revoke_api_key(created["id"])
    assert revoked is not None and revoked["revoked_at"] is not None
    assert repo.authenticate_api_key(plaintext) is None  # revoked keys do not authenticate

    deleted = repo.delete_api_key(created["id"])
    assert deleted is not None
    assert all(k["id"] != created["id"] for k in repo.list_api_keys()["keys"])


def test_postgres_backend_webhook_subscription_crud(postgres_repository) -> None:
    repo = postgres_repository
    sub = repo.create_webhook_subscription(
        name="ci-webhook",
        target_url="https://example.invalid/hook",
        secret="s" * 32,
        format="generic",
        event_filter=["project_updated"],
        scope="global",
    )
    assert sub["id"]

    listed = repo.list_webhook_subscriptions(include_secret=False)
    assert any(s["id"] == sub["id"] for s in listed["subscriptions"])
    fetched = repo.get_webhook_subscription(sub["id"], include_secret=True)
    assert fetched is not None and fetched["secret"] == "s" * 32

    repo.delete_webhook_subscription(sub["id"])
    assert repo.get_webhook_subscription(sub["id"]) is None


def test_postgres_backend_audit_log_round_trip(postgres_repository) -> None:
    repo = postgres_repository
    project = repo.create_project(_payload("Audit subject", "binary"))
    event = repo.log_audit_entry(
        action="project_updated",
        actor="ci-test",
        request_id="req-ci-1",
        ip_address="127.0.0.1",
        project_id=project["id"],
        project_name=project["project_name"],
        dispatch_webhooks=False,
    )
    assert event["id"]

    listed = repo.list_audit_entries(project_id=project["id"])
    actions = [entry["action"] for entry in listed["entries"]]
    assert "project_updated" in actions


def test_postgres_backend_slack_installation_upsert(postgres_repository) -> None:
    repo = postgres_repository
    repo.upsert_slack_installation(
        team_id="T-CI",
        team_name="CI Workspace",
        bot_token="xoxb-ci-1",
    )
    fetched = repo.get_slack_installation("T-CI")
    assert fetched is not None and fetched["bot_token"] == "xoxb-ci-1"

    repo.upsert_slack_installation(
        team_id="T-CI",
        team_name="CI Workspace",
        bot_token="xoxb-ci-2",
    )
    refreshed = repo.get_slack_installation("T-CI")
    assert refreshed is not None and refreshed["bot_token"] == "xoxb-ci-2"


def test_postgres_backend_query_filters_and_pagination(postgres_repository) -> None:
    repo = postgres_repository
    initial_total = repo.query_projects(limit=1000)["total"]

    binary_a = repo.create_project(_payload("Filter binary A", "binary"))
    binary_b = repo.create_project(_payload("Filter binary B", "binary"))
    repo.create_project(_payload("Filter continuous", "continuous"))
    ratio_project = repo.create_project(_payload("Filter ratio", "ratio"))
    repo.archive_project(binary_b["id"])

    only_binary = repo.query_projects(metric_type="binary", status="active")
    binary_ids = {p["id"] for p in only_binary["projects"]}
    assert binary_a["id"] in binary_ids
    assert binary_b["id"] not in binary_ids

    only_ratio = repo.query_projects(metric_type="ratio", status="active")
    assert {p["id"] for p in only_ratio["projects"]} == {ratio_project["id"]}

    archived = repo.query_projects(status="archived")
    assert binary_b["id"] in {p["id"] for p in archived["projects"]}

    paged = repo.query_projects(limit=1, offset=0)
    assert len(paged["projects"]) == 1
    # +3 created, but binary_b is archived → +2 in default status="active" filter.
    assert paged["total"] >= initial_total + 2


def test_postgres_backend_cuped_aggregates_round_trip(postgres_repository) -> None:
    # Exercises the E5 pre-period ingestion (ON CONFLICT dedup) and the CUPED sufficient-statistics
    # CTE on a real Postgres, validating the portable dual-backend SQL (translated ? -> %s).
    repo = postgres_repository
    project = repo.create_project(_payload("CUPED PG", "continuous"))
    exp = project["id"]
    repo.record_exposures(
        exp,
        [
            {"user_id": "u1", "variation_index": 0},
            {"user_id": "u2", "variation_index": 0},
            {"user_id": "u3", "variation_index": 0},  # no covariate -> excluded
            {"user_id": "u4", "variation_index": 1},
            {"user_id": "u5", "variation_index": 1},
            {"user_id": "uH", "variation_index": -1},  # holdout -> excluded
        ],
    )
    assert repo.record_pre_period_values(
        exp,
        [
            {"user_id": "u1", "value": 10.0},
            {"user_id": "u2", "value": 20.0},
            {"user_id": "u4", "value": 40.0},
            {"user_id": "u5", "value": 50.0},
        ],
    ) == {"received": 4, "recorded": 4, "deduplicated": 0}
    # First-write-wins dedup holds on Postgres too.
    assert repo.record_pre_period_values(exp, [{"user_id": "u1", "value": 99.0}])["deduplicated"] == 1
    repo.record_conversions(
        exp,
        [
            {"user_id": "u1", "metric": "aov", "value": 2.0},
            {"user_id": "u2", "metric": "aov", "value": 3.0},
            {"user_id": "u4", "metric": "aov", "value": 5.0},
            # u5 has no conversion -> Y = 0
        ],
    )

    aggregates = repo.get_cuped_aggregates(exp, "aov")
    assert aggregates is not None
    assert aggregates["covariate_names"] == ["__default__"]  # legacy single-covariate ingestion
    by_index = {arm["variation_index"]: arm for arm in aggregates["variations"]}
    assert by_index[0]["n"] == 2  # u1, u2 (u3 has no covariate)
    assert by_index[0]["sum_x"] == [30.0]
    assert by_index[0]["sum_y"] == 5.0
    assert by_index[0]["sum_xy"] == [80.0]  # 10*2 + 20*3
    assert by_index[1]["n"] == 2  # u4, u5
    assert by_index[1]["sum_y"] == 5.0  # u4: 5.0 + u5: 0
    assert by_index[1]["sum_xy"] == [200.0]  # 40*5 + 50*0
    assert -1 not in by_index  # holdout never appears


def test_postgres_backend_multi_cuped_aggregates_round_trip(postgres_repository) -> None:
    # Exercises the F3a multi-covariate CUPED rollup (covariate discovery + the self-join cross-moment
    # CTEs + the complete-vector HAVING filter) on a real Postgres, validating the portable dual-backend
    # SQL (translated ? -> %s) that cannot be checked on Windows without a Postgres.
    repo = postgres_repository
    project = repo.create_project(_payload("Multi CUPED PG", "continuous"))
    exp = project["id"]
    repo.record_exposures(
        exp,
        [
            {"user_id": "a", "variation_index": 0},
            {"user_id": "b", "variation_index": 0},
            {"user_id": "c", "variation_index": 0},  # only one covariate -> incomplete -> excluded
        ],
    )
    repo.record_pre_period_values(
        exp,
        [
            {"user_id": "a", "covariate_name": "spend", "value": 2.0},
            {"user_id": "a", "covariate_name": "visits", "value": 1.0},
            {"user_id": "b", "covariate_name": "spend", "value": 4.0},
            {"user_id": "b", "covariate_name": "visits", "value": 3.0},
            {"user_id": "c", "covariate_name": "spend", "value": 9.0},  # no "visits"
        ],
    )
    repo.record_conversions(
        exp,
        [
            {"user_id": "a", "metric": "aov", "value": 10.0},
            {"user_id": "b", "metric": "aov", "value": 20.0},
        ],
    )

    aggregates = repo.get_cuped_aggregates(exp, "aov")
    assert aggregates is not None
    assert aggregates["covariate_names"] == ["spend", "visits"]  # discovered, sorted
    assert aggregates["too_many_covariates"] is False
    arm0 = {arm["variation_index"]: arm for arm in aggregates["variations"]}[0]
    assert arm0["n"] == 2  # a, b (c dropped — incomplete vector)
    assert arm0["sum_x"] == [6.0, 4.0]  # spend 2+4, visits 1+3
    assert arm0["sum_y"] == 30.0 and arm0["sum_y2"] == 500.0
    assert arm0["sum_xx"] == [[20.0, 14.0], [14.0, 10.0]]  # symmetric raw cross-moments
    assert arm0["sum_xy"] == [100.0, 70.0]  # spend*y 20+80, visits*y 10+60


def test_postgres_backend_ratio_aggregates_round_trip(postgres_repository) -> None:
    # Exercises the F2 ratio sufficient-statistics CTE (numerator/denominator CASE rollup) on a real
    # Postgres, validating the portable dual-backend SQL (translated ? -> %s). The CTE is independent
    # of the design metric_type — it rolls up two named conversion metrics per exposed user.
    repo = postgres_repository
    project = repo.create_project(_payload("Ratio PG", "binary"))
    exp = project["id"]
    repo.record_exposures(
        exp,
        [
            {"user_id": "u1", "variation_index": 0},
            {"user_id": "u2", "variation_index": 0},
            {"user_id": "u3", "variation_index": 1},
            {"user_id": "u4", "variation_index": 1},  # exposed, no events -> (x=0, y=0)
            {"user_id": "uH", "variation_index": -1},  # holdout -> excluded
        ],
    )
    repo.record_conversions(
        exp,
        [
            {"user_id": "u1", "metric": "clicks", "value": 2.0},
            {"user_id": "u1", "metric": "impressions", "value": 10.0},
            {"user_id": "u2", "metric": "clicks", "value": 1.0},
            {"user_id": "u2", "metric": "impressions", "value": 20.0},
            {"user_id": "u3", "metric": "clicks", "value": 5.0},
            {"user_id": "u3", "metric": "impressions", "value": 50.0},
            {"user_id": "uH", "metric": "clicks", "value": 100.0},  # holdout -> excluded
        ],
    )

    aggregates = repo.get_ratio_aggregates(exp, "clicks", "impressions")
    assert aggregates is not None
    by_index = {arm["variation_index"]: arm for arm in aggregates["variations"]}
    assert by_index[0]["n"] == 2  # u1, u2
    assert by_index[0]["sum_x"] == 30.0  # impressions 10 + 20
    assert by_index[0]["sum_y"] == 3.0  # clicks 2 + 1
    assert by_index[0]["sum_xy"] == 40.0  # 10*2 + 20*1
    assert by_index[1]["n"] == 2  # u3, u4 (u4 has no events but is still counted)
    assert by_index[1]["sum_x"] == 50.0
    assert by_index[1]["sum_xy"] == 250.0  # 50*5 + 0
    assert -1 not in by_index  # holdout never appears


def test_postgres_backend_stratified_aggregates_round_trip(postgres_repository) -> None:
    # Exercises the F3b post-stratification rollup (user_strata inner join + GROUP BY stratum,
    # variation) on a real Postgres, validating the portable dual-backend SQL (translated ? -> %s)
    # and first-write-wins strata dedup that cannot be checked on Windows without a Postgres.
    repo = postgres_repository
    project = repo.create_project(_payload("Stratified PG", "binary"))
    exp = project["id"]
    repo.record_exposures(
        exp,
        [
            {"user_id": "u1", "variation_index": 0},
            {"user_id": "u2", "variation_index": 0},
            {"user_id": "u3", "variation_index": 1},
            {"user_id": "u4", "variation_index": 1},
            {"user_id": "u5", "variation_index": 0},  # no stratum -> excluded
            {"user_id": "uH", "variation_index": -1},  # holdout -> excluded
        ],
    )
    assert repo.record_strata(
        exp,
        [
            {"user_id": "u1", "stratum": "ios"},
            {"user_id": "u2", "stratum": "android"},
            {"user_id": "u3", "stratum": "ios"},
            {"user_id": "u4", "stratum": "android"},
        ],
    ) == {"received": 4, "recorded": 4, "deduplicated": 0}
    # First-write-wins dedup holds on Postgres too.
    assert repo.record_strata(exp, [{"user_id": "u1", "stratum": "android"}])["deduplicated"] == 1
    repo.record_conversions(
        exp,
        [
            {"user_id": "u1", "metric": "purchase", "value": 1.0},
            {"user_id": "u3", "metric": "purchase", "value": 1.0},
        ],
    )

    aggregates = repo.get_stratified_aggregates(exp, "purchase")
    assert aggregates is not None
    assert aggregates["num_strata"] == 2
    by_name = {stratum["stratum"]: stratum for stratum in aggregates["strata"]}
    assert sorted(by_name) == ["android", "ios"]
    ios = {arm["variation_index"]: arm for arm in by_name["ios"]["variations"]}
    assert ios[0]["exposed_users"] == 1 and ios[0]["converted_users"] == 1  # u1 (kept ios)
    assert ios[1]["exposed_users"] == 1 and ios[1]["converted_users"] == 1  # u3
    android = {arm["variation_index"]: arm for arm in by_name["android"]["variations"]}
    assert android[0]["exposed_users"] == 1 and android[0]["converted_users"] == 0  # u2
    assert android[1]["exposed_users"] == 1 and android[1]["converted_users"] == 0  # u4
    total_users = sum(arm["exposed_users"] for s in aggregates["strata"] for arm in s["variations"])
    assert total_users == 4  # u5 (no stratum) and uH (holdout) never appear


def test_postgres_backend_holdout_aggregates_round_trip(postgres_repository) -> None:
    # Exercises the F5 holdout rollup (variation_index = -1 selection) on a real Postgres, validating
    # the portable dual-backend SQL (translated ? -> %s) and that record_holdout writes the held-back
    # tail as -1 exposures with first-write-wins dedup — neither checkable on Windows without Postgres.
    repo = postgres_repository
    project = repo.create_project(_payload("Holdout PG", "binary"))
    exp = project["id"]
    repo.record_exposures(
        exp,
        [
            {"user_id": "t1", "variation_index": 1},
            {"user_id": "t2", "variation_index": 1},
            {"user_id": "c1", "variation_index": 0},
        ],
    )
    assert repo.record_holdout(
        exp, [{"user_id": "h1"}, {"user_id": "h2"}, {"user_id": "h3"}]
    ) == {"received": 3, "recorded": 3, "deduplicated": 0}
    # A user already exposed to an arm cannot also be held back (first-write-wins on the exposure key).
    assert repo.record_holdout(exp, [{"user_id": "t1"}])["deduplicated"] == 1
    repo.record_conversions(
        exp,
        [
            {"user_id": "t1", "metric": "purchase", "value": 1.0},
            {"user_id": "h1", "metric": "purchase", "value": 1.0},
            {"user_id": "h2", "metric": "purchase", "value": 1.0},
        ],
    )

    holdout = repo.get_holdout_aggregates(exp, "purchase")
    assert holdout is not None
    assert holdout["holdout"]["exposed_users"] == 3  # h1, h2, h3 (t1 stayed in its arm)
    assert holdout["holdout"]["converted_users"] == 2  # h1, h2
    assert holdout["holdout"]["value_sum"] == 2.0

    # The held-back tail never leaks into the per-arm primary rollup (variation_index >= 0).
    arms = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert arms is not None
    by_index = {arm["variation_index"]: arm for arm in arms["variations"]}
    assert -1 not in by_index
    assert by_index[1]["exposed_users"] == 2  # t1, t2
    assert by_index[1]["converted_users"] == 1  # t1


def test_postgres_backend_event_time_occurred_at_round_trip(postgres_repository) -> None:
    # Exercises the P4.1 event-time column (occurred_at) on a real Postgres: a supplied client event
    # time is stored distinctly from created_at, an omitted one defaults to the server-receive time,
    # and holdout's -1 tail keeps the NOT NULL column populated. None of this is checkable on Windows
    # without a Postgres (the SQLite suite covers the same behaviour on its own backend).
    repo = postgres_repository
    project = repo.create_project(_payload("Event-time PG", "binary"))
    exp = project["id"]
    exposure_time = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    conversion_time = datetime(2026, 5, 1, 13, 0, 0, tzinfo=UTC)
    repo.record_exposures(
        exp,
        [
            {"user_id": "u1", "variation_index": 0, "occurred_at": exposure_time},
            {"user_id": "u2", "variation_index": 1},  # no occurred_at -> defaults to created_at
        ],
    )
    repo.record_conversions(
        exp,
        [
            {"user_id": "u1", "metric": "purchase", "occurred_at": conversion_time},
            {"user_id": "u2", "metric": "purchase"},  # no occurred_at -> defaults to created_at
        ],
    )
    repo.record_holdout(exp, [{"user_id": "h1"}])

    with repo._backend._connect() as connection:  # type: ignore[attr-defined]
        exposures = {
            row["user_id"]: (row["created_at"], row["occurred_at"])
            for row in connection.execute(
                "SELECT user_id, created_at, occurred_at FROM exposures WHERE experiment_id = ?",
                (exp,),
            ).fetchall()
        }
        conversions = {
            row["user_id"]: (row["created_at"], row["occurred_at"])
            for row in connection.execute(
                "SELECT user_id, created_at, occurred_at FROM conversions WHERE experiment_id = ?",
                (exp,),
            ).fetchall()
        }

    # Supplied event time is stored (UTC-normalized), separate from the server-receive time.
    assert exposures["u1"][1] == exposure_time.isoformat()
    assert exposures["u1"][1] != exposures["u1"][0]
    assert conversions["u1"][1] == conversion_time.isoformat()
    # Omitted event time and the holdout tail default to the server-receive time.
    assert exposures["u2"][1] == exposures["u2"][0]
    assert conversions["u2"][1] == conversions["u2"][0]
    assert exposures["h1"][1] == exposures["h1"][0]


def test_postgres_backend_event_timing_summary_round_trip(postgres_repository) -> None:
    # Exercises the P4.2 late / out-of-order classification on a real Postgres: the timing query
    # joins conversions to exposures and the counts come back correctly through the dual-backend SQL.
    # Not checkable on Windows without a Postgres (the SQLite suite covers the same logic).
    repo = postgres_repository
    project = repo.create_project(_payload("Event-timing PG", "binary"))
    exp = project["id"]

    def at(day: int) -> datetime:
        return datetime(2026, 6, day, 12, 0, 0, tzinfo=UTC)

    repo.record_exposures(
        exp,
        [
            {"user_id": "u1", "variation_index": 0, "occurred_at": at(1)},
            {"user_id": "u2", "variation_index": 1, "occurred_at": at(1)},
            {"user_id": "u3", "variation_index": 0, "occurred_at": at(10)},
        ],
    )
    repo.record_conversions(
        exp,
        [
            {"user_id": "u1", "metric": "purchase", "occurred_at": at(2)},  # in-window
            {"user_id": "u2", "metric": "purchase", "occurred_at": at(25)},  # late (+24d > 14)
            {"user_id": "u3", "metric": "purchase", "occurred_at": at(8)},  # out-of-order
        ],
    )
    repo.record_holdout(exp, [{"user_id": "h1"}])
    repo.record_conversions(exp, [{"user_id": "h1", "metric": "purchase", "occurred_at": at(2)}])

    summary = repo.get_event_timing_summary(exp, "purchase", 14.0)
    assert summary is not None
    assert summary["in_window"] == 1
    assert summary["late"] == 1
    assert summary["out_of_order"] == 1
    assert summary["total"] == 3  # holdout conversion excluded


def test_postgres_backend_identity_resolution_round_trip(postgres_repository) -> None:
    # Exercises the P4.3 identity-resolution rollup on a real Postgres: the resolution CTE folds each
    # user's events onto their canonical id (COALESCE + string `||` order key + MIN first-exposure-wins
    # + the EXISTS summary subqueries) — the dual-backend SQL paths most prone to SQLite/Postgres
    # divergence. Not checkable on Windows without a Postgres (the SQLite suite covers the same logic).
    repo = postgres_repository
    project = repo.create_project(_payload("Identity PG", "binary"))
    exp = project["id"]

    def at(day: int) -> datetime:
        return datetime(2026, 6, day, 12, 0, 0, tzinfo=UTC)

    # 'anon' exposed first (arm 0), re-exposed after login as 'user' (arm 1); a conversion lands under
    # 'user'. After linking anon → user the person is one canonical unit in their first arm (0).
    repo.record_exposures(exp, [{"user_id": "anon", "variation_index": 0, "occurred_at": at(1)}])
    repo.record_exposures(exp, [{"user_id": "user", "variation_index": 1, "occurred_at": at(2)}])
    repo.record_conversions(exp, [{"user_id": "user", "metric": "purchase", "occurred_at": at(3)}])
    repo.record_identities(exp, [{"anonymous_id": "anon", "canonical_id": "user"}])

    aggregates = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert aggregates is not None
    by_index = {v["variation_index"]: v for v in aggregates["variations"]}
    # Collapsed to one canonical user in arm 0 (first-exposure-wins); no SRM inflation.
    assert sum(v["exposed_users"] for v in aggregates["variations"]) == 1
    assert by_index[0]["exposed_users"] == 1
    assert by_index[0]["converted_users"] == 1  # 'user' conversion resolves onto the canonical unit

    summary = repo.get_identity_resolution_summary(exp)
    assert summary is not None
    assert summary["linked_identities"] == 1
    assert summary["canonicalized_events"] == 1  # the 'anon' exposure was re-attributed
    assert summary["merged_users"] == 1

    # First-write-wins canonical + self-link skip behave the same on Postgres.
    assert repo.record_identities(exp, [{"anonymous_id": "anon", "canonical_id": "other"}])["recorded"] == 0
    assert repo.record_identities(exp, [{"anonymous_id": "z", "canonical_id": "z"}]) == {
        "received": 1,
        "recorded": 0,
        "deduplicated": 0,
    }


def test_postgres_backend_exclusion_filter_round_trip(postgres_repository) -> None:
    # Exercises the P4.4 bot / fraud filter on a real Postgres: the rollup's two NOT EXISTS anti-joins
    # (manual deny-list + rate-spike HAVING COUNT) and the exclusion summary's CASE/EXISTS counts — the
    # dual-backend SQL added on top of the resolution CTE. Not checkable on Windows without a Postgres.
    from app.backend.app.constants import BOT_CONVERSION_EVENT_THRESHOLD

    repo = postgres_repository
    project = repo.create_project(_payload("Exclusion PG", "binary"))
    exp = project["id"]

    repo.record_exposures(
        exp,
        [
            {"user_id": "human", "variation_index": 1},
            {"user_id": "manual_bad", "variation_index": 1},
            {"user_id": "bot", "variation_index": 1},
        ],
    )
    repo.record_conversions(exp, [{"user_id": "human", "metric": "purchase"}])
    repo.record_conversions(
        exp,
        [
            {"user_id": "bot", "metric": "purchase", "idempotency_key": f"k{i}"}
            for i in range(BOT_CONVERSION_EVENT_THRESHOLD + 1)
        ],
    )
    repo.record_exclusions(exp, [{"user_id": "manual_bad", "exclusion_reason": "fraud"}])

    aggregates = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert aggregates is not None
    arm = next(v for v in aggregates["variations"] if v["variation_index"] == 1)
    assert arm["exposed_users"] == 1  # only 'human'; 'manual_bad' + 'bot' removed
    summary = repo.get_exclusion_summary(exp, "purchase")
    assert summary is not None
    assert summary["manual_filtered"] == 1
    assert summary["rate_spike_filtered"] == 1
    assert summary["total_filtered"] == 2
    # First-write-wins on the deny-list behaves the same on Postgres.
    assert repo.record_exclusions(exp, [{"user_id": "manual_bad", "exclusion_reason": "other"}])["recorded"] == 0


def test_readyz_uses_postgres_checks_without_sqlite_regression(monkeypatch) -> None:
    monkeypatch.setenv("AB_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/abtest")
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    get_settings.cache_clear()

    repository = SimpleNamespace(
        backend_name="postgres",
        supports_snapshots=False,
        schema_version=7,
        has_api_keys=lambda: False,
        set_webhook_service=lambda webhook_service: None,
        get_diagnostics_summary=lambda: {
            "db_path": "postgresql://postgres:postgres@localhost:5432/abtest",
            "db_parent_path": "localhost:5432",
            "db_exists": True,
            "db_size_bytes": 1024,
            "disk_free_bytes": 0,
            "schema_version": 7,
            "sqlite_user_version": 7,
            "busy_timeout_ms": 0,
            "journal_mode": "POSTGRES",
            "synchronous": "READ COMMITTED",
            "write_probe_ok": True,
            "write_probe_detail": "BEGIN succeeded",
            "projects_total": 0,
            "archived_projects_total": 0,
            "analysis_runs_total": 0,
            "export_events_total": 0,
            "project_revisions_total": 0,
            "workspace_bundle_schema_version": 3,
            "workspace_signature_enabled": False,
            "latest_project_updated_at": None,
        },
        close=lambda: None,
    )

    with patch("app.backend.app.main.ProjectRepository", return_value=repository):
        with patch("app.backend.app.main.WebhookService") as webhook_service_cls:
            webhook_service = webhook_service_cls.return_value
            webhook_service.shutdown.return_value = None

            with TestClient(create_app()) as client:
                response = client.get("/readyz")

    assert response.status_code == 200
    checks = response.json()["checks"]
    assert any(check["name"] == "postgres_storage" and check["ok"] is True for check in checks)
    assert any(check["name"] == "postgres_write_probe" and check["ok"] is True for check in checks)
    assert not any(check["name"] == "sqlite_journal_mode" for check in checks)
    get_settings.cache_clear()


# --- F-02: the PostgreSQL upgrade path -------------------------------------------------------
#
# `CREATE TABLE IF NOT EXISTS` is a no-op on a table that already exists, so `occurred_at`
# (added to exposures/conversions on 2026-06-26; both tables created 2026-06-14) never reached
# a database provisioned in that window. These drills prove the migration runner repairs such a
# database without losing rows, and that readiness now refuses to serve one that is behind.


def _legacy_database(connection_url: str) -> None:
    """Rewind a current database to its pre-2026-06-26 shape, keeping the rows.

    Building the old schema by hand would drift from the real one; rewinding the real schema
    cannot. Dropping `schema_migrations` reproduces a database that predates the runner itself.
    """
    import psycopg

    with psycopg.connect(connection_url, autocommit=True) as connection:
        connection.execute("ALTER TABLE exposures DROP COLUMN occurred_at")
        connection.execute("ALTER TABLE conversions DROP COLUMN occurred_at")
        connection.execute("DROP TABLE IF EXISTS schema_migrations")


def _seed_legacy_rows(connection_url: str, project_id: str) -> str:
    import psycopg

    created_at = "2026-06-20T10:00:00+00:00"
    with psycopg.connect(connection_url, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO exposures (id, experiment_id, user_id, variation_index, created_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            ("exposure-legacy", project_id, "user-1", 1, created_at),
        )
        connection.execute(
            "INSERT INTO conversions (id, experiment_id, user_id, metric, value, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            ("conversion-legacy", project_id, "user-1", "purchase", 1.0, created_at),
        )
    return created_at


def test_postgres_migrates_a_legacy_database_without_losing_data() -> None:
    if PostgresContainer is None:
        pytest.fail("testcontainers is required for Postgres backend tests")
    _require_docker()

    import psycopg

    with PostgresContainer("postgres:16-alpine") as postgres:
        url = _postgres_url(postgres)

        repository = ProjectRepository(url, pool_size=2)
        project = repository.create_project(_payload("Legacy project", "binary"))
        repository.close()

        _legacy_database(url)
        created_at = _seed_legacy_rows(url, project["id"])

        # The upgrade: a current build opening an old database.
        migrated = ProjectRepository(url, pool_size=2)

        with psycopg.connect(url, autocommit=True) as connection:
            exposure = connection.execute(
                "SELECT occurred_at, created_at FROM exposures WHERE id = 'exposure-legacy'"
            ).fetchone()
            conversion = connection.execute(
                "SELECT occurred_at, created_at FROM conversions WHERE id = 'conversion-legacy'"
            ).fetchone()
            nullability = connection.execute(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'exposures' AND column_name = 'occurred_at'"
            ).fetchone()
            recorded_version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()

        # The column is back, backfilled from created_at — and the rows are still there.
        assert exposure == (created_at, created_at)
        assert conversion == (created_at, created_at)
        assert nullability == ("NO",)
        assert recorded_version == (EXPECTED_POSTGRES_SCHEMA_VERSION,)
        assert migrated.get_project(project["id"])["project_name"] == "Legacy project"
        assert migrated.read_applied_schema_version() == EXPECTED_POSTGRES_SCHEMA_VERSION

        migrated.close()


def test_postgres_migrations_are_idempotent_across_restarts() -> None:
    if PostgresContainer is None:
        pytest.fail("testcontainers is required for Postgres backend tests")
    _require_docker()

    import psycopg

    with PostgresContainer("postgres:16-alpine") as postgres:
        url = _postgres_url(postgres)

        for _ in range(3):
            repository = ProjectRepository(url, pool_size=2)
            repository.close()

        with psycopg.connect(url, autocommit=True) as connection:
            rows = connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()

        # Restarting must not re-apply or duplicate a migration.
        assert rows == [(EXPECTED_POSTGRES_SCHEMA_VERSION,)]


def test_readyz_reports_503_when_the_database_is_behind_the_expected_schema(monkeypatch) -> None:
    """The check that used to compare a constant with itself must now catch a real drift."""
    if PostgresContainer is None:
        pytest.fail("testcontainers is required for Postgres backend tests")
    _require_docker()

    import psycopg

    with PostgresContainer("postgres:16-alpine") as postgres:
        url = _postgres_url(postgres)
        monkeypatch.setenv("AB_DATABASE_URL", url)
        monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
        get_settings.cache_clear()

        client = TestClient(create_app())

        healthy = client.get("/readyz")
        assert healthy.status_code == 200

        # Simulate a deploy whose migration never ran: the code expects N, the database is at 0.
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute("DELETE FROM schema_migrations")

        degraded = client.get("/readyz")

        assert degraded.status_code == 503
        checks = {check["name"]: check for check in degraded.json()["checks"]}
        assert checks["postgres_schema_version"]["ok"] is False
        assert "pending migration" in checks["postgres_schema_version"]["detail"]

    get_settings.cache_clear()
