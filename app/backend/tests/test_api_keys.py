import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings
from app.backend.app.main import create_app
from app.backend.app.repository import ProjectRepository
from app.backend.app.repository._utils import hash_api_key


def _admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer admin-secret-token"}


def _tmp_db(monkeypatch, **env: str) -> Path:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"
    monkeypatch.setenv("AB_DB_PATH", str(db_path))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    return db_path


def test_api_key_management_crud_flow(monkeypatch) -> None:
    _tmp_db(monkeypatch, AB_ADMIN_TOKEN="admin-secret-token")

    with TestClient(create_app()) as client:
        created = client.post(
            "/api/v1/keys",
            headers=_admin_headers(),
            json={
                "name": "Partner read key",
                "scope": "read",
            },
        )
        listed = client.get("/api/v1/keys", headers=_admin_headers())
        revoked = client.post(
            f"/api/v1/keys/{created.json()['id']}/revoke",
            headers=_admin_headers(),
        )
        deleted = client.delete(
            f"/api/v1/keys/{created.json()['id']}",
            headers=_admin_headers(),
        )
        listed_after_delete = client.get("/api/v1/keys", headers=_admin_headers())

    assert created.status_code == 200
    assert created.json()["plaintext_key"]
    assert created.json()["scope"] == "read"
    assert listed.status_code == 200
    assert listed.json()["keys"][0]["id"] == created.json()["id"]
    assert "plaintext_key" not in listed.json()["keys"][0]
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    assert deleted.status_code == 200
    assert listed_after_delete.json()["keys"] == []
    get_settings.cache_clear()


def test_api_key_management_requires_admin_token(monkeypatch) -> None:
    _tmp_db(monkeypatch, AB_ADMIN_TOKEN="admin-secret-token")

    with TestClient(create_app()) as client:
        unauthorized = client.get("/api/v1/keys")
        wrong_token = client.get(
            "/api/v1/keys",
            headers={"Authorization": "Bearer wrong-admin-token"},
        )

    assert unauthorized.status_code == 401
    assert wrong_token.status_code == 401
    get_settings.cache_clear()


def test_api_key_delete_requires_revocation_first(monkeypatch) -> None:
    _tmp_db(monkeypatch, AB_ADMIN_TOKEN="admin-secret-token")

    with TestClient(create_app()) as client:
        created = client.post(
            "/api/v1/keys",
            headers=_admin_headers(),
            json={
                "name": "Partner write key",
                "scope": "write",
            },
        )
        deleted = client.delete(
            f"/api/v1/keys/{created.json()['id']}",
            headers=_admin_headers(),
        )

    assert created.status_code == 200
    assert deleted.status_code == 409
    assert deleted.json()["error_code"] == "api_key_not_revoked"
    get_settings.cache_clear()


def test_create_api_key_rejects_admin_scope(monkeypatch) -> None:
    """Issued keys are only read/write; admin is not a creatable scope (audit F-09)."""
    _tmp_db(monkeypatch, AB_ADMIN_TOKEN="admin-secret-token")

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/keys",
            headers=_admin_headers(),
            json={"name": "Misleading admin key", "scope": "admin"},
        )

    assert response.status_code == 422
    get_settings.cache_clear()


def test_legacy_admin_api_key_normalizes_to_write_without_operator_access(monkeypatch) -> None:
    """Stored scope=admin migrates to write and never unlocks keys/webhooks."""
    db_path = _tmp_db(monkeypatch)
    # Insert a legacy admin key before the app boots and normalizes scopes.
    seed = ProjectRepository(str(db_path))
    with seed._transaction() as connection:  # noqa: SLF001 — intentional seed of legacy row
        connection.execute(
            """
            INSERT INTO api_keys (
                id, name, key_hash, scope, created_at,
                last_used_at, revoked_at, rate_limit_requests, rate_limit_window_seconds
            )
            VALUES (?, ?, ?, 'admin', ?, NULL, NULL, NULL, NULL)
            """,
            (
                "legacy-admin-key",
                "Legacy admin",
                hash_api_key("abk_legacy_admin_plaintext_token_32chars"),
                "2026-01-01T00:00:00+00:00",
            ),
        )

    monkeypatch.setenv("AB_ADMIN_TOKEN", "admin-secret-token")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        listed = client.get("/api/v1/keys", headers=_admin_headers())
        assert listed.status_code == 200
        keys = listed.json()["keys"]
        assert any(key["id"] == "legacy-admin-key" and key["scope"] == "write" for key in keys)

        # Legacy secret authenticates as write, not operator.
        diagnostics = client.get(
            "/api/v1/diagnostics",
            headers={"Authorization": "Bearer abk_legacy_admin_plaintext_token_32chars"},
        )
        assert diagnostics.status_code == 200

        operator_list = client.get(
            "/api/v1/keys",
            headers={"Authorization": "Bearer abk_legacy_admin_plaintext_token_32chars"},
        )
        assert operator_list.status_code == 403
        assert operator_list.json()["error_code"] == "admin_token_required"

        audit = client.get(
            "/api/v1/audit",
            params={"action": "api_key_scope_normalized", "key_id": "legacy-admin-key"},
            headers={"Authorization": "Bearer abk_legacy_admin_plaintext_token_32chars"},
        )
        assert audit.status_code == 200
        assert any(entry["key_id"] == "legacy-admin-key" for entry in audit.json()["entries"])

    get_settings.cache_clear()


def test_write_api_key_cannot_manage_keys_or_webhooks(monkeypatch) -> None:
    db_path = _tmp_db(monkeypatch, AB_ADMIN_TOKEN="admin-secret-token")
    repository = ProjectRepository(str(db_path))
    write_key = repository.create_api_key(name="Partner write", scope="write")
    write_headers = {"Authorization": f"Bearer {write_key['plaintext_key']}"}

    with TestClient(create_app()) as client:
        keys = client.get("/api/v1/keys", headers=write_headers)
        webhooks = client.get("/api/v1/webhooks", headers=write_headers)
        create_key = client.post(
            "/api/v1/keys",
            headers=write_headers,
            json={"name": "Nope", "scope": "read"},
        )

    assert keys.status_code == 403
    assert keys.json()["error_code"] == "admin_token_required"
    assert webhooks.status_code == 403
    assert webhooks.json()["error_code"] == "admin_token_required"
    assert create_key.status_code == 403
    assert create_key.json()["error_code"] == "admin_token_required"
    get_settings.cache_clear()


def test_static_admin_token_manages_keys_and_webhooks(monkeypatch) -> None:
    _tmp_db(monkeypatch, AB_ADMIN_TOKEN="admin-secret-token")

    with TestClient(create_app()) as client:
        created_key = client.post(
            "/api/v1/keys",
            headers=_admin_headers(),
            json={"name": "Ops write", "scope": "write"},
        )
        listed_keys = client.get("/api/v1/keys", headers=_admin_headers())
        created_webhook = client.post(
            "/api/v1/webhooks",
            headers=_admin_headers(),
            json={
                "name": "Partner alerts",
                "target_url": "https://example.com/webhook",
                "secret": "top-secret",
                "format": "generic",
                "event_filter": ["api_key_created"],
                "scope": "global",
            },
        )
        listed_webhooks = client.get("/api/v1/webhooks", headers=_admin_headers())
        revoked = client.post(
            f"/api/v1/keys/{created_key.json()['id']}/revoke",
            headers=_admin_headers(),
        )

    assert created_key.status_code == 200
    assert listed_keys.status_code == 200
    assert created_webhook.status_code == 200
    assert listed_webhooks.status_code == 200
    assert revoked.status_code == 200
    get_settings.cache_clear()


def test_operator_endpoints_without_admin_token_return_documented_error(monkeypatch) -> None:
    db_path = _tmp_db(monkeypatch)
    repository = ProjectRepository(str(db_path))
    write_key = repository.create_api_key(name="Only write", scope="write")
    # No AB_ADMIN_TOKEN configured.
    monkeypatch.delenv("AB_ADMIN_TOKEN", raising=False)
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.get(
            "/api/v1/keys",
            headers={"Authorization": f"Bearer {write_key['plaintext_key']}"},
        )
        anonymous = client.get("/api/v1/keys")

    assert response.status_code == 401
    assert response.json()["error_code"] == "admin_token_not_configured"
    assert anonymous.status_code == 401
    assert anonymous.json()["error_code"] == "admin_token_not_configured"
    get_settings.cache_clear()
