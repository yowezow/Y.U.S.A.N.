import pytest
from yusan_core.config.secrets import SecretsService
from yusan_core.llm import APIKeyRequiredError, UnsupportedProviderError
from yusan_core.llm.gemini import GeminiProvider
from yusan_core.llm.manager import LLMManager


class MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


@pytest.mark.asyncio
async def test_missing_key_uses_local_fallback() -> None:
    manager = LLMManager("gemini", SecretsService(MemoryBackend(), {}))
    assert not manager.is_configured()
    with pytest.raises(APIKeyRequiredError):
        await manager.respond("Merhaba")


def test_manager_builds_provider_from_secure_configuration_and_applies_the_selected_model() -> None:
    secrets = SecretsService(MemoryBackend(), {})
    secrets.save_api_key("gemini", "safe-test-key")
    manager = LLMManager("gemini", secrets, model="gemini-3.8-flash")
    assert manager.is_configured()
    provider = manager._provider()
    assert isinstance(provider, GeminiProvider)
    assert provider.model == "gemini-3.8-flash"


@pytest.mark.asyncio
async def test_invalid_provider_is_rejected() -> None:
    manager = LLMManager("future-provider", SecretsService(MemoryBackend(), {}))
    with pytest.raises(UnsupportedProviderError):
        await manager.respond("Merhaba")
