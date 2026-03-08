from __future__ import annotations

import argparse
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
    args = parser.parse_args()

    env = os.environ.copy()
    env.setdefault("AB_API_TOKEN", WRITE_TOKEN)
    env.setdefault("AB_READONLY_API_TOKEN", READONLY_TOKEN)
    env.setdefault("VITE_API_TOKEN", env["AB_API_TOKEN"])

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

        print("[docker-verify] docker compose secure flow passed")
        return 0
    finally:
        subprocess.run(
            ["docker", "compose", "down", "-v"],
            cwd=ROOT_DIR,
            env=env,
            check=False,
        )


if __name__ == "__main__":
    raise SystemExit(main())
