"""Change Request primitive (v0.2.x cycle).

Generalises the ``approver_username`` pattern that v0.1 hard-coded
for self-evolution. Every write inside JAMES — wiki edits, workspace
job runs, ontology patches, config saves — becomes a *proposal* in
this module first; only a separate reviewer's approval, recorded
with an apply dispatcher (CR-B2), turns the proposal into a real
write. Every state transition writes one row to the audit-log via
``core.audit_bridge``, so the ``change_requests`` table can be
reconstructed from audit alone if it's ever lost.

Scope (PR-CR-B1 — this module): CR state machine + SQLite table
init + CRUD + reject + supersede + review attach. **No apply path,
no merge, no endpoint glue.** The apply dispatcher and the six
``/admin/cr/...`` endpoints land in PR-CR-B2.

Read the full track at:
    docs/handovers/v0.2.x-cr-track.md
    docs/ARCHITECTURE.md §5.6
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

try:
    from config import BASE_DIR as _BASE_DIR
    _DEFAULT_DB = os.path.join(_BASE_DIR, "james_change_requests.db")
except ImportError:
    _DEFAULT_DB = "james_change_requests.db"


# ─── State constants ────────────────────────────────────────────
STATUS_OPEN       = "open"
STATUS_MERGED     = "merged"
STATUS_REJECTED   = "rejected"
STATUS_SUPERSEDED = "superseded"
VALID_STATUSES = frozenset({
    STATUS_OPEN, STATUS_MERGED, STATUS_REJECTED, STATUS_SUPERSEDED,
})
# Open is the only non-terminal status.
TERMINAL_STATUSES = frozenset({
    STATUS_MERGED, STATUS_REJECTED, STATUS_SUPERSEDED,
})

# Closed enum — see ARCHITECTURE.md §5.6 for why this is not a
# plugin extension point until v0.3.
TARGET_WIKI_ENTITY       = "wiki_entity"
TARGET_RUN_JOBS          = "run_jobs"
# Stage B / CR-E (audit 2026-05-23 §2) — self-evolution approval
# events get a *shadow* CR row so the unified audit shape becomes
# part of the platform contract. The legacy JSONL writers
# (``james_patch_log.jsonl`` / ``james_evo_log.jsonl``) stay
# authoritative; the CR row is additive and the apply handler is a
# no-op (the actual patch / proposal write happens in the legacy
# path, with its own bench gate + rollback chain). See
# ``docs/handovers/v0.3.x-audit-2026-05-23.md`` §9 Stage B + the four
# locked JSONL-shape tests (test_self_evolution_gate /
# test_evolution_bench_gate / test_evolution_rollback /
# test_evolution_audit_query).
TARGET_SELF_EVO_PATCH    = "self_evo_patch"
TARGET_SELF_EVO_PROPOSAL = "self_evo_proposal"
VALID_TARGET_TYPES = frozenset({
    TARGET_WIKI_ENTITY,
    TARGET_RUN_JOBS,
    TARGET_SELF_EVO_PATCH,
    TARGET_SELF_EVO_PROPOSAL,
})

REVIEW_APPROVE         = "approve"
REVIEW_REQUEST_CHANGES = "request_changes"
REVIEW_COMMENT         = "comment"
VALID_REVIEW_DECISIONS = frozenset({
    REVIEW_APPROVE, REVIEW_REQUEST_CHANGES, REVIEW_COMMENT,
})


# ─── Frozen DTOs ─────────────────────────────────────────────────
@dataclass(frozen=True)
class ChangeRequest:
    cr_id:         str
    target_type:   str
    target_id:     str
    title:         str
    description:   str
    proposed_diff: str          # JSON string; structure is target_type-specific
    base_hash:     str
    proposer:      str
    status:        str
    labels:        str          # CSV — flat, not hierarchical until v0.3
    created_at:    int
    updated_at:    int
    merged_at:     Optional[int] = None
    merged_by:     Optional[str] = None
    reject_reason: Optional[str] = None


@dataclass(frozen=True)
class CrReview:
    review_id:  str
    cr_id:      str
    reviewer:   str
    decision:   str
    body:       str
    created_at: int


# ─── Schema bootstrap (idempotent, runs at module import) ────────
_DDL = """
CREATE TABLE IF NOT EXISTS change_requests (
  cr_id          TEXT PRIMARY KEY,
  target_type    TEXT NOT NULL,
  target_id      TEXT NOT NULL,
  title          TEXT NOT NULL,
  description    TEXT,
  proposed_diff  TEXT NOT NULL,
  base_hash      TEXT NOT NULL,
  proposer       TEXT NOT NULL,
  status         TEXT NOT NULL,
  labels         TEXT,
  created_at     INTEGER NOT NULL,
  updated_at     INTEGER NOT NULL,
  merged_at      INTEGER,
  merged_by      TEXT,
  reject_reason  TEXT,
  CHECK (status IN ('open','merged','rejected','superseded')),
  CHECK ((status='merged') = (merged_at IS NOT NULL AND merged_by IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_cr_status_target
  ON change_requests(status, target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_cr_proposer
  ON change_requests(proposer, status);

CREATE TABLE IF NOT EXISTS cr_reviews (
  review_id   TEXT PRIMARY KEY,
  cr_id       TEXT NOT NULL REFERENCES change_requests(cr_id) ON DELETE CASCADE,
  reviewer    TEXT NOT NULL,
  decision    TEXT NOT NULL,
  body        TEXT,
  created_at  INTEGER NOT NULL,
  CHECK (decision IN ('approve','request_changes','comment'))
);
CREATE INDEX IF NOT EXISTS idx_cr_reviews_cr
  ON cr_reviews(cr_id, created_at);
"""


def init_db(db_path: Optional[str] = None) -> None:
    """Idempotent table + index creation. Public so tests can hit
    a temp DB path."""
    path = db_path or _DEFAULT_DB
    conn = sqlite3.connect(path, check_same_thread=False)
    try:
        # Foreign-key enforcement is per-connection, but the CASCADE
        # constraint only kicks in when callers enable it. The CHECK
        # constraints fire unconditionally.
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_DDL)
        conn.commit()
    finally:
        conn.close()


# Run once on import so the tables exist before any caller writes —
# same pattern as core.audit_bridge / core.api_keys.
init_db()


# ─── Helpers ─────────────────────────────────────────────────────
def _gen_id(prefix: str) -> str:
    """ULID-like sortable id: ``<prefix>_<epoch_ms_hex>_<10char-random>``.

    Lexicographic order matches creation order, which keeps default
    ``ORDER BY cr_id`` listings monotonic without needing a separate
    sort key. 10 hex chars (~40 bits) of randomness make collisions
    within the same millisecond statistically negligible.
    """
    ts_ms = int(time.time() * 1000)
    rand  = secrets.token_hex(5)
    return f"{prefix}_{ts_ms:013x}_{rand}"


def cr_id_for_now() -> str:
    return _gen_id("cr")


def review_id_for_now() -> str:
    return _gen_id("rv")


def compute_base_hash(content: bytes) -> str:
    """SHA-256 hex of the target state at propose time. Used by the
    apply dispatcher (CR-B2) for conflict detection — if the target
    has shifted between propose and merge, the CR is superseded.

    Bytes-typed input forces callers to be explicit about encoding;
    a stray ``str``-vs-``bytes`` mix would change the hash and break
    conflict detection silently."""
    if not isinstance(content, (bytes, bytearray)):
        raise TypeError("compute_base_hash expects bytes")
    return hashlib.sha256(content).hexdigest()


def _audit_event(event_type: str, cr_id: str, **fields) -> None:
    """Mirror a CR state transition to the audit log. Endpoint prefix
    is ``cr:<event_type>`` so ``/admin/audit/list`` can filter all CR
    events with one LIKE pattern.

    Swallows exceptions on the audit side — audit mirroring must
    never block a state transition (matches audit_bridge's policy).
    """
    try:
        from core.audit_bridge import mirror_to_audit_db
        mirror_to_audit_db({
            "time":      datetime.now().isoformat(),
            "role":      fields.get("role", "unknown"),
            "endpoint":  f"cr:{event_type}",
            "event":     f"cr.{event_type}",
            "tool_used": "change_request",
            "target":    cr_id,
            **fields,
        })
    except Exception:
        # Audit is best-effort; the CR transition itself already
        # committed under its own SQLite transaction.
        pass


def _row_to_cr(row: sqlite3.Row) -> ChangeRequest:
    return ChangeRequest(
        cr_id=row["cr_id"],
        target_type=row["target_type"],
        target_id=row["target_id"],
        title=row["title"],
        description=row["description"] or "",
        proposed_diff=row["proposed_diff"],
        base_hash=row["base_hash"],
        proposer=row["proposer"],
        status=row["status"],
        labels=row["labels"] or "",
        created_at=int(row["created_at"]),
        updated_at=int(row["updated_at"]),
        merged_at=int(row["merged_at"]) if row["merged_at"] is not None else None,
        merged_by=row["merged_by"],
        reject_reason=row["reject_reason"],
    )


def _row_to_review(row: sqlite3.Row) -> CrReview:
    return CrReview(
        review_id=row["review_id"],
        cr_id=row["cr_id"],
        reviewer=row["reviewer"],
        decision=row["decision"],
        body=row["body"] or "",
        created_at=int(row["created_at"]),
    )


# ─── Public API — propose ────────────────────────────────────────
def create_cr(
    *,
    target_type:   str,
    target_id:     str,
    title:         str,
    description:   str           = "",
    proposed_diff,                                  # dict or JSON string
    base_hash:     str,
    proposer:      str,
    labels:        Iterable[str] = (),
    role:          str           = "unknown",
    db_path:       Optional[str] = None,
) -> ChangeRequest:
    """Insert a CR in ``status='open'``.

    Raises ``ValueError`` on invariant violations (unknown
    target_type, empty proposer/title/target_id/base_hash, malformed
    proposed_diff). The error is surfaced — silent fallthrough at
    propose time would let typos authorise nothing.
    """
    if target_type not in VALID_TARGET_TYPES:
        raise ValueError(f"unknown target_type: {target_type!r}")
    if not proposer:
        raise ValueError("proposer required")
    if not title or not title.strip():
        raise ValueError("title required")
    if not target_id:
        raise ValueError("target_id required")
    if not base_hash:
        raise ValueError("base_hash required")

    if isinstance(proposed_diff, dict):
        proposed_diff = json.dumps(proposed_diff, ensure_ascii=False)
    elif not isinstance(proposed_diff, str):
        raise ValueError("proposed_diff must be a dict or JSON string")

    now    = int(time.time())
    cr_id  = cr_id_for_now()
    labels_csv = ",".join(sorted({
        lab.strip() for lab in labels if lab and lab.strip()
    }))

    path = db_path or _DEFAULT_DB
    conn = sqlite3.connect(path, check_same_thread=False)
    try:
        conn.execute(
            "INSERT INTO change_requests "
            "(cr_id, target_type, target_id, title, description, "
            " proposed_diff, base_hash, proposer, status, labels, "
            " created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)",
            (cr_id, target_type, target_id, title, description,
             proposed_diff, base_hash, proposer, labels_csv, now, now),
        )
        conn.commit()
    finally:
        conn.close()

    _audit_event(
        "propose", cr_id,
        target_type=target_type, target_id=target_id,
        proposer=proposer, role=role,
    )
    cr = get_cr(cr_id, db_path=db_path)
    assert cr is not None, "freshly-inserted CR must be readable back"
    return cr


# ─── Public API — read ───────────────────────────────────────────
def get_cr(cr_id: str, *, db_path: Optional[str] = None) -> Optional[ChangeRequest]:
    path = db_path or _DEFAULT_DB
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM change_requests WHERE cr_id = ?", (cr_id,),
        ).fetchone()
        return _row_to_cr(row) if row else None
    finally:
        conn.close()


def list_crs(
    *,
    status:      Optional[str] = None,
    target_type: Optional[str] = None,
    proposer:    Optional[str] = None,
    limit:       int           = 50,
    offset:      int           = 0,
    db_path:     Optional[str] = None,
) -> List[ChangeRequest]:
    """List CRs newest first, with optional filters. ``limit`` is
    clamped to ``[1, 500]`` so a typo can't dump the whole table."""
    path = db_path or _DEFAULT_DB
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        where:  List[str] = []
        params: list      = []
        if status is not None:
            if status not in VALID_STATUSES:
                raise ValueError(f"unknown status filter: {status!r}")
            where.append("status = ?")
            params.append(status)
        if target_type is not None:
            if target_type not in VALID_TARGET_TYPES:
                raise ValueError(f"unknown target_type filter: {target_type!r}")
            where.append("target_type = ?")
            params.append(target_type)
        if proposer is not None:
            where.append("proposer = ?")
            params.append(proposer)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        params.append(min(max(int(limit), 1), 500))
        params.append(max(int(offset), 0))
        rows = conn.execute(
            f"SELECT * FROM change_requests {where_sql} "
            "ORDER BY created_at DESC, cr_id DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [_row_to_cr(r) for r in rows]
    finally:
        conn.close()


# ─── Public API — state transitions (no apply yet) ───────────────
def reject_cr(
    cr_id:    str,
    *,
    reviewer: str,
    reason:   str = "",
    role:     str = "unknown",
    db_path:  Optional[str] = None,
) -> ChangeRequest:
    """Transition ``open → rejected``. Reviewer MUST differ from
    proposer (CLAUDE.md rule #3 spirit — no self-approval / self-
    rejection)."""
    if not reviewer:
        raise ValueError("reviewer required")

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
                f"cannot reject cr_id={cr_id} from status={row['status']!r}"
            )
        if row["proposer"] == reviewer:
            raise ValueError("reviewer must differ from proposer")

        now = int(time.time())
        conn.execute(
            "UPDATE change_requests SET status='rejected', "
            "reject_reason = ?, updated_at = ? WHERE cr_id = ?",
            (reason, now, cr_id),
        )
        conn.commit()
    finally:
        conn.close()

    _audit_event("reject", cr_id, reviewer=reviewer, reason=reason, role=role)
    cr = get_cr(cr_id, db_path=db_path)
    assert cr is not None
    return cr


def supersede_cr(
    cr_id:   str,
    *,
    reason:  str = "base_hash mismatch",
    role:    str = "unknown",
    db_path: Optional[str] = None,
) -> ChangeRequest:
    """Transition ``open → superseded``. Called by the apply
    dispatcher (CR-B2) when the target has shifted between propose
    and merge — the proposer must re-propose against current state.

    Exposed at the module level so the state machine is testable
    without the apply dispatcher's wiki-specific code."""
    path = db_path or _DEFAULT_DB
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT status FROM change_requests WHERE cr_id = ?", (cr_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"cr not found: {cr_id}")
        if row["status"] != STATUS_OPEN:
            raise ValueError(
                f"cannot supersede cr_id={cr_id} from status={row['status']!r}"
            )

        now = int(time.time())
        conn.execute(
            "UPDATE change_requests SET status='superseded', "
            "reject_reason = ?, updated_at = ? WHERE cr_id = ?",
            (reason, now, cr_id),
        )
        conn.commit()
    finally:
        conn.close()

    _audit_event("supersede", cr_id, reason=reason, role=role)
    cr = get_cr(cr_id, db_path=db_path)
    assert cr is not None
    return cr


# ─── Public API — reviews (advisory; do NOT transition state) ────
def add_review(
    cr_id:    str,
    *,
    reviewer: str,
    decision: str,
    body:     str = "",
    role:     str = "unknown",
    db_path:  Optional[str] = None,
) -> CrReview:
    """Attach a review row. Comments / request_changes are advisory —
    they neither approve nor reject. The actual approve transition
    lives in the apply dispatcher (CR-B2); rejecting calls
    ``reject_cr`` directly. This separation keeps the state machine
    minimal: only an explicit ``reject_cr`` / future ``merge_cr``
    call moves a CR out of ``open``.
    """
    if decision not in VALID_REVIEW_DECISIONS:
        raise ValueError(f"unknown decision: {decision!r}")
    if not reviewer:
        raise ValueError("reviewer required")

    path = db_path or _DEFAULT_DB
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        existing = conn.execute(
            "SELECT proposer FROM change_requests WHERE cr_id = ?",
            (cr_id,),
        ).fetchone()
        if existing is None:
            raise ValueError(f"cr not found: {cr_id}")
        # Proposers may comment on their own CR but cannot
        # ``approve`` or ``request_changes`` it — that would be a
        # self-review, defeating the point of the two-person rule.
        if decision != REVIEW_COMMENT and existing["proposer"] == reviewer:
            raise ValueError(
                "reviewer must differ from proposer for non-comment reviews",
            )

        now       = int(time.time())
        review_id = review_id_for_now()
        conn.execute(
            "INSERT INTO cr_reviews "
            "(review_id, cr_id, reviewer, decision, body, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (review_id, cr_id, reviewer, decision, body, now),
        )
        conn.commit()
    finally:
        conn.close()

    _audit_event(
        "review", cr_id,
        reviewer=reviewer, decision=decision, role=role,
    )
    return CrReview(
        review_id=review_id, cr_id=cr_id, reviewer=reviewer,
        decision=decision, body=body, created_at=now,
    )


def list_reviews(
    cr_id:   str,
    *,
    db_path: Optional[str] = None,
) -> List[CrReview]:
    path = db_path or _DEFAULT_DB
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM cr_reviews WHERE cr_id = ? "
            "ORDER BY created_at ASC, review_id ASC",
            (cr_id,),
        ).fetchall()
        return [_row_to_review(r) for r in rows]
    finally:
        conn.close()
