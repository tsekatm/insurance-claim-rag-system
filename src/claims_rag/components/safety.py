"""PII redaction and a grounding check — a local stand-in for Bedrock Guardrails (LLD §4.6)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

from claims_rag.components.retriever import RetrievedChunk

# Order matters: a 13-digit ID number must be masked before the phone pattern can see part of it.
_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[EMAIL]"),
    (re.compile(r"(?<!\d)\d{13}(?!\d)"), "[ID_NUMBER]"),
    (re.compile(r"(?<![\w+])\+\d{1,3}(?:[ -]?\d{2,4}){2,4}(?!\d)"), "[PHONE]"),
    (re.compile(r"(?<![\w+])0\d{2}[ -]?\d{3}[ -]?\d{4}(?!\d)"), "[PHONE]"),
]


@dataclass(frozen=True)
class GroundingResult:
    grounded: bool
    cited_ids: tuple[str, ...]
    unknown_ids: tuple[str, ...]  # cited but not among the retrieved clauses
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def redact_pii(text: str) -> str:
    """Mask emails, 13-digit national ID numbers and phone numbers. Idempotent."""
    for pattern, mask in _PATTERNS:
        text = pattern.sub(mask, text)
    return text


def check_grounding(
    cited_ids: Sequence[str], retrieved: Sequence[RetrievedChunk], citations_required: bool
) -> GroundingResult:
    known = {chunk.clause_id for chunk in retrieved}
    cited = tuple(cited_ids)
    unknown = tuple(cid for cid in cited if cid not in known)
    if unknown:
        reason = f"cited clauses not retrieved: {', '.join(unknown)}"
    elif citations_required and not cited:
        reason = "no clauses cited"
    else:
        reason = "all cited clauses were retrieved"
    return GroundingResult(not unknown and not (citations_required and not cited), cited, unknown, reason)
