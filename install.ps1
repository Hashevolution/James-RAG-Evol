# ================================================================
#  JAMES / SEKOS - one-shot setup (Windows, run-from-source).
#
#  Double-click install.bat (or run: powershell -ExecutionPolicy Bypass
#  -File install.ps1) on a freshly-cloned repo. It:
#    1. finds Python, creates a .venv virtualenv,
#    2. installs requirements.txt into it,
#    3. creates .env from .env.example with a fresh API key + JWT secret,
#    4. DETECTS + GUIDES native deps (Ollama / Tesseract / Poppler) -
#       it does NOT silently install system software,
#    5. offers to pull the default model if Ollama is present.
#
#  Then run start.bat to launch the dev server (auto-reload).
#  Re-running is safe (idempotent): existing .venv / .env are reused.
# ================================================================
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

function Info($m) { Write-Host "[install] $m" -ForegroundColor Cyan }
function Good($m) { Write-Host "[ ok ]   $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[warn]   $m" -ForegroundColor Yellow }

Info "JAMES / SEKOS setup - $root"

# -- 1. Python ----------------------------------------------------
$py = $null
foreach ($c in @('python', 'py')) {
    if (Get-Command $c -ErrorAction SilentlyContinue) { $py = $c; break }
}
if (-not $py) {
    Warn "Python 3.11+ not found on PATH."
    Warn "  Install from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'),"
    Warn "  then re-run this script."
    exit 1
}
Good "Python found ($py)."

# -- 2. virtualenv ------------------------------------------------
if (-not (Test-Path ".venv")) {
    Info "Creating virtualenv (.venv)..."
    & $py -m venv .venv
}
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Warn "venv python missing at $venvPy - delete .venv and re-run."
    exit 1
}
Good "Virtualenv ready (.venv)."

# -- 3. dependencies ----------------------------------------------
Info "Installing Python dependencies (first run can take 5-10 min)..."
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r requirements.txt
Good "Dependencies installed."

# -- 4. .env (+ generated secrets) --------------------------------
if (-not (Test-Path ".env")) {
    Info "Creating .env from .env.example with fresh secrets..."
    Copy-Item ".env.example" ".env"
    $apiKey = (& $venvPy -c "import secrets;print(secrets.token_urlsafe(32))").Trim()
    $jwt    = (& $venvPy -c "import secrets;print(secrets.token_urlsafe(48))").Trim()
    $envTxt = Get-Content ".env" -Raw
    $envTxt = $envTxt -replace 'JAMES_API_KEY=your-api-key-here', "JAMES_API_KEY=$apiKey"
    $envTxt = $envTxt -replace 'JAMES_JWT_SECRET=your-jwt-secret-here-min-32-chars', "JAMES_JWT_SECRET=$jwt"
    Set-Content ".env" $envTxt -Encoding UTF8
    Good ".env created (API key + JWT secret generated)."
} else {
    Good ".env already exists - left untouched."
}

# -- 5. Ollama (REQUIRED - detect + guide) ------------------------
$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
$ollamaUp  = $false
try {
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://127.0.0.1:11434/api/tags" | Out-Null
    $ollamaUp = $true
} catch {}

if (-not $ollamaCmd -and -not $ollamaUp) {
    Warn "Ollama (local LLM runtime) NOT found - it is REQUIRED to answer."
    Warn "  Install:  winget install Ollama.Ollama"
    Warn "  or download: https://ollama.com/download"
    Warn "  After installing, pull the default model:  ollama pull gemma4:e4b"
} else {
    Good "Ollama detected."
    $models = ""
    try { $models = (& ollama list | Out-String) } catch {}
    if ($models -notmatch 'gemma4:e4b') {
        Warn "Default model 'gemma4:e4b' not present (~2.5 GB download)."
        $ans = Read-Host "Pull it now? [y/N]"
        if ($ans -match '^[Yy]') {
            Info "Pulling gemma4:e4b..."
            & ollama pull gemma4:e4b
            Good "Model pulled."
        } else {
            Warn "Skipped - pull later with:  ollama pull gemma4:e4b"
        }
    } else {
        Good "Model 'gemma4:e4b' present."
    }
}

# -- 6. optional native deps (detect + guide) ---------------------
$hasTess = (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe") -or (Get-Command tesseract -ErrorAction SilentlyContinue)
if (-not $hasTess) {
    Warn "Tesseract OCR not found (optional - image OCR)."
    Warn "  winget install UB-Mannheim.TesseractOCR"
}
$hasPoppler = (Test-Path "C:\poppler") -or (Test-Path "C:\Program Files\poppler")
if (-not $hasPoppler) {
    Warn "Poppler not found (optional - PDF page to image)."
    Warn "  https://github.com/oschwartz10612/poppler-windows/releases"
}

Write-Host ""
Good "Setup complete."
Write-Host "  Start the server:   .\start.bat" -ForegroundColor White
Write-Host "  Admin / chat:       http://localhost:8000/admin  |  http://localhost:8000" -ForegroundColor White
