"""v0.5 G2.b — CR merge (apply) function with approval-evidence gate.

Per `docs/reviews/v0.5-b2-multi-tenant-isolation.md` §4.3. Lives in
its own module because `core/change_request.py` is already at the
20 KB cap (CLAUDE.md rule #5); adding merge_cr to the same file
would push it over.

Import convention:

  >>> from core.change_request_merge import merge_cr
  >>> merge_cr(cr_id, reviewer="alex", db_path=path)

The function uses the same `change_requests` table that
`core/change_request.py` owns — there is one SQLite source of
truth. This module is a pure consumer: it READs the row state,
applies the gate logic, mutates one row, and emits one audit
event via the existing `_audit_event` helper in
`core/change_request.py`.

## What this function ships (G2.b contract)

  * **Reviewer required + non-self-approve invariant** — reviewer
    must differ from the proposer.
  * **Optional principal evidence** — caller may pass
    ``approval_evidence`` (an
    :class:`core.security.approval_evidence.ApprovalEvidence`).
    When provided, evidence.principal must match reviewer.
  * **Enforcement env** — when
    :func:`core.security.approval_evidence.require_approval_evidence`
    returns True AND ``approval_evidence`` is None, the function
    raises ``ValueError``. Default (env unset) preserves
    byte-identical pre-G2.b behaviour.
  * **Audit row fingerprint** — when evidence is present, the
    audit row carries the principal + source + evidence_hash +
    captured_at (the fingerprint, NOT the raw evidence blob).

## What this module is NOT

- **Not a state-machine extension** — the same `open → merged`
  transition that `change_request.py` schema already declares
  (CHECK constraints + STATUS_MERGED constant). This function
  just adds the principal-binding wire-in.
- **Not an HTTP route** — the CR.d UI's approve button (UI shell
  is PR #867) will call this function in a future PR when the
  HTTP layer lands.
- **Not vertical-pack-aware** — the gate applies the same way
  regardless of CR target_type. Vertical-specific approver rules
  would live in a separate v1.0 module per CLAUDE.md rule #1.
"""
from __future__ import annotations

import sqlite3
import time
from typing import Optional

from core.change_request import (
    STATUS_OPEN,
    ChangeRequest,
    _DEFAULT_DB,
    _audit_event,
    get_cr,
)


def merge_cr(
    cr_id:              str,
    *,
    reviewer:           str,
    approval_evidence:  Optional["object"] = None,
    role:               str = "unknown",
    db_path:            Optional[str] = None,
) -> ChangeRequest:
    """Transition ``open → merged`` (the apply path) with optional
    G2.b approval-evidence gating.

    Args:
        cr_id: CR identifier to merge.
        reviewer: free-form reviewer username (the "who" string).
            MUST differ from the CR's proposer (no self-approval).
        approval_evidence: optional
            :class:`core.security.approval_evidence.ApprovalEvidence`
            dataclass. When provided, its ``principal`` field must
            match ``reviewer``. When
            :func:`core.security.approval_evidence.require_approval_evidence`
            is True AND this is None, the function raises
            ``ValueError`` (SaaS-pilot gate; default is unset →
            no evidence required, byte-identical to pre-G2.b).
        role: caller role for the audit row. Defaults to
            ``"unknown"``.
        db_path: optional override of the change-requests DB path.

    Returns:
        The merged :class:`ChangeRequest` row (status flipped to
        ``"merged"``, ``merged_at`` + ``merged_by`` populated).

    Raises:
        ValueError: missing reviewer; CR not found; CR status not
            ``"open"``; reviewer == proposer; enforce-mode env set
            without evidence; evidence-principal != reviewer.
    """
    if not reviewer:
        raise ValueError("reviewer required")

    # G2.b — enforce-mode + evidence-principal-match check (BEFORE
    # the DB transition so a rejection leaves the CR's status
    # untouched).
    from core.security.approval_evidence import require_approval_evidence
    if require_approval_evidence() and approval_evidence is None:
        raise ValueError(
            "approval_evidence required when "
            "JAMES_REQUIRE_APPROVAL_EVIDENCE is set"
        )
    if approval_evidence is not None:
        principal = getattr(approval_evidence, "principal", None)
        if principal != reviewer:
            raise ValueError(
                f"approval_evidence.principal={principal!r} does "
                f"not match reviewer={reviewer!r}"
            )

    path = db_path or _DEFAULT_DB
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT status, proposer FROM change_requests WHERE cr_id = ?",
            (cr_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"cr not found: {cr_id}")
        if row["status"] != STATUS_OPEN:
            raise ValueError(
                f"cannot merge cr_id={cr_id} from status="
                f"{row['status']!r}"
            )
        if row["proposer"] == reviewer:
            raise ValueError("reviewer must differ from proposer")

        now = int(time.time())
        conn.execute(
            "UPDATE change_requests SET status='merged', "
            "merged_at = ?, merged_by = ?, updated_at = ? "
            "WHERE cr_id = ?",
            (now, reviewer, now, cr_id),
        )
        conn.commit()
    finally:
        conn.close()

    # Audit event — carry evidence fingerprint when present.
    audit_fields = {"reviewer": reviewer, "role": role}
    if approval_evidence is not None:
        audit_fields["evidence_principal"] = getattr(
            approval_evidence, "principal", "",
        )
        audit_fields["evidence_source"] = getattr(
            approval_evidence, "source", "",
        )
        audit_fields["evidence_hash"] = getattr(
            approval_evidence, "evidence_hash", "",
        )
        audit_fields["evidence_captured_at"] = getattr(
            approval_evidence, "captured_at", "",
        )
    _audit_event("merge", cr_id, **audit_fields)

    cr = get_cr(cr_id, db_path=db_path)
    assert cr is not None
    return cr


__all__ = ("merge_cr",)
