from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

import uvicorn


ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIST_DIR = ROOT_DIR / "app" / "frontend" / "dist"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8010

sys.path.insert(0, str(ROOT_DIR))


def main() -> int:
    if not (FRONTEND_DIST_DIR / "index.html").exists():
        raise SystemExit(
            "Frontend dist is missing. Run `npm.cmd run build` in app/frontend before test:e2e."
        )

    temp_dir = Path(tempfile.gettempdir()) / "ab_test_playwright"
    temp_dir.mkdir(parents=True, exist_ok=True)
    db_path = temp_dir / "projects.sqlite3"

    os.environ.update(
        {
            "AB_ENV": "playwright",
            "AB_DB_PATH": str(db_path),
            "AB_HOST": BACKEND_HOST,
            "AB_PORT": str(BACKEND_PORT),
            "AB_SERVE_FRONTEND_DIST": "true",
            "AB_FRONTEND_DIST_PATH": str(FRONTEND_DIST_DIR),
            "AB_CORS_ORIGINS": "http://127.0.0.1:5173,http://localhost:5173",
            "AB_LLM_TIMEOUT_SECONDS": "1",
            "AB_LLM_MAX_ATTEMPTS": "1",
        }
    )

    uvicorn.run(
        "app.backend.app.main:app",
        host=BACKEND_HOST,
        port=BACKEND_PORT,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
