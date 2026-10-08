import platform
from urllib.parse import quote_plus
from . import linux, macos, windows


class SystemManager:
    def __init__(self, system_name: str | None = None) -> None:
        self.system_name = system_name or platform.system()

    @property
    def adapter(self):
        return {"Darwin": macos, "Windows": windows, "Linux": linux}.get(self.system_name)

    def _require_adapter(self):
        if not self.adapter:
            raise RuntimeError(f"Unsupported platform: {self.system_name}")
        return self.adapter

    def open_app(self, name: str) -> None:
        self._require_adapter().open_app(name)

    def open_url(self, url: str) -> None:
        self._require_adapter().open_url(url)

    def web_search(self, query: str) -> None:
        self.open_url(f"https://www.google.com/search?q={quote_plus(query)}")
