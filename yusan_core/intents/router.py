from dataclasses import dataclass
from enum import StrEnum
import re


class Intent(StrEnum):
    OPEN_APP = "open_app"
    OPEN_URL = "open_url"
    WEB_SEARCH = "web_search"
    GET_TIME = "get_time"
    OPEN_SETTINGS = "open_settings"
    LLM = "llm"


@dataclass(frozen=True)
class Route:
    intent: Intent
    value: str | None = None


class IntentRouter:
    """Small deterministic Turkish-first action router for v1.0."""

    def route(self, message: str) -> Route:
        normalized = message.strip().casefold()
        if "saat kaç" in normalized or "saati söyle" in normalized:
            return Route(Intent.GET_TIME)
        if "ayarları aç" in normalized or "ayarlari aç" in normalized:
            return Route(Intent.OPEN_SETTINGS)
        if "youtube" in normalized and ("aç" in normalized or "ac" in normalized):
            return Route(Intent.OPEN_URL, "https://www.youtube.com")
        if "google" in normalized and ("ara" in normalized or "search" in normalized):
            query = re.sub(r".*?google(?:'da|da)?\s*", "", message, flags=re.IGNORECASE)
            query = re.sub(r"\s*ara\.?$", "", query, flags=re.IGNORECASE).strip()
            return Route(Intent.WEB_SEARCH, query or "YUSAN")
        if "safari" in normalized and ("aç" in normalized or "ac" in normalized):
            return Route(Intent.OPEN_APP, "Safari")
        return Route(Intent.LLM)
