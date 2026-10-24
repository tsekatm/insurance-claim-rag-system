"""LLD §4.7 / §6.7: clause-aware chunking of policy text."""

from pathlib import Path

import pytest

from claims_rag.components.chunker import chunk_policy, load_policy_folder

POLICY = """\
Home Buildings and Contents Policy. Read with your schedule.

## 4 Exclusions

## 4.1 Exclusions — wear and tear
We do not cover wear and tear.

## 4.2 Exclusions — gradual damage
We do not cover damage that happens gradually, including leaks over time.
"""


def test_splits_by_heading_with_clause_ids_and_titles() -> None:
    chunks = chunk_policy(POLICY, "home_buildings_contents.txt", size=800, overlap=100)

    assert [c.clause_id for c in chunks] == [
        "home_buildings_contents:0",
        "home_buildings_contents:4.1",
        "home_buildings_contents:4.2",
    ]
    preamble, wear, gradual = chunks
    assert preamble.title == "Preamble"
    assert gradual.section == "4.2"
    assert gradual.title == "Exclusions — gradual damage"
    assert gradual.source == "home_buildings_contents.txt"
    assert gradual.text.startswith("4.2 Exclusions — gradual damage\n")
    assert "leaks over time" in gradual.text
    assert "wear and tear" not in gradual.text  # never mixed with its neighbour


def test_long_section_is_split_with_suffix_and_overlap() -> None:
    sentences = [f"Sentence number {i:02d} explains a condition of cover." for i in range(12)]
    text = "## 5 Conditions\n" + " ".join(sentences) + "\n"
    chunks = chunk_policy(text, "motor.txt", size=200, overlap=60)

    assert len(chunks) > 1
    assert [c.clause_id for c in chunks] == [f"motor:5#{n}" for n in range(1, len(chunks) + 1)]
    for chunk in chunks:
        body = chunk.text.removeprefix("5 Conditions\n")
        assert len(body) <= 200
    for previous, current in zip(chunks, chunks[1:], strict=False):
        prev_body = previous.text.removeprefix("5 Conditions\n")
        cur_body = current.text.removeprefix("5 Conditions\n")
        assert cur_body[:20] in prev_body  # carried-over overlap
    joined = " ".join(c.text for c in chunks)
    assert all(s in joined for s in sentences)  # nothing lost


def test_overlap_must_be_smaller_than_size() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_policy(POLICY, "p.txt", size=100, overlap=100)


def test_duplicate_section_numbers_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate section 1"):
        chunk_policy("## 1 A\nx\n## 1 B\ny\n", "p.txt", size=800, overlap=100)


def test_load_policy_folder_reads_txt_sorted(tmp_path: Path) -> None:
    (tmp_path / "b_motor.txt").write_text("## 1 Cover\nMotor cover.\n")
    (tmp_path / "a_home.txt").write_text("## 1 Cover\nHome cover.\n")
    (tmp_path / "notes.md").write_text("## 1 Ignore\nx\n")

    chunks = load_policy_folder(tmp_path, size=800, overlap=100)
    assert [c.clause_id for c in chunks] == ["a_home:1", "b_motor:1"]
    assert chunks[0].to_dict()["source"] == "a_home.txt"
