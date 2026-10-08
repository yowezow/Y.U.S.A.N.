import os
import platform
import signal
import threading
import time
import uvicorn
from .api.server import app
from .config import get_settings
from .logging import configure_logging


def stop_when_parent_exits(parent_pid: int, logger) -> None:
    """Ensure a PyInstaller child cannot outlive the Tauri process that launched it."""

    def parent_is_alive() -> bool:
        try:
            os.kill(parent_pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def watch() -> None:
        while parent_is_alive():
            time.sleep(0.5)
        logger.info("YUSAN Core parent exited; stopping Core")
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=watch, name="yusan-parent-watch", daemon=True).start()


def main() -> None:
    settings = get_settings()
    logger = configure_logging(settings.yusan_log_level)
    logger.info("YUSAN Core started")
    logger.info("Platform: %s", platform.system())
    logger.info("LLM provider: %s", settings.llm_provider)
    parent_pid = os.environ.get("YUSAN_PARENT_PID")
    if parent_pid and parent_pid.isdecimal():
        stop_when_parent_exits(int(parent_pid), logger)
    uvicorn.run(app, host=settings.yusan_host, port=settings.yusan_port, reload=False)


if __name__ == "__main__":
    main()
