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
- Pytest test suite for planner, validation, policy, and execution behavior.

## Project Layout

```text
src/ultron27/            Assistant package
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
  }
}
```

Environment variables override the JSON config:

```powershell
$env:ULTRON_DRY_RUN = "true"
$env:ULTRON_AUDIT_LOG = ".ultron/audit.jsonl"
$env:ULTRON_SAFE_ROOTS = ".;~/Desktop;~/Documents;~/Downloads"
```

Useful CLI flags:

```powershell
ultron "open notepad" --no-audit
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
4. Add optional local/cloud LLM planner adapters.
5. Grow the dataset with real corrected transcripts and Hinglish/Hindi variants.
6. Add richer OS-specific executor plugins for Windows, macOS, and Linux.
