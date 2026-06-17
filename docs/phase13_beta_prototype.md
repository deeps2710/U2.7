# Phase 13 - Beta-Ready Local Prototype

Phase 13 packages ULTRON 2.7 so it feels usable as a local Windows beta prototype. The focus is installability, configuration, launch ergonomics, diagnostics, repeatable demos, and CI-style verification.

## What Was Added

- `scripts/setup_ultron_windows.ps1` creates a virtual environment, installs the project, writes a safe default config, and runs dependency checks.
- `scripts/check_dependencies.py` checks required repository files and report/knowledge packages.
- `scripts/check_providers.py` checks configured STT, TTS, wake-word, and VAD providers and reports fallback behavior.
- `scripts/config_wizard.py` writes `ultron.config.json` interactively or with safe defaults.
- `scripts/launch_ultron.py` starts the backend and UI with port conflict handling and clear URLs.
- `scripts/demo_phase13.py` runs typed, mock voice, note creation, and confirmation demos without a microphone.
- `scripts/verify_phase13.py` runs tests, dataset evaluation, safety regression, and API smoke checks.
- `/api/diagnostics` returns backend, brain, voice, memory, audit, safe-root, and error readiness data.
- `/diagnostics` shows a local diagnostics page in the web UI.

## Local Startup

```powershell
.\scripts\setup_ultron_windows.ps1
.\.venv\Scripts\python.exe scripts\launch_ultron.py
```

Then open the URL printed by the launcher, usually:

```text
http://127.0.0.1:8765
```

The diagnostics page is available at:

```text
http://127.0.0.1:8765/diagnostics
```

If port `8765` is busy, the launcher automatically searches the next available local port and prints the selected URL.

## Demo Flow

Run the no-microphone demo:

```powershell
python scripts\demo_phase13.py
```

The demo covers:

- typed command processing,
- low-risk note creation inside `.ultron/demo_workspace`,
- high-risk confirmation pause,
- mock voice transcript through the same voice-to-brain runtime path.

## Verification Flow

Run the CI-style verification script:

```powershell
python scripts\verify_phase13.py
```

It performs:

- unit tests,
- dataset evaluation,
- safety regression,
- local API smoke checks.

## Safety Boundary

Phase 13 does not add a new execution path. Launch, diagnostics, demo, and verification scripts all use the existing architecture:

```text
user input -> brain/planner -> typed tool call -> schema validation
-> policy gate -> executor -> audit log -> response
```

The diagnostics page is read-only. It reports readiness and paths but does not execute tools.
