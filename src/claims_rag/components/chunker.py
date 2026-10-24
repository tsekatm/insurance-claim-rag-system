"""Clause-aware chunking of policy text with `## <section> <title>` headings (LLD §4.7, §6.7)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_HEADING = re.compile(r"^## +(\S+) +(.+?)\s*$", re.MULTILINE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    clause_id: str  # "{source_stem}:{section}" or "{source_stem}:{section}#{n}" when a section is split
    source: str
    section: str
    title: str
    text: str  # "<section> <title>\n<body>" so each chunk carries its heading into the embedding

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _units(body: str, size: int) -> list[str]:
    """Paragraphs; a paragraph longer than size becomes sentences; a sentence longer than size is cut."""
    units: list[str] = []
    for paragraph in (p.strip() for p in body.split("\n\n")):
        if not paragraph:
            continue
        parts = [paragraph] if len(paragraph) <= size else _SENTENCE_END.split(paragraph)
        for part in parts:
            units += [part[i : i + size] for i in range(0, len(part), size)]
    return units


def _tail(text: str, overlap: int) -> str:
    """Last `overlap` characters, starting at a word boundary."""
    tail = text[-overlap:]
    return tail[tail.find(" ") + 1 :] if " " in tail and len(text) > overlap else tail


def _split(body: str, size: int, overlap: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for unit in _units(body, size):
        if not current:
            current = unit
        elif len(current) + 1 + len(unit) <= size:
            current = f"{current} {unit}"
        else:
            pieces.append(current)
            carried = _tail(current, overlap)
            current = f"{carried} {unit}" if carried and len(carried) + 1 + len(unit) <= size else unit
    if current:
        pieces.append(current)
    return pieces


def chunk_policy(text: str, source: str, size: int, overlap: int) -> list[Chunk]:
    """Split by heading first so a clause is never mixed with its neighbour, then by size within a section."""
    if overlap >= size:
        raise ValueError(f"overlap ({overlap}) must be smaller than size ({size})")
    stem = Path(source).stem
    headings = list(_HEADING.finditer(text))
    sections = [("0", "Preamble", text[: headings[0].start()] if headings else text)]
    for i, match in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        sections.append((match.group(1), match.group(2), text[match.end() : end]))

    chunks: list[Chunk] = []
    seen: set[str] = set()
    for section, title, body in sections:
        if section in seen:
            raise ValueError(f"{source}: duplicate section {section}")
        seen.add(section)
        pieces = _split(body.strip(), size, overlap) if body.strip() else []
        for n, piece in enumerate(pieces, start=1):
            clause_id = f"{stem}:{section}" if len(pieces) == 1 else f"{stem}:{section}#{n}"
            chunks.append(Chunk(clause_id, source, section, title, f"{section} {title}\n{piece}"))
    return chunks


def load_policy_folder(folder: Path, size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(folder.glob("*.txt")):
        chunks += chunk_policy(path.read_text(), path.name, size, overlap)
    return chunks
