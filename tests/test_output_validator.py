"""LLD §4.4: parse model output as JSON and check it against a field-type schema."""

import pytest

from claims_rag.components.output_validator import parse_json, validate_schema
from claims_rag.errors import OutputValidationError

SCHEMA = {
    "policy_number": (str, type(None)),
    "amount_claimed": (float, int, type(None)),
    "confidence": float,
}


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        '```\n{"a": 1}\n```',
        'Here is the result:\n{"a": 1}\nThanks.',
    ],
)
def test_parse_json_accepts_fenced_and_surrounded_objects(text: str) -> None:
    assert parse_json(text) == {"a": 1}


def test_parse_json_keeps_nested_objects() -> None:
    assert parse_json('{"a": {"b": [1, {"c": 2}]}}') == {"a": {"b": [1, {"c": 2}]}}


@pytest.mark.parametrize("text", ["", "no json here", "[1, 2]", '{"a": ', "{not json}"])
def test_parse_json_rejects_non_objects(text: str) -> None:
    with pytest.raises(OutputValidationError):
        parse_json(text)


def test_validate_schema_passes_valid_data_and_allows_extra_keys() -> None:
    data = {"policy_number": None, "amount_claimed": 1200, "confidence": 0.9, "extra": "ok"}
    assert validate_schema(data, SCHEMA) == []


def test_validate_schema_reports_missing_and_wrong_types() -> None:
    errors = validate_schema({"amount_claimed": "1200", "confidence": 0.9}, SCHEMA)
    assert errors == [
        "missing: policy_number",
        "wrong type: amount_claimed (expected float|int|None, got str)",
    ]


@pytest.mark.parametrize("field", ["amount_claimed", "confidence"])
def test_bool_is_not_a_number(field: str) -> None:
    data = {"policy_number": "MOT-123456", "amount_claimed": 1.0, "confidence": 0.5, field: True}
    assert validate_schema(data, SCHEMA) == [f"wrong type: {field} (expected {_names(field)}, got bool)"]


def _names(field: str) -> str:
    return {"amount_claimed": "float|int|None", "confidence": "float"}[field]
