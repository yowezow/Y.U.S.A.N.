from fastapi.testclient import TestClient
import pytest
from yusan_core.api import server
from yusan_core.config.secrets import SecretStorageError, SecretsService
from yusan_core.config.settings import DEFAULT_GEMINI_MODEL
from yusan_core.llm import (
    ConnectionFailedError,
    InvalidAPIKeyError,
    ModelUnavailableError,
    QuotaExceededError,
)


class MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


def test_time_action_contract() -> None:
    with TestClient(server.app) as client:
        response = client.post("/api/chat", json={"message": "Saat kaç?"})
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "system_action"
    assert data["action"] == "get_time"
    assert data["success"] is True


def test_packaged_tauri_origin_can_call_the_local_core() -> None:
    with TestClient(server.app) as client:
        response = client.get("/api/config/llm", headers={"Origin": "tauri://localhost"})
    assert response.headers["access-control-allow-origin"] == "tauri://localhost"


def test_startup_and_missing_key_are_safe(monkeypatch) -> None:
    class UnconfiguredManager:
        provider_name = "gemini"
        model = DEFAULT_GEMINI_MODEL

        def is_configured(self) -> bool:
            raise AssertionError("/health must not inspect credentials or LLM configuration")

    monkeypatch.setattr(server, "llm", UnconfiguredManager())
    with TestClient(server.app) as client:
        response = client.get("/health")
    assert response.json() == {"status": "ok", "service": "yusan-core", "version": "1.0"}

    class MissingKeyManager:
        provider_name = "gemini"
        model = DEFAULT_GEMINI_MODEL

        def is_configured(self) -> bool:
            return False

    monkeypatch.setattr(server, "llm", MissingKeyManager())
    with TestClient(server.app) as client:
        config = client.get("/api/config/llm")
    assert config.json()["status"] == "api_key_required"
    assert config.json()["model"] == DEFAULT_GEMINI_MODEL


def test_api_key_save_only_returns_configuration_status(monkeypatch) -> None:
    secure_store = SecretsService(MemoryBackend(), {})
    monkeypatch.setattr(server, "secrets", secure_store)
    monkeypatch.setattr(server, "llm", type("Manager", (), {"provider_name": "gemini", "model": DEFAULT_GEMINI_MODEL})())
    with TestClient(server.app) as client:
        response = client.post("/api/config/llm", json={"provider": "gemini", "api_key": "private-key"})
    assert response.status_code == 200
    assert response.json() == {"configured": True, "provider": "gemini", "model": DEFAULT_GEMINI_MODEL, "status": "configured"}
    assert "private-key" not in response.text


@pytest.mark.asyncio
async def test_model_discovery_returns_models_and_selected_model(monkeypatch) -> None:
    class ConfiguredManager:
        provider_name = "gemini"
        model = DEFAULT_GEMINI_MODEL

        def is_configured(self) -> bool:
            return True

        async def discover_models(self):
            return type("Discovery", (), {"models": ["gemini-3.8-flash", "gemini-3.7-flash"], "selected_model": "gemini-3.8-flash"})()

    monkeypatch.setattr(server, "llm", ConfiguredManager())
    with TestClient(server.app) as client:
        response = client.get("/api/config/llm/models")
    assert response.json() == {
        "models": ["gemini-3.8-flash", "gemini-3.7-flash"],
        "selected_model": "gemini-3.8-flash",
        "provider": "gemini",
        "status": "configured",
        "error_type": None,
        "message": None,
    }


def test_config_api_forwards_the_api_key_property_to_secure_storage(monkeypatch) -> None:
    class CapturingSecrets:
        received: tuple[str, str] | None = None

        def save_api_key(self, provider: str, api_key: str) -> None:
            self.received = provider, api_key

    secure_store = CapturingSecrets()
    monkeypatch.setattr(server, "secrets", secure_store)
    monkeypatch.setattr(server, "llm", type("Manager", (), {"provider_name": "gemini", "model": DEFAULT_GEMINI_MODEL})())

    with TestClient(server.app) as client:
        response = client.post(
            "/api/config/llm",
            json={"provider": "gemini", "api_key": "  safe-test-key  \n"},
        )

    assert response.status_code == 200
    assert secure_store.received == ("gemini", "  safe-test-key  \n")


def test_config_api_returns_a_structured_storage_error(monkeypatch) -> None:
    class FailingSecrets:
        def save_api_key(self, provider: str, api_key: str) -> None:
            raise SecretStorageError("keyring_readback", "credential_readback_missing", "Credential save could not be verified")

    monkeypatch.setattr(server, "secrets", FailingSecrets())
    monkeypatch.setattr(server, "llm", type("Manager", (), {"provider_name": "gemini", "model": DEFAULT_GEMINI_MODEL})())
    with TestClient(server.app) as client:
        response = client.post("/api/config/llm", json={"provider": "gemini", "api_key": "safe-test-key"})

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "stage": "keyring_readback",
            "code": "credential_readback_missing",
            "message": "Credential save could not be verified",
        }
    }
    assert "safe-test-key" not in response.text


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (InvalidAPIKeyError("do not expose a provider response"), {"authenticated": False, "status": "invalid_api_key", "error_type": "authentication", "message": "API key is invalid"}),
        (ModelUnavailableError("do not expose a provider response"), {"authenticated": True, "status": "model_unavailable", "error_type": "model_unavailable", "message": "The API key is valid, but this model is not available for this project."}),
        (QuotaExceededError("do not expose a provider response"), {"authenticated": True, "status": "quota_exceeded", "error_type": "quota_exceeded", "message": "API quota exceeded"}),
        (ConnectionFailedError("do not expose a provider response"), {"authenticated": None, "status": "connection_failed", "error_type": "network", "message": "Could not reach Gemini"}),
    ],
)
def test_connection_test_returns_safe_structured_error_statuses(monkeypatch, error, expected) -> None:
    class FailingManager:
        provider_name = "gemini"
        model = DEFAULT_GEMINI_MODEL

        async def test_connection(self) -> None:
            raise error

    monkeypatch.setattr(server, "llm", FailingManager())
    with TestClient(server.app) as client:
        response = client.post("/api/config/llm/test", json={"provider": "gemini"})
    assert response.json() == {
        "success": False,
        "provider": "gemini",
        "model": DEFAULT_GEMINI_MODEL,
        **expected,
    }
