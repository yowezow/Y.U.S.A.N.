from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors

from yusan_core.llm import ConnectionFailedError, InvalidAPIKeyError, ModelUnavailableError, QuotaExceededError
from yusan_core.llm.gemini import GeminiProvider


class FakePager:
    def __init__(self, models: list[object]) -> None:
        self.models = models

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index == len(self.models):
            raise StopAsyncIteration
        model = self.models[self._index]
        self._index += 1
        return model


class FakeModels:
    def __init__(self, models: list[object], generation: object = SimpleNamespace(text="OK")) -> None:
        self.models = models
        self.generation = generation
        self.generated_with: list[str] = []

    async def list(self) -> FakePager:
        if isinstance(self.models, Exception):
            raise self.models
        return FakePager(self.models)

    async def generate_content(self, *, model: str, contents: str) -> object:
        self.generated_with.append(model)
        if isinstance(self.generation, Exception):
            raise self.generation
        return self.generation


class FakeAio:
    def __init__(self, models: FakeModels) -> None:
        self.models = models
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeClient:
    def __init__(self, models: FakeModels) -> None:
        self.aio = FakeAio(models)


def provider(models: list[object], generation: object = SimpleNamespace(text="OK")) -> tuple[GeminiProvider, FakeModels, FakeClient]:
    fake_models = FakeModels(models, generation)
    client = FakeClient(fake_models)
    return GeminiProvider("not-a-real-key", "gemini-3.8-flash", client_factory=lambda **_: client), fake_models, client


@pytest.mark.asyncio
async def test_valid_key_lists_models_then_tests_the_selected_model() -> None:
    gemini, models, client = provider([SimpleNamespace(name="models/gemini-3.8-flash")])

    result = await gemini.test_connection()

    assert result.authenticated is True
    assert result.model == "gemini-3.8-flash"
    assert models.generated_with == ["gemini-3.8-flash"]
    assert client.aio.closed is True


@pytest.mark.asyncio
async def test_model_discovery_filters_non_chat_models() -> None:
    gemini, _, _ = provider([
        SimpleNamespace(name="models/gemini-3.8-flash"),
        SimpleNamespace(name="models/gemini-embedding-001"),
        SimpleNamespace(name="models/gemini-3.8-flash-image"),
        SimpleNamespace(name="models/veo-3.1"),
    ])

    assert await gemini.discover_models() == ["gemini-3.8-flash"]


@pytest.mark.asyncio
async def test_valid_key_without_selected_model_is_not_an_authentication_failure() -> None:
    gemini, models, _ = provider([SimpleNamespace(name="models/gemini-3.7-flash")])

    with pytest.raises(ModelUnavailableError):
        await gemini.test_connection()

    assert models.generated_with == []


@pytest.mark.asyncio
async def test_connection_maps_invalid_credentials() -> None:
    error = errors.ClientError(401, {"error": {"status": "UNAUTHENTICATED", "message": "API key not valid"}})
    gemini, _, _ = provider([SimpleNamespace(name="models/gemini-3.8-flash")], error)

    with pytest.raises(InvalidAPIKeyError):
        await gemini.test_connection()


@pytest.mark.asyncio
async def test_connection_maps_quota_errors() -> None:
    error = errors.ClientError(429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "quota"}})
    gemini, _, _ = provider([SimpleNamespace(name="models/gemini-3.8-flash")], error)

    with pytest.raises(QuotaExceededError):
        await gemini.test_connection()


@pytest.mark.asyncio
async def test_connection_maps_network_errors() -> None:
    gemini, _, _ = provider(httpx.ConnectError("offline"))

    with pytest.raises(ConnectionFailedError):
        await gemini.test_connection()
