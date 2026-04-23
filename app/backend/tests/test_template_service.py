from pathlib import Path

import pytest
import yaml

from app.backend.app.schemas.template import TemplateRecord


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
TEMPLATE_PATHS = sorted(TEMPLATES_DIR.glob("*.yaml"))


def test_built_in_template_gallery_contains_ten_yaml_files() -> None:
    assert len(TEMPLATE_PATHS) == 10


@pytest.mark.parametrize("template_path", TEMPLATE_PATHS, ids=lambda path: path.stem)
def test_built_in_templates_parse_as_template_records(template_path: Path) -> None:
    raw_template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    template = TemplateRecord.model_validate(
        {
            "id": template_path.stem,
            "name": raw_template["name"],
            "category": raw_template["category"],
            "description": raw_template["description"],
            "built_in": True,
            "payload": raw_template["payload"],
            "tags": raw_template["tags"],
        }
    )

    assert template.name.strip()
    assert template.category.strip()
    assert template.description.strip()
    assert template.tags
    assert template.payload.project.project_name == ""
    assert template.payload.metrics.baseline_value > 0
    assert template.payload.metrics.mde_pct > 0
    assert 0.01 <= template.payload.metrics.alpha <= 0.1
    assert sum(template.payload.setup.traffic_split) == 100
