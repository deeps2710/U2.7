param(
  [switch]$SkipInstall,
  [switch]$ForceConfig
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"

Write-Host "ULTRON 2.7 Windows setup"
Write-Host "Root: $Root"

if (-not (Test-Path $Venv)) {
  Write-Host "Creating virtual environment..."
  if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 -m venv $Venv
  } else {
    python -m venv $Venv
  }
}

if (-not $SkipInstall) {
  Write-Host "Installing editable package and test tools..."
  & $Python -m pip install --upgrade pip
  & $Python -m pip install -e "$Root[dev]"
}

$Config = Join-Path $Root "ultron.config.json"
if ((-not (Test-Path $Config)) -or $ForceConfig) {
  Write-Host "Writing safe default config..."
  & $Python (Join-Path $Root "scripts\config_wizard.py") --defaults --force --output $Config
}

Write-Host "Running dependency check..."
& $Python (Join-Path $Root "scripts\check_dependencies.py")

Write-Host ""
Write-Host "Setup complete."
Write-Host "Start ULTRON with:"
Write-Host "  .\.venv\Scripts\python.exe scripts\launch_ultron.py"
