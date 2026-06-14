# Phase 5: Interactive Prototype

Phase 5 turns ULTRON 2.7 from a one-command CLI into a basic working assistant session. The core safety architecture does not change: every user command still becomes a typed tool call, passes schema validation, goes through policy, executes only through the allowlisted executor, and is written to the audit log unless disabled.

## What Changed

- Added `src/ultron27/runtime.py` with `RuntimeSettings` and `UltronAssistant`.
- Added `src/ultron27/console.py` for interactive command handling and concise text responses.
- Updated `src/ultron27/cli.py` so one-shot JSON mode and interactive mode share the same runtime.
- Added `--interactive` / `-i` for assistant sessions.
- Added `--text` for single-command human-readable output.
- Added tests for the runtime pipeline, text response formatting, and console commands.

## How To Run

```powershell
python -m ultron27 --interactive
```

Useful console commands:

```text
/help              Show console commands.
/json <command>    Run a command and print the full JSON payload.
/yes <command>     Confirm a command that needs confirmation.
/exit              Leave the console.
```

For one-shot text output:

```powershell
python -m ultron27 "set volume to 40 percent" --text
```

## Prototype Boundary

This phase intentionally avoids adding microphone input, wake-word detection, or text-to-speech dependencies. The interactive console is the stable base for those layers because it exercises the full planner, policy, executor, and audit loop repeatedly in one session.

## Verification

Phase 5 should pass:

```powershell
python -m unittest discover -s tests
python scripts/evaluate_dataset.py --split test
python scripts/evaluate_safety_regression.py
```
