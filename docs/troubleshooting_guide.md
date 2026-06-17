# ULTRON 2.7 Troubleshooting Guide

## Port Already In Use

Use the Phase 13 launcher:

```powershell
python scripts\launch_ultron.py --port 8765
```

If `8765` is busy, the launcher selects the next available port and prints the new URL.

## Missing Python Packages

Run:

```powershell
python scripts\check_dependencies.py
```

Install missing report/knowledge packages:

```powershell
python -m pip install python-docx reportlab pypdf pillow
```

## Voice Provider Falls Back

Run:

```powershell
python scripts\check_providers.py
```

Fallback is expected if local models or optional packages are not installed. Browser/mock voice remains available for demo mode.

## Microphone Unavailable

Use typed mode or Mock Voice in the UI. The demo script also works without a microphone:

```powershell
python scripts\demo_phase13.py
```

## Commands Do Not Execute

Check whether `dry_run` is enabled in `ultron.config.json`. Dry-run is the default. Low-risk real actions need execute mode, safe roots, and supported local adapters.

## File Access Is Blocked

File and knowledge operations must stay inside configured safe roots. Update `safe_roots` with:

```powershell
python scripts\config_wizard.py --force
```

Then restart ULTRON.
