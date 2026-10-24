"""LLD §4.10 / §6.6: route a claim to auto_approve or human_review from generic signals."""

from pathlib import Path

import pytest

from claims_rag.components.router import Router, RoutingSignals
from claims_rag.errors import RulesFormatError

ROUTING_YAML = """\
version: "1.0"
min_confidence: 0.75
high_value_amount: 50000
review_decisions: [insufficient_information, partially_covered]
"""
CLEAN = RoutingSignals(confidence=0.9, amount=18500.0, decision="covered", blocking_issues=())


@pytest.fixture
def router(tmp_path: Path) -> Router:
    path = tmp_path / "routing.yaml"
    path.write_text(ROUTING_YAML)
    return Router.from_yaml(path)


def _with(**changes: object) -> RoutingSignals:
    return RoutingSignals(**{**CLEAN.__dict__, **changes})  # type: ignore[arg-type]


def test_clean_claim_is_auto_approved(router: Router) -> None:
    decision = router.decide(CLEAN)
    assert decision.route == "auto_approve"
    assert decision.reasons == ("all checks passed",)
    assert decision.to_dict() == {"route": "auto_approve", "reasons": ("all checks passed",)}


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"blocking_issues": ("BR5: policy_number has an invalid format",)}, "BR5"),
        ({"confidence": None}, "confidence missing"),
        ({"confidence": 0.74}, "confidence 0.74 < 0.75"),
        ({"amount": 50000.01}, "amount 50000.01 > 50000"),
        ({"decision": "partially_covered"}, "decision partially_covered"),
        ({"decision": None}, "decision missing"),
    ],
)
def test_each_condition_sends_to_human_review(
    router: Router, changes: dict[str, object], reason: str
) -> None:
    decision = router.decide(_with(**changes))
    assert decision.route == "human_review"
    assert len(decision.reasons) == 1
    assert reason in decision.reasons[0]


def test_boundaries_are_not_triggers(router: Router) -> None:
    assert router.decide(_with(confidence=0.75, amount=50000.0)).route == "auto_approve"


def test_missing_amount_alone_does_not_trigger_review(router: Router) -> None:
    # a missing amount is a blocking issue raised by the rules engine (BR3/required), not a router decision
    assert router.decide(_with(amount=None)).route == "auto_approve"


def test_not_covered_is_auto_routed(router: Router) -> None:
    assert router.decide(_with(decision="not_covered")).route == "auto_approve"


def test_every_triggered_condition_is_listed(router: Router) -> None:
    signals = RoutingSignals(
        confidence=0.2,
        amount=90000.0,
        decision="insufficient_information",
        blocking_issues=("parse failure", "not grounded"),
    )
    assert len(router.decide(signals).reasons) == 5


@pytest.mark.parametrize(
    "body",
    [
        "min_confidence: [",
        "high_value_amount: 1\nreview_decisions: []",
        "min_confidence: 1.5\nhigh_value_amount: 1\nreview_decisions: []",
        "min_confidence: 0.5\nhigh_value_amount: -1\nreview_decisions: []",
        "min_confidence: 0.5\nhigh_value_amount: 1\nreview_decisions: covered",
    ],
)
def test_malformed_routing_fails_at_load(tmp_path: Path, body: str) -> None:
    path = tmp_path / "r.yaml"
    path.write_text(body)
    with pytest.raises(RulesFormatError):
        Router.from_yaml(path)
