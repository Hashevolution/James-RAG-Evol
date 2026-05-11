"""Web search configuration — admin-tunable.

[#A6-1, 2026-05-08] User asked for three knobs:
  (a) per-role permission — currently hardcoded admin-only in
      pipeline.py:287. Admins want to extend to manager/employee on
      a case-by-case basis.
  (b) admin warning when TAVILY_API_KEY is missing — toast at admin
      load time, not silent log.
  (d) low_relevance threshold (0.30 default) — admins want to tune
      based on their corpus density. Sparse internal data → lower
      threshold (more web fallback). Rich corpus → higher threshold
      (avoid unnecessary web calls).

Storage: JSON at <BASE_DIR>/web_search_config.json. Read on every
query (file is < 1KB, cost is negligible). Defaults applied when
file is missing or fields absent — first-run servers behave
identically to the pre-#A6-1 hardcoded values.

This module is the single source of truth — pipeline.py reads via
is_role_allowed / get_threshold, and the /admin/web-search-config/
endpoint reads/writes via load / save.

Why a separate file (not core/memory): the latter is a SQLite layer
designed for chat history and persona, not configuration. Keeping
this as a JSON file makes operator inspection easy (just `cat the
file`) and avoids a SQLite migration just to store two fields.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Tuple

try:
    from config import BASE_DIR
except ImportError:
    BASE_DIR = "."

_CONFIG_PATH = os.path.join(BASE_DIR, "web_search_config.json")

_DEFAULTS: Dict = {
    "allowed_roles": ["admin"],
    "threshold":     0.30,
}

# Roles we recognise. Used to validate admin updates so a typo
# doesn't quietly disable the gate. Keep in sync with the rest of
# the auth surface (core.auth) — currently 4 distinct roles.
VALID_ROLES = {"admin", "manager", "employee", "external"}


def load() -> Dict:
    """Read settings from disk, layered over defaults.

    A missing or unreadable file returns the defaults — never raises,
    so a corrupt config doesn't take down /query/. Operators see the
    server fall back to admin-only + 0.30 threshold and can fix the
    file when convenient.
    """
    if not os.path.exists(_CONFIG_PATH):
        return dict(_DEFAULTS)
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return dict(_DEFAULTS)
    out = dict(_DEFAULTS)
    if isinstance(data, dict):
        if isinstance(data.get("allowed_roles"), list):
            out["allowed_roles"] = [r for r in data["allowed_roles"] if r in VALID_ROLES]
            if not out["allowed_roles"]:
                # All roles got filtered out — defensive: don't leave
                # the system with an empty allowlist (no one could
                # use web search). Restore default.
                out["allowed_roles"] = list(_DEFAULTS["allowed_roles"])
        if isinstance(data.get("threshold"), (int, float)):
            t = float(data["threshold"])
            if 0.0 <= t <= 1.0:
                out["threshold"] = t
    return out


def save(allowed_roles: List[str], threshold: float) -> Dict:
    """Persist settings. Caller is responsible for input validation
    (the /admin/ endpoint does it before calling here).

    Returns the new config dict for the caller to echo back to the
    UI without needing a follow-up GET.
    """
    cfg = {
        "allowed_roles": list(allowed_roles),
        "threshold":     float(threshold),
    }
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    return cfg


def is_role_allowed(role: str) -> bool:
    """Used by pipeline.py — does this role get to trigger a web
    search when retrieval is sparse?"""
    return role in load().get("allowed_roles", [])


def get_threshold() -> float:
    """unified_score below which web search is considered."""
    return float(load().get("threshold", _DEFAULTS["threshold"]))


def validate_update(allowed_roles: List, threshold) -> Tuple[List[str], float, str]:
    """Admin endpoint pre-flight. Returns (clean_roles, clean_threshold,
    error). When error is non-empty, caller raises HTTPException(400).

    Empty allowed_roles list is rejected — silently disabling web
    search is rarely the operator's intent and is harder to debug
    later. If they really want to disable it, they can clear
    TAVILY_API_KEY and uninstall ddg packages instead.
    """
    if not isinstance(allowed_roles, list):
        return [], 0.0, "allowed_roles must be a list"
    bad = [r for r in allowed_roles if r not in VALID_ROLES]
    if bad:
        return [], 0.0, f"unknown role(s): {bad}; valid: {sorted(VALID_ROLES)}"
    if not allowed_roles:
        return [], 0.0, "allowed_roles cannot be empty (set TAVILY_API_KEY='' to disable)"
    try:
        t = float(threshold)
    except (TypeError, ValueError):
        return [], 0.0, "threshold must be a number"
    if not (0.0 <= t <= 1.0):
        return [], 0.0, f"threshold must be in [0.0, 1.0], got {t}"
    return list(allowed_roles), t, ""
