from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

import uvicorn


ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIST_DIR = ROOT_DIR / "app" / "frontend" / "dist"
BACKEND_HOST = os.environ.get("AB_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("AB_PORT", "8010"))

sys.path.insert(0, str(ROOT_DIR))


def main() -> int:
    if not (FRONTEND_DIST_DIR / "index.html").exists():
        raise SystemExit(
            "Frontend dist is missing. Run `npm.cmd run build` in app/frontend before test:e2e."
        )

    default_temp_dir = Path(tempfile.gettempdir()) / "ab_test_playwright"
    default_temp_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(os.environ.get("AB_DB_PATH", str(default_temp_dir / "projects.sqlite3")))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("AB_ENV", "playwright")
    os.environ.setdefault("AB_DB_PATH", str(db_path))
    os.environ.setdefault("AB_HOST", BACKEND_HOST)
    os.environ.setdefault("AB_PORT", str(BACKEND_PORT))
    os.environ.setdefault("AB_SERVE_FRONTEND_DIST", "true")
    os.environ.setdefault("AB_FRONTEND_DIST_PATH", str(FRONTEND_DIST_DIR))
    os.environ.setdefault("AB_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
    os.environ.setdefault("AB_LLM_TIMEOUT_SECONDS", "1")
    os.environ.setdefault("AB_LLM_MAX_ATTEMPTS", "1")

    uvicorn.run(
        "app.backend.app.main:app",
        host=BACKEND_HOST,
        port=BACKEND_PORT,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
