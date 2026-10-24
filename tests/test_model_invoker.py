"""LLD §4.2: ModelInvoker against a fake bedrock-runtime client (no AWS)."""

import io
import json
from typing import Any

import pytest
from botocore.exceptions import ClientError

from claims_rag.components.model_invoker import DocumentInput, ModelInvoker
from claims_rag.errors import ModelInvocationError

MODEL = "us.anthropic.claude-haiku-5-5"


class FakeClient:
    def __init__(self, error_code: str | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.error_code = error_code

    def _maybe_fail(self, op: str) -> None:
        if self.error_code:
            raise ClientError({"Error": {"Code": self.error_code, "Message": "x"}}, op)

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("converse", kwargs))
        self._maybe_fail("Converse")
        return {
            "output": {"message": {"role": "assistant", "content": [{"text": '{"a": '}, {"text": "1}"}]}},
            "usage": {"inputTokens": 120, "outputTokens": 7, "totalTokens": 127},
            "stopReason": "end_turn",
        }

    def invoke_model(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("invoke_model", kwargs))
        self._maybe_fail("InvokeModel")
        return {"body": io.BytesIO(json.dumps({"embedding": [0.1, 0.2, 0.3]}).encode())}


def _invoker(client: FakeClient) -> ModelInvoker:
    return ModelInvoker(client)  # type: ignore[arg-type]


def test_converse_without_document_sends_system_text_and_inference_config() -> None:
    client = FakeClient()
    resp = _invoker(client).converse(MODEL, "be exact", "hello", temperature=0.2, max_tokens=300)

    ((op, kwargs),) = client.calls
    assert op == "converse"
    assert kwargs["modelId"] == MODEL
    assert kwargs["system"] == [{"text": "be exact"}]
    assert kwargs["messages"] == [{"role": "user", "content": [{"text": "hello"}]}]
    assert kwargs["inferenceConfig"] == {"temperature": 0.2, "maxTokens": 300}
    assert resp.text == '{"a": 1}'
    assert (resp.input_tokens, resp.output_tokens) == (120, 7)
    assert resp.stop_reason == "end_turn"
    assert resp.model_id == MODEL
    assert resp.latency_ms >= 0


def test_converse_puts_bytes_document_block_before_the_question() -> None:
    client = FakeClient()
    doc = DocumentInput(name="motor_clean.pdf", format="pdf", content=b"%PDF-1.7")
    _invoker(client).converse(MODEL, "s", "extract", document=doc)

    content = client.calls[0][1]["messages"][0]["content"]
    assert content[0] == {
        "document": {"format": "pdf", "name": "motor clean pdf", "source": {"bytes": b"%PDF-1.7"}}
    }
    assert content[1] == {"text": "extract"}


def test_converse_wraps_text_document_in_tags() -> None:
    client = FakeClient()
    _invoker(client).converse(MODEL, "s", "q", document=DocumentInput(name="n", text="claim text"))

    content = client.calls[0][1]["messages"][0]["content"]
    assert content == [{"text": "<document>\nclaim text\n</document>"}, {"text": "q"}]


def test_converse_sends_one_png_image_block_per_page() -> None:
    client = FakeClient()
    doc = DocumentInput(name="scan", format="pdf", images=(b"p1", b"p2"))
    _invoker(client).converse(MODEL, "s", "q", document=doc)

    content = client.calls[0][1]["messages"][0]["content"]
    assert content[:2] == [
        {"image": {"format": "png", "source": {"bytes": b"p1"}}},
        {"image": {"format": "png", "source": {"bytes": b"p2"}}},
    ]
    assert content[2] == {"text": "q"}


@pytest.mark.parametrize(
    "doc",
    [
        DocumentInput(name="none"),
        DocumentInput(name="two", format="pdf", content=b"x", text="y"),
        DocumentInput(name="three", format="pdf", content=b"x", images=(b"p",)),
    ],
)
def test_document_must_have_exactly_one_payload(doc: DocumentInput) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        _invoker(FakeClient()).converse(MODEL, "s", "q", document=doc)


def test_document_mode_reflects_payload() -> None:
    assert DocumentInput(name="a", format="pdf", content=b"x").mode == "document_block"
    assert DocumentInput(name="a", images=(b"p",)).mode == "page_images"
    assert DocumentInput(name="a", text="t").mode == "text"


def test_document_name_is_sanitised_and_truncated() -> None:
    client = FakeClient()
    doc = DocumentInput(name="claim_#1/scan.pdf" + "x" * 300, format="pdf", content=b"x")
    _invoker(client).converse(MODEL, "s", "q", document=doc)

    name = client.calls[0][1]["messages"][0]["content"][0]["document"]["name"]
    assert name.startswith("claim 1 scan pdf")
    assert len(name) == 200


def test_client_error_after_retries_becomes_model_invocation_error() -> None:
    with pytest.raises(ModelInvocationError) as exc:
        _invoker(FakeClient(error_code="ThrottlingException")).converse(MODEL, "s", "q")
    assert exc.value.model_id == MODEL
    assert exc.value.code == "ThrottlingException"


def test_converse_is_called_once_no_hand_written_retry() -> None:
    client = FakeClient(error_code="ThrottlingException")
    with pytest.raises(ModelInvocationError):
        _invoker(client).converse(MODEL, "s", "q")
    assert len(client.calls) == 1


def test_embed_calls_titan_v2_with_normalised_1024_dims() -> None:
    client = FakeClient()
    vector = _invoker(client).embed("amazon.titan-embed-text-v2:0", "water damage")

    ((op, kwargs),) = client.calls
    assert op == "invoke_model"
    assert kwargs["modelId"] == "amazon.titan-embed-text-v2:0"
    assert json.loads(kwargs["body"]) == {"inputText": "water damage", "dimensions": 1024, "normalize": True}
    assert vector == [0.1, 0.2, 0.3]


def test_embed_client_error_becomes_model_invocation_error() -> None:
    with pytest.raises(ModelInvocationError) as exc:
        _invoker(FakeClient(error_code="AccessDeniedException")).embed("amazon.titan-embed-text-v2:0", "t")
    assert exc.value.code == "AccessDeniedException"


def test_from_region_uses_adaptive_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_client(service: str, **kwargs: Any) -> FakeClient:
        captured.update(service=service, **kwargs)
        return FakeClient()

    monkeypatch.setattr("claims_rag.components.model_invoker.boto3.client", fake_client)
    ModelInvoker.from_region("us-east-1", max_retries=4)

    assert captured["service"] == "bedrock-runtime"
    assert captured["region_name"] == "us-east-1"
    assert captured["config"].retries == {"mode": "adaptive", "max_attempts": 4}


def test_to_dict_carries_metadata_but_never_document_bytes() -> None:
    doc = DocumentInput(name="a", format="pdf", content=b"secret")
    assert doc.to_dict() == {"name": "a", "format": "pdf", "mode": "document_block"}
    resp = _invoker(FakeClient()).converse(MODEL, "s", "q")
    assert set(resp.to_dict()) == {
        "text",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "model_id",
        "stop_reason",
    }
