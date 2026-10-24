"""Error hierarchy (LLD §8). Every error the package raises derives from ClaimsRagError."""


class ClaimsRagError(Exception):
    """Base class for all claims_rag errors."""


class ConfigError(ClaimsRagError):
    """A required setting is missing or malformed."""


class PromptNotFoundError(ClaimsRagError):
    """No prompt file for the requested name/version."""


class PromptFormatError(ClaimsRagError):
    """A prompt file is malformed."""


class PromptVariableError(ClaimsRagError):
    """Render variables do not match the template's required_vars."""


class RulesFormatError(ClaimsRagError):
    """A rules or routing file is malformed."""


class OutputValidationError(ClaimsRagError):
    """Model output is not a JSON object."""


class InvalidClaimIdError(ClaimsRagError):
    """A claim id is not safe to use in an S3 key."""


class UnsupportedDocumentError(ClaimsRagError):
    """The document format cannot be sent to the model."""


class DocumentTooLargeError(ClaimsRagError):
    """The document exceeds the size or page limit."""


class RetrieverError(ClaimsRagError):
    """The retriever was used incorrectly (not indexed, bad k)."""


class ModelInvocationError(ClaimsRagError):
    """A Bedrock call failed after botocore's retries."""

    def __init__(self, model_id: str, code: str) -> None:
        super().__init__(f"{model_id}: {code}")
        self.model_id = model_id
        self.code = code


class ProcessingError(ClaimsRagError):
    """A pipeline step failed."""

    def __init__(self, step: str, message: str) -> None:
        super().__init__(f"{step}: {message}")
        self.step = step
