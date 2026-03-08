from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.backend.app.main import create_app

OUTPUT_PATH = ROOT_DIR / "docs" / "API.md"

ROUTE_EXAMPLES = {
    "/health": 'curl http://127.0.0.1:8008/health',
    "/api/v1/diagnostics": 'curl http://127.0.0.1:8008/api/v1/diagnostics',
    "/api/v1/calculate": (
        'curl -X POST http://127.0.0.1:8008/api/v1/calculate ^\n'
        '  -H "Content-Type: application/json" ^\n'
        '  -d "{\\"metric_type\\":\\"binary\\",\\"baseline_value\\":0.042,\\"mde_pct\\":5,\\"alpha\\":0.05,\\"power\\":0.8,\\"expected_daily_traffic\\":12000,\\"audience_share_in_test\\":0.6,\\"traffic_split\\":[50,50],\\"variants_count\\":2}"'
    ),
    "/api/v1/analyze": (
        'curl -X POST http://127.0.0.1:8008/api/v1/analyze ^\n'
        '  -H "Content-Type: application/json" ^\n'
        '  -d @docs/demo/sample-project.json'
    ),
    "/api/v1/projects": 'curl http://127.0.0.1:8008/api/v1/projects',
    "/api/v1/projects/{project_id}/history": (
        'curl "http://127.0.0.1:8008/api/v1/projects/PROJECT_ID/history?analysis_limit=5&export_limit=5"'
    ),
    "/api/v1/projects/compare": (
        'curl "http://127.0.0.1:8008/api/v1/projects/compare?base_id=BASE&candidate_id=CANDIDATE"'
    ),
    "/api/v1/export/markdown": (
        'curl -X POST http://127.0.0.1:8008/api/v1/export/markdown ^\n'
        '  -H "Content-Type: application/json" ^\n'
        '  -d @report.json'
    ),
}

SECTION_ORDER = [
    "Health",
    "Diagnostics",
    "Deterministic analysis",
    "Project storage",
    "Project activity",
    "Comparison",
    "Report export",
    "Other",
]


def classify_route(path: str) -> str:
    if path == "/health":
        return "Health"
    if path == "/api/v1/diagnostics":
        return "Diagnostics"
    if path in {"/api/v1/calculate", "/api/v1/design", "/api/v1/analyze", "/api/v1/llm/advice"}:
        return "Deterministic analysis"
    if path in {"/api/v1/projects", "/api/v1/projects/{project_id}"}:
        return "Project storage"
    if path in {"/api/v1/projects/{project_id}/history", "/api/v1/projects/{project_id}/analysis", "/api/v1/projects/{project_id}/exports"}:
        return "Project activity"
    if path == "/api/v1/projects/compare":
        return "Comparison"
    if path in {"/api/v1/export/markdown", "/api/v1/export/html"}:
        return "Report export"
    return "Other"


def render_route_block(path: str, method: str, operation: dict) -> list[str]:
    lines = [f"### `{method.upper()} {path}`", ""]
    summary = operation.get("summary")
    description = operation.get("description")
    if isinstance(summary, str) and summary.strip():
        lines.append(summary.strip())
        lines.append("")
    if isinstance(description, str) and description.strip():
        lines.append(description.strip())
        lines.append("")
    example = ROUTE_EXAMPLES.get(path)
    if example:
        lines.append("```bash")
        lines.append(example)
        lines.append("```")
        lines.append("")
    return lines


def generate_api_markdown() -> str:
    openapi = create_app().openapi()
    paths = openapi.get("paths", {})
    grouped: dict[str, list[tuple[str, str, dict]]] = {section: [] for section in SECTION_ORDER}

    for path in sorted(paths):
        for method in sorted(paths[path]):
            operation = paths[path][method]
            grouped.setdefault(classify_route(path), []).append((path, method, operation))

    lines: list[str] = [
        "# API",
        "",
        "This file is generated from FastAPI OpenAPI metadata via `python scripts/generate_api_docs.py`.",
        "",
        "Base URL:",
        "",
        "```text",
        "http://127.0.0.1:8008",
        "```",
        "",
    ]

    for section in SECTION_ORDER:
        routes = grouped.get(section, [])
        if not routes:
            continue
        lines.append(f"## {section}")
        lines.append("")
        for path, method, operation in routes:
            lines.extend(render_route_block(path, method, operation))

    lines.extend(
        [
            "## Validation notes",
            "",
            "- supported variant count is `2..10`",
            "- binary baselines must be between `0` and `1`",
            "- continuous metrics require positive `baseline_value` and `std_dev`",
            "- `traffic_split` length must match `variants_count`",
            "- malformed request bodies return `422`",
            "- domain errors return structured `400`",
            "- all API responses include `X-Request-ID` and `X-Process-Time-Ms` headers",
            "",
            "## Contract generation",
            "",
            "- TypeScript contracts: `python scripts/generate_frontend_api_types.py`",
            "- API docs markdown: `python scripts/generate_api_docs.py`",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> int:
    markdown = generate_api_markdown()
    OUTPUT_PATH.write_text(markdown, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
