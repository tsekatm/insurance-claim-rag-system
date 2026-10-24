"""LLD §8: every error the package raises derives from ClaimsRagError."""

import pytest

from claims_rag import errors

ALL_ERRORS = [
    errors.ConfigError,
    errors.PromptNotFoundError,
    errors.PromptFormatError,
    errors.PromptVariableError,
    errors.RulesFormatError,
    errors.OutputValidationError,
    errors.InvalidClaimIdError,
    errors.UnsupportedDocumentError,
    errors.DocumentTooLargeError,
    errors.RetrieverError,
    errors.ModelInvocationError,
    errors.ProcessingError,
]


@pytest.mark.parametrize("cls", ALL_ERRORS)
def test_every_error_is_a_claims_rag_error(cls: type[Exception]) -> None:
    assert issubclass(cls, errors.ClaimsRagError)


def test_model_invocation_error_keeps_model_and_code() -> None:
    err = errors.ModelInvocationError("us.anthropic.claude-haiku-5-5", "ThrottlingException")
    assert err.model_id == "us.anthropic.claude-haiku-5-5"
    assert err.code == "ThrottlingException"
    assert "ThrottlingException" in str(err)


def test_processing_error_names_the_step() -> None:
    err = errors.ProcessingError("extract_fields", "model failed")
    assert err.step == "extract_fields"
    assert str(err) == "extract_fields: model failed"
