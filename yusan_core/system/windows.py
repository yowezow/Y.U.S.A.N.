import os
import webbrowser


def open_app(name: str) -> None:
    os.startfile(name)  # type: ignore[attr-defined]


def open_url(url: str) -> None:
    webbrowser.open(url)
