from pathlib import Path
import sys
import uuid

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings
from app.backend.app.main import create_app


def _admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer admin-secret-token"}


def test_api_key_management_crud_flow(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"

    monkeypatch.setenv("AB_DB_PATH", str(db_path))
    monkeypatch.setenv("AB_ADMIN_TOKEN", "admin-secret-token")
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    get_settings.cache_clear()

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
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"

    monkeypatch.setenv("AB_DB_PATH", str(db_path))
    monkeypatch.setenv("AB_ADMIN_TOKEN", "admin-secret-token")
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    get_settings.cache_clear()

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
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"

    monkeypatch.setenv("AB_DB_PATH", str(db_path))
    monkeypatch.setenv("AB_ADMIN_TOKEN", "admin-secret-token")
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    get_settings.cache_clear()

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
