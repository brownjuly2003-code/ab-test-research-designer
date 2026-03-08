from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.backend.app.main import create_app

OUTPUT_PATH = ROOT_DIR / "app" / "frontend" / "src" / "lib" / "generated" / "api-contract.ts"
INDENT = "  "


def normalize_schema_name(name: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z_]", "_", name)
    if normalized[:1].isdigit():
        normalized = f"_{normalized}"
    return normalized


def format_property_name(name: str) -> str:
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        return name
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def parenthesize_union(member: str) -> str:
    if "\n" in member or " | " in member:
        return f"({member})"
    return member


def render_schema(
    schema: dict,
    *,
    name_map: dict[str, str],
    indent_level: int = 0,
) -> str:
    if "$ref" in schema:
        ref_name = schema["$ref"].rsplit("/", 1)[-1]
        return name_map[ref_name]

    any_of = schema.get("anyOf")
    if isinstance(any_of, list):
        members = [render_schema(item, name_map=name_map, indent_level=indent_level) for item in any_of]
        deduplicated: list[str] = []
        for member in members:
            if member not in deduplicated:
                deduplicated.append(member)
        return " | ".join(parenthesize_union(member) for member in deduplicated)

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return " | ".join(repr(value).replace("'", '"') for value in enum_values)

    schema_type = schema.get("type")

    if schema_type == "array":
        item_type = render_schema(schema.get("items", {}), name_map=name_map, indent_level=indent_level)
        return f"{parenthesize_union(item_type)}[]"

    if schema_type == "object" or "properties" in schema or "additionalProperties" in schema:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        additional_properties = schema.get("additionalProperties")

        if not properties and additional_properties is True:
            return "{ [key: string]: unknown; }"
        if not properties and isinstance(additional_properties, dict):
            value_type = render_schema(
                additional_properties,
                name_map=name_map,
                indent_level=indent_level + 1,
            )
            return f"{{ [key: string]: {value_type}; }}"
        if not properties:
            return "{}"

        lines = ["{"]
        for property_name, property_schema in properties.items():
            property_type = render_schema(
                property_schema,
                name_map=name_map,
                indent_level=indent_level + 1,
            )
            optional_marker = "" if property_name in required else "?"
            lines.append(
                f"{INDENT * (indent_level + 1)}"
                f"{format_property_name(property_name)}{optional_marker}: {property_type};"
            )

        if additional_properties is True:
            lines.append(f"{INDENT * (indent_level + 1)}[key: string]: unknown;")
        elif isinstance(additional_properties, dict):
            value_type = render_schema(
                additional_properties,
                name_map=name_map,
                indent_level=indent_level + 1,
            )
            lines.append(f"{INDENT * (indent_level + 1)}[key: string]: {value_type};")

        lines.append(f"{INDENT * indent_level}}}")
        return "\n".join(lines)

    primitive_map = {
        "boolean": "boolean",
        "integer": "number",
        "null": "null",
        "number": "number",
        "string": "string",
    }
    if schema_type in primitive_map:
        return primitive_map[schema_type]

    return "unknown"


def generate_typescript() -> str:
    openapi_schema = create_app().openapi()
    component_schemas = openapi_schema.get("components", {}).get("schemas", {})
    name_map = {
        schema_name: normalize_schema_name(schema_name)
        for schema_name in component_schemas
    }

    lines = [
        "// This file is auto-generated from FastAPI OpenAPI components.",
        "// Do not edit manually. Run `python scripts/generate_frontend_api_types.py`.",
        "",
    ]

    for original_name in sorted(component_schemas):
        generated_name = name_map[original_name]
        rendered = render_schema(component_schemas[original_name], name_map=name_map)
        lines.append(f"export type {generated_name} = {rendered};")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the generated file is out of date instead of rewriting it.",
    )
    args = parser.parse_args()

    generated = generate_typescript()

    if args.check:
        if not OUTPUT_PATH.exists() or OUTPUT_PATH.read_text(encoding="utf-8") != generated:
            print(f"{OUTPUT_PATH} is out of date")
            return 1
        print(f"{OUTPUT_PATH} is up to date")
        return 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(generated, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
