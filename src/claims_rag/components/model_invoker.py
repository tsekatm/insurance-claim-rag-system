"""Model access through the Bedrock Converse API (LLD §4.2)."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Literal

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from claims_rag.errors import ModelInvocationError

if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime import BedrockRuntimeClient

DocumentMode = Literal["document_block", "page_images", "text"]

_NAME_DISALLOWED = re.compile(r"[^A-Za-z0-9 \-()\[\]]+")
_MAX_NAME = 200


@dataclass(frozen=True)
class DocumentInput:
    """What a model receives as the document: bytes for a Converse document block, page images, or text."""

    name: str
    format: str | None = None  # "pdf" | "docx" | "txt" when content is bytes
    content: bytes | None = None
    text: str | None = None  # set instead of content by a text-producing reader (e.g. Textract)
    images: tuple[bytes, ...] = ()  # PNG page images, set instead of content for scanned PDFs

    @property
    def mode(self) -> DocumentMode:
        self._check_one_payload()
        if self.content is not None:
            return "document_block"
        return "page_images" if self.images else "text"

    def _check_one_payload(self) -> None:
        if sum((self.content is not None, self.text is not None, bool(self.images))) != 1:
            raise ValueError(f"document {self.name!r} must set exactly one of content, text, images")

    def to_dict(self) -> dict[str, Any]:
        """Metadata only — document bytes and text are never included."""
        return {"name": self.name, "format": self.format, "mode": self.mode}


@dataclass(frozen=True)
class ModelResponse:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    model_id: str
    stop_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sanitise_name(name: str) -> str:
    """Converse allows only alphanumerics, single spaces, hyphens, parentheses and square brackets."""
    return " ".join(_NAME_DISALLOWED.sub(" ", name).split())[:_MAX_NAME]


def _document_blocks(document: DocumentInput) -> list[Any]:
    mode = document.mode
    if mode == "document_block":
        return [
            {
                "document": {
                    "format": document.format,
                    "name": _sanitise_name(document.name),
                    "source": {"bytes": document.content},
                }
            }
        ]
    if mode == "page_images":
        return [{"image": {"format": "png", "source": {"bytes": page}}} for page in document.images]
    return [{"text": f"<document>\n{document.text}\n</document>"}]


class ModelInvoker:
    """Model-agnostic Converse calls plus Titan embeddings. Never logs prompts, documents or output."""

    def __init__(self, client: BedrockRuntimeClient) -> None:
        self.client = client

    @classmethod
    def from_region(cls, region: str, max_retries: int = 5) -> ModelInvoker:
        """bedrock-runtime client with botocore adaptive retries (backoff, jitter, client-side rate limit)."""
        config = Config(retries={"mode": "adaptive", "max_attempts": max_retries})
        return cls(boto3.client("bedrock-runtime", region_name=region, config=config))

    def converse(
        self,
        model_id: str,
        system: str,
        user_text: str,
        document: DocumentInput | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> ModelResponse:
        content = (_document_blocks(document) if document else []) + [{"text": user_text}]
        start = time.perf_counter()
        try:
            response = self.client.converse(
                modelId=model_id,
                system=[{"text": system}],
                messages=[{"role": "user", "content": content}],
                inferenceConfig={"temperature": temperature, "maxTokens": max_tokens},
            )
        except ClientError as exc:
            raise ModelInvocationError(model_id, exc.response["Error"]["Code"]) from exc
        latency_ms = int((time.perf_counter() - start) * 1000)
        blocks = response["output"]["message"]["content"]
        return ModelResponse(
            text="".join(block.get("text", "") for block in blocks),
            input_tokens=response["usage"]["inputTokens"],
            output_tokens=response["usage"]["outputTokens"],
            latency_ms=latency_ms,
            model_id=model_id,
            stop_reason=response["stopReason"],
        )

    def embed(self, model_id: str, text: str) -> list[float]:
        """Amazon Titan Text Embeddings V2 only: embeddings have no model-agnostic API like Converse."""
        body = json.dumps({"inputText": text, "dimensions": 1024, "normalize": True})
        try:
            response = self.client.invoke_model(modelId=model_id, body=body)
        except ClientError as exc:
            raise ModelInvocationError(model_id, exc.response["Error"]["Code"]) from exc
        embedding: list[float] = json.loads(response["body"].read())["embedding"]
        return embedding
