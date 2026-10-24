"""LLD §6.6–6.8: the committed synthetic policies, claims and ground truth are consistent with the design."""

import json
from datetime import date
from pathlib import Path

import pytest
from docx import Document

from claims_rag.components.chunker import load_policy_folder
from claims_rag.components.document_reader import ConverseDocumentReader, ScanAwareDocumentReader
from claims_rag.components.output_validator import validate_schema
from claims_rag.components.rules_engine import RulesEngine
from claims_rag.components.safety import redact_pii

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
GENERATED_ON = date(2026, 10, 24)
CLAIMS = {
    "motor_clean": ("pdf", "document_block", "covered", "auto_approve"),
    "home_gradual_leak": ("docx", "document_block", "not_covered", "auto_approve"),
    "home_storm": ("txt", "document_block", "covered", "human_review"),
    "motor_messy_scan": ("pdf", "page_images", "insufficient_information", "human_review"),
}
FIELD_SCHEMA = {
    "claimant": (str, type(None)),
    "policy_number": (str, type(None)),
    "incident_date": (str, type(None)),
    "incident_type": str,
    "amount_claimed": (float, int, type(None)),
    "currency": (str, type(None)),
    "description": str,
    "missing_info": list,
}
INCIDENT_TYPES = {
    "motor_collision",
    "motor_theft",
    "home_water",
    "home_storm",
    "home_fire",
    "home_theft",
    "other",
}


def _truth(stem: str) -> dict:  # type: ignore[type-arg]
    return json.loads((DATA / "ground_truth" / f"{stem}.json").read_text())


def _engine(tmp_path: Path) -> RulesEngine:
    path = tmp_path / "rules.yaml"
    path.write_text(
        "rules:\n"
        "  - {id: BR1, type: required, field: policy_number}\n"
        "  - {id: BR2, type: required, field: incident_date}\n"
        "  - {id: BR3, type: positive_number, field: amount_claimed}\n"
        "  - {id: BR4, type: date_not_future, field: incident_date}\n"
        '  - {id: BR5, type: regex, field: policy_number, pattern: "^(MOT|HOM)-\\\\d{6}$"}\n'
    )
    return RulesEngine.from_yaml(path)


def test_policies_chunk_into_unique_clauses() -> None:
    chunks = load_policy_folder(DATA / "policies", size=800, overlap=100)
    sources = {c.source for c in chunks}
    assert sources == {"motor_comprehensive.txt", "home_buildings_contents.txt"}
    ids = [c.clause_id for c in chunks]
    assert len(ids) == len(set(ids))
    assert "home_buildings_contents:4.2" in ids
    assert any("gradual" in c.title.lower() for c in chunks if c.clause_id == "home_buildings_contents:4.2")


@pytest.mark.parametrize("stem", CLAIMS)
def test_ground_truth_matches_the_field_contract(stem: str) -> None:
    truth = _truth(stem)
    assert set(truth) == {
        "fields",
        "expected_coverage_decision",
        "expected_route",
        "expected_clause_ids",
        "notes",
    }
    assert validate_schema(truth["fields"], FIELD_SCHEMA) == []
    assert truth["fields"]["incident_type"] in INCIDENT_TYPES
    _, _, decision, route = CLAIMS[stem]
    assert (truth["expected_coverage_decision"], truth["expected_route"]) == (decision, route)


@pytest.mark.parametrize("stem", CLAIMS)
def test_expected_clauses_exist_in_the_policies(stem: str) -> None:
    ids = {c.clause_id for c in load_policy_folder(DATA / "policies", size=800, overlap=100)}
    expected = set(_truth(stem)["expected_clause_ids"])
    assert expected and expected <= ids


def test_business_rules_flag_only_the_messy_scan(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    for stem in CLAIMS:
        violations = {v.rule_id for v in engine.evaluate(_truth(stem)["fields"], GENERATED_ON)}
        assert violations == ({"BR1", "BR2"} if stem == "motor_messy_scan" else set()), stem


@pytest.mark.parametrize("stem", CLAIMS)
def test_claim_document_reaches_the_model_in_the_expected_mode(stem: str) -> None:
    fmt, mode, _, _ = CLAIMS[stem]
    path = DATA / "claims" / f"{stem}.{fmt}"
    doc = ScanAwareDocumentReader(ConverseDocumentReader()).read(path.read_bytes(), fmt, path.name)
    assert doc.mode == mode


def test_document_text_carries_the_ground_truth() -> None:
    docx_text = "\n".join(
        p.text for p in Document(str(DATA / "claims" / "home_gradual_leak.docx")).paragraphs
    )
    assert "HOM-215067" in docx_text
    storm = (DATA / "claims" / "home_storm.txt").read_text()
    assert "HOM-730442" in storm
    assert redact_pii(storm) != storm  # contains synthetic PII so redaction has something to do
