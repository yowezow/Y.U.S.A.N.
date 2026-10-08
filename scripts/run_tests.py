"""Run the core test suite with the project virtual environment when available."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    candidates = [ROOT / ".venv" / "bin" / "python", ROOT / ".venv" / "Scripts" / "python.exe", Path(sys.executable)]
    python = next(candidate for candidate in candidates if candidate.exists())
    subprocess.run([str(python), "-m", "pytest"], check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
