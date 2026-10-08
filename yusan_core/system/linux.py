import subprocess


def open_app(name: str) -> None:
    subprocess.run([name], check=True)


def open_url(url: str) -> None:
    subprocess.run(["xdg-open", url], check=True)
