"""LLD §4.6: PII redaction and grounding check (Bedrock Guardrails stand-in)."""

import pytest

from claims_rag.components.retriever import RetrievedChunk
from claims_rag.components.safety import check_grounding, redact_pii


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Email thandi.m@example.co.za now", "Email [EMAIL] now"),
        ("ID 8001015009087 on file", "ID [ID_NUMBER] on file"),
        ("Call +27 82 555 0123 today", "Call [PHONE] today"),
        ("Call +27825550123 today", "Call [PHONE] today"),
        ("Call 082 555 0123 today", "Call [PHONE] today"),
        ("Call 0825550123 today", "Call [PHONE] today"),
        ("Call +44 20 7946 0958 today", "Call [PHONE] today"),
    ],
)
def test_redacts_pii(text: str, expected: str) -> None:
    assert redact_pii(text) == expected


@pytest.mark.parametrize(
    "text",
    ["Policy MOT-123456", "Incident 2026-10-01", "Claimed R 18 500.00", "Amount 18500", "Clause 4.2"],
)
def test_leaves_claim_data_alone(text: str) -> None:
    assert redact_pii(text) == text


def test_redaction_is_idempotent() -> None:
    once = redact_pii("a@b.com, 8001015009087, 082 555 0123")
    assert once == "[EMAIL], [ID_NUMBER], [PHONE]"
    assert redact_pii(once) == once


def _retrieved(*ids: str) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(clause_id=i, source="p.txt", section=i, title="t", text="x", score=0.5) for i in ids
    ]


def test_grounded_when_all_citations_were_retrieved() -> None:
    result = check_grounding(["home:4.2"], _retrieved("home:4.2", "home:3.1"), citations_required=True)
    assert result.grounded
    assert result.cited_ids == ("home:4.2",)
    assert result.unknown_ids == ()
    assert result.to_dict()["grounded"] is True


def test_not_grounded_when_a_citation_was_not_retrieved() -> None:
    result = check_grounding(["home:4.2", "home:9.9"], _retrieved("home:4.2"), citations_required=True)
    assert not result.grounded
    assert result.unknown_ids == ("home:9.9",)
    assert "home:9.9" in result.reason


def test_citations_required_but_none_given() -> None:
    assert not check_grounding([], _retrieved("home:4.2"), citations_required=True).grounded
    assert check_grounding([], _retrieved("home:4.2"), citations_required=False).grounded
