"""LLD §4.5 / §6.5: deterministic business rules from YAML."""

from datetime import date
from pathlib import Path

import pytest

from claims_rag.components.rules_engine import Rule, RulesEngine, RuleViolation
from claims_rag.errors import RulesFormatError

TODAY = date(2026, 10, 24)
RULES_YAML = """\
version: "1.0"
rules:
  - {id: BR1, type: required,        field: policy_number}
  - {id: BR2, type: required,        field: incident_date}
  - {id: BR3, type: positive_number, field: amount_claimed}
  - {id: BR4, type: date_not_future, field: incident_date}
  - {id: BR5, type: regex,           field: policy_number, pattern: "^(MOT|HOM)-\\\\d{6}$"}
"""
VALID = {"policy_number": "MOT-123456", "incident_date": "2026-10-01", "amount_claimed": 18500.0}


@pytest.fixture
def engine(tmp_path: Path) -> RulesEngine:
    path = tmp_path / "business_rules.yaml"
    path.write_text(RULES_YAML)
    return RulesEngine.from_yaml(path)


def _ids(violations: list[RuleViolation]) -> list[str]:
    return [v.rule_id for v in violations]


def test_valid_claim_has_no_violations(engine: RulesEngine) -> None:
    assert engine.evaluate(VALID, TODAY) == []


@pytest.mark.parametrize("value", [None, "", "   "])
def test_required_rejects_null_and_empty(engine: RulesEngine, value: str | None) -> None:
    assert _ids(engine.evaluate({**VALID, "policy_number": value}, TODAY)) == ["BR1"]


def test_missing_key_counts_as_null(engine: RulesEngine) -> None:
    data = {k: v for k, v in VALID.items() if k != "incident_date"}
    assert _ids(engine.evaluate(data, TODAY)) == ["BR2"]


@pytest.mark.parametrize("value", [0, -5, "100", True])
def test_positive_number(engine: RulesEngine, value: object) -> None:
    assert _ids(engine.evaluate({**VALID, "amount_claimed": value}, TODAY)) == ["BR3"]


def test_null_amount_is_not_reported_by_positive_number(engine: RulesEngine) -> None:
    assert engine.evaluate({**VALID, "amount_claimed": None}, TODAY) == []


@pytest.mark.parametrize("value", ["2026-10-25", "24/10/2026", "yesterday", "2026-02-30"])
def test_date_not_future_rejects_future_and_unparseable(engine: RulesEngine, value: str) -> None:
    assert _ids(engine.evaluate({**VALID, "incident_date": value}, TODAY)) == ["BR4"]


def test_today_is_not_future(engine: RulesEngine) -> None:
    assert engine.evaluate({**VALID, "incident_date": "2026-10-24"}, TODAY) == []


@pytest.mark.parametrize("value", ["MOT-12345", "mot-123456", "XYZ-123456", "MOT-1234567"])
def test_regex_is_a_full_match(engine: RulesEngine, value: str) -> None:
    violations = engine.evaluate({**VALID, "policy_number": value}, TODAY)
    assert violations == [RuleViolation("BR5", "policy_number", violations[0].message)]
    assert violations[0].to_dict()["field"] == "policy_number"


def test_constructor_accepts_rules_directly() -> None:
    engine = RulesEngine([Rule(rule_id="R1", type="required", field="x")])
    assert _ids(engine.evaluate({}, TODAY)) == ["R1"]


@pytest.mark.parametrize(
    "body",
    [
        "rules: [",
        "rules: {}",
        "rules:\n  - {id: X, type: unknown, field: a}",
        "rules:\n  - {id: X, type: required}",
        "rules:\n  - {id: X, type: regex, field: a}",
        "rules:\n  - {id: X, type: regex, field: a, pattern: '('}",
    ],
)
def test_malformed_rules_fail_at_load(tmp_path: Path, body: str) -> None:
    path = tmp_path / "r.yaml"
    path.write_text(body)
    with pytest.raises(RulesFormatError):
        RulesEngine.from_yaml(path)
