from datetime import datetime
import asyncio
import logging
import os
import signal
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ..config import SecretsService, get_settings
from ..config.secrets import SecretStorageError
from ..intents import Intent, IntentRouter
from ..llm import (
    APIKeyRequiredError,
    ConnectionFailedError,
    GeminiServiceError,
    InvalidAPIKeyError,
    LLMManager,
    ModelUnavailableError,
    PermissionDeniedError,
    QuotaExceededError,
    UnknownProviderError,
    UnsupportedProviderError,
)
from ..system import SystemManager

settings = get_settings()
logger = logging.getLogger("yusan")
router = IntentRouter()
system = SystemManager()
secrets = SecretsService()
llm = LLMManager(settings.llm_provider, secrets, settings.gemini_model)

app = FastAPI(title="YUSAN Core", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["tauri://localhost", "http://tauri.localhost", "http://localhost:1420"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


class CoreResponse(BaseModel):
    type: str
    content: str | None = None
    action: str | None = None
    success: bool | None = None
    message: str | None = None


class LLMConfigRequest(BaseModel):
    provider: str = "gemini"
    api_key: str | None = None


class LLMConfigStatus(BaseModel):
    configured: bool
    provider: str
    model: str
    status: str


class LLMModelsStatus(BaseModel):
    models: list[str]
    selected_model: str | None = None
    provider: str
    status: str
    error_type: str | None = None
    message: str | None = None


class LLMModelSelectionRequest(BaseModel):
    provider: str = "gemini"
    model: str


class ConnectionStatus(BaseModel):
    success: bool
    authenticated: bool | None
    provider: str
    model: str | None = None
    status: str
    error_type: str | None = None
    message: str | None = None


class ConfigErrorDetail(BaseModel):
    stage: str
    code: str
    message: str


def config_error(status_code: int, stage: str, code: str, message: str) -> None:
    logger.error("LLM configuration failed: stage=%s code=%s", stage, code)
    raise HTTPException(
        status_code=status_code,
        detail=ConfigErrorDetail(stage=stage, code=code, message=message).model_dump(),
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Report only Core liveness; credential and provider checks remain separate."""

    return {"status": "ok", "service": "yusan-core", "version": "1.0"}


@app.post("/shutdown")
async def shutdown() -> dict[str, str]:
    """Stop a Core instance that is bound exclusively to the local loopback address."""

    logger.info("YUSAN Core shutdown requested by its desktop parent")
    asyncio.get_running_loop().call_later(0.1, os.kill, os.getpid(), signal.SIGTERM)
    return {"status": "stopping"}


@app.get("/api/config/llm", response_model=LLMConfigStatus)
async def get_llm_config() -> LLMConfigStatus:
    try:
        configured = llm.is_configured()
    except SecretStorageError as exc:
        config_error(503, exc.stage, exc.code, str(exc))
    return LLMConfigStatus(
        configured=configured,
        provider=llm.provider_name,
        model=llm.model,
        status="configured" if configured else "api_key_required",
    )


@app.get("/api/config/llm/models", response_model=LLMModelsStatus)
async def get_llm_models() -> LLMModelsStatus:
    try:
        if not llm.is_configured():
            return LLMModelsStatus(models=[], provider=llm.provider_name, status="api_key_required", message="API key required")
        discovered = await llm.discover_models()
        return LLMModelsStatus(
            models=discovered.models,
            selected_model=discovered.selected_model,
            provider=llm.provider_name,
            status="configured",
        )
    except APIKeyRequiredError:
        return LLMModelsStatus(models=[], provider=llm.provider_name, status="api_key_required", message="API key required")
    except InvalidAPIKeyError:
        return LLMModelsStatus(models=[], provider=llm.provider_name, status="invalid_api_key", error_type="authentication", message="API key is invalid")
    except ModelUnavailableError:
        return LLMModelsStatus(models=[], provider=llm.provider_name, status="model_unavailable", error_type="model_unavailable", message="No chat-capable model is available for this project")
    except PermissionDeniedError:
        return LLMModelsStatus(models=[], provider=llm.provider_name, status="permission_denied", error_type="permission_denied", message="Your API project does not have access to Gemini models")
    except QuotaExceededError:
        return LLMModelsStatus(models=[], provider=llm.provider_name, status="quota_exceeded", error_type="quota_exceeded", message="API quota exceeded")
    except ConnectionFailedError:
        return LLMModelsStatus(models=[], provider=llm.provider_name, status="connection_failed", error_type="network", message="Could not reach Gemini")
    except GeminiServiceError:
        return LLMModelsStatus(models=[], provider=llm.provider_name, status="service_error", error_type="service_error", message="Gemini service error")
    except (SecretStorageError, UnknownProviderError, UnsupportedProviderError):
        return LLMModelsStatus(models=[], provider=llm.provider_name, status="unknown_error", error_type="configuration", message="Model list could not be loaded")


@app.put("/api/config/llm/model", response_model=LLMConfigStatus)
async def select_llm_model(payload: LLMModelSelectionRequest) -> LLMConfigStatus:
    if payload.provider.strip().casefold() != llm.provider_name:
        config_error(400, "request_validation", "unsupported_provider", "Unsupported LLM provider")
    try:
        selected = await llm.select_model(payload.model)
    except APIKeyRequiredError:
        config_error(400, "request_validation", "api_key_required", "API key required")
    except ModelUnavailableError:
        config_error(400, "model_selection", "model_unavailable", "Selected model is not available")
    except UnsupportedProviderError:
        config_error(400, "model_selection", "model_unavailable", "Selected model is not available")
    except (ConnectionFailedError, GeminiServiceError, SecretStorageError) as exc:
        config_error(503, "model_selection", "provider_unavailable", str(exc))
    return LLMConfigStatus(configured=True, provider=llm.provider_name, model=selected, status="configured")


@app.post("/api/config/llm", response_model=LLMConfigStatus)
async def save_llm_config(payload: LLMConfigRequest) -> LLMConfigStatus:
    provider = payload.provider.strip().casefold()
    key_received = payload.api_key is not None
    key_length = len(payload.api_key or "")
    logger.info(
        "LLM save request received: Provider=%s API key received=%s API key length=%d",
        provider,
        key_received,
        key_length,
    )
    if provider != llm.provider_name:
        config_error(400, "request_validation", "unsupported_provider", "Unsupported LLM provider")
    if payload.api_key is None or not payload.api_key.strip():
        config_error(400, "request_validation", "api_key_required", "API key required")
    try:
        logger.info("LLM save request forwarding to secure storage")
        secrets.save_api_key(provider, payload.api_key)
    except SecretStorageError as exc:
        config_error(503, exc.stage, exc.code, str(exc))
    except ValueError:
        config_error(400, "request_validation", "invalid_request", "API key could not be saved")
    logger.info("LLM save request completed successfully: Provider=%s", provider)
    return LLMConfigStatus(configured=True, provider=llm.provider_name, model=llm.model, status="configured")


@app.post("/api/config/llm/test", response_model=ConnectionStatus)
async def test_llm_connection(payload: LLMConfigRequest) -> ConnectionStatus:
    if payload.provider.strip().casefold() != llm.provider_name:
        return ConnectionStatus(
            success=False,
            authenticated=None,
            provider=payload.provider,
            status="invalid_provider",
            error_type="invalid_provider",
            message="Unsupported LLM provider",
        )
    try:
        result = await llm.test_connection()
        return ConnectionStatus(
            success=True,
            authenticated=result.authenticated,
            provider=result.provider,
            model=result.model,
            status="connected",
        )
    except APIKeyRequiredError:
        return ConnectionStatus(success=False, authenticated=False, provider=llm.provider_name, model=llm.model, status="api_key_required", error_type="api_key_required", message="API key required")
    except InvalidAPIKeyError:
        return ConnectionStatus(success=False, authenticated=False, provider=llm.provider_name, model=llm.model, status="invalid_api_key", error_type="authentication", message="API key is invalid")
    except ModelUnavailableError:
        return ConnectionStatus(success=False, authenticated=True, provider=llm.provider_name, model=llm.model, status="model_unavailable", error_type="model_unavailable", message="The API key is valid, but this model is not available for this project.")
    except PermissionDeniedError:
        return ConnectionStatus(success=False, authenticated=True, provider=llm.provider_name, model=llm.model, status="permission_denied", error_type="permission_denied", message="Your API project does not have access to this model")
    except QuotaExceededError:
        return ConnectionStatus(success=False, authenticated=True, provider=llm.provider_name, model=llm.model, status="quota_exceeded", error_type="quota_exceeded", message="API quota exceeded")
    except ConnectionFailedError:
        return ConnectionStatus(success=False, authenticated=None, provider=llm.provider_name, model=llm.model, status="connection_failed", error_type="network", message="Could not reach Gemini")
    except GeminiServiceError:
        return ConnectionStatus(success=False, authenticated=None, provider=llm.provider_name, model=llm.model, status="service_error", error_type="service_error", message="Gemini service error")
    except UnknownProviderError:
        return ConnectionStatus(success=False, authenticated=None, provider=llm.provider_name, model=llm.model, status="unknown_error", error_type="unknown", message="Gemini could not complete the request")
    except (SecretStorageError, UnsupportedProviderError):
        return ConnectionStatus(success=False, authenticated=None, provider=llm.provider_name, model=llm.model, status="connection_failed", error_type="configuration", message="Secure configuration is unavailable")


@app.post("/api/chat", response_model=CoreResponse)
async def chat(payload: ChatRequest) -> CoreResponse:
    route = router.route(payload.message)
    logger.info("Intent detected: %s", route.intent)
    try:
        if route.intent is Intent.GET_TIME:
            return CoreResponse(type="system_action", action="get_time", success=True, content=datetime.now().strftime("Şu an saat %H:%M."))
        if route.intent is Intent.OPEN_SETTINGS:
            return CoreResponse(type="system_action", action="open_settings", success=True, content="Ayarlar sayfasını açıyorum.")
        if route.intent in {Intent.OPEN_APP, Intent.OPEN_URL, Intent.WEB_SEARCH}:
            action = getattr(system, route.intent.value)
            action(route.value or "")
            return CoreResponse(type="system_action", action=route.intent.value, success=True, content="Tamamdır, isteğini yerine getirdim.")
        return CoreResponse(type="llm_response", content=await llm.respond(payload.message))
    except APIKeyRequiredError:
        return CoreResponse(
            type="configuration_required",
            content="Yapay zekâyı kullanmak için Ayarlar bölümünden Gemini API anahtarını ekle.",
        )
    except InvalidAPIKeyError:
        return CoreResponse(type="error", message="Yapay zekâ bağlantısı kurulamadı. Ayarlar bölümünden bağlantıyı kontrol et.")
    except ModelUnavailableError:
        return CoreResponse(type="error", message="Seçili Gemini modeli bu proje için kullanılamıyor.")
    except QuotaExceededError:
        return CoreResponse(type="error", message="Gemini API kotası aşıldı.")
    except (PermissionDeniedError, ConnectionFailedError, GeminiServiceError, UnknownProviderError):
        return CoreResponse(type="error", message="Yapay zekâ bağlantısı kurulamadı. Ayarlar bölümünden bağlantıyı kontrol et.")
    except Exception:
        logger.error("Action failed for intent: %s", route.intent)
        raise HTTPException(
            status_code=500,
            detail={"type": "error", "message": "YUSAN isteği tamamlayamadı."},
        ) from None
