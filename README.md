# ULTRON 2.7

ULTRON 2.7 is a local-first Jarvis-style laptop assistant MVP. It turns natural-language commands into typed tool calls, validates them, applies a safety policy, and executes them only through an allowlisted tool layer.

The repo is built around the supplied research paper and synthetic laptop-command dataset. The current implementation is text-first so the command, policy, and evaluation loop can become reliable before wake-word, STT, and TTS are added.

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
- Optional LLM planner adapter with Ollama support, strict JSON parsing, schema validation, and safe fallback behavior.
- Interactive assistant console for repeated commands, confirmations, and JSON inspection.
- Agentic brain layer for multi-step task planning, safe execution, and non-sensitive memory.
- Cyberpunk green plasma-sphere web interface backed by the local brain/runtime API.
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
ultron "delete project_report.txt" --yes
python scripts/evaluate_dataset.py --split test
python scripts/analyze_dataset_quality.py
python scripts/evaluate_safety_regression.py
python -m ultron27 "launch the basic text editor" --planner-mode hybrid
python -m ultron27 --interactive
python -m ultron27 "/plan Create a note called project ideas and add that I should test voice mode next." --text
python -m ultron27 "/do Create a note called project ideas and add that I should test voice mode next." --text --execute --workspace .
python scripts/run_phase7_ui.py --port 8765
python -m unittest discover -s tests
```

If the `ultron` command is not available after installation, use:

```powershell
python -m ultron27 "set volume to 40 percent"
```

By default ULTRON runs in dry-run mode. Use `--execute` only after reviewing the tool, policy, and implementation. High-risk actions are still not implemented as destructive operations, even after confirmation.

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
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "terminal": "wt.exe"
  },
  "planner_mode": "rules",
  "llm_provider": "ollama",
  "llm_model": "qwen2.5:7b-instruct",
  "llm_endpoint": "http://localhost:11434",
  "llm_timeout_seconds": 8
}
```

Environment variables override the JSON config:

```powershell
$env:ULTRON_DRY_RUN = "true"
$env:ULTRON_AUDIT_LOG = ".ultron/audit.jsonl"
$env:ULTRON_SAFE_ROOTS = ".;~/Desktop;~/Documents;~/Downloads"
$env:ULTRON_PLANNER_MODE = "rules"
$env:ULTRON_LLM_MODEL = "qwen2.5:7b-instruct"
$env:ULTRON_LLM_ENDPOINT = "http://localhost:11434"
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
ultron "create note standup" --workspace .
ultron "open notepad" --execute
ultron "delete project_report.txt" --yes
```

## Phase 2 Safe Execution

Phase 2 adds real execution for low-risk tools while keeping destructive commands disabled:

- `create_note` and `append_to_note` write Markdown files under `notes/`.
- `set_reminder` and `start_timer` append JSONL records under `.ultron/`.
- `search_files`, `open_file`, and `open_folder` operate only inside configured `safe_roots`.
- `open_application` uses configurable `app_aliases`.
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
POST /api/subtitles/toggle
POST /api/state
```

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

High-risk operations such as deleting files, sending email, running scripts, restarting, or shutting down require confirmation. Destructive execution is intentionally left unimplemented in this MVP.

## Roadmap

1. Add local STT using faster-whisper or whisper.cpp.
2. Add local TTS using Piper.
3. Add wake-word and VAD using openWakeWord and Silero VAD.
4. Grow the dataset with real corrected transcripts and Hinglish/Hindi variants.
5. Add richer OS-specific executor plugins for Windows, macOS, and Linux.
