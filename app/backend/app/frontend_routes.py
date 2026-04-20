from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def register_frontend_routes(app: FastAPI, settings) -> None:
    frontend_dist_path = Path(settings.frontend_dist_path)
    frontend_index_path = frontend_dist_path / "index.html"
    if not (settings.serve_frontend_dist and frontend_index_path.exists()):
        return
    assets_path = frontend_dist_path / "assets"
    frontend_dist_root = frontend_dist_path.resolve()
    if assets_path.exists():
        app.mount("/assets", StaticFiles(directory=assets_path), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def serve_frontend_index() -> FileResponse:
        return FileResponse(frontend_index_path)

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend_app(full_path: str) -> FileResponse:
        if full_path.startswith(("api/", "health", "docs", "openapi.json", "redoc")):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (frontend_dist_path / full_path).resolve()
        if not candidate.is_relative_to(frontend_dist_root):
            raise HTTPException(status_code=404, detail="Not found")
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(frontend_index_path)
