"""Parse model output as a JSON object and check field types (LLD §4.4)."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from claims_rag.errors import OutputValidationError

FieldType = type | tuple[type, ...]  # e.g. (str, type(None)) for a nullable string

_FENCE = re.compile(r"^```[A-Za-z]*\s*$", re.MULTILINE)


def parse_json(text: str) -> dict[str, Any]:
    """Strip Markdown code fences, then parse the outermost {...}."""
    body = _FENCE.sub("", text)
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end < start:
        raise OutputValidationError("no JSON object in model output")
    try:
        data = json.loads(body[start : end + 1])
    except json.JSONDecodeError as exc:
        raise OutputValidationError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise OutputValidationError("model output is not a JSON object")
    return data


def _type_names(expected: FieldType) -> str:
    types = expected if isinstance(expected, tuple) else (expected,)
    return "|".join("None" if t is type(None) else t.__name__ for t in types)


def _matches(value: Any, expected: FieldType) -> bool:
    types = expected if isinstance(expected, tuple) else (expected,)
    if isinstance(value, bool):  # bool subclasses int; never accept it as a number
        return bool in types
    return isinstance(value, types)


def validate_schema(data: Mapping[str, Any], schema: Mapping[str, FieldType]) -> list[str]:
    """Return one message per missing key or wrong type. Extra keys are allowed."""
    errors: list[str] = []
    for field, expected in schema.items():
        if field not in data:
            errors.append(f"missing: {field}")
        elif not _matches(data[field], expected):
            got = type(data[field]).__name__
            errors.append(f"wrong type: {field} (expected {_type_names(expected)}, got {got})")
    return errors
