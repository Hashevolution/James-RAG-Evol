# JAMES / SEKOS - dev server launcher (Windows).
# Runs server_llmwiki.py from the .venv with auto-reload, so code edits
# are picked up live. Run install.bat once first.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "[start] .venv not found — run install.bat first." -ForegroundColor Yellow
    exit 1
}

# Ollama health check (warn only — server boots either way).
try {
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 `
        "http://127.0.0.1:11434/api/tags" | Out-Null
    Write-Host "[start] Ollama reachable." -ForegroundColor Green
} catch {
    Write-Host "[start] WARNING: Ollama not reachable on :11434 - LLM answers will fail until you start it." -ForegroundColor Yellow
}

Start-Process "http://localhost:8000/admin"
Write-Host "[start] Launching JAMES on http://localhost:8000  (Ctrl+C to stop)" -ForegroundColor Cyan
& $venvPy server_llmwiki.py
