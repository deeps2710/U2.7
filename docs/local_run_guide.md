# ULTRON 2.7 Local Run Guide

## Recommended Start Command

```powershell
python scripts\launch_ultron.py
```

The launcher starts the backend and serves the UI from the same local process. It prints:

- main interface URL,
- diagnostics URL,
- selected port.

If the requested port is busy, it automatically tries the next available port.

## Useful Options

```powershell
python scripts\launch_ultron.py --port 8765
python scripts\launch_ultron.py --dry-run
python scripts\launch_ultron.py --execute
python scripts\launch_ultron.py --config ultron.config.json
python scripts\launch_ultron.py --open
```

Use `--execute` only after reviewing the safety behavior. Destructive actions remain blocked or unimplemented.

## Diagnostics

Open:

```text
http://127.0.0.1:8765/diagnostics
```

The page shows:

- backend status,
- brain and dataset status,
- voice provider status,
- memory and audit paths,
- safe roots,
- recent readiness errors.

## Demo Without Microphone

```powershell
python scripts\demo_phase13.py
```

This runs a typed command, a note creation command, a confirmation-gated command, and a mock voice command.

## Full Verification

```powershell
python scripts\verify_phase13.py
```
