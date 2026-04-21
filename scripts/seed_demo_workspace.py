from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backend.app.config import get_settings
from app.backend.app.main import create_app


SAMPLE_PROJECTS = (
    {
        "template_id": "checkout_conversion",
        "project_name": "Demo - Checkout Conversion",
    },
    {
        "template_id": "pricing_sensitivity",
        "project_name": "Demo - Pricing Sensitivity",
    },
    {
        "template_id": "onboarding_completion",
        "project_name": "Demo - Onboarding Completion",
    },
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the demo workspace with built-in sample projects.")
    parser.add_argument(
        "--idempotent",
        action="store_true",
        help="Skip projects that already exist by name.",
    )
    args = parser.parse_args()

    write_token = (os.getenv("AB_API_TOKEN") or "").strip()
    readonly_token = (os.getenv("AB_READONLY_API_TOKEN") or "").strip()
    if readonly_token and not write_token:
        print("AB_API_TOKEN is required to seed the workspace when readonly auth is enabled.", file=sys.stderr)
        return 2

    headers = {"Authorization": f"Bearer {write_token}"} if write_token else {}
    get_settings.cache_clear()

    try:
        with TestClient(create_app()) as client:
            existing_response = client.get(
                "/api/v1/projects",
                params={"status": "all", "limit": 200},
                headers=headers,
            )
            if existing_response.status_code != 200:
                print(existing_response.text, file=sys.stderr)
                return 1

            existing_names = {
                project["project_name"]
                for project in existing_response.json().get("projects", [])
            }
            created = 0
            skipped = 0

            for sample in SAMPLE_PROJECTS:
                if args.idempotent and sample["project_name"] in existing_names:
                    print(f"skip {sample['project_name']}")
                    skipped += 1
                    continue

                template_response = client.get(
                    f"/api/v1/templates/{sample['template_id']}",
                    headers=headers,
                )
                if template_response.status_code != 200:
                    print(template_response.text, file=sys.stderr)
                    return 1

                payload = copy.deepcopy(template_response.json()["payload"])
                payload["project"]["project_name"] = sample["project_name"]
                payload["project"]["project_description"] = (
                    f"{payload['project']['project_description']} Seeded demo sample."
                )
                payload["additional_context"]["llm_context"] = (
                    f"{payload['additional_context'].get('llm_context', '').strip()} Seeded demo sample."
                ).strip()

                create_response = client.post(
                    "/api/v1/projects",
                    json=payload,
                    headers=headers,
                )
                if create_response.status_code != 200:
                    print(create_response.text, file=sys.stderr)
                    return 1

                print(f"created {sample['project_name']}")
                created += 1

            print(f"done created={created} skipped={skipped}")
            return 0
    finally:
        get_settings.cache_clear()


if __name__ == "__main__":
    raise SystemExit(main())
