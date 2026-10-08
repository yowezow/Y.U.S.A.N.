"""PyInstaller entry point for the bundled YUSAN Core sidecar."""

from __future__ import annotations

import json
import sys

from yusan_core.config.secrets import run_keyring_self_test
from yusan_core.main import main


if __name__ == "__main__":
    if "--keyring-self-test" in sys.argv:
        try:
            result = run_keyring_self_test()
        except Exception as exc:
            print(json.dumps({"status": "error", "stage": getattr(exc, "stage", "keyring_self_test"), "code": getattr(exc, "code", "unknown_error")}))
            raise SystemExit(1) from None
        print(json.dumps({"status": "ok", "backend": result.backend, "readback_verified": result.readback_verified, "cleanup_verified": result.cleanup_verified}))
        raise SystemExit(0)
    main()
