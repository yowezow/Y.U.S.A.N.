"""Gemini provider powered by the official Google GenAI SDK."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from google import genai
from google.genai import errors

from .base import (
    ConnectionFailedError,
    ConnectionResult,
    GeminiServiceError,
    InvalidAPIKeyError,
    LLMProvider,
    ModelUnavailableError,
    PermissionDeniedError,
    QuotaExceededError,
    UnknownProviderError,
)


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, client_factory: Callable[..., Any] = genai.Client) -> None:
        self.api_key = api_key
        self.model = model
        self._client_factory = client_factory

    async def complete(self, prompt: str) -> str:
        client = self._client_factory(api_key=self.api_key)
        try:
            response = await client.aio.models.generate_content(model=self.model, contents=prompt)
            if not response.text:
                raise UnknownProviderError("Gemini returned an empty response")
            return response.text
        except errors.APIError as exc:
            raise self._map_api_error(exc) from exc
        except (httpx.HTTPError, OSError, TimeoutError) as exc:
            raise ConnectionFailedError("Could not reach Gemini") from exc
        finally:
            await self._close_client(client)

    async def discover_models(self) -> list[str]:
        """List models this API project can use for text chat."""

        client = self._client_factory(api_key=self.api_key)
        try:
            return await self._discover_models_with_client(client)
        except errors.APIError as exc:
            raise self._map_api_error(exc) from exc
        except (httpx.HTTPError, OSError, TimeoutError) as exc:
            raise ConnectionFailedError("Could not reach Gemini") from exc
        finally:
            await self._close_client(client)

    async def test_connection(self) -> ConnectionResult:
        """Validate credentials independently from selected-model availability."""

        client = self._client_factory(api_key=self.api_key)
        try:
            available_models = set(await self._discover_models_with_client(client))
            if self.model not in available_models:
                raise ModelUnavailableError("Selected model is unavailable")

            await client.aio.models.generate_content(
                model=self.model,
                contents="Reply with exactly: OK",
            )
            return ConnectionResult(provider="gemini", model=self.model)
        except errors.APIError as exc:
            raise self._map_api_error(exc) from exc
        except (httpx.HTTPError, OSError, TimeoutError) as exc:
            raise ConnectionFailedError("Could not reach Gemini") from exc
        finally:
            await self._close_client(client)

    @staticmethod
    def _model_id(model: Any) -> str:
        return str(getattr(model, "name", "")).removeprefix("models/")

    @classmethod
    async def _discover_models_with_client(cls, client: Any) -> list[str]:
        pager = await client.aio.models.list()
        available = {
            model_id
            async for model in pager
            if (model_id := cls._model_id(model)) and cls._is_chat_model(model, model_id)
        }
        if not available:
            raise ModelUnavailableError("No chat-capable Gemini models are available")
        return sorted(available)

    @staticmethod
    def _is_chat_model(model: Any, model_id: str) -> bool:
        normalized = model_id.casefold()
        if not normalized.startswith("gemini-"):
            return False
        excluded = ("embedding", "image", "audio", "tts", "live", "robotics", "nano", "veo")
        if any(marker in normalized for marker in excluded):
            return False
        capabilities = getattr(model, "supported_generation_methods", None) or getattr(model, "supported_actions", None)
        if capabilities:
            return any("generatecontent" in str(capability).replace("_", "").casefold() for capability in capabilities)
        return True

    @staticmethod
    async def _close_client(client: Any) -> None:
        close = getattr(getattr(client, "aio", None), "aclose", None)
        if close is not None:
            await close()

    @staticmethod
    def _map_api_error(error: errors.APIError):
        code = error.code
        status = (error.status or "").upper()
        message = (error.message or "").casefold()

        if code == 401 or status == "UNAUTHENTICATED" or "api key not valid" in message or "api_key_invalid" in message:
            return InvalidAPIKeyError("API key is invalid")
        if code == 429 or status == "RESOURCE_EXHAUSTED":
            return QuotaExceededError("API quota exceeded")
        if code == 404 or status == "NOT_FOUND":
            return ModelUnavailableError("Selected model is unavailable")
        if code == 403 or status == "PERMISSION_DENIED":
            return PermissionDeniedError("Your API project does not have access to this model")
        if code >= 500:
            return GeminiServiceError("Gemini service error")
        return UnknownProviderError("Gemini could not complete the request")
