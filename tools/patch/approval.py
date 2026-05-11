"""Patch approval recording — #48 phase 1 (Axis 5 Controlled Evolution).

A patch's lifecycle is:

    feedback → candidate → 4-gate eval → AWAITING_APPROVAL
        (human approver hits /admin/patch/approve)
        → record_approval() — this module
        → patch_applier.apply()
        → audit log (approver_username, before/after, outcome)

This module is the chokepoint for "who approved this patch and how".
The platform-readiness contract (Dimension E) says deploy without an
approver field is a bug. By concentrating the metadata write here,
the contract becomes enforceable: removing this module breaks the
approval endpoint, and tests assert the metadata is present.

Storage:
  - The patch JSON at `./workspace/patches/<patch_id>.json` is updated
    in place with the approval fields.
  - A lifecycle event is appended to `james_patch_log.jsonl` so the
    /admin/audit feed picks it up alongside other patch events.

Approval methods (per #48):
  - "ui"   — admin clicked through the web UI
  - "api"  — admin called the endpoint directly with an api_key /
             JWT (the most common path today, since UI integration is
             a follow-up frontend task)
  - "auto" — only allowed when both `JAMES_DEV_MODE=1` and
             `JAMES_AUTO_APPROVE=1`. Used by tests. The config-time
             safety check (config.py) refuses to start the server if
             AUTO_APPROVE is set without DEV_MODE — see #48 spec.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

PATCH_STORE    = "./workspace/patches"
PATCH_LOG_PATH = "james_patch_log.jsonl"

# The set is intentionally small — adding "auto-by-ai-reviewer" or
# similar would require a new issue per the #48 out-of-scope list.
ALLOWED_METHODS = ("ui", "api", "auto")


def _log_lifecycle(event: str, patch_id: str, **fields) -> None:
    """Append one JSONL line to `james_patch_log.jsonl` capturing a
    patch lifecycle event (created / approved / rejected / deployed /
    rolled_back). The /admin/audit feed reads this file."""
    entry = {
        "time":     datetime.now().isoformat(),
        "event":    event,
        "patch_id": patch_id,
        "layer":    "patch_approval",
        **fields,
    }
    try:
        with open(PATCH_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # Approval recording must not crash on log-file failure;
        # the patch JSON itself still carries the truth-of-record
        # data, and operators see the gap on the next audit query.
        pass


def record_approval(
    patch_id:          str,
    approver_username: str,
    approver_role:     str,
    approval_method:   str = "api",
) -> Tuple[bool, dict]:
    """Augment a stored patch with approval metadata + emit a
    lifecycle log event.

    Args:
      patch_id:           the id from `tools.patch.patch_generator`.
      approver_username:  identity of the approver (audit trail).
      approver_role:      role at approval time ("admin" expected).
      approval_method:    "ui" | "api" | "auto" — see module docstring.

    Returns:
      (success, augmented_patch_dict). On success the patch JSON file
      on disk is updated in place. On failure (patch missing / bad
      method / write error) returns (False, {"error": "..."}). The
      caller MUST treat False as a hard refusal — do not call
      patch_applier.apply().
    """
    if approval_method not in ALLOWED_METHODS:
        return False, {"error": f"invalid approval_method: {approval_method!r}"}
    if not approver_username:
        return False, {"error": "approver_username required"}

    pf = Path(PATCH_STORE) / f"{patch_id}.json"
    if not pf.exists():
        return False, {"error": f"patch not found: {patch_id}"}
    try:
        patch = json.loads(pf.read_text(encoding="utf-8"))
    except Exception as e:
        return False, {"error": f"patch read failed: {e}"}

    now = datetime.now().isoformat()
    patch["approver_username"] = approver_username
    patch["approver_role"]     = approver_role
    patch["approved_at"]       = now
    patch["approval_method"]   = approval_method
    patch["status"]            = "APPROVED"

    try:
        pf.write_text(json.dumps(patch, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    except Exception as e:
        return False, {"error": f"patch write failed: {e}"}

    _log_lifecycle(
        "APPROVED", patch_id,
        approver_username=approver_username,
        approver_role=approver_role,
        approval_method=approval_method,
        approved_at=now,
        target=patch.get("target", ""),
    )
    return True, patch


def record_outcome(
    patch_id:    str,
    outcome:     str,                 # "deployed" | "rolled_back" | "rejected" | "expired"
    detail:      str = "",
    before_metrics: Optional[dict] = None,
    after_metrics:  Optional[dict] = None,
) -> None:
    """Append a deploy/rollback outcome to the lifecycle log.

    Called by the approval endpoint after `patch_applier.apply()` so
    operators can correlate `(approver_username, outcome)` for any
    deployed patch.
    """
    _log_lifecycle(
        outcome.upper(),
        patch_id,
        outcome=outcome,
        detail=detail[:300],
        before_metrics=before_metrics or {},
        after_metrics=after_metrics or {},
    )
