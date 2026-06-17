# ULTRON 2.7 Install Guide

This guide is for a local Windows prototype setup.

## Requirements

- Windows 10 or 11.
- Python 3.10 or newer.
- PowerShell.
- Git, if cloning from GitHub.

Optional voice/model dependencies can be added later. The default beta setup uses browser/mock voice fallbacks so the prototype can run without local STT/TTS models.

## Install

From the repository root:

```powershell
.\scripts\setup_ultron_windows.ps1
```

The setup script:

- creates `.venv`,
- installs ULTRON in editable mode,
- writes `ultron.config.json` if missing,
- checks required files and Python packages.

If you want to skip package installation and only run checks:

```powershell
.\scripts\setup_ultron_windows.ps1 -SkipInstall
```

## Manual Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[dev]
python scripts\config_wizard.py --defaults
python scripts\check_dependencies.py
python scripts\check_providers.py
```

## First Launch

```powershell
python scripts\launch_ultron.py
```

Open the printed local URL in your browser.
