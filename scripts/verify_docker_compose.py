from __future__ import annotations

import argparse
import http.client
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WRITE_TOKEN = "verify-write-token"
READONLY_TOKEN = "verify-readonly-token"
WORKSPACE_SIGNING_KEY = "verify-workspace-signing-key"


def run_step(label: str, command: list[str], *, env: dict[str, str]) -> None:
    print(f"[docker-verify] {label}: {' '.join(command)}")
    completed = subprocess.run(
        command,
        cwd=ROOT_DIR,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def http_request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    payload: dict | None = None,
) -> tuple[int, str]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        f"http://127.0.0.1:8008{path}",
        headers=headers,
        data=data,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as exc:
        return 0, str(exc)


def wait_for_health(timeout_seconds: float) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        status_code, _ = http_request("GET", "/health")
        if status_code == 200:
            return
        time.sleep(2)
    raise SystemExit("Timed out waiting for docker compose health endpoint")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument(
        "--preserve",
        action="store_true",
        help="Leave the docker compose stack running instead of calling docker compose down -v at the end.",
    )
    args = parser.parse_args()

    env = os.environ.copy()
    env.setdefault("AB_API_TOKEN", WRITE_TOKEN)
    env.setdefault("AB_READONLY_API_TOKEN", READONLY_TOKEN)
    env.setdefault("AB_WORKSPACE_SIGNING_KEY", WORKSPACE_SIGNING_KEY)

    try:
        run_step("docker compose config", ["docker", "compose", "config"], env=env)
        run_step("docker compose up", ["docker", "compose", "up", "-d", "--build"], env=env)
        wait_for_health(args.timeout_seconds)

        readonly_ready_status, readonly_ready_body = http_request(
            "GET",
            "/readyz",
            token=env["AB_READONLY_API_TOKEN"],
        )
        if readonly_ready_status != 200:
            raise SystemExit(
                f"Readonly token failed readiness check: {readonly_ready_status} {readonly_ready_body}"
            )

        diagnostics_status, diagnostics_body = http_request(
            "GET",
            "/api/v1/diagnostics",
            token=env["AB_READONLY_API_TOKEN"],
        )
        if diagnostics_status != 200:
            raise SystemExit(
                f"Readonly token failed diagnostics check: {diagnostics_status} {diagnostics_body}"
            )
        diagnostics_payload = json.loads(diagnostics_body)
        if diagnostics_payload["auth"]["mode"] != "dual_token":
            raise SystemExit(
                f"Expected dual_token auth mode in diagnostics, got {diagnostics_payload['auth']['mode']}"
            )
        if diagnostics_payload["storage"]["workspace_signature_enabled"] is not True:
            raise SystemExit("Expected workspace signature mode to be enabled in diagnostics")

        calculation_payload = {
            "metric_type": "binary",
            "baseline_value": 0.042,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "traffic_split": [50, 50],
            "variants_count": 2,
        }
        readonly_calc_status, readonly_calc_body = http_request(
            "POST",
            "/api/v1/calculate",
            token=env["AB_READONLY_API_TOKEN"],
            payload=calculation_payload,
        )
        if readonly_calc_status != 403:
            raise SystemExit(
                f"Readonly token should be rejected for POST /api/v1/calculate, got {readonly_calc_status} {readonly_calc_body}"
            )
        readonly_error_payload = json.loads(readonly_calc_body)
        if readonly_error_payload.get("error_code") != "forbidden":
            raise SystemExit(
                f"Readonly POST should return forbidden error code, got {readonly_error_payload}"
            )

        write_calc_status, write_calc_body = http_request(
            "POST",
            "/api/v1/calculate",
            token=env["AB_API_TOKEN"],
            payload=calculation_payload,
        )
        if write_calc_status != 200:
            raise SystemExit(
                f"Write token failed POST /api/v1/calculate: {write_calc_status} {write_calc_body}"
            )

        project_payload = {
            "project": {
                "project_name": "Docker verification workspace",
                "domain": "e-commerce",
                "product_type": "web app",
                "platform": "web",
                "market": "US",
                "project_description": "Verification project for signed workspace backups.",
            },
            "hypothesis": {
                "change_description": "Simplify checkout",
                "target_audience": "new users",
                "business_problem": "checkout abandonment",
                "hypothesis_statement": "If checkout is shorter, conversion will improve.",
                "what_to_validate": "conversion impact",
                "desired_result": "measurable uplift",
            },
            "setup": {
                "experiment_type": "ab",
                "randomization_unit": "user",
                "traffic_split": [50, 50],
                "expected_daily_traffic": 12000,
                "audience_share_in_test": 0.6,
                "variants_count": 2,
                "inclusion_criteria": "new users only",
                "exclusion_criteria": "internal staff",
            },
            "metrics": {
                "primary_metric_name": "purchase_conversion",
                "metric_type": "binary",
                "baseline_value": 0.042,
                "expected_uplift_pct": 8,
                "mde_pct": 5,
                "alpha": 0.05,
                "power": 0.8,
                "secondary_metrics": ["add_to_cart_rate"],
                "guardrail_metrics": ["payment_error_rate"],
            },
            "constraints": {
                "seasonality_present": False,
                "active_campaigns_present": False,
                "returning_users_present": True,
                "interference_risk": "low",
                "technical_constraints": "none",
                "legal_or_ethics_constraints": "none",
                "known_risks": "none",
                "deadline_pressure": "low",
                "long_test_possible": True,
            },
            "additional_context": {
                "llm_context": "",
            },
        }
        create_project_status, create_project_body = http_request(
            "POST",
            "/api/v1/projects",
            token=env["AB_API_TOKEN"],
            payload=project_payload,
        )
        if create_project_status != 200:
            raise SystemExit(
                f"Write token failed POST /api/v1/projects: {create_project_status} {create_project_body}"
            )

        export_workspace_status, export_workspace_body = http_request(
            "GET",
            "/api/v1/workspace/export",
            token=env["AB_API_TOKEN"],
        )
        if export_workspace_status != 200:
            raise SystemExit(
                f"Write token failed GET /api/v1/workspace/export: {export_workspace_status} {export_workspace_body}"
            )
        exported_workspace = json.loads(export_workspace_body)
        signature = str(exported_workspace.get("integrity", {}).get("signature_hmac_sha256", ""))
        if len(signature) != 64:
            raise SystemExit("Expected signed workspace export from docker runtime")

        validate_workspace_status, validate_workspace_body = http_request(
            "POST",
            "/api/v1/workspace/validate",
            token=env["AB_API_TOKEN"],
            payload=exported_workspace,
        )
        if validate_workspace_status != 200:
            raise SystemExit(
                f"Write token failed POST /api/v1/workspace/validate: {validate_workspace_status} {validate_workspace_body}"
            )
        validation_payload = json.loads(validate_workspace_body)
        if validation_payload.get("signature_verified") is not True:
            raise SystemExit(
                f"Expected signature_verified=true from workspace validation, got {validation_payload}"
            )

        import_workspace_status, import_workspace_body = http_request(
            "POST",
            "/api/v1/workspace/import",
            token=env["AB_API_TOKEN"],
            payload=exported_workspace,
        )
        if import_workspace_status != 200:
            raise SystemExit(
                f"Write token failed POST /api/v1/workspace/import: {import_workspace_status} {import_workspace_body}"
            )

        print("[docker-verify] docker compose secure flow passed")
        return 0
    finally:
        if not args.preserve:
            subprocess.run(
                ["docker", "compose", "down", "-v"],
                cwd=ROOT_DIR,
                env=env,
                check=False,
            )


if __name__ == "__main__":
    raise SystemExit(main())
