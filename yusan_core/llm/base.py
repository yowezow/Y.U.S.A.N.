from abc import ABC, abstractmethod
from dataclasses import dataclass


class LLMError(RuntimeError):
    """Base error with a safe message that can be shown in the UI."""


class APIKeyRequiredError(LLMError):
    pass


class InvalidAPIKeyError(LLMError):
    pass


class ModelUnavailableError(LLMError):
    pass


class PermissionDeniedError(LLMError):
    pass


class QuotaExceededError(LLMError):
    pass


class ConnectionFailedError(LLMError):
    pass


class GeminiServiceError(LLMError):
    pass


class UnknownProviderError(LLMError):
    pass


class UnsupportedProviderError(LLMError):
    pass


@dataclass(frozen=True)
class ConnectionResult:
    provider: str
    model: str
    authenticated: bool = True


@dataclass(frozen=True)
class ModelDiscoveryResult:
    models: list[str]
    selected_model: str


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str) -> str:
        """Return a safe assistant response for the supplied prompt."""

    @abstractmethod
    async def discover_models(self) -> list[str]:
        """Return chat-capable models available to this provider account."""

    @abstractmethod
    async def test_connection(self) -> ConnectionResult:
        """Validate provider access without exposing provider implementation details."""
