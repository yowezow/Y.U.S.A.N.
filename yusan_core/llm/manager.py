from ..config.model_preferences import ModelPreferences
from ..config.settings import DEFAULT_GEMINI_MODEL
from ..config.secrets import SecretsService
from .base import APIKeyRequiredError, ConnectionResult, LLMProvider, ModelDiscoveryResult, UnsupportedProviderError
from .gemini import GeminiProvider


class LocalFallbackProvider(LLMProvider):
    async def complete(self, prompt: str) -> str:
        return f"Bunu konuşmak isterim. Şimdilik yerel moddayım; bana daha fazla bağlam verir misin?"

    async def discover_models(self) -> list[str]:
        return ["local"]

    async def test_connection(self) -> ConnectionResult:
        return ConnectionResult(provider="local", model="local")


class LLMManager:
    def __init__(
        self,
        provider_name: str,
        secrets: SecretsService | None = None,
        model: str = DEFAULT_GEMINI_MODEL,
        model_preferences: ModelPreferences | None = None,
    ) -> None:
        self.provider_name = provider_name.strip().casefold()
        self.secrets = secrets or SecretsService()
        self._model_preferences = model_preferences or ModelPreferences()
        self.model = self._model_preferences.selected_model() or model.strip() or DEFAULT_GEMINI_MODEL

    def is_configured(self) -> bool:
        if self.provider_name != "gemini":
            raise UnsupportedProviderError("Unsupported LLM provider")
        return bool(self.secrets.resolve_api_key(self.provider_name))

    def _provider(self) -> LLMProvider:
        if self.provider_name != "gemini":
            raise UnsupportedProviderError("Unsupported LLM provider")
        api_key = self.secrets.resolve_api_key(self.provider_name)
        if not api_key:
            raise APIKeyRequiredError("API key required")
        return GeminiProvider(api_key, self.model)

    async def respond(self, message: str) -> str:
        return await self._provider().complete(message)

    async def test_connection(self) -> ConnectionResult:
        return await self._provider().test_connection()

    async def discover_models(self) -> ModelDiscoveryResult:
        models = await self._provider().discover_models()
        selected = self.model if self.model in models else self._preferred_model(models)
        self.model = selected
        self._model_preferences.save_selected_model(selected)
        return ModelDiscoveryResult(models=models, selected_model=selected)

    async def select_model(self, model: str) -> str:
        requested = model.strip()
        models = await self._provider().discover_models()
        if requested not in models:
            raise UnsupportedProviderError("Selected model is not available")
        self.model = requested
        self._model_preferences.save_selected_model(requested)
        return self.model

    @staticmethod
    def _preferred_model(models: list[str]) -> str:
        if DEFAULT_GEMINI_MODEL in models:
            return DEFAULT_GEMINI_MODEL
        flash = next((model for model in models if "flash" in model.casefold()), None)
        return flash or models[0]
