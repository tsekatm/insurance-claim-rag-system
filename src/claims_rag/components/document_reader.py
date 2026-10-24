"""Turn uploaded document bytes into what a model receives (LLD §4.9)."""

from __future__ import annotations

import io
from typing import Protocol

import pypdfium2 as pdfium

from claims_rag.components.model_invoker import DocumentInput
from claims_rag.errors import DocumentTooLargeError, UnsupportedDocumentError


class DocumentReader(Protocol):
    def read(self, content: bytes, fmt: str, name: str) -> DocumentInput: ...


class ConverseDocumentReader:
    """Sends the file as a Converse document block, unchanged."""

    SUPPORTED = frozenset({"pdf", "docx", "txt"})
    MAX_BYTES = 4_500_000  # Converse document block limit

    def read(self, content: bytes, fmt: str, name: str) -> DocumentInput:
        fmt = fmt.lower()
        if fmt not in self.SUPPORTED:
            raise UnsupportedDocumentError(f"{name}: format {fmt!r} not in {sorted(self.SUPPORTED)}")
        if len(content) > self.MAX_BYTES:
            raise DocumentTooLargeError(f"{name}: {len(content)} bytes > {self.MAX_BYTES}")
        return DocumentInput(name=name, format=fmt, content=content)


class ScanAwareDocumentReader:
    """Decorator over another reader: image-only PDFs are sent as page images instead of a document block.

    A Converse PDF document block may carry only the PDF's text layer, so a scanned page with no text layer
    would reach the model empty. Production swap: a TextractDocumentReader returning DocumentInput(text=...).
    """

    MAX_IMAGE_BYTES = 3_750_000  # Converse image block limit

    def __init__(
        self, inner: DocumentReader, min_text_chars: int = 50, max_pages: int = 5, render_scale: float = 2.0
    ) -> None:
        self._inner = inner
        self._min_text_chars = min_text_chars
        self._max_pages = max_pages
        self._render_scale = render_scale  # 2.0 x 72 pt ≈ 144 DPI

    def read(self, content: bytes, fmt: str, name: str) -> DocumentInput:
        if fmt.lower() != "pdf":
            return self._inner.read(content, fmt, name)
        try:
            pdf = pdfium.PdfDocument(content)
        except pdfium.PdfiumError as exc:
            raise UnsupportedDocumentError(f"{name}: not a readable PDF") from exc
        try:
            if self._text_chars(pdf) >= self._min_text_chars:
                return self._inner.read(content, fmt, name)
            if len(pdf) > self._max_pages:
                raise DocumentTooLargeError(f"{name}: scanned PDF has {len(pdf)} pages > {self._max_pages}")
            return DocumentInput(name=name, format="pdf", images=tuple(self._render(pdf, name)))
        finally:
            pdf.close()

    def _text_chars(self, pdf: pdfium.PdfDocument) -> int:
        count = 0
        for index in range(min(len(pdf), self._max_pages)):
            text = pdf[index].get_textpage().get_text_bounded()
            count += sum(1 for ch in text if not ch.isspace())
        return count

    def _render(self, pdf: pdfium.PdfDocument, name: str) -> list[bytes]:
        pages = []
        for index in range(len(pdf)):
            buffer = io.BytesIO()
            pdf[index].render(scale=self._render_scale).to_pil().save(buffer, format="PNG")
            if buffer.tell() > self.MAX_IMAGE_BYTES:
                raise DocumentTooLargeError(f"{name}: page {index + 1} image {buffer.tell()} bytes")
            pages.append(buffer.getvalue())
        return pages
