param(
  [switch]$SkipInstall,
  [switch]$Launch,
  [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Icon = Join-Path $Root "assets\ultron.ico"
$PackageRoot = Join-Path $env:LOCALAPPDATA "ULTRON 2.7\desktop-build"
$WorkPath = Join-Path $PackageRoot "work"
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
  $DistPath = Join-Path $PackageRoot "dist"
} elseif ([System.IO.Path]::IsPathRooted($OutputRoot)) {
  $DistPath = $OutputRoot
} else {
  $DistPath = Join-Path $Root $OutputRoot
}
$Executable = Join-Path $DistPath "ULTRON 2.7\ULTRON 2.7.exe"

if (-not (Test-Path $Python)) {
  throw "Run scripts\setup_ultron_windows.ps1 first so the project virtual environment exists."
}

if (-not $SkipInstall) {
  & $Python -m pip install -e "${Root}[desktop,windows,build]"
  if ($LASTEXITCODE -ne 0) { throw "Desktop build dependencies could not be installed." }
}

& $Python (Join-Path $Root "scripts\generate_desktop_icon.py") --output $Icon
if ($LASTEXITCODE -ne 0) { throw "The application icon could not be generated." }

Push-Location $Root
try {
  & $Python -m PyInstaller --noconfirm --clean --workpath $WorkPath --distpath $DistPath "ultron27.spec"
  if ($LASTEXITCODE -ne 0) { throw "PyInstaller could not build ULTRON 2.7." }
} finally {
  Pop-Location
}

Write-Host ""
Write-Host "Desktop build ready:"
Write-Host "  $Executable"

if ($Launch) {
  Start-Process -FilePath $Executable -WorkingDirectory (Split-Path -Parent $Executable)
}
