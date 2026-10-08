"""Secure API-key storage backed by the operating system credential manager."""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import keyring


SERVICE_NAME = "YUSAN"
GEMINI_ACCOUNT = "gemini_api_key"
SUPPORTED_PROVIDERS = frozenset({"gemini"})
logger = logging.getLogger("yusan.secrets")


class SecretStorageError(RuntimeError):
    """Raised when the operating-system credential store cannot be used."""

    def __init__(self, stage: str, code: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage
        self.code = code


@dataclass(frozen=True)
class KeyringSelfTestResult:
    backend: str
    readback_verified: bool
    cleanup_verified: bool


class CredentialBackend(Protocol):
    def get_password(self, service_name: str, username: str) -> str | None: ...

    def set_password(self, service_name: str, username: str, password: str) -> None: ...

    def delete_password(self, service_name: str, username: str) -> None: ...


class KeyringBackend:
    """The only adapter that calls the third-party keyring package directly."""

    def get_password(self, service_name: str, username: str) -> str | None:
        return keyring.get_password(service_name, username)

    def set_password(self, service_name: str, username: str, password: str) -> None:
        keyring.set_password(service_name, username, password)

    def delete_password(self, service_name: str, username: str) -> None:
        keyring.delete_password(service_name, username)

    @staticmethod
    def backend_name() -> str:
        backend = keyring.get_keyring()
        return f"{backend.__class__.__module__}.{backend.__class__.__qualname__}"


class SecretsService:
    """Provider-independent, safe API-key resolution and persistence."""

    def __init__(
        self,
        backend: CredentialBackend | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._backend = backend or KeyringBackend()
        self._environment = environment if environment is not None else os.environ

    @staticmethod
    def _provider(provider: str) -> str:
        normalized = provider.strip().casefold()
        if normalized not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        return normalized

    @staticmethod
    def _environment_name(provider: str) -> str:
        return f"{provider.upper()}_API_KEY"

    @staticmethod
    def _account(provider: str) -> str:
        if provider == "gemini":
            return GEMINI_ACCOUNT
        raise ValueError(f"Unsupported LLM provider: {provider}")

    def _backend_name(self) -> str:
        if isinstance(self._backend, KeyringBackend):
            try:
                return self._backend.backend_name()
            except Exception as exc:
                return f"unavailable ({type(exc).__name__})"
        return f"{self._backend.__class__.__module__}.{self._backend.__class__.__qualname__}"

    @staticmethod
    def _safe_exception_message(exc: Exception, api_key: str | None = None) -> str:
        message = " ".join(str(exc).split()) or "No additional details"
        if api_key:
            message = message.replace(api_key, "<redacted>")
        return message[:240]

    def _raise_storage_error(self, stage: str, code: str, exc: Exception, api_key: str | None = None) -> None:
        logger.error(
            "Credential %s failed: exception=%s message=%s",
            stage,
            type(exc).__name__,
            self._safe_exception_message(exc, api_key),
        )
        messages = {
            "keyring_write": "Credential could not be saved",
            "keyring_readback": "Stored credential could not be read back",
            "keyring_read": "Stored credential could not be read",
            "keyring_delete": "Credential could not be deleted",
        }
        raise SecretStorageError(stage, code, messages.get(stage, "Credential storage operation failed")) from None

    def save_api_key(self, provider: str, api_key: str) -> None:
        normalized = self._provider(provider)
        clean_key = api_key.strip()
        account = self._account(normalized)
        logger.info(
            "API key received: %s; API key length: %d; Provider: %s",
            bool(api_key),
            len(api_key),
            normalized,
        )
        logger.info("Keyring backend: %s", self._backend_name())
        if not clean_key:
            raise ValueError("API key is required")
        try:
            logger.info("Saving credential: service=%s account=%s", SERVICE_NAME, account)
            self._backend.set_password(SERVICE_NAME, account, clean_key)
            logger.info("Credential save succeeded")
        except Exception as exc:
            self._raise_storage_error("keyring_write", "credential_save_failed", exc, clean_key)

        try:
            saved = self._backend.get_password(SERVICE_NAME, account)
        except Exception as exc:
            self._raise_storage_error("keyring_readback", "credential_readback_failed", exc, clean_key)
        if saved is None:
            logger.error("Credential readback failed: stage=keyring_readback reason=missing")
            raise SecretStorageError("keyring_readback", "credential_readback_missing", "Credential save could not be verified")
        if saved != clean_key:
            logger.error("Credential readback failed: stage=keyring_readback reason=mismatch")
            raise SecretStorageError("keyring_readback", "credential_readback_mismatch", "Credential save could not be verified")
        logger.info("Credential readback succeeded")

    def get_api_key(self, provider: str) -> str | None:
        normalized = self._provider(provider)
        account = self._account(normalized)
        logger.info(
            "Reading credential: Provider=%s service=%s account=%s backend=%s",
            normalized,
            SERVICE_NAME,
            account,
            self._backend_name(),
        )
        try:
            saved = self._backend.get_password(SERVICE_NAME, account)
        except Exception as exc:
            self._raise_storage_error("keyring_read", "credential_read_failed", exc)
        logger.info("Credential read succeeded: present=%s length=%d", saved is not None, len(saved or ""))
        return saved

    def delete_api_key(self, provider: str) -> None:
        normalized = self._provider(provider)
        account = self._account(normalized)
        try:
            self._backend.delete_password(SERVICE_NAME, account)
        except Exception as exc:
            self._raise_storage_error("keyring_delete", "credential_delete_failed", exc)

    def has_api_key(self, provider: str) -> bool:
        return bool(self.get_api_key(provider))

    def resolve_api_key(self, provider: str) -> str | None:
        """Prefer Keychain/Credential Manager; only then use the dev environment."""

        normalized = self._provider(provider)
        return self.get_api_key(normalized) or self._environment.get(self._environment_name(normalized))


def run_keyring_self_test(backend: CredentialBackend | None = None) -> KeyringSelfTestResult:
    """Exercise the current OS credential backend with an isolated temporary credential."""

    adapter = backend or KeyringBackend()
    service = "YUSAN.keyring-self-test"
    account = f"run-{uuid.uuid4()}"
    harmless_value = "yusan-keyring-self-test"
    backend_name = KeyringBackend.backend_name() if backend is None else f"{adapter.__class__.__module__}.{adapter.__class__.__qualname__}"
    try:
        adapter.set_password(service, account, harmless_value)
        stored = adapter.get_password(service, account)
        if stored != harmless_value:
            raise SecretStorageError("keyring_self_test", "readback_mismatch", "Keyring self-test readback did not match")
        adapter.delete_password(service, account)
        if adapter.get_password(service, account) is not None:
            raise SecretStorageError("keyring_self_test", "cleanup_failed", "Keyring self-test cleanup did not complete")
        return KeyringSelfTestResult(backend=backend_name, readback_verified=True, cleanup_verified=True)
    except SecretStorageError:
        raise
    except Exception as exc:
        logger.error(
            "Credential keyring_self_test failed: exception=%s message=%s",
            type(exc).__name__,
            SecretsService._safe_exception_message(exc),
        )
        raise SecretStorageError("keyring_self_test", "storage_failure", "Keyring self-test failed") from None
    finally:
        try:
            adapter.delete_password(service, account)
        except Exception:
            pass


_default_secrets = SecretsService()


def save_api_key(provider: str, api_key: str) -> None:
    _default_secrets.save_api_key(provider, api_key)


def get_api_key(provider: str) -> str | None:
    return _default_secrets.get_api_key(provider)


def delete_api_key(provider: str) -> None:
    _default_secrets.delete_api_key(provider)


def has_api_key(provider: str) -> bool:
    return _default_secrets.has_api_key(provider)
