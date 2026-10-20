$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Missing .venv. Run scripts\setup_solar_mind.ps1 first."
}

Set-Location -LiteralPath $ProjectRoot
& $VenvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8765
if ($LASTEXITCODE -ne 0) { throw "SolarMind server exited with code $LASTEXITCODE." }
