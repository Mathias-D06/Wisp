"""Validate and clean tool arguments against the declared (OpenAPI-subset) schema.

The model usually sends correct arguments, but the dispatcher never trusts them: unknown keys
are dropped, required keys enforced, enums checked and whole-number floats coerced to int.
"""

from __future__ import annotations

from typing import Any

from wisp.tools.base import ToolError


def _check(value: Any, schema: dict[str, Any], path: str, problems: list[str]) -> Any:
    kind = schema.get("type")
    if kind == "string":
        if not isinstance(value, str):
            problems.append(f"{path} must be text")
            return value
        if "enum" in schema and value not in schema["enum"]:
            problems.append(f"{path} must be one of {', '.join(schema['enum'])}")
        return value
    if kind == "integer":
        whole_float = isinstance(value, float) and value.is_integer()
        digit_text = isinstance(value, str) and value.strip().lstrip("-").isdigit()
        if not isinstance(value, bool) and (whole_float or digit_text):
            return int(value)
        if isinstance(value, bool) or not isinstance(value, int):
            problems.append(f"{path} must be a whole number")
        return value
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, int | float):
            problems.append(f"{path} must be a number")
        return value
    if kind == "boolean":
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        if not isinstance(value, bool):
            problems.append(f"{path} must be true or false")
        return value
    if kind == "array":
        if not isinstance(value, list):
            problems.append(f"{path} must be a list")
            return value
        items = schema.get("items", {})
        return [_check(v, items, f"{path}[{i}]", problems) for i, v in enumerate(value)]
    if kind == "object":
        if not isinstance(value, dict):
            problems.append(f"{path} must be an object")
            return value
        return _clean_object(value, schema, path, problems)
    return value


def _clean_object(
    value: dict[str, Any], schema: dict[str, Any], path: str, problems: list[str]
) -> dict[str, Any]:
    properties = schema.get("properties", {})
    cleaned: dict[str, Any] = {}
    for key in schema.get("required", []):
        if key not in value or value[key] is None:
            problems.append(f"{path + '.' if path else ''}{key} is required")
    for key, item in value.items():
        if key not in properties or item is None:
            continue  # unknown keys are dropped, never forwarded to handlers
        cleaned[key] = _check(item, properties[key], f"{path + '.' if path else ''}{key}", problems)
    return cleaned


def validate_args(schema: dict[str, Any], args: dict[str, Any] | None) -> dict[str, Any]:
    problems: list[str] = []
    cleaned = _clean_object(dict(args or {}), schema, "", problems)
    if problems:
        raise ToolError("Invalid arguments: " + "; ".join(problems))
    return cleaned
