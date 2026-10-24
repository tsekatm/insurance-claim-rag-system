"""Route a claim to auto_approve or human_review from generic signals (LLD §4.10, §6.6)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from claims_rag.errors import RulesFormatError


@dataclass(frozen=True)
class RoutingSignals:
    """Generic inputs — the router does not read claim objects."""

    confidence: float | None
    amount: float | None
    decision: str | None
    blocking_issues: tuple[str, ...]  # schema errors, rule violations, grounding failure, parse failures


@dataclass(frozen=True)
class RouteDecision:
    route: Literal["auto_approve", "human_review"]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _num(value: float) -> str:
    """Exact, without a trailing .0 — `:g` would round 50000.01 to 50000."""
    return str(int(value)) if float(value).is_integer() else repr(float(value))


class Router:
    def __init__(
        self, min_confidence: float, high_value_amount: float, review_decisions: frozenset[str]
    ) -> None:
        if not 0 <= min_confidence <= 1:
            raise RulesFormatError(f"min_confidence must be between 0 and 1, got {min_confidence}")
        if high_value_amount <= 0:
            raise RulesFormatError(f"high_value_amount must be positive, got {high_value_amount}")
        self._min_confidence = min_confidence
        self._high_value_amount = high_value_amount
        self._review_decisions = review_decisions

    @classmethod
    def from_yaml(cls, path: Path) -> Router:
        try:
            raw = yaml.safe_load(path.read_text())
            decisions = raw["review_decisions"]
            if not isinstance(decisions, list):
                raise TypeError("review_decisions must be a list")
            return cls(
                min_confidence=float(raw["min_confidence"]),
                high_value_amount=float(raw["high_value_amount"]),
                review_decisions=frozenset(str(d) for d in decisions),
            )
        except (yaml.YAMLError, KeyError, TypeError, ValueError) as exc:
            raise RulesFormatError(f"{path}: invalid routing file ({exc})") from exc

    def decide(self, signals: RoutingSignals) -> RouteDecision:
        reasons = [f"blocking: {issue}" for issue in signals.blocking_issues]
        if signals.confidence is None:
            reasons.append("confidence missing")
        elif signals.confidence < self._min_confidence:
            reasons.append(f"confidence {_num(signals.confidence)} < {_num(self._min_confidence)}")
        if signals.amount is not None and signals.amount > self._high_value_amount:
            reasons.append(f"amount {_num(signals.amount)} > {_num(self._high_value_amount)}")
        if signals.decision is None:
            reasons.append("decision missing")
        elif signals.decision in self._review_decisions:
            reasons.append(f"decision {signals.decision} needs review")
        if reasons:
            return RouteDecision("human_review", tuple(reasons))
        return RouteDecision("auto_approve", ("all checks passed",))
