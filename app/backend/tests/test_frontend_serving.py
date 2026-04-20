from pathlib import Path
import sys
import uuid

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings
from app.backend.app.main import create_app


def test_backend_serves_frontend_dist_when_present(monkeypatch) -> None:
    temp_root = Path(__file__).resolve().parent / ".tmp"
    temp_root.mkdir(exist_ok=True)
    dist_dir = temp_root / f"frontend-dist-{uuid.uuid4()}"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<!doctype html><html><body>frontend shell</body></html>", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('frontend asset');", encoding="utf-8")

    monkeypatch.setenv("AB_FRONTEND_DIST_PATH", str(dist_dir))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "true")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        index_response = client.get("/")
        assert index_response.status_code == 200
        assert "frontend shell" in index_response.text

        nested_route_response = client.get("/projects/local-smoke")
        assert nested_route_response.status_code == 200
        assert "frontend shell" in nested_route_response.text

        asset_response = client.get("/assets/app.js")
        assert asset_response.status_code == 200
        assert "frontend asset" in asset_response.text

        health_response = client.get("/health")
        assert health_response.status_code == 200
        assert health_response.json()["status"] == "ok"

    get_settings.cache_clear()


def test_backend_rejects_frontend_path_traversal(monkeypatch) -> None:
    temp_root = Path(__file__).resolve().parent / ".tmp"
    temp_root.mkdir(exist_ok=True)
    dist_dir = temp_root / f"frontend-dist-{uuid.uuid4()}"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<!doctype html><html><body>frontend shell</body></html>", encoding="utf-8")
    outside_file = temp_root / f"secret-{uuid.uuid4()}.txt"
    outside_file.write_text("top secret", encoding="utf-8")

    monkeypatch.setenv("AB_FRONTEND_DIST_PATH", str(dist_dir))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "true")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        for traversal_path in (
            f"/%2e%2e/{outside_file.name}",
            f"/assets/..%2F..%2F{outside_file.name}",
        ):
            response = client.get(traversal_path)
            assert response.status_code == 404
            assert "top secret" not in response.text

    get_settings.cache_clear()


def test_backend_skips_frontend_serving_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.get("/")
        assert response.status_code == 404

    get_settings.cache_clear()
