from pathlib import Path
from typing import Any

import yaml


BUILT_IN_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"


def load_built_in_templates() -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    for template_path in sorted(BUILT_IN_TEMPLATE_DIR.glob("*.yaml")):
        payload = yaml.safe_load(template_path.read_text(encoding="utf-8")) or {}
        templates.append(
            {
                "id": template_path.stem,
                "name": str(payload["name"]),
                "category": str(payload["category"]),
                "description": str(payload["description"]),
                "built_in": True,
                "payload": payload["payload"],
                "tags": [str(tag) for tag in payload.get("tags", [])],
            }
        )
    return templates


def sync_built_in_templates(repository) -> None:
    for template in load_built_in_templates():
        repository.upsert_template(
            template_id=template["id"],
            name=template["name"],
            category=template["category"],
            description=template["description"],
            built_in=True,
            tags=template["tags"],
            payload=template["payload"],
        )
