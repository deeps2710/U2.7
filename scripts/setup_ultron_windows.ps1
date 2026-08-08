param(
  [switch]$SkipInstall,
  [switch]$ForceConfig,
  [switch]$SkipShortcut
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
  Write-Host "Installing editable package, desktop runtime, and test tools..."
  & $Python -m pip install --upgrade pip
  & $Python -m pip install -e "${Root}[dev,desktop,windows]"
}

$Config = Join-Path $Root "ultron.config.json"
if ((-not (Test-Path $Config)) -or $ForceConfig) {
  Write-Host "Writing safe default config..."
  & $Python (Join-Path $Root "scripts\config_wizard.py") --defaults --force --output $Config
}

Write-Host "Running dependency check..."
& $Python (Join-Path $Root "scripts\check_dependencies.py")

if (-not $SkipShortcut) {
  $Icon = Join-Path $Root "assets\ultron.ico"
  if (-not (Test-Path $Icon)) {
    & $Python (Join-Path $Root "scripts\generate_desktop_icon.py") --output $Icon
  }
  $Launcher = Join-Path $Venv "Scripts\ultron-desktop.exe"
  $Desktop = [Environment]::GetFolderPath("Desktop")
  $ShortcutPath = Join-Path $Desktop "ULTRON 2.7.lnk"
  $Shell = New-Object -ComObject WScript.Shell
  $Shortcut = $Shell.CreateShortcut($ShortcutPath)
  $Shortcut.TargetPath = $Launcher
  $Shortcut.WorkingDirectory = $Root
  $Shortcut.Description = "ULTRON 2.7 desktop assistant"
  $Shortcut.IconLocation = $Icon
  $Shortcut.Save()
  Write-Host "Desktop shortcut: $ShortcutPath"
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "Start ULTRON with:"
Write-Host "  .\.venv\Scripts\ultron-desktop.exe"
Write-Host "Build the standalone Windows app with:"
Write-Host "  .\scripts\build_ultron_desktop.ps1"
