#!/usr/bin/env bash
# PROJECT JAMES — operator launcher (v0.6.1), POSIX variant
#
# See start_james.ps1 for the Windows companion + full rationale.
#
# Usage:
#   ./scripts/operator/start_james.sh                    # interactive
#   ./scripts/operator/start_james.sh dogfood-2026-06    # non-interactive
#   ./scripts/operator/start_james.sh default
set -euo pipefail

WORKSPACE="${1:-}"
PYTHON_EXE="${PYTHON_EXE:-python}"
SERVER_ENTRY="${SERVER_ENTRY:-server_llmwiki.py}"

# Repo root = parent of scripts/operator/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORKSPACES_DIR="$REPO_ROOT/workspaces"

_name_re='^[a-z][a-z0-9_-]*$'

# ── List built-in + existing workspace choices ────────────────────

declare -a CHOICE_KEYS=("default")
declare -a CHOICE_LABELS=("default (main, 313+ entity)")
declare -a CHOICE_ENVS=("")

if [[ -d "$WORKSPACES_DIR" ]]; then
    for d in "$WORKSPACES_DIR"/*/; do
        [[ -d "$d" ]] || continue
        name="$(basename "$d")"
        if [[ "$name" =~ $_name_re ]]; then
            CHOICE_KEYS+=("$name")
            CHOICE_LABELS+=("$name (workspaces/$name)")
            CHOICE_ENVS+=("workspaces/$name")
        fi
    done
fi

# Always offer NEW dogfood-<YYYY-MM> slot if not already listed.
today="$(date +%Y-%m)"
dogfood_key="dogfood-$today"
already=0
for k in "${CHOICE_KEYS[@]}"; do
    if [[ "$k" == "$dogfood_key" ]]; then
        already=1
        break
    fi
done
if [[ "$already" -eq 0 ]]; then
    CHOICE_KEYS+=("$dogfood_key")
    CHOICE_LABELS+=("NEW: $dogfood_key (Stream A.3 dogfooding workspace)")
    CHOICE_ENVS+=("workspaces/$dogfood_key")
fi

# ── Pick ──────────────────────────────────────────────────────────

picked_key=""
picked_env=""

if [[ -n "$WORKSPACE" ]]; then
    if [[ "$WORKSPACE" == "default" ]]; then
        picked_key="default"
        picked_env=""
    elif [[ "$WORKSPACE" =~ $_name_re ]]; then
        picked_key="$WORKSPACE"
        picked_env="workspaces/$WORKSPACE"
    else
        echo "Invalid workspace name: $WORKSPACE" >&2
        echo "Must be 'default' or match $_name_re" >&2
        exit 1
    fi
else
    echo
    echo "═══════════════════════════════════════════════════════════"
    echo "  PROJECT JAMES — workspace picker"
    echo "═══════════════════════════════════════════════════════════"
    echo
    for i in "${!CHOICE_LABELS[@]}"; do
        printf "  [%d] %s\n" $((i + 1)) "${CHOICE_LABELS[$i]}"
    done
    echo
    read -r -p "Choose [1-${#CHOICE_LABELS[@]}] (Enter = 1): " sel
    if [[ -z "$sel" ]]; then sel=1; fi
    if ! [[ "$sel" =~ ^[0-9]+$ ]] || [[ "$sel" -lt 1 ]] || [[ "$sel" -gt "${#CHOICE_LABELS[@]}" ]]; then
        echo "Invalid choice; aborting." >&2
        exit 1
    fi
    idx=$((sel - 1))
    picked_key="${CHOICE_KEYS[$idx]}"
    picked_env="${CHOICE_ENVS[$idx]}"
fi

# ── Create workspace dir if missing ───────────────────────────────

if [[ -n "$picked_env" ]]; then
    abs_path="$REPO_ROOT/$picked_env"
    if [[ ! -d "$abs_path" ]]; then
        echo
        echo "Creating new workspace dir: $abs_path"
        mkdir -p "$abs_path"
    fi
fi

# ── Boot ──────────────────────────────────────────────────────────

export JAMES_WORKSPACE="$picked_env"

echo
echo "═══════════════════════════════════════════════════════════"
echo "  Booting JAMES on workspace: $picked_key"
echo "  JAMES_WORKSPACE = '$picked_env'"
echo "═══════════════════════════════════════════════════════════"
echo

cd "$REPO_ROOT"
exec "$PYTHON_EXE" "$SERVER_ENTRY"
