import logging
import os
import tempfile
from pathlib import Path


def configure_logging(level: str = "INFO") -> logging.Logger:
    configured_dir = os.environ.get("YUSAN_LOG_DIR")
    log_dir = Path(configured_dir) if configured_dir else Path.home() / "Library" / "Logs" / "YUSAN"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_dir = Path(tempfile.gettempdir()) / "YUSAN" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("yusan")
    if not logger.handlers:
        logger.setLevel(level.upper())
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        file_handler = logging.FileHandler(log_dir / "yusan.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger
