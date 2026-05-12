"""Change Request — apply dispatcher + merge orchestrator (PR-CR-B2).

The state machine in ``core.change_request`` knows how to move a CR
through ``open → rejected | superseded`` without ever touching the
underlying target. The actual write — turning a CR into the change
it proposes — lives here. Keeping these separate has two effects:

  1. ``core.change_request`` stays under the 20 KB module-size gate
     (CLAUDE.md rule #5) as more target types come online.
  2. Adding a new ``target_type`` is a one-line dispatch-table entry
     plus one apply function — no edits to the state machine.

``merge_cr`` is the single entry point callers reach for. It:

  - locks the CR row (status MUST be ``'open'``),
  - enforces invariant #2 (``approver ≠ proposer``),
  - calls the target-specific ``apply_*`` (which detects ``base_hash``
    drift and surfaces it as a supersede signal),
  - on a successful apply, transitions the CR to ``'merged'`` and
    mirrors one audit row.

Ordering note. apply runs BEFORE the CR row is marked merged, so
that an apply failure leaves ``status='open'`` (invariant #5). If
the file write succeeds but the row update fails (rare — same DB,
same process), the audit row that records the merge intent is what
operators see; manual repair is preferable to silently un-doing a
file change.

Read the cycle plan in:
    docs/handovers/v0.2.x-cr-track.md
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

import core.change_request as _cr_mod
from core.change_request import (
    STATUS_OPEN,
    TARGET_WIKI_ENTITY, TARGET_RUN_JOBS,
    ChangeRequest,
    compute_base_hash, get_cr, supersede_cr,
)
# ``_DEFAULT_DB`` and ``_audit_event`` are accessed via the module
# alias (_cr_mod.X) rather than imported by value, so a test that
# swaps ``_cr_mod._DEFAULT_DB`` to a temp path also takes effect
# here — ``from … import _DEFAULT_DB`` would bind a frozen copy.

try:
    from config import BASE_DIR as _BASE_DIR
except ImportError:
    _BASE_DIR = os.getcwd()

# The wiki root is fixed by repo layout; resolving relative target_ids
# against it (and refusing anything outside) is the path-traversal guard.
_WIKI_ROOT = os.path.realpath(os.path.join(_BASE_DIR, "wiki"))


# ─── Apply result ────────────────────────────────────────────────
@dataclass(frozen=True)
class ApplyResult:
    """What an ``apply_*`` returned.

    ``applied=True`` ⇒ target write committed; the orchestrator
    should then mark the CR ``'merged'``.

    ``superseded=True`` ⇒ ``base_hash`` no longer matches the
    target's current state; the orchestrator MUST mark the CR
    ``'superseded'`` and tell the proposer to re-propose.

    A raised exception means an unexpected error — the orchestrator
    leaves ``status='open'`` (invariant #5) and surfaces the error
    to the caller.
    """
    applied:    bool
    superseded: bool          = False
    new_hash:   Optional[str] = None
    reason:     str           = ""


# ─── Target-specific apply: wiki_entity ─────────────────────────
def _resolve_wiki_path(target_id: str) -> str:
    """Map a CR's ``target_id`` to an on-disk wiki file.

    For ``target_type='wiki_entity'`` the contract is:
    ``target_id`` is a path RELATIVE to ``wiki/`` that:
      - starts with ``entity/`` (the wiki tree's entity subtree),
      - ends with ``.md``,
      - contains no ``..`` traversal,
      - resolves (after realpath) to a path under ``wiki/entity/``.

    Anything else is a 400-class bug — surface immediately.
    """
    if not target_id or not isinstance(target_id, str):
        raise ValueError("target_id required for wiki_entity")
    if ".." in target_id.replace("\\", "/").split("/"):
        raise ValueError("target_id may not contain '..'")
    if not target_id.endswith(".md"):
        raise ValueError("target_id must end with .md")
    # Use a normalised forward-slash form for the prefix check so
    # callers can pass either OS-flavoured separator.
    norm = target_id.replace("\\", "/")
    if not norm.startswith("entity/"):
        raise ValueError("target_id must start with entity/")

    abs_path = os.path.realpath(os.path.join(_WIKI_ROOT, norm))
    entity_root = os.path.realpath(os.path.join(_WIKI_ROOT, "entity"))
    # Containment check — realpath defeats symlink + .. escape.
    if not (abs_path == entity_root or
            abs_path.startswith(entity_root + os.sep)):
        raise ValueError("target_id resolved outside wiki/entity/")
    return abs_path


def _apply_wiki_entity(cr: ChangeRequest) -> ApplyResult:
    """Apply a ``wiki_entity`` CR to its target file.

    Steps:
      1. Resolve target path under ``wiki/entity/`` (path-traversal
         guard; raises ValueError on a malformed target_id).
      2. Read current file bytes and compute its sha256.
      3. Compare to ``cr.base_hash``. Mismatch ⇒ supersede signal,
         no write happens.
      4. Decode ``cr.proposed_diff`` JSON. For v0.2.x only
         ``{"op": "replace", "body": "..."}`` is supported — the op
         field is checked so future ops surface as 400 instead of
         silently doing the wrong thing.
      5. Atomic write via tempfile + ``os.replace`` so a half-written
         file is impossible. Tempfile lives next to the target so
         the rename stays on the same filesystem.

    Raises ``FileNotFoundError`` if the target file is missing
    (the orchestrator will surface this as a 4xx; the CR stays open
    so the proposer can fix it).
    """
    abs_path = _resolve_wiki_path(cr.target_id)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"target file missing: {cr.target_id}")

    with open(abs_path, "rb") as f:
        current = f.read()
    current_hash = compute_base_hash(current)
    if current_hash != cr.base_hash:
        return ApplyResult(
            applied=False, superseded=True,
            reason=("target has changed since this proposal was "
                    "filed — please rebase against current state"),
        )

    # Decode + validate the diff.
    try:
        diff = json.loads(cr.proposed_diff)
    except json.JSONDecodeError as exc:
        raise ValueError(f"proposed_diff is not valid JSON: {exc}") from exc
    if not isinstance(diff, dict):
        raise ValueError("proposed_diff must decode to a JSON object")
    op = diff.get("op")
    if op != "replace":
        # Closed enum on op too — the v0.3 plugin contract surface.
        raise ValueError(f"unsupported wiki_entity op: {op!r}")
    body = diff.get("body")
    if not isinstance(body, str):
        raise ValueError("wiki_entity replace op requires body: str")

    new_bytes = body.encode("utf-8")

    # Atomic write — tempfile in the target directory so os.replace
    # is a same-fs rename (POSIX + NTFS both atomic).
    target_dir = os.path.dirname(abs_path) or "."
    fd, tmp_path = tempfile.mkstemp(
        prefix=".cr_apply_", suffix=".md.tmp", dir=target_dir,
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(new_bytes)
        os.replace(tmp_path, abs_path)
    except Exception:
        # Clean up the tmp on any failure before re-raising; we
        # never want to leave .cr_apply_*.tmp orphans on disk.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return ApplyResult(
        applied=True, new_hash=compute_base_hash(new_bytes),
    )


# ─── Target-specific apply: run_jobs (PR-CR-D) ──────────────────
def _apply_run_jobs(cr: ChangeRequest) -> ApplyResult:
    """Apply a ``run_jobs`` CR by registering and executing a
    workspace job under the proposer's name.

    Diff shape (closed for v0.2.x — same plugin-contract reasoning
    as the wiki op enum):

        {"op":         "run",
         "job_type":   "excel_build" | "doc_combine" | "entity_export",
         "input_refs": [ "...", ... ],
         "options":    {...}                   # optional
        }

    Unlike ``wiki_entity``, ``run_jobs`` is a *trigger* — the CR's
    ``base_hash`` is informational only (no current "state" of the
    target to compare against). The proposer typically computes it
    as ``sha256(json.dumps({job_type, input_refs}, sort_keys=True))``
    so duplicate proposals can be spotted by id; the apply does
    not enforce a comparison.

    Returns ``ApplyResult(applied=True, new_hash=job_id)`` — the
    job_id is the merge artifact a reviewer can trace via the
    workspace Jobs tab.
    """
    # Decode + validate the diff.
    try:
        diff = json.loads(cr.proposed_diff)
    except json.JSONDecodeError as exc:
        raise ValueError(f"proposed_diff is not valid JSON: {exc}") from exc
    if not isinstance(diff, dict):
        raise ValueError("proposed_diff must decode to a JSON object")
    if diff.get("op") != "run":
        raise ValueError(f"unsupported run_jobs op: {diff.get('op')!r}")

    job_type = diff.get("job_type")
    if not isinstance(job_type, str) or not job_type:
        raise ValueError("run_jobs requires a non-empty job_type string")

    input_refs = diff.get("input_refs")
    if not isinstance(input_refs, list):
        raise ValueError("run_jobs requires input_refs as a list")
    if not all(isinstance(r, str) for r in input_refs):
        raise ValueError("run_jobs input_refs must be a list of strings")

    options = diff.get("options")
    if options is not None and not isinstance(options, dict):
        raise ValueError("run_jobs options must be a JSON object or null")

    # Import lazily so the CR module stays importable on installs
    # without the workspace job tables (e.g., test fixtures).
    from core import workspace as _ws

    # HANDLERS is the canonical allowlist of job_types — same enum
    # the /jobs/run endpoint consults.
    if job_type not in _ws.HANDLERS:
        raise ValueError(
            f"unknown job_type: {job_type!r} "
            f"(known: {sorted(_ws.HANDLERS.keys())})"
        )

    # Register under the proposer's name — the job becomes visible
    # in their /jobs/list view (admin sees it in /admin/jobs/list).
    # The approver is recorded in the CR row + audit, NOT on the
    # job, to keep workspace.jobs schema unchanged.
    job_id = _ws.register_job(
        job_type=job_type,
        input_refs=input_refs,
        owner=cr.proposer,
        options=options,
    )
    try:
        _ws.execute_job(job_id)
    except Exception as exc:
        # The job row exists at this point (status='failed' or 'pending'
        # depending on where execute_job blew up). Surface to caller so
        # merge_cr raises and CR stays open — invariant #5.
        raise RuntimeError(
            f"run_jobs execution failed for job_id={job_id}: {exc}"
        ) from exc

    return ApplyResult(applied=True, new_hash=job_id)


# ─── Dispatcher ──────────────────────────────────────────────────
# Closed enum — ARCHITECTURE.md §5.6 explains why. Plugin-style
# external registration is the v0.3 contract surface, not now.
_APPLY_DISPATCH: Dict[str, Callable[[ChangeRequest], ApplyResult]] = {
    TARGET_WIKI_ENTITY: _apply_wiki_entity,
    TARGET_RUN_JOBS:    _apply_run_jobs,
}


def apply_cr(cr: ChangeRequest) -> ApplyResult:
    """Dispatch on ``cr.target_type``. Unknown types raise — the
    state machine already refuses to *propose* an unknown type at
    create_cr time, so reaching this branch means someone smuggled
    in a row; fail loud."""
    fn = _APPLY_DISPATCH.get(cr.target_type)
    if fn is None:
        raise ValueError(
            f"no apply handler for target_type={cr.target_type!r}"
        )
    return fn(cr)


# ─── Merge orchestrator ──────────────────────────────────────────
def merge_cr(
    cr_id:    str,
    *,
    approver: str,
    role:     str = "unknown",
    db_path:  Optional[str] = None,
) -> ChangeRequest:
    """Transition a CR from ``open → merged`` by applying its diff.

    Invariants enforced here:
      - CR must currently be ``status='open'`` (invariant #5).
      - ``approver != proposer`` (invariant #2; two-person rule).
      - ``base_hash`` mismatch routes to ``supersede_cr`` and the
        returned CR carries ``status='superseded'`` (invariant #3).
      - apply() raising leaves ``status='open'`` (invariant #5).
      - On success, exactly one ``cr:merge`` row lands in the
        audit log (invariant #7).

    Returns the final state of the CR. The caller does NOT need
    to refetch.
    """
    if not approver:
        raise ValueError("approver required")

    path = db_path or _cr_mod._DEFAULT_DB
    cr = get_cr(cr_id, db_path=path)
    if cr is None:
        raise ValueError(f"cr not found: {cr_id}")
    if cr.status != STATUS_OPEN:
        raise ValueError(
            f"cannot merge cr_id={cr_id} from status={cr.status!r}"
        )
    if cr.proposer == approver:
        raise ValueError("approver must differ from proposer")

    # Run apply BEFORE the row update so invariant #5 holds — an
    # apply failure must leave the CR in 'open'. ``apply_cr`` itself
    # decides whether the target has drifted (supersede) or written
    # successfully.
    result = apply_cr(cr)

    if result.superseded:
        return supersede_cr(
            cr_id, reason=result.reason or "base_hash mismatch",
            role=role, db_path=path,
        )

    if not result.applied:
        # apply chose neither merge nor supersede — treat as an
        # internal bug. The CR stays open.
        raise RuntimeError(
            "apply returned applied=False without supersede signal "
            f"(target_type={cr.target_type})"
        )

    # Apply succeeded → mark the CR merged. WHERE status='open' is
    # belt-and-suspenders against a concurrent merge attempt.
    now = int(time.time())
    conn = sqlite3.connect(path, check_same_thread=False)
    try:
        cursor = conn.execute(
            "UPDATE change_requests "
            "SET status='merged', merged_at = ?, merged_by = ?, "
            "    updated_at = ? "
            "WHERE cr_id = ? AND status = 'open'",
            (now, approver, now, cr_id),
        )
        conn.commit()
        if cursor.rowcount != 1:
            # A concurrent transition closed the CR between apply
            # and update. The target file was already mutated; this
            # is a real edge case worth audit-logging loudly.
            _cr_mod._audit_event(
                "merge_conflict", cr_id,
                approver=approver, role=role,
                detail="UPDATE matched 0 rows after apply succeeded",
            )
            raise RuntimeError(
                "merge UPDATE matched 0 rows — concurrent state "
                f"change on cr_id={cr_id}"
            )
    finally:
        conn.close()

    _cr_mod._audit_event(
        "merge", cr_id, approver=approver, role=role,
        new_hash=result.new_hash,
    )
    out = get_cr(cr_id, db_path=path)
    assert out is not None
    return out


# ─── Re-exports for ergonomic test imports ──────────────────────
__all__ = [
    "ApplyResult",
    "apply_cr",
    "merge_cr",
]
