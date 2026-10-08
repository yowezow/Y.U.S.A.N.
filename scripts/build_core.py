"""Build the Python YUSAN Core as the native Tauri sidecar for this host."""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIDE_CAR_NAME = "yusan-core"


def tauri_target() -> str:
    override = os.environ.get("YUSAN_TAURI_TARGET")
    if override:
        return override

    system = platform.system()
    machine = platform.machine().lower()
    targets = {
        ("Darwin", "arm64"): "aarch64-apple-darwin",
        ("Darwin", "aarch64"): "aarch64-apple-darwin",
        ("Darwin", "x86_64"): "x86_64-apple-darwin",
        ("Windows", "amd64"): "x86_64-pc-windows-msvc",
        ("Windows", "x86_64"): "x86_64-pc-windows-msvc",
        ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
        ("Linux", "aarch64"): "aarch64-unknown-linux-gnu",
    }
    try:
        return targets[(system, machine)]
    except KeyError as exc:
        raise SystemExit(f"Unsupported native sidecar target: {system} / {machine}") from exc


def build_python() -> Path:
    candidates = [
        PROJECT_ROOT / ".venv" / "bin" / "python",
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
        Path(sys.executable),
    ]
    return next(candidate for candidate in candidates if candidate.exists())


def main() -> None:
    python = build_python()
    target = tauri_target()
    work_dir = PROJECT_ROOT / "build" / "pyinstaller-work"
    dist_dir = PROJECT_ROOT / "build" / "sidecar"
    spec_dir = PROJECT_ROOT / "build" / "pyinstaller-spec"
    source = PROJECT_ROOT / "yusan_core" / "sidecar.py"
    command = [
        str(python), "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--name", SIDE_CAR_NAME, "--paths", str(PROJECT_ROOT), "--collect-all", "keyring",
        "--collect-all", "google.genai",
        "--hidden-import", "uvicorn.logging", "--hidden-import", "uvicorn.loops.auto",
        "--workpath", str(work_dir), "--distpath", str(dist_dir), "--specpath", str(spec_dir), str(source),
    ]
    subprocess.run(command, check=True, cwd=PROJECT_ROOT)

    source_name = f"{SIDE_CAR_NAME}.exe" if platform.system() == "Windows" else SIDE_CAR_NAME
    compiled = dist_dir / source_name
    binary_dir = PROJECT_ROOT / "apps" / "desktop" / "src-tauri" / "binaries"
    binary_dir.mkdir(parents=True, exist_ok=True)
    target_name = f"{SIDE_CAR_NAME}-{target}{'.exe' if platform.system() == 'Windows' else ''}"
    output = binary_dir / target_name
    shutil.copy2(compiled, output)
    if platform.system() != "Windows":
        output.chmod(output.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Built YUSAN Core sidecar: {output}")


if __name__ == "__main__":
    main()
