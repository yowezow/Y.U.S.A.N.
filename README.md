# YUSAN v1.0

A cross-platform, local-first desktop assistant with a React/Tauri interface and a Python core.

## Development

1. Install Python dependencies: `python -m pip install -e '.[dev]'`
2. Install desktop dependencies from `apps/desktop`: `npm install`
3. Launch the app from `apps/desktop`: `npm run tauri:dev`

The development and packaged desktop app automatically starts the bundled core. A `.env` is optional and is only a development fallback. Normal users add their Gemini key in **Settings → Genel → Yapay zekâ**; it is saved to macOS Keychain, Windows Credential Manager, or a compatible Linux Secret Service backend.

## Build and test

From the project root:

```bash
python scripts/run_tests.py                 # Python tests
python scripts/build_core.py                # Native Python sidecar for this host
cd apps/desktop && npm run build            # React production build
cd apps/desktop && npm run tauri:build      # Complete native Tauri package
```

`tauri:build` invokes `core:build` automatically, then bundles the host-native core executable as an external Tauri sidecar. The sidecar starts with the desktop window and is terminated when the application exits.

The sidecar build is native, not cross-compiled. Build macOS on macOS, Windows on Windows, and Linux on Linux (or provide a platform-specific sidecar through the documented `YUSAN_TAURI_TARGET` override).

## Architecture

- `apps/desktop` — Tauri + React + TypeScript interface and sidecar configuration.
- `yusan_core` — HTTP API, deterministic intent routing, provider-neutral LLM layer, system actions, configuration, and logs.
- `scripts/build_core.py` — builds the current platform's PyInstaller sidecar with the target filename Tauri expects.
- `tests` — core unit and API contract tests.

The desktop app calls the local core through `POST /api/chat`. System operations live only in the platform modules under `yusan_core/system`. API keys are never logged or returned by the core.

Gemini uses the official `google-genai` SDK. It validates a stored key by listing models before it tests the configured model, so an unavailable model, quota problem, access restriction, network fault, and bad key are reported separately. `GEMINI_MODEL` defaults to `gemini-3.8-flash` and is configurable in the runtime environment.

On macOS, YUSAN uses the native decorated title-bar overlay and system traffic lights. The interface reserves the title-bar area for those controls while retaining the existing visual layout.
