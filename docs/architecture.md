# ULTRON 2.7 Architecture

ULTRON is designed as a safe local automation assistant. The LLM or planner proposes a tool call, but the application owns validation, permission checks, execution, and audit logging.

## Pipeline

```text
wake word -> VAD -> STT -> planner -> tool call -> validation
-> policy -> executor -> observation -> response -> TTS
```

The current repository implements the middle of the pipeline:

```text
text command -> planner -> validator -> policy -> safe executor -> audit log
```

Phase 4 optionally expands the planner step:

```text
dataset/rules planner -> optional LLM planner -> typed tool call
```

The optional LLM planner is only allowed to propose a JSON tool call. The validator, policy layer, confirmation gates, and executor remain authoritative.

Phase 6 adds a task-level brain above the runtime:

```text
user goal -> brain -> TaskPlan -> safe runtime step(s)
```

Each runtime step still uses the original command pipeline:

```text
step utterance -> planner -> typed tool call -> validator -> policy -> executor -> audit log
```

The brain can plan multi-step tasks, pause on confirmation gates, summarize outcomes, and store non-sensitive memory. It cannot bypass validation, policy, executor restrictions, or audit logging.

Phase 7 adds a local visual interface above the same brain/runtime boundary:

```text
web UI -> local API -> brain -> TaskPlan -> safe runtime step(s)
```

The browser interface can change visual state, send typed commands, show subtitles, and inspect memory through typed API endpoints. It is not an execution authority. Command execution still flows through the brain and the existing safe runtime.

The conversation manager sits between typed/voice input and the brain:

```text
user input/voice -> conversation manager -> fast intent router
-> chat/memory response or brain/runtime command
```

Simple chat, help, thanks, and memory-control messages are handled quickly through the allowlisted `assistant_reply` path. Commands that operate on the laptop still enter the brain/runtime pipeline and cannot bypass typed tool validation, policy gates, executor restrictions, or audit logging.

Phase 8 adds voice adapters around the visual interface:

```text
voice -> STT adapter -> local API -> brain -> TaskPlan -> safe runtime step(s)
-> text response -> TTS adapter
```

Voice mode is still an input/output layer. It does not change the planner, validator, policy, executor, or audit responsibilities.

Phase 9 replaces the lightweight voice prototype with provider-selected voice adapters:

```text
browser/local audio -> configured STT provider -> brain/runtime
-> typed tool call -> validation -> policy -> executor -> audit
-> response text -> configured TTS provider
```

Local voice providers are runtime adapters only. They can transcribe audio or synthesize speech, but they cannot execute tools, skip validation, change policy decisions, or access shell execution authority.

Phase 10 adds wake-word and VAD gates ahead of STT:

```text
candidate audio/text -> wake-word provider -> VAD provider -> STT
-> brain/runtime -> typed tool call -> validation -> policy -> executor
```

Wake word and VAD providers are input gates only. They can allow, delay, or ignore a speech segment, but they cannot create tasks or run tools.

Phase 14 adds backend microphone capture and richer voice diagnostics:

```text
backend/browser/mock microphone -> audio diagnostics -> STT
-> conversation manager -> brain/runtime -> typed tool call
```

Capture providers can record or supply audio/transcript payloads, but they cannot execute tasks. Empty, noisy, or too-short audio is rejected before command execution. Low-confidence transcripts become clarification prompts.

Phase 15 adds semantic local-LLM intent routing through Ollama:

```text
fast rules -> optional semantic router -> typed JSON tool proposal
-> schema validation -> policy -> executor
```

The semantic router is untrusted. It can only propose one allowlisted JSON tool call or `ask_clarification`. Unknown tools, malformed JSON, invalid arguments, and low confidence are rejected before execution.

Phase 11 adds a Windows executor adapter pack behind the same policy gate:

```text
typed tool call -> schema validation -> policy decision
-> Windows automation adapter -> audit record
```

The Windows adapter can open approved apps, operate on files inside safe roots, use typed clipboard/screenshot helpers, and optionally use local volume/brightness packages. It does not accept raw shell commands.

Phase 12 adds skills and local knowledge above the same safety model:

```text
skill input -> skill schema validation -> skill policy gate
-> typed tool call when needed -> validation -> policy -> executor
```

Knowledge retrieval can supply context and summaries, but it cannot run tools or override policy decisions.

Phase 13 adds beta prototype operations around the same local server:

```text
setup/check/launcher/demo/verify -> local API -> existing safe runtime
```

The diagnostics page is read-only. It reports readiness, paths, providers, safe roots, and recent errors, but it does not execute tools.

## Core Principles

- Local-first by default.
- Tool calls are typed and allowlisted.
- High-risk actions require confirmation.
- Destructive actions are previewed, not blindly executed.
- Every decision is logged for evaluation and improvement.
- Conversation, voice, and LLM components are adapters around the same safe tool layer.
- Real execution is limited to low-risk, allowlisted tools.
- File tools are restricted to configured safe roots.
- LLM output is treated as untrusted input until it passes schema validation and policy.
- The brain is orchestration only; it does not receive raw shell access.
- Persistent memory rejects obvious sensitive content such as passwords, API keys, tokens, credentials, and secrets.
- Personalization memory can be viewed, forgotten, or disabled by the user.
- Voice mode requires explicit confirmation phrases for high-risk actions.
- Voice providers must fail closed into typed/browser fallback rather than crashing or bypassing the runtime.
- Wake/VAD providers must ignore random background speech, empty input, and noisy segments before STT or the brain sees them.
- Backend microphone capture is input only; it cannot run tools or bypass the conversation manager.
- Semantic LLM routing is proposal only; typed schema validation, policy, executor, and audit remain authoritative.
- Windows automation must use typed adapters, app aliases, safe roots, confirmation gates, and audit logs.
- Skills must be schema-validated, policy-gated, auditable, and unable to bypass the typed tool runtime.
- Knowledge retrieval is context only and never execution authority.
- Setup, diagnostics, demo, and verification tooling must not introduce a raw execution side channel.

## Risk Levels

| Level | Examples | Behavior |
|---|---|---|
| none | clarification, unsupported request | no execution |
| low | open app, set volume, search files | allowed after validation |
| medium | terminal launch, draft email, move file, smart-home control | confirmation required |
| high | delete file, send email, run script, shutdown | confirmation required |
| blocked | arbitrary shell, credential access | rejected |

## Phase 2 Execution Boundary

Phase 2 introduces real low-risk execution while keeping destructive actions blocked or preview-only.

Implemented low-risk execution includes:

- note creation and append operations under the configured workspace,
- reminder and timer JSONL records under `.ultron/`,
- safe-root file search,
- safe-root file and folder opening,
- application launch through aliases,
- clipboard helpers on Windows,
- screenshot capture when Pillow/ImageGrab is available.

High-risk operations such as file deletion, sending email, script execution, shutdown, and restart remain non-destructive. Even if the policy receives confirmation, the executor returns `not_implemented` for destructive actions.

## Phase 6 Brain Boundary

The brain owns task-level orchestration, not raw execution. It can:

- decompose a user goal into one or more step utterances,
- preview the selected tool and policy decision for each step,
- execute steps through `UltronAssistant.handle()`,
- stop when a step requires confirmation, fails, or is blocked,
- write a task-level audit record,
- store small non-sensitive memory facts under `.ultron/memory.json`.

It cannot directly call the OS, run shell commands, skip policy, skip schema validation, or treat an LLM response as trusted execution authority.

## Phase 7 Visual Interface Boundary

The visual interface is a client of the local API in `src/ultron27/web_server.py`. The UI provides:

- `POST /api/command` for typed commands,
- `GET /api/status` for current visual/runtime state,
- `GET /api/memory` for non-sensitive memory inspection,
- `POST /api/memory/forget` for deleting matching memory entries,
- `POST /api/memory/toggle` for turning personalization memory on or off,
- `POST /api/subtitles/toggle` for subtitle visibility,
- `POST /api/state` for development-only visual state testing.

The frontend lives under `web/` and uses Three.js for the animated green plasma sphere and particle field. The sphere states map to assistant state rather than policy decisions:

| State | Visual Behavior | Runtime Meaning |
|---|---|---|
| idle | steady sphere and background particles | waiting for interaction |
| listening | slightly contracted sphere and calmer glow | user input is expected |
| thinking | orbiting green eclipse rings and active particles | a command is being planned or executed |
| speaking | expanded glow and crawling plasma arcs | ULTRON is presenting the result |

The UI never receives raw shell access and does not run tools directly. `/api/command` sends the user text through `ConversationManager`; real commands continue to `UltronBrain`, which routes each step through the planner, validator, policy gate, executor, and audit log.

## Phase 8 Voice Boundary

Voice support lives in `src/ultron27/voice.py` and the web API routes in `src/ultron27/web_server.py`. The voice layer owns:

- microphone/session state,
- transcript history,
- provider abstraction for STT and TTS,
- mute and stop-speaking state,
- explicit confirmation phrase handling.

The browser can use its built-in speech recognition as a capture adapter. The backend accepts a transcript through `POST /api/voice/transcribe`, strips the wake word, trims filler text, rejects empty/noisy inputs, and sends confident goals through `ConversationManager` and then the brain/runtime when a command is needed.

Voice API endpoints:

| Endpoint | Purpose |
|---|---|
| `POST /api/voice/start` | Mark voice mode active and listening. |
| `POST /api/voice/stop` | Stop listening. |
| `POST /api/voice/transcribe` | Accept a transcript/audio-provider payload and process it safely. |
| `POST /api/voice/capture` | Run configured backend/mock capture, then process through the same voice pipeline. |
| `POST /api/speak` | Track or stop speech output. |
| `GET /api/voice/status` | Return voice state and transcript history. |

High-risk voice commands pause with `waiting_for_confirmation`. The confirmation phrase must be explicit, for example `yes confirm`. Confirmed destructive actions still remain dry-run or not implemented unless a safe executor is later designed.

If an STT provider reports low confidence, ULTRON records the transcript and asks for clarification instead of executing. The UI history shows the raw user phrase, the cleaned understanding, and the assistant response.

## Phase 14 Voice Diagnostics Boundary

`VoiceSession` owns the backend capture provider, STT provider, transcript cleanup, audio diagnostics, and clarification gating. The diagnostics model records:

- active microphone,
- capture provider,
- STT provider and model path,
- last transcript,
- confidence,
- audio duration,
- speech duration,
- audio energy,
- rejected/noisy status.

These diagnostics are visible through `GET /api/voice/status`, `GET /api/voice/providers`, and voice command responses. They are observational only and do not grant execution authority.

## Phase 15 Semantic Router Boundary

The semantic router lives in `src/ultron27/llm.py`. It uses local Ollama only to propose structured JSON:

```json
{"intent":"open_app","tool_name":"open_application","tool_arguments":{"app":"notepad"},"confidence":0.92}
```

The runtime treats this output as untrusted. It must parse as JSON, match an allowlisted tool, pass schema validation, and pass policy. If the model is unavailable in `hybrid` mode, ULTRON continues with the rules/fallback plan. If the model is uncertain, it must use `ask_clarification` rather than invent an action.

## Phase 9 Offline Voice Provider Boundary

Phase 9 keeps `src/ultron27/voice.py` as the voice boundary and adds local provider adapters:

| Provider Type | Supported Adapters | Fallback |
|---|---|---|
| STT | `faster_whisper`, `whisper_cpp`, `browser`, `text_payload`, `mock` | browser transcript payloads |
| TTS | `piper`, `pyttsx3`, `browser_speech_synthesis`, `mock` | browser speech synthesis or subtitles |

Provider selection comes from `ultron.config.json` or `ULTRON_*` environment variables. The provider health model records:

- configured provider,
- active provider,
- availability,
- fallback target,
- readiness detail.

Provider health endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /api/voice/providers` | Return configured, active, and health-checked STT/TTS providers. |
| `POST /api/voice/test-stt` | Test the active STT provider without running a command. |
| `POST /api/voice/test-tts` | Test the active TTS provider without changing tool state. |

Missing local models, missing Python packages, or missing Piper binaries are reported through health checks and do not crash the web server. The frontend displays active STT/TTS providers so the user can see whether ULTRON is local, browser-backed, or mocked.

## Phase 10 Wake Word and VAD Boundary

Phase 10 adds `src/ultron27/wake.py` and extends `VoiceSession` with a wake gate. The always-listening state machine is:

```text
inactive -> waiting_for_wake_word -> listening -> transcribing
-> thinking -> speaking
```

Supported wake providers:

| Provider | Purpose | Fallback |
|---|---|---|
| `text_wake_word` | Detect `ULTRON` and `Hey ULTRON` in transcript payloads. | none |
| `openwakeword` | Health-checked adapter for future local wake-word audio models. | text wake-word detection |
| `mock_wake_word` | Deterministic tests. | none |

Supported VAD providers:

| Provider | Purpose | Fallback |
|---|---|---|
| `energy_threshold` | Ignore empty, noisy, or low-energy segments. | none |
| `silero_vad` | Health-checked adapter for future Silero VAD use. | energy threshold |
| `webrtc_vad` | Health-checked adapter for future WebRTC VAD use. | energy threshold |
| `mock_vad` | Deterministic tests. | none |

Wake API endpoints:

| Endpoint | Purpose |
|---|---|
| `POST /api/wake/start` | Enable always-listening mode and enter `waiting_for_wake_word`. |
| `POST /api/wake/stop` | Disable always-listening mode and return to `inactive`. |
| `GET /api/wake/status` | Return wake/VAD state and provider health. |
| `POST /api/wake/process` | Browser adapter route for candidate speech segments. |

`POST /api/wake/process` only calls STT and the brain after both gates pass. While the session is `waiting_for_wake_word`, speech without `ULTRON` or `Hey ULTRON` is ignored. Empty/noisy input is ignored before wake detection. Push-to-talk remains available through the Phase 8 `/api/voice/transcribe` route.

## Phase 11 Windows Executor Boundary

Phase 11 adds `src/ultron27/windows_executor.py` as an OS adapter behind `src/ultron27/executor.py`. The planner and LLM still only produce typed tool calls. The executor decides whether a supported OS adapter can run the call.

Windows executor capabilities:

| Capability | Boundary |
|---|---|
| Application launch | Only approved aliases are launchable. Unknown app names are blocked. |
| File/folder open | Explicit paths outside `safe_roots` are blocked. Relative names are resolved inside `safe_roots`. |
| File search | Searches only within `safe_roots`; unsafe explicit folders are blocked. |
| Notes/reminders/timers | Writes under the workspace or `.ultron/`. |
| Clipboard/screenshot | Typed helper adapters only, with dry-run support. |
| Volume/brightness | Optional local provider packages; missing packages return `not_implemented`. |
| Delete/move/rename/shutdown/restart/script/email | Confirmation-gated and intentionally not implemented as destructive behavior. |

Phase 11 also exposes:

| Endpoint | Purpose |
|---|---|
| `GET /api/audit/recent?limit=25` | Return recent audit records, newest first. |
| `POST /api/confirmation/cancel` | Clear pending voice confirmation state after a UI cancel action. |

The UI confirmation modal is a client-side affordance only. Confirming sends the original command back to the same `/api/command` route with `confirmed: true`; it does not run tools directly.

## Phase 12 Skills and Knowledge Boundary

Phase 12 adds `src/ultron27/skills.py` and `src/ultron27/knowledge.py`.

Skill execution has two safety layers:

| Layer | Responsibility |
|---|---|
| Skill schema | Validate the skill name, required inputs, input types, enums, and obvious sensitive content. |
| Skill policy | Apply risk-level behavior before the handler runs. Medium and high-risk skills require confirmation. |
| Tool runtime | For OS-facing actions, skills call `UltronAssistant.handle_tool_call()` so the existing tool validator, policy gate, executor, and audit log still run. |

Built-in skills:

| Skill | Runtime Behavior |
|---|---|
| `notes` | Calls `create_note` or `append_to_note` through the safe runtime. |
| `reminders` | Calls `set_reminder` through the safe runtime. |
| `file_search` | Calls `search_files` through the safe runtime. |
| `project_summary` | Searches local knowledge and returns summaries only. |
| `daily_planning` | Drafts a plan from user-provided priorities and local context only. |

Knowledge base behavior:

| Area | Rule |
|---|---|
| Source path | Must be inside configured `safe_roots`. |
| Supported files | Markdown, TXT, PDF with `pypdf`, DOCX with `python-docx`. |
| Storage | `.ultron/knowledge/index.json` with metadata and chunks. |
| Privacy | Rejects obvious secrets such as passwords, tokens, API keys, credentials, and private keys. |
| Retrieval | Keyword search first; embedding provider abstraction is present for later. |
| Authority | Retrieved text can inform responses but cannot execute tasks or override policy. |

Phase 12 endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /api/skills` | Return built-in skill metadata and schemas. |
| `POST /api/skills/run` | Run a skill after skill schema validation and policy. |
| `POST /api/knowledge/ingest` | Ingest a safe local document into the knowledge index. |
| `GET /api/knowledge/search` | Search indexed knowledge chunks by keyword. |

## Phase 13 Beta Operations Boundary

Phase 13 adds setup and operations tooling without changing execution authority.

Operator scripts:

| Script | Purpose |
|---|---|
| `scripts/setup_ultron_windows.ps1` | Create a Windows virtual environment, install the package, write a safe config, and run dependency checks. |
| `scripts/check_dependencies.py` | Check required repo files and report/knowledge Python packages. |
| `scripts/check_providers.py` | Check configured STT/TTS/wake/VAD providers and fallback status. |
| `scripts/config_wizard.py` | Write `ultron.config.json` interactively or with safe defaults. |
| `scripts/launch_ultron.py` | Start backend and UI together, handle port conflicts, and print URLs. |
| `scripts/demo_phase13.py` | Run typed, mock voice, note creation, and confirmation demos without a microphone. |
| `scripts/verify_phase13.py` | Run unit tests, dataset evaluation, safety regression, and API smoke checks. |

Diagnostics endpoint:

| Endpoint | Purpose |
|---|---|
| `GET /api/diagnostics` | Return backend, brain, runtime path, voice provider, safe-root, knowledge, dependency, and recent-error readiness data. |

Diagnostics data is informational. It cannot approve actions, run tools, bypass policy, or modify the workspace.

## Dataset Role

The provided dataset is used for:

- intent recognition experiments,
- tool-name accuracy,
- slot/tool-argument extraction,
- confirmation-policy regression tests,
- unsafe-action refusal testing.

It should not be treated as execution authority. Dataset rows are examples for learning and evaluation, not commands to run without policy checks.
