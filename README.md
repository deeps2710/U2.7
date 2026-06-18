# ULTRON 2.7

ULTRON 2.7 is a local-first Jarvis-style laptop assistant MVP. It turns natural-language commands into typed tool calls, validates them, applies a safety policy, and executes them only through an allowlisted tool layer.

The repo is built around the supplied research paper and synthetic laptop-command dataset. The current implementation keeps command planning, voice input, policy, and execution separated so ULTRON can grow toward a Jarvis-style assistant without giving any model raw shell access.

## What Works Now

- Dataset-backed command planner with fuzzy matching and regex fallbacks.
- Typed tool registry for laptop actions such as app launch, volume, brightness, files, reminders, notes, email drafts, and smart-home placeholders.
- Safety policy with low, medium, high, and blocked risk handling.
- Dry-run executor by default, so model/tool output can be tested without changing the computer.
- Real low-risk execution for notes, reminders, timers, safe file search, safe file/folder opening, app launching, clipboard helpers, and screenshot capture where supported.
- Configurable safe roots and app aliases for laptop-specific behavior.
- JSONL audit logging for every command.
- Dataset evaluation script for tool-name, argument, and confirmation-gate accuracy.
- Dataset quality analyzer for duplicate-label conflicts, underspecified commands, and safety case extraction.
- Safety regression evaluator for high-risk and confirmation-gated examples.
- Optional LLM planner adapter with Ollama or Groq support, strict JSON parsing, schema validation, and safe fallback behavior.
- Interactive assistant console for repeated commands, confirmations, and JSON inspection.
- Agentic brain layer for multi-step task planning, safe execution, and non-sensitive memory.
- Conversation manager with fast chat routing, clarification behavior, and a consistent calm assistant personality.
- Optional PyTorch neural intent-router training path using the 50,000-example ULTRON synthetic dataset.
- Cyberpunk green plasma-sphere web interface backed by the local brain/runtime API.
- Voice mode with transcript cleanup, confidence handling, speech synthesis, transcript history, mute, push-to-talk, and confirmation controls.
- Offline-first voice provider layer with faster-whisper, whisper.cpp, Piper, and pyttsx3 adapters plus browser/mock fallbacks.
- Wake-word and voice activity gates for always-listening mode, with push-to-talk still available.
- Backend microphone capture abstraction with sounddevice/mock/browser capture providers and voice diagnostics.
- Semantic LLM intent routing through Ollama or Groq, with strict typed JSON validation and clarification fallback.
- Windows automation executor pack with app aliases, safe-root file enforcement, confirmation modal support, and audit viewing.
- Skill registry and local knowledge base for reusable safe capabilities and document-grounded project context.
- Beta-ready local prototype tooling for setup, launch, diagnostics, demos, and verification.
- Pytest test suite for planner, validation, policy, and execution behavior.

## Project Layout

```text
src/ultron27/            Assistant package
web/                     Phase 7 visual interface
scripts/                 Utility scripts
tests/                   Safety and planner tests
data/jarvis_dataset_v2/  Supplied synthetic command dataset
docs/                    Supplied research paper and architecture notes
```

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
ultron "set volume to 40 percent"
ultron "open notepad"
ultron "search the web for Python speech recognition"
ultron "play lofi beats on Spotify"
ultron "hello ultron" --text
ultron "delete project_report.txt" --yes
python scripts/evaluate_dataset.py --split test
python scripts/analyze_dataset_quality.py
python scripts/evaluate_safety_regression.py
python -m ultron27 "launch the basic text editor" --planner-mode hybrid
python -m ultron27 --interactive
python -m ultron27 "/plan Create a note called project ideas and add that I should test voice mode next." --text
python -m ultron27 "/do Create a note called project ideas and add that I should test voice mode next." --text --execute --workspace .
python scripts/run_phase7_ui.py --port 8765
python scripts/run_phase8_voice_ui.py --port 8765
python scripts/run_phase9_voice_ui.py --port 8765
python scripts/run_phase10_wake_ui.py --port 8765
python scripts/run_phase11_windows_ui.py --port 8765
python scripts/run_phase12_skills_ui.py --port 8765
python scripts/launch_ultron.py --execute
python scripts/demo_phase13.py
python scripts/verify_phase13.py
python -m unittest discover -s tests
```

## Optional Neural Router

The larger synthetic router dataset lives at:

```text
data/ultron_synthetic_training_dataset_v2_large_50000.jsonl
```

Train the advisory neural router with:

```powershell
pip install -e .[neural]
python -m ultron27.neural_router.train --dataset data/ultron_synthetic_training_dataset_v2_large_50000.jsonl --output .ultron/models/neural_router.pt
```

Then enable it with either config or environment variables:

```powershell
$env:ULTRON_NEURAL_ROUTER_ENABLED = "true"
$env:ULTRON_NEURAL_ROUTER_MODEL = ".ultron/models/neural_router.pt"
```

The neural router only predicts route, intent, tool name, risk, and confirmation labels. It never executes tools directly and never bypasses schema validation, policy gates, executor safety checks, or audit logging.

If the `ultron` command is not available after installation, use:

```powershell
python -m ultron27 "set volume to 40 percent"
```

By default ULTRON runs in dry-run mode. In dry-run mode it will speak what it would do, but it will not actually open apps, launch browser searches, or open Spotify. Use `--execute` only after reviewing the tool, policy, and implementation. High-risk actions are still not implemented as destructive operations, even after confirmation.

## Configuration

ULTRON looks for `ultron.config.json` first, then `.ultron/config.json`. You can start from `ultron.config.example.json`:

```json
{
  "dataset_path": "data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl",
  "audit_log": ".ultron/audit.jsonl",
  "dry_run": true,
  "workspace": ".",
  "safe_roots": [".", "~/Desktop", "~/Documents", "~/Downloads"],
  "screenshot_dir": ".ultron/screenshots",
  "app_aliases": {
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "vs code": "code",
    "vscode": "code",
    "notepad": "notepad.exe",
    "spotify": "spotify.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "terminal": "wt.exe"
  },
  "planner_mode": "rules",
  "llm_provider": "ollama",
  "llm_model": "qwen2.5:7b-instruct",
  "llm_endpoint": "http://localhost:11434",
  "llm_timeout_seconds": 8,
  "voice_stt_provider": "browser",
  "voice_capture_provider": "browser",
  "voice_microphone_device": null,
  "voice_sample_rate": 16000,
  "voice_capture_seconds": 4,
  "voice_tts_provider": "browser_speech_synthesis",
  "voice_stt_model_path": null,
  "voice_tts_model_path": null,
  "voice_tts_voice_path": null,
  "voice_device": "cpu",
  "voice_identity": "ULTRON",
  "voice_rate": 0.94,
  "voice_pitch": 0.86,
  "voice_volume": 0.95,
  "wake_word_provider": "text",
  "wake_phrases": ["ULTRON", "Hey ULTRON"],
  "wake_model_path": null,
  "vad_provider": "energy",
  "vad_energy_threshold": 0.015,
  "clap_spike_ratio": 7.0,
  "clap_min_rms": 0.012,
  "clap_min_gap_s": 0.05,
  "clap_max_gap_s": 0.35,
  "clap_cooldown_s": 0.45
}
```

Environment variables override the JSON config:

```powershell
$env:ULTRON_DRY_RUN = "true"
$env:ULTRON_AUDIT_LOG = ".ultron/audit.jsonl"
$env:ULTRON_SAFE_ROOTS = ".;~/Desktop;~/Documents;~/Downloads"
$env:ULTRON_PLANNER_MODE = "rules"
$env:ULTRON_LLM_PROVIDER = "ollama"
$env:ULTRON_LLM_MODEL = "qwen2.5:7b-instruct"
$env:ULTRON_LLM_ENDPOINT = "http://localhost:11434"
$env:ULTRON_STT_PROVIDER = "browser"
$env:ULTRON_CAPTURE_PROVIDER = "browser"
$env:ULTRON_MICROPHONE_DEVICE = ""
$env:ULTRON_VOICE_SAMPLE_RATE = "16000"
$env:ULTRON_VOICE_CAPTURE_SECONDS = "4"
$env:ULTRON_TTS_PROVIDER = "browser_speech_synthesis"
$env:ULTRON_STT_MODEL_PATH = ".ultron/models/whisper"
$env:ULTRON_TTS_MODEL_PATH = ".ultron/models/piper.onnx"
$env:ULTRON_TTS_VOICE_PATH = ".ultron/models/piper.json"
$env:ULTRON_VOICE_DEVICE = "cpu"
$env:ULTRON_VOICE_IDENTITY = "ULTRON"
$env:ULTRON_WAKE_WORD_PROVIDER = "text"
$env:ULTRON_WAKE_PHRASES = "ULTRON;Hey ULTRON"
$env:ULTRON_VAD_PROVIDER = "energy"
$env:ULTRON_VAD_ENERGY_THRESHOLD = "0.015"
```

For the cloud-backed setup, use Groq for planning and Deepgram for speech-to-text:

```powershell
[Environment]::SetEnvironmentVariable("GROQ_API_KEY", "your-groq-key", "User")
[Environment]::SetEnvironmentVariable("DEEPGRAM_API_KEY", "your-deepgram-key", "User")
$env:ULTRON_LLM_PROVIDER = "groq"
$env:ULTRON_LLM_MODEL = "openai/gpt-oss-20b"
$env:ULTRON_LLM_ENDPOINT = "https://api.groq.com/openai/v1"
$env:ULTRON_STT_PROVIDER = "deepgram"
$env:ULTRON_STT_MODEL = "nova-3"
```

Useful CLI flags:

```powershell
ultron "open notepad" --no-audit
ultron "open notepad" --text
ultron --interactive
ultron "/plan create a note called ideas and add that voice mode is next" --text
ultron "/do create a note called ideas and add that voice mode is next" --text --execute
ultron "/memory" --text
ultron "/forget last_note" --text
ultron-ui --port 8765
python scripts/run_phase10_wake_ui.py --port 8765
python scripts/run_phase11_windows_ui.py --port 8765
python scripts/run_phase12_skills_ui.py --port 8765
python scripts/launch_ultron.py --port 8765 --execute
ultron "create note standup" --workspace .
ultron "open notepad" --execute
ultron "search the web for local voice assistants" --execute
ultron "play lofi beats on Spotify" --execute
ultron "delete project_report.txt" --yes
```

## Phase 2 Safe Execution

Phase 2 adds real execution for low-risk tools while keeping destructive commands disabled:

- `create_note` and `append_to_note` write Markdown files under `notes/`.
- `set_reminder` and `start_timer` append JSONL records under `.ultron/`.
- `search_files`, `open_file`, and `open_folder` operate only inside configured `safe_roots`.
- `open_application` uses configurable `app_aliases`.
- `search_web` opens a browser search URL through a typed low-risk tool.
- `play_music` opens Spotify search through a typed low-risk tool.
- `copy_to_clipboard` and `read_clipboard` use Windows clipboard commands when available.
- `take_screenshot` saves under `screenshot_dir` when Pillow/ImageGrab is available.

Use dry-run previews first:

```powershell
python -m ultron27 "start timer for 15 minutes"
python -m ultron27 "create note phase two" --execute --workspace .
```

## Phase 3 Dataset Quality

Phase 3 adds dataset quality and safety evaluation tooling:

- `scripts/analyze_dataset_quality.py` writes `docs/phase3_dataset_quality_report.json`.
- The same script extracts `data/regression/safety_cases.jsonl`.
- `scripts/evaluate_safety_regression.py` checks whether planner and policy behavior matches those safety cases.

Current audit summary:

```text
Total examples: 2500
Unique utterances: 2319
Duplicate utterance groups: 101
Conflicting duplicate groups: 101
Underspecified examples: 879
Safety examples: 362
Safety regression policy-action accuracy: 1.0
```

## Phase 4 LLM Planner

Phase 4 adds an optional LLM planner. The default remains `rules`, so ULTRON continues to work without any model server.

Planner modes:

- `rules`: dataset, regex, and fuzzy planning only.
- `hybrid`: use rules first; if no safe rule matches, try the LLM planner.
- `llm`: try the LLM planner first, then fall back safely if the provider is unavailable or invalid.

Example:

```powershell
python -m ultron27 "launch the basic text editor" --planner-mode hybrid
```

The LLM must return JSON like:

```json
{
  "intent": "open_app",
  "tool_name": "open_application",
  "tool_arguments": {
    "app": "notepad"
  },
  "confidence": 0.8
}
```

The returned tool call still goes through schema validation, risk policy, confirmation gates, and the safe executor.

## Phase 5 Interactive Prototype

Phase 5 adds a basic assistant console for day-to-day prototype testing:

```powershell
python -m ultron27 --interactive
```

Inside the console:

```text
/help              Show console commands.
/json <command>    Run a command and print the full JSON payload.
/plan <goal>       Show a safe multi-step plan without executing it.
/do <goal>         Plan and execute allowed steps through ULTRON's runtime.
/memory            Show stored non-sensitive memory.
/forget <query>    Remove matching memory entries.
/yes <command>     Confirm a command that needs confirmation.
/exit              Leave the console.
```

The console uses the same runtime pipeline as the one-shot CLI:

```text
utterance -> planner -> validator -> policy -> executor -> audit -> response
```

Single-command mode still prints JSON by default. Use `--text` for the same concise response format used by the console:

```powershell
python -m ultron27 "set volume to 40 percent" --text
```

## Phase 6 Brain Layer

Phase 6 adds `UltronBrain`, a task-level reasoning layer for multi-step goals. The brain can decompose a goal into steps, preview the tool calls, execute allowed steps, pause for confirmation, and remember useful non-sensitive context.

Example:

```powershell
python -m ultron27 "/plan Create a note called project ideas and add that I should test voice mode next." --text
python -m ultron27 "/do Create a note called project ideas and add that I should test voice mode next." --text --execute --workspace .
```

Brain commands:

```text
/plan <goal>       Build a TaskPlan without execution.
/do <goal>         Execute each allowed step through the safe runtime.
/memory            Show stored non-sensitive memory.
/forget <query>    Delete matching memory entries.
```

The brain stores memory at `.ultron/memory.json` by default. It rejects obvious sensitive keys or values such as passwords, API keys, tokens, credentials, and secrets.

## Phase 7 Visual Interface

Phase 7 adds a local web interface with a black cyberpunk scene, green particle field, and animated Three.js plasma sphere.

Run it with:

```powershell
python scripts/run_phase7_ui.py --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

The interface includes:

- listening state: contracted calmer sphere,
- thinking state: spiraling green eclipse/ring animation,
- speaking state: expanded plasma lines and stronger glow,
- live subtitles below the sphere,
- subtitles on/off toggle,
- typed command input and Send button,
- development controls for Listening, Thinking, Speaking, and Idle.

Local API endpoints:

```text
POST /api/command
GET  /api/status
GET  /api/memory
POST /api/memory/forget
POST /api/memory/toggle
POST /api/subtitles/toggle
POST /api/state
```

Typed input first passes through the conversation manager. Simple chat, help, thanks, and memory commands are answered through a low-risk `assistant_reply` tool path. Laptop actions still go through the brain, typed tool call, schema validation, policy, executor, audit log, and response pipeline.

## Phase 8 Voice Mode

Phase 8 adds voice interaction on top of the Phase 7 interface. The browser captures speech when its speech-recognition API is available, sends the transcript to ULTRON's local API, and ULTRON answers through browser speech synthesis unless muted. The backend cleans wake words and filler text, rejects empty/noisy inputs, and asks for clarification when a provider reports low transcript confidence.

Run it with:

```powershell
python scripts/run_phase8_voice_ui.py --port 8765
```

Voice controls:

- Mic On/Off for browser speech capture.
- Push-to-talk or continuous recognition.
- Mute Off/Muted for ULTRON voice output.
- Stop Voice to cancel speech synthesis.
- Confirm for explicit high-risk action confirmation.
- Mock Voice to test the full voice pipeline without a microphone.

Voice API endpoints:

```text
POST /api/voice/start
POST /api/voice/stop
POST /api/voice/transcribe
POST /api/speak
GET  /api/voice/status
```

Voice still uses the same safe runtime:

```text
voice -> STT -> brain/runtime -> typed tool call -> validation -> policy
-> executor -> audit -> response -> TTS
```

If microphone/STT is unavailable, typed mode and Mock Voice still work. If TTS is unavailable or muted, subtitles still show the response.

Conversation history in the UI shows what the user said, what ULTRON understood, and the final response. Memory controls let the user view memory, forget matching facts, and turn learning on or off. ULTRON refuses to store obvious secrets such as passwords, tokens, credentials, and API keys.

## Phase 14 Backend Voice Capture

Phase 14 adds an optional backend capture path while keeping browser voice as a fallback. Configure it with:

```json
{
  "voice_capture_provider": "sounddevice",
  "voice_stt_provider": "faster_whisper",
  "voice_stt_model": "base.en",
  "voice_stt_model_path": null,
  "voice_sample_rate": 16000,
  "voice_capture_seconds": 4
}
```

Capture providers:

- `browser`: browser captures speech/transcripts.
- `sounddevice`: backend records microphone audio when the optional Python package is installed.
- `mock`: deterministic backend capture for tests and demos.

New route:

```text
POST /api/voice/capture
```

The voice diagnostics panel shows the capture provider, STT provider, active microphone, last understood transcript, confidence, audio duration, speech duration, and rejected/noisy status. Empty, noisy, or too-short audio is ignored before command execution. Low-confidence transcripts ask for clarification.

`voice_stt_model` accepts faster-whisper model names such as `base.en`, `small.en`, or `medium.en`. Use `voice_stt_model_path` instead when you have already downloaded a model folder and want a fully local path.

## Phase 15 Semantic Intent Routing

Phase 15 strengthens natural-language understanding with a semantic router. The fast rules still handle obvious commands first. If a command is unsupported by rules and `planner_mode` is `hybrid` or `llm`, ULTRON asks the configured Ollama or Groq model to return one strict JSON tool call.

The model can only propose typed tools:

```json
{
  "intent": "open_app",
  "tool_name": "open_application",
  "tool_arguments": {
    "app": "notepad"
  },
  "confidence": 0.92,
  "needs_clarification": false,
  "clarification_question": ""
}
```

Invalid JSON, unknown tools, invalid arguments, and low confidence are rejected or converted into `ask_clarification`. Provider unavailability does not crash ULTRON; it falls back to the safe rules result.

## Phase 9 Offline Voice Providers

Phase 9 strengthens the voice layer with offline-first provider adapters while keeping browser voice as the practical fallback. The browser UI now shows the configured and active STT/TTS providers, and the backend exposes health-check routes for provider readiness.

Run it with:

```powershell
python scripts/run_phase9_voice_ui.py --port 8765
```

Provider choices:

- `voice_stt_provider`: `browser`, `text_payload`, `faster_whisper`, `whisper_cpp`, `deepgram`, or `mock`.
- `voice_stt_model`: faster-whisper model name such as `base.en`, or Deepgram model name such as `nova-3`.
- `voice_tts_provider`: `browser_speech_synthesis`, `piper`, `pyttsx3`, or `mock`.
- `voice_stt_model_path`: local faster-whisper or whisper.cpp model path.
- `voice_tts_model_path`: local Piper model path.
- `voice_tts_voice_path`: optional Piper voice config path.
- `voice_device`: `cpu`, `cuda`, or `auto`.
- `voice_identity`, `voice_rate`, `voice_pitch`, and `voice_volume`: voice output tuning.

New provider endpoints:

```text
GET  /api/voice/providers
POST /api/voice/test-stt
POST /api/voice/test-tts
```

If a local STT model, TTS model, Python package, or Piper executable is missing, ULTRON reports the issue and falls back to browser transcript/speech behavior. Typed commands, subtitles, and the safe runtime continue to work.

## Phase 10 Wake Word and VAD

Phase 10 adds an input gate before speech reaches STT and the brain. Wake word detection and VAD only decide whether a speech segment should be considered; they never execute tools directly.

Run it with:

```powershell
python scripts/run_phase10_wake_ui.py --port 8765
```

Always-listening states:

```text
inactive -> waiting_for_wake_word -> listening -> transcribing
-> thinking -> speaking
```

Wake/VAD providers:

- `wake_word_provider`: `text`, `openwakeword`, `double_clap`, or `mock`.
- `wake_phrases`: defaults to `ULTRON` and `Hey ULTRON`.
- `wake_model_path`: optional openWakeWord model path.
- `vad_provider`: `energy`, `silero`, `webrtc`, or `mock`.
- `vad_energy_threshold`: fallback energy threshold for noisy/empty input.
- `double_clap`: optional adaptive energy-spike wake gate inspired by the reviewed Jarvis script. It only opens listening mode and never executes actions directly.

Wake API endpoints:

```text
POST /api/wake/start
POST /api/wake/stop
GET  /api/wake/status
POST /api/wake/process
```

`/api/wake/process` is the browser adapter route for candidate speech segments. It ignores empty/noisy audio and speech without `ULTRON` or `Hey ULTRON` while the session is waiting for the wake word. Push-to-talk still uses `/api/voice/transcribe`.

## Phase 11 Windows Automation Pack

Phase 11 formalizes real low-risk Windows laptop automation inside the executor boundary. ULTRON still never gives the planner or LLM raw shell access. Every action must be a typed tool call that passes schema validation and policy before the executor adapter sees it.

Run it with:

```powershell
python scripts/run_phase11_windows_ui.py --port 8765
```

Implemented or safely fronted Windows tasks:

- open approved apps by alias: Chrome, VS Code, Notepad, Calculator, File Explorer, and Terminal,
- open/search files and folders only inside configured `safe_roots`,
- create and append notes,
- read/write clipboard text where supported,
- take screenshots where Pillow/ImageGrab is available,
- set volume with optional `pycaw`/`comtypes`,
- set brightness with optional `screen-brightness-control`,
- save reminders and timers.

Permission behavior:

```text
low-risk -> allowed after validation
medium-risk -> confirmation required
high-risk -> confirmation required
destructive -> confirmation-gated but not implemented
blocked -> rejected
```

New API endpoint:

```text
GET /api/audit/recent?limit=25
```

The Phase 7-10 interface now shows a confirmation modal for risky typed or voice actions. Confirming retries the command with `confirmed: true`; cancelling clears the pending voice confirmation state.

## Phase 12 Skills and Local Knowledge

Phase 12 adds a skill registry and local knowledge base. Skills are reusable typed capabilities with input schemas, risk levels, handlers, examples, policy checks, and audit records. Knowledge retrieval can inform summaries and planning, but it cannot execute actions or bypass the safe tool runtime.

Run it with:

```powershell
python scripts/run_phase12_skills_ui.py --port 8765
```

Built-in skills:

- `notes`: create or append notes through safe note tools,
- `reminders`: save reminders through the safe reminder tool,
- `file_search`: search files inside safe roots,
- `project_summary`: summarize matching local knowledge,
- `daily_planning`: draft a daily plan from explicit priorities and local context.

Knowledge support:

- ingests Markdown, TXT, PDF, and DOCX where local dependencies are available,
- stores metadata and chunks under `.ultron/knowledge/index.json`,
- rejects obvious secrets such as passwords, API keys, tokens, credentials, and private keys,
- searches by keyword first, with an embedding-provider abstraction ready for later.

New endpoints:

```text
GET  /api/skills
POST /api/skills/run
POST /api/knowledge/ingest
GET  /api/knowledge/search?query=<text>&limit=5
```

The web interface now includes panels for skills, memory/knowledge, local knowledge search, and recent task history.

## Phase 13 Beta Prototype Tooling

Phase 13 makes ULTRON easier to install, launch, diagnose, demo, and verify on Windows.

Recommended setup:

```powershell
.\scripts\setup_ultron_windows.ps1
```

Recommended launch:

```powershell
python scripts\launch_ultron.py
```

The launcher starts the backend and UI together, handles port conflicts, and prints both the main interface URL and diagnostics URL.

Operator scripts:

```powershell
python scripts\check_dependencies.py
python scripts\check_providers.py
python scripts\config_wizard.py --defaults
python scripts\demo_phase13.py
python scripts\verify_phase13.py
```

New diagnostics endpoint and page:

```text
GET /api/diagnostics
http://127.0.0.1:8765/diagnostics
```

Diagnostics show backend readiness, brain status, voice provider status, memory path, audit path, safe roots, and recent readiness errors. The diagnostics page is read-only and does not execute tools.

## Example

```powershell
python -m ultron27 "open notepad"
```

Example output:

```json
{
  "utterance": "open notepad",
  "tool_call": {
    "name": "open_application",
    "arguments": {
      "app": "notepad"
    }
  },
  "policy": {
    "action": "allow",
    "reason": "Low-risk command can run."
  },
  "result": {
    "status": "dry_run",
    "message": "Would open application: notepad"
  }
}
```

## Safety Model

ULTRON does not give an LLM unrestricted shell access. The intended production flow is:

```text
utterance -> planner -> typed tool call -> schema validator -> policy gate
-> executor -> audit log -> response
```

Medium-risk and high-risk operations require confirmation. In voice mode, confirmation must be explicit, such as `yes confirm`. Destructive execution is intentionally left unimplemented in this MVP.

Skills and knowledge do not create a side channel around this model. Skills validate their own schemas and then call the same safe runtime for any OS-facing action. Knowledge search returns context only.

Phase 13 setup, launcher, diagnostics, demo, and verification scripts are operator tooling. They do not give ULTRON a new execution path or raw shell authority.

## Roadmap

1. Install and tune real faster-whisper/whisper.cpp and Piper models for the target laptop.
2. Install real openWakeWord and Silero/WebRTC VAD dependencies for microphone audio.
3. Add streaming partial transcripts and lower-latency speech playback.
4. Grow the dataset with real corrected transcripts and Hinglish/Hindi variants.
5. Add embeddings and source-aware answer generation for the local knowledge base.
