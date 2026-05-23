"""Patch lifecycle audit query — #68 phase 2-C.

Coverage:
  - `query_patch_audit` reads JSONL, filters by since / approver /
    outcome, returns newest-first.
  - Empty file / missing file → empty list (no exception).
  - Malformed JSONL line is skipped silently (partial mid-rotation
    write must not break the audit read).
  - Limit clamped to [1, 1000]; non-int / negative → safe defaults.
  - Source-level: `/admin/patch/audit` route exists, requires admin,
    forwards filter args into query_patch_audit, returns the
    documented response shape (`filters`, `count`, `events`).

Run:
  python -m unittest tests.test_evolution_audit_query
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _write_log(path: Path, entries: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _sample_entries() -> list[dict]:
    """Five lifecycle entries spanning two approvers and three outcomes."""
    return [
        {
            "time": "2026-05-08T09:00:00",
            "event": "APPROVED", "patch_id": "p1",
            "approver_username": "alice", "approver_role": "admin",
            "approval_method": "api",
        },
        {
            "time": "2026-05-08T09:01:00",
            "event": "DEPLOYED", "patch_id": "p1",
            "outcome": "deployed",
            "before_metrics": {}, "after_metrics": {"queries": 13, "ok": 11},
            "detail": "bench gate passed",
        },
        {
            "time": "2026-05-08T10:00:00",
            "event": "APPROVED", "patch_id": "p2",
            "approver_username": "bob", "approver_role": "admin",
            "approval_method": "ui",
        },
        {
            "time": "2026-05-08T10:05:00",
            "event": "ROLLED_BACK", "patch_id": "p2",
            "outcome": "rolled_back",
            "approver_username": "bob",
            "before_metrics": {}, "after_metrics": {"errors": 1},
            "detail": "bench regression — rollback=ok",
        },
        {
            "time": "2026-05-08T11:00:00",
            "event": "APPROVED", "patch_id": "p3",
            "approver_username": "alice", "approver_role": "admin",
            "approval_method": "api",
        },
    ]


class QueryBasicShapeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        )
        self._tmp.close()
        self.path = Path(self._tmp.name)

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_missing_file_returns_empty(self):
        from tools.patch.audit_query import query_patch_audit
        self.assertEqual(query_patch_audit(log_path="/nonexistent/foo.jsonl"), [])

    def test_empty_file_returns_empty(self):
        from tools.patch.audit_query import query_patch_audit
        # File exists but is empty.
        self.assertEqual(query_patch_audit(log_path=str(self.path)), [])

    def test_basic_read_returns_newest_first(self):
        from tools.patch.audit_query import query_patch_audit
        _write_log(self.path, _sample_entries())
        rows = query_patch_audit(log_path=str(self.path))
        self.assertEqual(len(rows), 5)
        # Newest first = 11:00 > 10:05 > 10:00 > 09:01 > 09:00
        times = [r["time"] for r in rows]
        self.assertEqual(times, sorted(times, reverse=True))

    def test_malformed_line_skipped_silently(self):
        from tools.patch.audit_query import query_patch_audit
        # Mix valid + malformed.
        with self.path.open("w", encoding="utf-8") as f:
            f.write(json.dumps(_sample_entries()[0]) + "\n")
            f.write("{ this is not valid json\n")
            f.write(json.dumps(_sample_entries()[1]) + "\n")
        rows = query_patch_audit(log_path=str(self.path))
        self.assertEqual(len(rows), 2,
                         "malformed line must be skipped, not crash")


class FilterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        )
        self._tmp.close()
        self.path = Path(self._tmp.name)
        _write_log(self.path, _sample_entries())

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_since_lower_bound_inclusive(self):
        from tools.patch.audit_query import query_patch_audit
        # since=10:00 → keep 10:00, 10:05, 11:00 (3 entries)
        rows = query_patch_audit(since="2026-05-08T10:00:00", log_path=str(self.path))
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertGreaterEqual(r["time"], "2026-05-08T10:00:00")

    def test_since_date_only_form(self):
        from tools.patch.audit_query import query_patch_audit
        rows = query_patch_audit(since="2026-05-08", log_path=str(self.path))
        # All 5 entries are 2026-05-08 → all included.
        self.assertEqual(len(rows), 5)

    def test_since_invalid_value_does_not_crash(self):
        from tools.patch.audit_query import query_patch_audit
        # Garbage since string — entries with `time` < garbage compare
        # may be included or excluded based on lex order; what matters
        # is no exception. Valid contract is "noisier feed, not crash".
        rows = query_patch_audit(since="not-a-date", log_path=str(self.path))
        self.assertIsInstance(rows, list)

    def test_approver_exact_match(self):
        from tools.patch.audit_query import query_patch_audit
        # approver=alice → entries with approver_username='alice' only.
        # That's the two APPROVED entries (p1 + p3). The DEPLOYED
        # entry for p1 has no approver_username → excluded.
        rows = query_patch_audit(approver="alice", log_path=str(self.path))
        self.assertEqual(len(rows), 2)
        for r in rows:
            self.assertEqual(r["approver_username"], "alice")

    def test_approver_case_insensitive(self):
        from tools.patch.audit_query import query_patch_audit
        rows = query_patch_audit(approver="ALICE", log_path=str(self.path))
        self.assertEqual(len(rows), 2)

    def test_outcome_filter(self):
        from tools.patch.audit_query import query_patch_audit
        rows_dep = query_patch_audit(outcome="deployed", log_path=str(self.path))
        self.assertEqual(len(rows_dep), 1)
        self.assertEqual(rows_dep[0]["patch_id"], "p1")

        rows_rb = query_patch_audit(outcome="rolled_back", log_path=str(self.path))
        self.assertEqual(len(rows_rb), 1)
        self.assertEqual(rows_rb[0]["patch_id"], "p2")

    def test_combined_filters_and_semantics(self):
        from tools.patch.audit_query import query_patch_audit
        # alice + outcome=deployed → 0 (alice's DEPLOYED entry has no
        # approver field; the filter requires both to match the same row).
        rows = query_patch_audit(
            approver="alice", outcome="deployed", log_path=str(self.path)
        )
        self.assertEqual(rows, [])

        # bob + outcome=rolled_back → 1 (the p2 ROLLED_BACK entry
        # carries approver_username='bob' too).
        rows = query_patch_audit(
            approver="bob", outcome="rolled_back", log_path=str(self.path)
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["patch_id"], "p2")


class LimitClampTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        )
        self._tmp.close()
        self.path = Path(self._tmp.name)
        _write_log(self.path, _sample_entries())

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_limit_caps_at_supplied_value(self):
        from tools.patch.audit_query import query_patch_audit
        rows = query_patch_audit(limit=2, log_path=str(self.path))
        self.assertEqual(len(rows), 2)
        # Newest 2 entries: 11:00 + 10:05
        self.assertEqual(rows[0]["time"], "2026-05-08T11:00:00")
        self.assertEqual(rows[1]["time"], "2026-05-08T10:05:00")

    def test_limit_clamped_to_max(self):
        from tools.patch.audit_query import query_patch_audit
        # Even an absurdly large limit is clamped — but with only 5
        # entries we just see all 5. The clamp logic still runs.
        rows = query_patch_audit(limit=999999, log_path=str(self.path))
        self.assertEqual(len(rows), 5)

    def test_limit_zero_or_negative_clamped_to_one(self):
        from tools.patch.audit_query import query_patch_audit
        rows = query_patch_audit(limit=0, log_path=str(self.path))
        self.assertEqual(len(rows), 1)
        rows = query_patch_audit(limit=-5, log_path=str(self.path))
        self.assertEqual(len(rows), 1)

    def test_limit_garbage_falls_back_to_default(self):
        from tools.patch.audit_query import query_patch_audit
        rows = query_patch_audit(limit="not-a-number", log_path=str(self.path))
        # 5 entries < DEFAULT_LIMIT → all returned.
        self.assertEqual(len(rows), 5)


class EndpointContractTests(unittest.TestCase):
    """Source-level: /admin/patch/audit must require admin and
    forward filter args into query_patch_audit."""

    def test_route_exists_and_is_admin_gated(self):
        import server_llmwiki as srv
        import inspect
        src = inspect.getsource(srv)
        self.assertIn('@app.get("/admin/patch/audit"', src,
                      "audit endpoint must be registered as GET")
        self.assertIn("from tools.patch.audit_query import query_patch_audit", src,
                      "audit endpoint must import query_patch_audit")
        # Admin gating — same pattern as the rest of /admin/* handlers.
        # Either the legacy _require_admin(api_key, role) call or the
        # W4-Q2 _require_feature(api_key, role, "admin.evolution") call
        # gates this endpoint; both enforce admin authority for the
        # admin.evolution feature.
        idx = src.index('@app.get("/admin/patch/audit"')
        # Window: 2200 chars after the decorator covers the handler body.
        # Bumped from 1500 in Stage B / CR-E.4 (2026-05-24) — the
        # include_shadow query param + the new docstring paragraph
        # documenting the dual-source merge pushed the response-shape
        # block past the old window. The shape contract (filters /
        # count / events keys + admin gating) is unchanged.
        window = src[idx:idx + 2200]
        self.assertTrue(
            "_require_admin(api_key, role)" in window
            or '_require_feature(api_key, role, "admin.evolution")' in window,
            "audit endpoint must call _require_admin or "
            "_require_feature for admin.evolution",
        )
        self.assertIn("query_patch_audit(", window,
                      "audit endpoint must call query_patch_audit")
        # Response shape contract.
        self.assertIn('"filters"', window)
        self.assertIn('"count"', window)
        self.assertIn('"events"', window)


if __name__ == "__main__":
    unittest.main()
