# Builds both Collection AI executables (Service + Configuration) via PyInstaller.
#
# Usage (from repo root, or anywhere):
#   .\scripts\build_exes.ps1
#
# Output: dist\CollectionAI-Service.exe and dist\CollectionAI-Config.exe,
# built side by side — the Configuration app's Service tab looks for the
# Service exe next to itself (see src/gui_config/service_control.py).

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$DistPath = Join-Path $Root "dist"
$WorkPath = Join-Path $Root "build"

if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment not found at $VenvPython. Create it with: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
}

Write-Host "=== Building CollectionAI-Config.exe ===" -ForegroundColor Cyan
& $VenvPython -m PyInstaller --noconfirm --clean `
    --distpath $DistPath --workpath $WorkPath `
    (Join-Path $Root "packaging\collectionai_config.spec")
if ($LASTEXITCODE -ne 0) { throw "Config exe build failed." }

Write-Host "=== Building CollectionAI-Service.exe ===" -ForegroundColor Cyan
& $VenvPython -m PyInstaller --noconfirm --clean `
    --distpath $DistPath --workpath $WorkPath `
    (Join-Path $Root "packaging\collectionai_service.spec")
if ($LASTEXITCODE -ne 0) { throw "Service exe build failed." }

Write-Host ""
Write-Host "Done. Executables:" -ForegroundColor Green
Write-Host "  $DistPath\CollectionAI-Config.exe"
Write-Host "  $DistPath\CollectionAI-Service.exe"
Write-Host ""
Write-Host "Copy both to the target machine's install folder (same folder), then:" -ForegroundColor Yellow
Write-Host "  1. Run CollectionAI-Config.exe, fill in the Database tab, Save."
Write-Host "  2. In the Service tab, click Install then Start."
