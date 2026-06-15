# Phase 7: Visual Interface

Phase 7 gives ULTRON 2.7 its own local web interface. The UI is a cyberpunk black-and-green scene with a Three.js plasma sphere, green particle field, live subtitles, typed fallback command input, and development controls for the assistant's visual state.

## What Changed

- Added `src/ultron27/web_server.py`.
- Added `web/index.html`, `web/styles.css`, and `web/app.js`.
- Vendored a pinned Three.js browser module at `web/vendor/three.module.min.js`.
- Added `scripts/run_phase7_ui.py` as a local launcher.
- Added `ultron-ui` as a package script entry point.
- Added `scripts/phase7_visual_smoke.mjs` for browser smoke checks when a local Playwright browser binary is available.
- Added backend/API tests for status, subtitles, command processing, and static UI assets.

## How To Run

```powershell
python scripts/run_phase7_ui.py --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

If the package is installed, this also works:

```powershell
ultron-ui --port 8765
```

## Visual States

Listening:

- sphere contracts slightly,
- glow becomes calmer and tighter,
- background particle motion slows,
- the visual reads as attentive and waiting.

Thinking:

- green eclipse rings orbit the sphere,
- crescent-like arcs rotate around the core,
- particle motion and rim glow increase,
- the visual reads as analysis and processing.

Speaking:

- sphere expands slightly,
- plasma lines become brighter and more active,
- outer glow intensifies,
- the visual reads as response delivery.

## Runtime Integration

The frontend connects to the Phase 6 brain/runtime through local API endpoints:

```text
POST /api/command
GET  /api/status
GET  /api/memory
POST /api/subtitles/toggle
POST /api/state
```

`POST /api/command` sends typed input to `UltronBrain`, which still routes each step through:

```text
brain -> runtime -> planner -> validator -> policy -> executor -> audit
```

The UI does not bypass safety policy or execute raw shell commands.

## Verification

Phase 7 adds regression coverage for:

- web state command processing,
- subtitle toggle behavior,
- static UI assets and local Three.js import,
- real HTTP status and subtitle-toggle endpoints.

The included browser smoke script can run when Playwright's browser binary is installed:

```powershell
$env:NODE_PATH="C:\Users\DEEP\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules;C:\Users\DEEP\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\.pnpm\node_modules"
C:\Users\DEEP\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe scripts\phase7_visual_smoke.mjs
```

In the current Codex sandbox, the in-app browser could not start and the bundled Playwright browser executable was not installed, so automated screenshot capture was blocked. API and static UI checks still passed.
