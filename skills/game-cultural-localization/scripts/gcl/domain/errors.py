"""Shared domain exceptions and CLI exit code constants."""
from __future__ import annotations

__layer__ = "domain"
__pattern__ = "Domain Exceptions"
__owns__ = "exit codes, version string and core exception hierarchy"
__version__ = "3.1.0"

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2


class L10nError(Exception):
    """A usage or input error that ends CLI tools with EXIT_USAGE (2)."""


class ProviderError(L10nError):
    """A provider call failed after retries or hit a non retryable HTTP status."""


class ModelNotFoundError(ProviderError):
    """The vendor reported that the requested model identifier does not exist."""


class StreamInterrupted(ProviderError):
    """A streamed reply broke off before its completion marker."""


class BatchJobError(ProviderError):
    """A batch job failed, expired or was cancelled."""


class MissingKeyError(L10nError):
    """A required API key environment variable is missing."""


class ContextLeakError(L10nError):
    """Source text leaked into a blind jury slice or blind context view."""
