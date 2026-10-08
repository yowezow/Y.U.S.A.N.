import logging

import pytest

from yusan_core.config.secrets import GEMINI_ACCOUNT, SERVICE_NAME, SecretStorageError, SecretsService, run_keyring_self_test


class MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.calls: list[tuple[str, str, str]] = []

    def get_password(self, service: str, username: str) -> str | None:
        self.calls.append(("get", service, username))
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.calls.append(("set", service, username))
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.calls.append(("delete", service, username))
        self.values.pop((service, username), None)


def test_secure_store_never_returns_a_key_to_status_callers() -> None:
    backend = MemoryBackend()
    secrets = SecretsService(backend, {})
    secrets.save_api_key("gemini", "secret-value")
    assert backend.values[(SERVICE_NAME, GEMINI_ACCOUNT)] == "secret-value"
    assert secrets.has_api_key("gemini")
    assert secrets.get_api_key("gemini") == "secret-value"
    secrets.delete_api_key("gemini")
    assert not secrets.has_api_key("gemini")


def test_environment_is_only_a_fallback_after_secure_storage() -> None:
    backend = MemoryBackend()
    secrets = SecretsService(backend, {"GEMINI_API_KEY": "environment-key"})
    assert secrets.resolve_api_key("gemini") == "environment-key"
    secrets.save_api_key("gemini", "keychain-key")
    assert secrets.resolve_api_key("gemini") == "keychain-key"


def test_secure_store_trims_only_surrounding_api_key_whitespace() -> None:
    secrets = SecretsService(MemoryBackend(), {})
    secrets.save_api_key(" GEMINI ", "  key-with-internal-value  \n")
    assert secrets.get_api_key("gemini") == "key-with-internal-value"


def test_save_and_readback_use_the_fixed_gemini_keychain_identifiers() -> None:
    backend = MemoryBackend()
    SecretsService(backend, {}).save_api_key("gemini", "safe-test-key")

    assert backend.calls == [
        ("set", SERVICE_NAME, GEMINI_ACCOUNT),
        ("get", SERVICE_NAME, GEMINI_ACCOUNT),
    ]


def test_readback_mismatch_returns_a_structured_storage_error() -> None:
    class MismatchedReadbackBackend(MemoryBackend):
        def get_password(self, service: str, username: str) -> str | None:
            super().get_password(service, username)
            return "different-value"

    with pytest.raises(SecretStorageError) as error:
        SecretsService(MismatchedReadbackBackend(), {}).save_api_key("gemini", "safe-test-key")

    assert error.value.stage == "keyring_readback"
    assert error.value.code == "credential_readback_mismatch"


def test_secret_logs_include_safe_stages_without_the_key(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="yusan.secrets")
    SecretsService(MemoryBackend(), {}).save_api_key("gemini", "safe-test-key")

    assert "API key received: True" in caplog.text
    assert "Provider: gemini" in caplog.text
    assert "Credential save succeeded" in caplog.text
    assert "Credential readback succeeded" in caplog.text
    assert "safe-test-key" not in caplog.text


def test_keyring_self_test_uses_an_isolated_temporary_credential() -> None:
    backend = MemoryBackend()

    result = run_keyring_self_test(backend)

    assert result.readback_verified is True
    assert result.cleanup_verified is True
    assert backend.values == {}
    assert all(service == "YUSAN.keyring-self-test" for _, service, _ in backend.calls)


def test_rejects_an_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        SecretsService(MemoryBackend(), {}).has_api_key("unknown")
