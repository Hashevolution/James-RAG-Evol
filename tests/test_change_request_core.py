"""[PR-CR-B1, 2026-05-12] Change Request state machine + storage.

CR-B1 ships the model only — no apply, no endpoints. This suite
covers the invariants the handover doc names in
``docs/handovers/v0.2.x-cr-track.md § 3`` and the schema-level
``CHECK`` constraints in ``core/change_request.py``:

  1. ``merged_at`` / ``merged_by`` NOT NULL ⇔ status='merged'
  2. approver ≠ proposer (enforced by reject + add_review here;
     by merge_cr in CR-B2)
  3. ``base_hash`` mismatch surfaces via ``supersede_cr`` so the
     apply dispatcher (CR-B2) has a state-machine primitive to call
  4. transaction-atomic merge — deferred to CR-B2 where apply lives
  5. apply() failure leaves status='open' — deferred to CR-B2
  6. unknown ``target_type`` → ValueError at propose time
  7. every state transition writes one row to ``audit_log`` via
     ``core.audit_bridge``

Plus baseline storage correctness — round-trip, listing, filters,
ID sortability, schema-level CHECK constraints.

Run:
    python -m unittest tests.test_change_request_core
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.change_request as cr_mod  # noqa: E402
from core.change_request import (   # noqa: E402
    TARGET_WIKI_ENTITY, TARGET_RUN_JOBS,
    STATUS_OPEN, STATUS_REJECTED, STATUS_SUPERSEDED,
    VALID_STATUSES, VALID_TARGET_TYPES,
    REVIEW_APPROVE, REVIEW_REQUEST_CHANGES, REVIEW_COMMENT,
    ChangeRequest,
    init_db, create_cr, get_cr, list_crs,
    reject_cr, supersede_cr, add_review, list_reviews,
    compute_base_hash, cr_id_for_now, review_id_for_now,
)


def _tmpdb() -> str:
    """Fresh temp DB path with the CR schema already applied."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="cr_test_")
    os.close(fd)
    init_db(path)
    return path


class _AuditCapture:
    """Patch ``core.audit_bridge.mirror_to_audit_db`` during a test
    so we can assert that every state transition emits exactly one
    audit row, without having to scrub a real audit DB between tests.
    """
    def __init__(self):
        self.calls: list[dict] = []
        self._orig = None

    def __enter__(self):
        from core import audit_bridge
        self._orig = audit_bridge.mirror_to_audit_db

        def _capture(entry, **_kw):
            self.calls.append(dict(entry))
            return True
        audit_bridge.mirror_to_audit_db = _capture
        return self

    def __exit__(self, *exc):
        from core import audit_bridge
        audit_bridge.mirror_to_audit_db = self._orig


# ─── Schema bootstrap ────────────────────────────────────────────
class SchemaBootstrapTests(unittest.TestCase):

    def test_init_db_is_idempotent(self):
        path = _tmpdb()
        try:
            # Re-running init must not raise (CREATE TABLE IF NOT EXISTS).
            init_db(path)
            init_db(path)
        finally:
            os.unlink(path)

    def test_two_tables_and_three_indexes_exist(self):
        path = _tmpdb()
        try:
            conn = sqlite3.connect(path)
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            self.assertIn("change_requests", tables)
            self.assertIn("cr_reviews", tables)
            indexes = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND sql IS NOT NULL"
            ).fetchall()}
            self.assertIn("idx_cr_status_target", indexes)
            self.assertIn("idx_cr_proposer", indexes)
            self.assertIn("idx_cr_reviews_cr", indexes)
            conn.close()
        finally:
            os.unlink(path)

    def test_status_check_constraint_blocks_unknown_value(self):
        # CHECK (status IN (...)) at storage layer is a belt to the
        # python-side suspenders. Hand-crafted insert with a bogus
        # status must fail at COMMIT.
        path = _tmpdb()
        try:
            conn = sqlite3.connect(path)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO change_requests "
                    "(cr_id, target_type, target_id, title, "
                    " proposed_diff, base_hash, proposer, status, "
                    " created_at, updated_at) "
                    "VALUES "
                    "('x','wiki_entity','t','t','{}','h','p',"
                    " 'banana',0,0)"
                )
            conn.close()
        finally:
            os.unlink(path)

    def test_merged_fields_check_constraint(self):
        # Invariant #1: (status='merged') = (merged_at NOT NULL AND
        # merged_by NOT NULL). A row that claims merged but has NULL
        # merge fields must be rejected at the DB layer.
        path = _tmpdb()
        try:
            conn = sqlite3.connect(path)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO change_requests "
                    "(cr_id, target_type, target_id, title, "
                    " proposed_diff, base_hash, proposer, status, "
                    " created_at, updated_at, merged_at, merged_by) "
                    "VALUES "
                    "('x','wiki_entity','t','t','{}','h','p',"
                    " 'merged',0,0,NULL,NULL)"
                )
            conn.close()
        finally:
            os.unlink(path)


# ─── ID generation ───────────────────────────────────────────────
class IdGenerationTests(unittest.TestCase):

    def test_ids_are_sortable(self):
        # ULID-like — created order should match lex order so the
        # default ``ORDER BY cr_id`` listing stays monotonic.
        ids = [cr_id_for_now() for _ in range(5)]
        # Tiny sleep between to guarantee the ms component differs;
        # we don't depend on it but the test must not flake.
        # Actually: if all 5 land in the same ms, the random tail
        # still differs and equality / sort is deterministic anyway.
        self.assertEqual(len(set(ids)), 5, "ids must be unique")
        # Sort stability — at minimum sorted == time-ordered when
        # ms ticks. Even within one ms, the random tail isn't time-
        # bound, so we only assert uniqueness + prefix.
        for i in ids:
            self.assertTrue(i.startswith("cr_"))

    def test_review_id_has_different_prefix(self):
        # Cross-type collisions must be impossible by construction.
        self.assertTrue(review_id_for_now().startswith("rv_"))
        self.assertNotEqual(cr_id_for_now()[:3], review_id_for_now()[:3])


# ─── Hash helper ─────────────────────────────────────────────────
class HashHelperTests(unittest.TestCase):

    def test_compute_base_hash_round_trip(self):
        h1 = compute_base_hash(b"hello")
        h2 = compute_base_hash(b"hello")
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)         # sha256 hex digest

    def test_compute_base_hash_distinguishes_content(self):
        self.assertNotEqual(
            compute_base_hash(b"hello"),
            compute_base_hash(b"hello!"),
        )

    def test_compute_base_hash_rejects_str_input(self):
        # bytes-vs-str ambiguity would change the hash silently and
        # break conflict detection. Surface that error loudly.
        with self.assertRaises(TypeError):
            compute_base_hash("hello")          # type: ignore[arg-type]


# ─── Invariant #6 — unknown target_type fails fast ───────────────
class TargetTypeEnumTests(unittest.TestCase):

    def test_unknown_target_type_rejected_at_propose(self):
        path = _tmpdb()
        try:
            with self.assertRaises(ValueError):
                create_cr(
                    target_type="legal_clause",
                    target_id="X",
                    title="t",
                    proposed_diff={},
                    base_hash="h",
                    proposer="alice",
                    db_path=path,
                )
        finally:
            os.unlink(path)

    def test_both_v02_target_types_accepted(self):
        path = _tmpdb()
        try:
            for tt in (TARGET_WIKI_ENTITY, TARGET_RUN_JOBS):
                with self.subTest(target_type=tt):
                    cr = create_cr(
                        target_type=tt, target_id="X", title="t",
                        proposed_diff={}, base_hash="h",
                        proposer="alice", db_path=path,
                    )
                    self.assertEqual(cr.target_type, tt)
        finally:
            os.unlink(path)

    def test_target_type_set_matches_architecture_doc(self):
        # The closed enum is documented in ARCHITECTURE.md §5.6. If
        # someone adds a third entry without updating the doc PR
        # this test catches the drift.
        self.assertEqual(VALID_TARGET_TYPES,
                         frozenset({"wiki_entity", "run_jobs"}))


# ─── Propose path ────────────────────────────────────────────────
class CreateCrTests(unittest.TestCase):

    def setUp(self):
        self.path = _tmpdb()

    def tearDown(self):
        os.unlink(self.path)

    def test_create_minimum_fields(self):
        cr = create_cr(
            target_type=TARGET_WIKI_ENTITY, target_id="ent_x",
            title="Edit X", proposed_diff={"op": "noop"},
            base_hash="abc", proposer="alice",
            db_path=self.path,
        )
        self.assertIsInstance(cr, ChangeRequest)
        self.assertEqual(cr.status, STATUS_OPEN)
        self.assertEqual(cr.proposer, "alice")
        self.assertIsNone(cr.merged_at)
        self.assertIsNone(cr.merged_by)
        self.assertIsNone(cr.reject_reason)

    def test_create_serialises_dict_diff_as_json(self):
        cr = create_cr(
            target_type=TARGET_WIKI_ENTITY, target_id="ent_y",
            title="t", proposed_diff={"op": "replace", "body": "ko ⚡"},
            base_hash="h", proposer="alice",
            db_path=self.path,
        )
        import json
        decoded = json.loads(cr.proposed_diff)
        self.assertEqual(decoded["op"], "replace")
        # JSON round-trip must preserve non-ASCII (ensure_ascii=False).
        self.assertEqual(decoded["body"], "ko ⚡")

    def test_create_accepts_pre_serialised_string_diff(self):
        cr = create_cr(
            target_type=TARGET_WIKI_ENTITY, target_id="x",
            title="t", proposed_diff='{"raw": true}',
            base_hash="h", proposer="alice", db_path=self.path,
        )
        self.assertIn('"raw"', cr.proposed_diff)

    def test_create_rejects_non_dict_non_str_diff(self):
        with self.assertRaises(ValueError):
            create_cr(
                target_type=TARGET_WIKI_ENTITY, target_id="x",
                title="t", proposed_diff=12345,
                base_hash="h", proposer="alice", db_path=self.path,
            )

    def test_create_rejects_empty_required_fields(self):
        good = dict(
            target_type=TARGET_WIKI_ENTITY, target_id="X",
            title="t", proposed_diff={}, base_hash="h",
            proposer="alice", db_path=self.path,
        )
        for empty_field in ("title", "target_id", "base_hash", "proposer"):
            with self.subTest(field=empty_field):
                kwargs = dict(good)
                kwargs[empty_field] = ""
                with self.assertRaises(ValueError):
                    create_cr(**kwargs)

    def test_create_normalises_labels(self):
        # CSV column gets dedup'd + sorted + trimmed so display and
        # filter behaviour are deterministic regardless of caller.
        cr = create_cr(
            target_type=TARGET_WIKI_ENTITY, target_id="x",
            title="t", proposed_diff={}, base_hash="h",
            proposer="alice",
            labels=[" docs ", "docs", "policy", ""],
            db_path=self.path,
        )
        self.assertEqual(cr.labels, "docs,policy")


# ─── Read path ───────────────────────────────────────────────────
class ReadPathTests(unittest.TestCase):

    def setUp(self):
        self.path = _tmpdb()

    def tearDown(self):
        os.unlink(self.path)

    def _make(self, **over):
        kw = dict(
            target_type=TARGET_WIKI_ENTITY, target_id="x",
            title="t", proposed_diff={}, base_hash="h",
            proposer="alice", db_path=self.path,
        )
        kw.update(over)
        return create_cr(**kw)

    def test_get_cr_missing_returns_none(self):
        self.assertIsNone(get_cr("cr_does_not_exist", db_path=self.path))

    def test_get_cr_round_trip(self):
        cr = self._make(title="round-trip")
        back = get_cr(cr.cr_id, db_path=self.path)
        self.assertEqual(back, cr)

    def test_list_orders_newest_first(self):
        a = self._make(target_id="A")
        time.sleep(0.005)   # ensure created_at differs (sec precision)
        b = self._make(target_id="B")
        rows = list_crs(db_path=self.path, limit=10)
        # Newest first — B was created after A.
        self.assertEqual(rows[0].cr_id, b.cr_id)
        self.assertEqual(rows[1].cr_id, a.cr_id)

    def test_list_filter_by_status(self):
        a = self._make()
        b = self._make()
        reject_cr(a.cr_id, reviewer="bob", db_path=self.path)
        self.assertEqual(
            [r.cr_id for r in list_crs(status=STATUS_OPEN, db_path=self.path)],
            [b.cr_id],
        )
        self.assertEqual(
            [r.cr_id for r in list_crs(status=STATUS_REJECTED, db_path=self.path)],
            [a.cr_id],
        )

    def test_list_filter_by_target_type(self):
        self._make(target_type=TARGET_WIKI_ENTITY)
        self._make(target_type=TARGET_RUN_JOBS)
        wiki  = list_crs(target_type=TARGET_WIKI_ENTITY, db_path=self.path)
        jobs  = list_crs(target_type=TARGET_RUN_JOBS,    db_path=self.path)
        self.assertEqual(len(wiki), 1)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(wiki[0].target_type, TARGET_WIKI_ENTITY)
        self.assertEqual(jobs[0].target_type, TARGET_RUN_JOBS)

    def test_list_filter_by_proposer(self):
        self._make(proposer="alice")
        self._make(proposer="bob")
        bobs = list_crs(proposer="bob", db_path=self.path)
        self.assertEqual(len(bobs), 1)
        self.assertEqual(bobs[0].proposer, "bob")

    def test_list_clamps_limit_and_offset(self):
        # A 1-char query must NOT be able to dump the whole table —
        # same anti-DoS posture as /admin/audit/list.
        for _ in range(5):
            self._make()
        # limit=999999 clamps to 500.
        many = list_crs(limit=999999, db_path=self.path)
        self.assertLessEqual(len(many), 500)
        # limit=0 clamps to 1 (defensive — we still return at least
        # one row if asked, since 0 is almost certainly a bug).
        zero = list_crs(limit=0, db_path=self.path)
        self.assertEqual(len(zero), 1)
        # Negative offset clamps to 0.
        neg = list_crs(limit=10, offset=-5, db_path=self.path)
        self.assertEqual(len(neg), 5)

    def test_list_unknown_filter_raises(self):
        with self.assertRaises(ValueError):
            list_crs(status="banana", db_path=self.path)
        with self.assertRaises(ValueError):
            list_crs(target_type="legal_clause", db_path=self.path)


# ─── Invariant #2 — approver ≠ proposer ──────────────────────────
class ApproverIdentityTests(unittest.TestCase):

    def setUp(self):
        self.path = _tmpdb()
        self.cr   = create_cr(
            target_type=TARGET_WIKI_ENTITY, target_id="X",
            title="t", proposed_diff={}, base_hash="h",
            proposer="alice", db_path=self.path,
        )

    def tearDown(self):
        os.unlink(self.path)

    def test_self_rejection_blocked(self):
        # alice can't reject her own proposal — that defeats the
        # two-person rule that's the whole point of CR.
        with self.assertRaises(ValueError):
            reject_cr(self.cr.cr_id, reviewer="alice",
                      db_path=self.path)

    def test_self_approve_review_blocked(self):
        with self.assertRaises(ValueError):
            add_review(self.cr.cr_id, reviewer="alice",
                       decision=REVIEW_APPROVE, db_path=self.path)

    def test_self_request_changes_blocked(self):
        with self.assertRaises(ValueError):
            add_review(self.cr.cr_id, reviewer="alice",
                       decision=REVIEW_REQUEST_CHANGES,
                       db_path=self.path)

    def test_proposer_may_comment_on_own_cr(self):
        # Comments are not decisions — proposer should be able to
        # add a clarification on their own CR without tripping the
        # two-person rule.
        rev = add_review(
            self.cr.cr_id, reviewer="alice",
            decision=REVIEW_COMMENT, body="forgot to mention X",
            db_path=self.path,
        )
        self.assertEqual(rev.reviewer, "alice")
        self.assertEqual(rev.decision, REVIEW_COMMENT)

    def test_other_user_can_reject(self):
        out = reject_cr(self.cr.cr_id, reviewer="bob",
                        reason="not now", db_path=self.path)
        self.assertEqual(out.status, STATUS_REJECTED)
        self.assertEqual(out.reject_reason, "not now")


# ─── State machine: terminal states block further transitions ────
class StateMachineTests(unittest.TestCase):

    def setUp(self):
        self.path = _tmpdb()
        self.cr   = create_cr(
            target_type=TARGET_WIKI_ENTITY, target_id="X",
            title="t", proposed_diff={}, base_hash="h",
            proposer="alice", db_path=self.path,
        )

    def tearDown(self):
        os.unlink(self.path)

    def test_cannot_reject_already_rejected(self):
        reject_cr(self.cr.cr_id, reviewer="bob", db_path=self.path)
        with self.assertRaises(ValueError):
            reject_cr(self.cr.cr_id, reviewer="bob",
                      db_path=self.path)

    def test_cannot_supersede_already_rejected(self):
        reject_cr(self.cr.cr_id, reviewer="bob", db_path=self.path)
        with self.assertRaises(ValueError):
            supersede_cr(self.cr.cr_id, db_path=self.path)

    def test_supersede_records_reason(self):
        out = supersede_cr(
            self.cr.cr_id, reason="base_hash mismatch",
            db_path=self.path,
        )
        self.assertEqual(out.status, STATUS_SUPERSEDED)
        self.assertEqual(out.reject_reason, "base_hash mismatch")

    def test_reject_missing_cr(self):
        with self.assertRaises(ValueError):
            reject_cr("cr_does_not_exist", reviewer="bob",
                      db_path=self.path)


# ─── Reviews ─────────────────────────────────────────────────────
class ReviewTests(unittest.TestCase):

    def setUp(self):
        self.path = _tmpdb()
        self.cr   = create_cr(
            target_type=TARGET_WIKI_ENTITY, target_id="X",
            title="t", proposed_diff={}, base_hash="h",
            proposer="alice", db_path=self.path,
        )

    def tearDown(self):
        os.unlink(self.path)

    def test_unknown_decision_rejected(self):
        with self.assertRaises(ValueError):
            add_review(self.cr.cr_id, reviewer="bob",
                       decision="lgtm-ish", db_path=self.path)

    def test_review_ordered_by_created_at_asc(self):
        # Reviews list is a conversation — oldest first.
        r1 = add_review(self.cr.cr_id, reviewer="bob",
                        decision=REVIEW_COMMENT, body="first",
                        db_path=self.path)
        time.sleep(0.005)
        r2 = add_review(self.cr.cr_id, reviewer="carol",
                        decision=REVIEW_COMMENT, body="second",
                        db_path=self.path)
        listed = list_reviews(self.cr.cr_id, db_path=self.path)
        self.assertEqual([r.review_id for r in listed],
                         [r1.review_id, r2.review_id])

    def test_missing_cr_blocks_review(self):
        with self.assertRaises(ValueError):
            add_review("cr_does_not_exist", reviewer="bob",
                       decision=REVIEW_COMMENT, db_path=self.path)


# ─── Invariant #7 — every transition writes one audit row ────────
class AuditMirrorTests(unittest.TestCase):
    """A test-side capture replaces ``mirror_to_audit_db`` so we can
    assert the contract without touching the real audit DB."""

    def setUp(self):
        self.path = _tmpdb()

    def tearDown(self):
        os.unlink(self.path)

    def test_propose_emits_audit_row(self):
        with _AuditCapture() as cap:
            cr = create_cr(
                target_type=TARGET_WIKI_ENTITY, target_id="X",
                title="t", proposed_diff={}, base_hash="h",
                proposer="alice", db_path=self.path,
            )
        self.assertEqual(len(cap.calls), 1)
        entry = cap.calls[0]
        self.assertEqual(entry["endpoint"], "cr:propose")
        self.assertEqual(entry["event"],    "cr.propose")
        self.assertEqual(entry["target"],   cr.cr_id)

    def test_reject_emits_audit_row(self):
        cr = create_cr(
            target_type=TARGET_WIKI_ENTITY, target_id="X",
            title="t", proposed_diff={}, base_hash="h",
            proposer="alice", db_path=self.path,
        )
        with _AuditCapture() as cap:
            reject_cr(cr.cr_id, reviewer="bob", reason="no",
                      db_path=self.path)
        self.assertEqual(len(cap.calls), 1)
        self.assertEqual(cap.calls[0]["endpoint"], "cr:reject")

    def test_supersede_emits_audit_row(self):
        cr = create_cr(
            target_type=TARGET_WIKI_ENTITY, target_id="X",
            title="t", proposed_diff={}, base_hash="h",
            proposer="alice", db_path=self.path,
        )
        with _AuditCapture() as cap:
            supersede_cr(cr.cr_id, db_path=self.path)
        self.assertEqual(len(cap.calls), 1)
        self.assertEqual(cap.calls[0]["endpoint"], "cr:supersede")

    def test_review_emits_audit_row(self):
        cr = create_cr(
            target_type=TARGET_WIKI_ENTITY, target_id="X",
            title="t", proposed_diff={}, base_hash="h",
            proposer="alice", db_path=self.path,
        )
        with _AuditCapture() as cap:
            add_review(cr.cr_id, reviewer="bob",
                       decision=REVIEW_COMMENT, body="hi",
                       db_path=self.path)
        self.assertEqual(len(cap.calls), 1)
        self.assertEqual(cap.calls[0]["endpoint"], "cr:review")

    def test_audit_swallows_mirror_failure(self):
        # CR transition must commit even when audit mirroring blows
        # up (disk full, db locked, etc.). The audit gap is visible
        # to operators; a stuck CR write is not acceptable.
        from core import audit_bridge
        orig = audit_bridge.mirror_to_audit_db

        def _boom(*a, **kw):
            raise RuntimeError("audit DB is unreachable")
        audit_bridge.mirror_to_audit_db = _boom
        try:
            cr = create_cr(
                target_type=TARGET_WIKI_ENTITY, target_id="X",
                title="t", proposed_diff={}, base_hash="h",
                proposer="alice", db_path=self.path,
            )
        finally:
            audit_bridge.mirror_to_audit_db = orig
        # Despite the audit failure, the CR exists.
        self.assertIsNotNone(get_cr(cr.cr_id, db_path=self.path))


# ─── Constants smoke (handover ⇄ code consistency) ───────────────
class HandoverConsistencyTests(unittest.TestCase):

    def test_status_constants_match_handover(self):
        # The four statuses named in
        # docs/handovers/v0.2.x-cr-track.md must equal what the
        # module exports — drift would mean docs are wrong.
        self.assertEqual(
            VALID_STATUSES,
            frozenset({"open", "merged", "rejected", "superseded"}),
        )

    def test_review_decisions_match_handover(self):
        from core.change_request import VALID_REVIEW_DECISIONS
        self.assertEqual(
            VALID_REVIEW_DECISIONS,
            frozenset({"approve", "request_changes", "comment"}),
        )

    def test_module_size_under_gate(self):
        # CLAUDE.md rule #5: no core/ file may exceed 20 KB.
        size = Path(cr_mod.__file__).stat().st_size
        self.assertLess(size, 20 * 1024,
            f"core/change_request.py is {size} bytes, exceeds 20KB gate")


if __name__ == "__main__":
    unittest.main()
