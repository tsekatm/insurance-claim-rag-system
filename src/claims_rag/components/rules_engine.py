"""Deterministic business rules loaded from YAML (LLD §4.5, §6.5)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from claims_rag.errors import RulesFormatError

RULE_TYPES = frozenset({"required", "positive_number", "date_not_future", "regex"})


@dataclass(frozen=True)
class Rule:
    rule_id: str
    type: str
    field: str
    pattern: str | None = None

    def __post_init__(self) -> None:
        if self.type not in RULE_TYPES:
            raise RulesFormatError(f"{self.rule_id}: unknown rule type {self.type!r}")
        if self.type == "regex":
            if not self.pattern:
                raise RulesFormatError(f"{self.rule_id}: regex rule needs a pattern")
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise RulesFormatError(f"{self.rule_id}: invalid pattern ({exc})") from exc

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuleViolation:
    rule_id: str
    field: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _check(rule: Rule, value: Any, today: date) -> str | None:
    """Return a violation message, or None when the value passes."""
    if rule.type == "required":
        return "is required" if _is_empty(value) else None
    if _is_empty(value):  # absence is reported once, by the required rule
        return None
    if rule.type == "positive_number":
        is_number = isinstance(value, int | float) and not isinstance(value, bool)
        return None if is_number and value > 0 else "must be a positive number"
    if rule.type == "date_not_future":
        try:
            parsed = (
                date.fromisoformat(str(value)) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)) else None
            )
        except ValueError:
            parsed = None
        if parsed is None:
            return "must be an ISO date (YYYY-MM-DD)"
        return "must not be in the future" if parsed > today else None
    pattern = rule.pattern or ""  # regex rules always have a pattern (Rule.__post_init__)
    return None if isinstance(value, str) and re.fullmatch(pattern, value) else "has an invalid format"


class RulesEngine:
    def __init__(self, rules: Sequence[Rule]) -> None:
        self._rules = tuple(rules)

    @classmethod
    def from_yaml(cls, path: Path) -> RulesEngine:
        try:
            raw = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            raise RulesFormatError(f"{path}: invalid YAML") from exc
        entries = raw.get("rules") if isinstance(raw, dict) else None
        if not isinstance(entries, list):
            raise RulesFormatError(f"{path}: expected a 'rules' list")
        try:
            rules = [
                Rule(
                    rule_id=str(e["id"]), type=str(e["type"]), field=str(e["field"]), pattern=e.get("pattern")
                )
                for e in entries
            ]
        except (KeyError, TypeError) as exc:
            raise RulesFormatError(f"{path}: rule missing a field ({exc})") from exc
        return cls(rules)

    def evaluate(self, data: Mapping[str, Any], today: date) -> list[RuleViolation]:
        violations = []
        for rule in self._rules:
            message = _check(rule, data.get(rule.field), today)
            if message:
                violations.append(RuleViolation(rule.rule_id, rule.field, f"{rule.field} {message}"))
        return violations
