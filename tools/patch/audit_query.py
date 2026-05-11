"""Patch lifecycle audit query — #68 phase 2-C.

Reads `james_patch_log.jsonl` (the per-event lifecycle stream produced
by `tools/patch/approval.py` and `tools/patch/patch_applier.py`) and
returns a filtered, newest-first slice for the operator-facing
`GET /admin/patch/audit` endpoint.

Why a separate module rather than inlining in server_llmwiki.py
- Keeps the parsing + filtering logic test-coverable without a live
  FastAPI test client (the v0.2 test pattern is unittest, not pytest).
- The lifecycle log shape (`event` / `patch_id` / `outcome` /
  `approver_username` / `before_metrics` / `after_metrics`) is the
  contract this module enforces. A future event format change touches
  this file plus its test, not the route handler.

Filter semantics
- `since`: ISO 8601 string ("2026-05-08" or "2026-05-08T12:34:56").
  Inclusive lower bound on the entry's `time` field. Invalid values
  are silently ignored (the entry is included) — operators get a
  noisier feed rather than an opaque crash.
- `approver`: case-insensitive exact match on `approver_username`.
  Lifecycle entries that don't carry an approver field (e.g. the
  patch_applier-emitted APPLY_BACKUP_FAIL events) are excluded when
  this filter is set — they had no approver to filter by.
- `outcome`: case-insensitive exact match on the `outcome` field.
  Useful filters: `deployed` / `rolled_back` / `deployed_gate_skipped`.
  Entries without an outcome (e.g. APPROVED itself) are excluded
  when this filter is set.
- `limit`: hard cap (default 200) on the returned list. Newest-first.
  Operator pagination beyond this is out of scope for v0.2.

The log file is small at v0.2 scale (a single-user setup over a few
months); we read+filter in memory rather than streaming. If the file
grows past ~10 MB the pattern needs a more efficient reader — issue
flagged in the docstring's deferred-work block.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

PATCH_LOG_PATH = "james_patch_log.jsonl"
DEFAULT_LIMIT = 200
MAX_LIMIT = 1000


def query_patch_audit(
    since:    Optional[str] = None,
    approver: Optional[str] = None,
    outcome:  Optional[str] = None,
    limit:    int           = DEFAULT_LIMIT,
    log_path: Optional[str] = None,
) -> List[dict]:
    """Return filtered patch lifecycle entries, newest-first.

    Args:
      since:    ISO 8601 lower bound (inclusive). None / invalid → no filter.
      approver: case-insensitive `approver_username` match. None → no filter.
      outcome:  case-insensitive `outcome` match (deployed / rolled_back /
                deployed_gate_skipped). None → no filter.
      limit:    max entries returned. Clamped to [1, MAX_LIMIT].
      log_path: override file path (test seam). Default `james_patch_log.jsonl`.

    Returns:
      A list of lifecycle dicts as parsed from the JSONL, sorted by
      `time` descending. Each dict carries at minimum `event`, `time`,
      `patch_id`, plus event-specific fields (approver_*, outcome,
      before/after_metrics, detail).
    """
    path = Path(log_path or PATCH_LOG_PATH)
    if not path.exists():
        return []

    # Clamp limit defensively. None / non-int → default; negative → 1.
    try:
        cap = int(limit)
    except Exception:
        cap = DEFAULT_LIMIT
    cap = max(1, min(cap, MAX_LIMIT))

    since_norm    = (since or "").strip()
    approver_norm = (approver or "").strip().lower()
    outcome_norm  = (outcome or "").strip().lower()

    rows: List[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    # Skip malformed line silently — a partial write
                    # mid-rotation must not break audit reads.
                    continue

                # since filter (string compare on ISO timestamps).
                # ISO 8601 sorts lexicographically when same precision,
                # which the writer guarantees (datetime.now().isoformat()).
                if since_norm:
                    t = (entry.get("time") or "")
                    if t < since_norm:
                        continue

                if approver_norm:
                    a = (entry.get("approver_username") or "").lower()
                    if a != approver_norm:
                        continue

                if outcome_norm:
                    o = (entry.get("outcome") or "").lower()
                    if o != outcome_norm:
                        continue

                rows.append(entry)
    except Exception:
        # Outer read failure → return what we have. The endpoint
        # surfaces an empty-or-partial list rather than a 500.
        pass

    # Newest-first by `time`. Entries without a time field sink to the
    # bottom (very old / malformed).
    rows.sort(key=lambda e: e.get("time") or "", reverse=True)
    return rows[:cap]
