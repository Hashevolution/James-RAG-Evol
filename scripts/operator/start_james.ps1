# PROJECT JAMES — operator launcher (v0.6.1)
#
# Interactive workspace picker so the operator can run JAMES on the
# default workspace (313 entity 누적 main work) vs a fresh
# `dogfood-<date>` workspace (Stream A.3 dogfooding evidence) vs an
# existing isolated workspace (cycle-γ research data, etc.) without
# editing env vars by hand.
#
# Lives outside the Python server boot path on purpose — wraps the
# server boot so the env is set BEFORE FastAPI / Uvicorn / Ollama
# initialise their workspace-derived paths (chroma_db, wiki/entity,
# audit DBs, …). Switching mid-process requires a restart (see
# `docs/deployment/v0.6-workspace-switching.md`).
#
# Usage:
#   .\scripts\operator\start_james.ps1                  # interactive picker
#   .\scripts\operator\start_james.ps1 -Workspace dogfood-2026-06
#   .\scripts\operator\start_james.ps1 -Workspace default
#
# The script does NOT mutate the user's $PROFILE or persistent env —
# the JAMES_WORKSPACE export only affects the child python process.

[CmdletBinding()]
param(
    [string]$Workspace = "",
    [string]$PythonExe = "python",
    [string]$ServerEntry = "server_llmwiki.py"
)

$ErrorActionPreference = "Stop"

# Force UTF-8 console output so the Korean labels + Unicode box-drawing
# characters render correctly on Windows PowerShell 5.1 (default cp949
# on Korean Windows). PowerShell 7 already defaults to UTF-8.
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

# Project root = parent of scripts/operator/
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$workspacesDir = Join-Path $repoRoot "workspaces"

function _List-Workspaces {
    # Built-in choices + every existing subdir of $workspacesDir whose
    # name passes the path-safe pattern (mirrors
    # core/plugins/workspace.py::_TENANT_ID_RE for consistency).
    $choices = @(
        @{ Key = "default";    Label = "default (main, 313+ entity)";          Env = "" }
    )
    if (Test-Path $workspacesDir) {
        Get-ChildItem -Directory $workspacesDir | ForEach-Object {
            $name = $_.Name
            if ($name -match '^[a-z][a-z0-9_-]*$') {
                $choices += @{
                    Key   = $name
                    Label = "$name (workspaces/$name)"
                    Env   = (Join-Path "workspaces" $name)
                }
            }
        }
    }
    # Always offer a NEW dogfood-<date> slot.
    $today = Get-Date -Format "yyyy-MM"
    $dogfoodKey = "dogfood-$today"
    $dogfoodPath = Join-Path "workspaces" $dogfoodKey
    $alreadyListed = $choices | Where-Object { $_.Key -eq $dogfoodKey }
    if (-not $alreadyListed) {
        $choices += @{
            Key   = $dogfoodKey
            Label = "NEW: $dogfoodKey (Stream A.3 dogfooding workspace)"
            Env   = $dogfoodPath
        }
    }
    return $choices
}

function _Pick-Workspace {
    $choices = _List-Workspaces
    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════════════"
    Write-Host "  PROJECT JAMES — workspace picker"
    Write-Host "═══════════════════════════════════════════════════════════"
    Write-Host ""
    for ($i = 0; $i -lt $choices.Count; $i++) {
        $marker = "  [$($i+1)]"
        Write-Host "$marker $($choices[$i].Label)"
    }
    Write-Host ""
    $sel = Read-Host "Choose [1-$($choices.Count)] (Enter = 1)"
    if ([string]::IsNullOrWhiteSpace($sel)) { $sel = "1" }
    $idx = 0
    if (-not [int]::TryParse($sel, [ref]$idx) -or $idx -lt 1 -or $idx -gt $choices.Count) {
        Write-Host "Invalid choice; aborting." -ForegroundColor Red
        exit 1
    }
    return $choices[$idx - 1]
}

# ── Resolve picked workspace ──────────────────────────────────────

$pick = $null
if ($Workspace) {
    # Non-interactive path. Accept "default" or a name matching the
    # path-safe pattern; reject anything else early.
    if ($Workspace -eq "default") {
        $pick = @{ Key = "default"; Env = "" }
    } elseif ($Workspace -match '^[a-z][a-z0-9_-]*$') {
        $pick = @{
            Key = $Workspace
            Env = (Join-Path "workspaces" $Workspace)
        }
    } else {
        Write-Host "Invalid workspace name: $Workspace" -ForegroundColor Red
        Write-Host "Must be 'default' or match ^[a-z][a-z0-9_-]*$" -ForegroundColor Red
        exit 1
    }
} else {
    $pick = _Pick-Workspace
}

# ── Create workspace dir if missing ───────────────────────────────

if ($pick.Env -ne "") {
    $absWsPath = Join-Path $repoRoot $pick.Env
    if (-not (Test-Path $absWsPath)) {
        Write-Host ""
        Write-Host "Creating new workspace dir: $absWsPath" -ForegroundColor Yellow
        New-Item -ItemType Directory -Force $absWsPath | Out-Null
    }
}

# ── Set env (child-process scope only) + boot ─────────────────────

$env:JAMES_WORKSPACE = $pick.Env

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════"
Write-Host "  Booting JAMES on workspace: $($pick.Key)"
Write-Host "  JAMES_WORKSPACE = '$($pick.Env)'"
Write-Host "═══════════════════════════════════════════════════════════"
Write-Host ""

Push-Location $repoRoot
try {
    & $PythonExe $ServerEntry
} finally {
    Pop-Location
}
