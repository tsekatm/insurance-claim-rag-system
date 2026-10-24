"""LLD §4.9: format/size validation and the scanned-PDF fallback to page images."""

import io

import pypdfium2 as pdfium
import pytest
from PIL import Image

from claims_rag.components.document_reader import (
    ConverseDocumentReader,
    DocumentReader,
    ScanAwareDocumentReader,
)
from claims_rag.components.model_invoker import DocumentInput
from claims_rag.errors import DocumentTooLargeError, UnsupportedDocumentError


def text_pdf(text: str) -> bytes:
    """A one-page PDF with a real text layer, built by hand (no PDF-writing dependency)."""
    stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 200] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def image_only_pdf(pages: int) -> bytes:
    """Pages with no text layer — what a scanner produces."""
    doc = pdfium.PdfDocument.new()
    for _ in range(pages):
        doc.new_page(200, 100)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


CLAIM_TEXT = "Claimant Thandi Mokoena policy MOT-123456 incident 2026-10-01 amount 18500"


class RecordingReader:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str, str]] = []

    def read(self, content: bytes, fmt: str, name: str) -> DocumentInput:
        self.calls.append((content, fmt, name))
        return DocumentInput(name=name, format=fmt, content=content)


# ---- ConverseDocumentReader ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["pdf", "docx", "txt", "PDF"])
def test_supported_formats_become_a_document_block(fmt: str) -> None:
    doc = ConverseDocumentReader().read(b"bytes", fmt, "claim.x")
    assert doc == DocumentInput(name="claim.x", format=fmt.lower(), content=b"bytes")
    assert doc.mode == "document_block"


@pytest.mark.parametrize("fmt", ["png", "xlsx", "exe", ""])
def test_unsupported_format(fmt: str) -> None:
    with pytest.raises(UnsupportedDocumentError):
        ConverseDocumentReader().read(b"x", fmt, "f")


def test_too_large() -> None:
    reader = ConverseDocumentReader()
    reader.read(b"x" * reader.MAX_BYTES, "txt", "ok")
    with pytest.raises(DocumentTooLargeError):
        reader.read(b"x" * (reader.MAX_BYTES + 1), "txt", "big")


def test_satisfies_protocol() -> None:
    readers: list[DocumentReader] = [
        ConverseDocumentReader(),
        ScanAwareDocumentReader(ConverseDocumentReader()),
    ]
    assert len(readers) == 2


# ---- ScanAwareDocumentReader --------------------------------------------------------------------------


def test_pdf_with_text_layer_is_delegated() -> None:
    inner = RecordingReader()
    content = text_pdf(CLAIM_TEXT)
    doc = ScanAwareDocumentReader(inner).read(content, "pdf", "motor_clean.pdf")
    assert inner.calls == [(content, "pdf", "motor_clean.pdf")]
    assert doc.mode == "document_block"


@pytest.mark.parametrize("fmt", ["docx", "txt"])
def test_other_formats_are_delegated_without_opening(fmt: str) -> None:
    inner = RecordingReader()
    ScanAwareDocumentReader(inner).read(b"not a pdf", fmt, "f")
    assert inner.calls == [(b"not a pdf", fmt, "f")]


def test_image_only_pdf_becomes_png_page_images() -> None:
    inner = RecordingReader()
    doc = ScanAwareDocumentReader(inner, render_scale=2.0).read(
        image_only_pdf(2), "pdf", "motor_messy_scan.pdf"
    )

    assert inner.calls == []
    assert doc.mode == "page_images"
    assert doc.name == "motor_messy_scan.pdf"
    assert len(doc.images) == 2
    with Image.open(io.BytesIO(doc.images[0])) as page:
        assert page.format == "PNG"
        assert page.size == (400, 200)  # 200x100 pt at scale 2


def test_short_text_layer_counts_as_scanned() -> None:
    doc = ScanAwareDocumentReader(RecordingReader(), min_text_chars=50).read(text_pdf("Page 1"), "pdf", "s")
    assert doc.mode == "page_images"


def test_scanned_pdf_over_page_limit() -> None:
    with pytest.raises(DocumentTooLargeError, match="pages"):
        ScanAwareDocumentReader(RecordingReader(), max_pages=2).read(image_only_pdf(3), "pdf", "s")


def test_invalid_pdf() -> None:
    with pytest.raises(UnsupportedDocumentError):
        ScanAwareDocumentReader(RecordingReader()).read(b"not a pdf", "pdf", "broken.pdf")
