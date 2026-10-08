import subprocess
import webbrowser


def open_app(name: str) -> None:
    subprocess.run(["open", "-a", name], check=True)


def open_url(url: str) -> None:
    webbrowser.open(url)
