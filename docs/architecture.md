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

## Core Principles

- Local-first by default.
- Tool calls are typed and allowlisted.
- High-risk actions require confirmation.
- Destructive actions are previewed, not blindly executed.
- Every decision is logged for evaluation and improvement.
- Voice and LLM components are adapters around the same safe tool layer.
- Real execution is limited to low-risk, allowlisted tools.
- File tools are restricted to configured safe roots.
- LLM output is treated as untrusted input until it passes schema validation and policy.
- The brain is orchestration only; it does not receive raw shell access.
- Persistent memory rejects obvious sensitive content such as passwords, API keys, tokens, credentials, and secrets.
- Voice mode requires explicit confirmation phrases for high-risk actions.
- Voice providers must fail closed into typed/browser fallback rather than crashing or bypassing the runtime.

## Risk Levels

| Level | Examples | Behavior |
|---|---|---|
| none | clarification, unsupported request | no execution |
| low | open app, set volume, search files | allowed after validation |
| medium | draft email, move file, smart-home control | confirmation when configured |
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
- `POST /api/subtitles/toggle` for subtitle visibility,
- `POST /api/state` for development-only visual state testing.

The frontend lives under `web/` and uses Three.js for the animated green plasma sphere and particle field. The sphere states map to assistant state rather than policy decisions:

| State | Visual Behavior | Runtime Meaning |
|---|---|---|
| idle | steady sphere and background particles | waiting for interaction |
| listening | slightly contracted sphere and calmer glow | user input is expected |
| thinking | orbiting green eclipse rings and active particles | a command is being planned or executed |
| speaking | expanded glow and crawling plasma arcs | ULTRON is presenting the result |

The UI never receives raw shell access and does not run tools directly. `/api/command` sends the user goal to `UltronBrain`, which routes each step through the planner, validator, policy gate, executor, and audit log.

## Phase 8 Voice Boundary

Voice support lives in `src/ultron27/voice.py` and the web API routes in `src/ultron27/web_server.py`. The voice layer owns:

- microphone/session state,
- transcript history,
- provider abstraction for STT and TTS,
- mute and stop-speaking state,
- explicit confirmation phrase handling.

The browser can use its built-in speech recognition as a capture adapter. The backend accepts a transcript through `POST /api/voice/transcribe`, strips the wake word, and sends the resulting goal through `UltronBrain`.

Voice API endpoints:

| Endpoint | Purpose |
|---|---|
| `POST /api/voice/start` | Mark voice mode active and listening. |
| `POST /api/voice/stop` | Stop listening. |
| `POST /api/voice/transcribe` | Accept a transcript/audio-provider payload and process it safely. |
| `POST /api/speak` | Track or stop speech output. |
| `GET /api/voice/status` | Return voice state and transcript history. |

High-risk voice commands pause with `waiting_for_confirmation`. The confirmation phrase must be explicit, for example `yes confirm`. Confirmed destructive actions still remain dry-run or not implemented unless a safe executor is later designed.

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

## Dataset Role

The provided dataset is used for:

- intent recognition experiments,
- tool-name accuracy,
- slot/tool-argument extraction,
- confirmation-policy regression tests,
- unsafe-action refusal testing.

It should not be treated as execution authority. Dataset rows are examples for learning and evaluation, not commands to run without policy checks.
