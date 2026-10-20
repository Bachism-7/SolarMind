$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$env:PIP_CACHE_DIR = Join-Path $ProjectRoot ".pip-cache"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    & py -3 -m venv (Join-Path $ProjectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Could not create .venv. Install Python 3.12 and the py launcher first." }
}

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }
& $VenvPython -m pip install -e "${ProjectRoot}[test]"
if ($LASTEXITCODE -ne 0) { throw "SolarMind dependency installation failed." }

Write-Host "Setup complete. Start with: powershell -ExecutionPolicy Bypass -File .\scripts\start_solar_mind.ps1"
