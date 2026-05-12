"""[PR-CR-D, 2026-05-12] run_jobs apply path.

Second target_type in the CR apply dispatcher. Unlike wiki_entity
(which mutates a markdown file under wiki/), a ``run_jobs`` CR is a
trigger — approving the CR fires a workspace job under the
proposer's name. The job_id becomes the merge artifact (returned as
``ApplyResult.new_hash``) so reviewers can trace back from the CR
to the job row in the workspace Jobs tab.

This suite exercises the apply layer + merge orchestrator path for
run_jobs targets. Tests mock workspace.register_job / execute_job
so the suite doesn't depend on the workspace jobs DB schema being
in a particular state — the apply layer's concern is "did we
dispatch the right args", not "did workspace's executor work".

Run:
    python -m unittest tests.test_change_request_jobs_apply
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.change_request as _cr_mod          # noqa: E402
import core.change_request_apply as apply_mod  # noqa: E402
from core.change_request import (              # noqa: E402
    STATUS_OPEN, STATUS_MERGED,
    TARGET_RUN_JOBS,
    init_db, create_cr, get_cr,
)
from core.change_request_apply import (        # noqa: E402
    apply_cr, merge_cr,
)


class _JobsApplyEnv:
    """Sets up a temp CR DB and patches workspace.register_job +
    execute_job so the apply layer's behaviour is exercised
    without depending on the workspace SQLite schema.

    The recorder is a list of ``("register"/"execute", payload)``
    tuples — tests assert against this to verify arg passing."""

    def __init__(self, *, execute_raises: Exception | None = None,
                 register_returns: str = "job_xyz"):
        self.db: str = ""
        self._prev_db: str = ""
        self.calls: list[tuple] = []
        self._exec_raises = execute_raises
        self._register_returns = register_returns
        self._orig_register = None
        self._orig_execute = None

    def __enter__(self):
        fd, self.db = tempfile.mkstemp(suffix=".db", prefix="cr_jobs_")
        os.close(fd)
        init_db(self.db)
        self._prev_db = _cr_mod._DEFAULT_DB
        _cr_mod._DEFAULT_DB = self.db

        from core import workspace as ws
        self._orig_register = ws.register_job
        self._orig_execute  = ws.execute_job

        def _fake_register(*, job_type, input_refs, owner=None,
                           options=None, **_kw):
            self.calls.append((
                "register",
                {"job_type": job_type, "input_refs": list(input_refs),
                 "owner": owner, "options": options},
            ))
            return self._register_returns

        def _fake_execute(job_id):
            self.calls.append(("execute", {"job_id": job_id}))
            if self._exec_raises is not None:
                raise self._exec_raises
            return {"job_id": job_id, "status": "done"}

        ws.register_job = _fake_register
        ws.execute_job  = _fake_execute
        return self

    def __exit__(self, *exc):
        from core import workspace as ws
        ws.register_job = self._orig_register
        ws.execute_job  = self._orig_execute
        _cr_mod._DEFAULT_DB = self._prev_db
        try:
            os.unlink(self.db)
        except OSError:
            pass


def _propose_run(env: _JobsApplyEnv, *, diff: dict,
                 proposer: str = "alice",
                 base_hash: str = "deadbeef") -> str:
    cr = create_cr(
        target_type=TARGET_RUN_JOBS,
        target_id="excel_build:ent_001+ent_042",
        title="Build the weekly excel",
        proposed_diff=diff,
        base_hash=base_hash,
        proposer=proposer,
        db_path=env.db,
    )
    return cr.cr_id


# ─── Diff shape validation ───────────────────────────────────────
class DiffValidationTests(unittest.TestCase):

    def test_apply_rejects_non_run_op(self):
        with _JobsApplyEnv() as env:
            cr_id = _propose_run(env, diff={
                "op": "delete", "job_type": "excel_build",
                "input_refs": ["ent_001"],
            })
            cr = get_cr(cr_id, db_path=env.db)
            with self.assertRaises(ValueError):
                apply_cr(cr)

    def test_apply_rejects_missing_job_type(self):
        with _JobsApplyEnv() as env:
            cr_id = _propose_run(env, diff={
                "op": "run", "input_refs": ["ent_001"],
            })
            cr = get_cr(cr_id, db_path=env.db)
            with self.assertRaises(ValueError):
                apply_cr(cr)

    def test_apply_rejects_input_refs_not_list(self):
        with _JobsApplyEnv() as env:
            cr_id = _propose_run(env, diff={
                "op": "run", "job_type": "excel_build",
                "input_refs": "ent_001,ent_002",
            })
            cr = get_cr(cr_id, db_path=env.db)
            with self.assertRaises(ValueError):
                apply_cr(cr)

    def test_apply_rejects_non_string_input_ref(self):
        with _JobsApplyEnv() as env:
            cr_id = _propose_run(env, diff={
                "op": "run", "job_type": "excel_build",
                "input_refs": ["ent_001", 42, "ent_003"],
            })
            cr = get_cr(cr_id, db_path=env.db)
            with self.assertRaises(ValueError):
                apply_cr(cr)

    def test_apply_rejects_non_dict_options(self):
        with _JobsApplyEnv() as env:
            cr_id = _propose_run(env, diff={
                "op": "run", "job_type": "excel_build",
                "input_refs": ["ent_001"],
                "options": "not-a-dict",
            })
            cr = get_cr(cr_id, db_path=env.db)
            with self.assertRaises(ValueError):
                apply_cr(cr)

    def test_apply_rejects_unknown_job_type(self):
        # workspace.HANDLERS is the allowlist — same enum the
        # /jobs/run endpoint consults.
        with _JobsApplyEnv() as env:
            cr_id = _propose_run(env, diff={
                "op": "run", "job_type": "legal_clause_render",
                "input_refs": ["ent_001"],
            })
            cr = get_cr(cr_id, db_path=env.db)
            with self.assertRaises(ValueError):
                apply_cr(cr)
            # Nothing was registered.
            self.assertEqual(env.calls, [])

    def test_apply_rejects_invalid_json_diff(self):
        with _JobsApplyEnv() as env:
            # Bypass create_cr's serialisation by writing a row directly
            # with malformed JSON in proposed_diff.
            import sqlite3, time
            now = int(time.time())
            conn = sqlite3.connect(env.db)
            conn.execute(
                "INSERT INTO change_requests "
                "(cr_id, target_type, target_id, title, "
                " proposed_diff, base_hash, proposer, status, "
                " created_at, updated_at) "
                "VALUES (?, ?, ?, 't', ?, ?, 'alice', 'open', ?, ?)",
                ("cr_bad_json", "run_jobs", "x",
                 "{not-json", "h", now, now),
            )
            conn.commit()
            conn.close()
            cr = get_cr("cr_bad_json", db_path=env.db)
            with self.assertRaises(ValueError):
                apply_cr(cr)


# ─── Happy path ──────────────────────────────────────────────────
class HappyPathTests(unittest.TestCase):

    def test_apply_routes_through_register_and_execute(self):
        with _JobsApplyEnv(register_returns="job_xyz") as env:
            cr_id = _propose_run(env, diff={
                "op": "run", "job_type": "excel_build",
                "input_refs": ["ent_001", "ent_042"],
                "options": {"format": "xlsx"},
            }, proposer="alice")
            cr = get_cr(cr_id, db_path=env.db)
            result = apply_cr(cr)
            self.assertTrue(result.applied)
            self.assertFalse(result.superseded)
            self.assertEqual(result.new_hash, "job_xyz")

            # Order matters — register must precede execute.
            self.assertEqual(
                [k for (k, _) in env.calls],
                ["register", "execute"],
            )
            reg = env.calls[0][1]
            self.assertEqual(reg["job_type"],   "excel_build")
            self.assertEqual(reg["input_refs"], ["ent_001", "ent_042"])
            # Owner MUST be the proposer — not the approver. The
            # approver's identity lives on the CR row + audit.
            self.assertEqual(reg["owner"],   "alice")
            self.assertEqual(reg["options"], {"format": "xlsx"})
            self.assertEqual(env.calls[1][1]["job_id"], "job_xyz")

    def test_apply_works_without_options(self):
        with _JobsApplyEnv() as env:
            cr_id = _propose_run(env, diff={
                "op": "run", "job_type": "doc_combine",
                "input_refs": ["ent_001"],
            })
            cr = get_cr(cr_id, db_path=env.db)
            apply_cr(cr)
            self.assertIsNone(env.calls[0][1]["options"])

    def test_base_hash_is_informational_for_run_jobs(self):
        # Unlike wiki_entity, run_jobs apply doesn't compare
        # base_hash to anything — the same base_hash that would
        # cause a wiki_entity to supersede is fine here.
        with _JobsApplyEnv() as env:
            cr_id = _propose_run(env, diff={
                "op": "run", "job_type": "excel_build",
                "input_refs": ["ent_001"],
            }, base_hash="any-string-at-all")
            cr = get_cr(cr_id, db_path=env.db)
            result = apply_cr(cr)
            self.assertTrue(result.applied)


# ─── Merge orchestrator integration ─────────────────────────────
class MergeIntegrationTests(unittest.TestCase):

    def test_merge_transitions_run_jobs_cr_to_merged(self):
        with _JobsApplyEnv(register_returns="job_aaa") as env:
            cr_id = _propose_run(env, diff={
                "op": "run", "job_type": "excel_build",
                "input_refs": ["ent_001"],
            })
            out = merge_cr(cr_id, approver="bob", db_path=env.db)
            self.assertEqual(out.status, STATUS_MERGED)
            self.assertEqual(out.merged_by, "bob")

    def test_execute_failure_leaves_cr_open(self):
        # Apply-time exception → invariant #5 (status stays 'open').
        with _JobsApplyEnv(execute_raises=RuntimeError("disk full")) as env:
            cr_id = _propose_run(env, diff={
                "op": "run", "job_type": "excel_build",
                "input_refs": ["ent_001"],
            })
            with self.assertRaises(RuntimeError):
                merge_cr(cr_id, approver="bob", db_path=env.db)
            self.assertEqual(
                get_cr(cr_id, db_path=env.db).status, STATUS_OPEN)

    def test_merge_blocks_self_approval_on_run_jobs(self):
        # Two-person rule fires regardless of target_type.
        with _JobsApplyEnv() as env:
            cr_id = _propose_run(env, diff={
                "op": "run", "job_type": "excel_build",
                "input_refs": ["ent_001"],
            }, proposer="alice")
            with self.assertRaises(ValueError):
                merge_cr(cr_id, approver="alice", db_path=env.db)
            # And nothing was registered — we refuse BEFORE the
            # apply path runs.
            self.assertEqual(env.calls, [])


# ─── Audit invariant #7 — merge writes one cr:merge row ─────────
class AuditTests(unittest.TestCase):

    def test_run_jobs_merge_emits_one_cr_merge_audit_row(self):
        from core import audit_bridge
        with _JobsApplyEnv(register_returns="job_zzz") as env:
            cr_id = _propose_run(env, diff={
                "op": "run", "job_type": "excel_build",
                "input_refs": ["ent_001"],
            })
            captured = []
            orig = audit_bridge.mirror_to_audit_db

            def _cap(entry, **kw):
                captured.append(dict(entry))
                return True
            audit_bridge.mirror_to_audit_db = _cap
            try:
                merge_cr(cr_id, approver="bob", db_path=env.db)
            finally:
                audit_bridge.mirror_to_audit_db = orig
            merge_events = [e for e in captured
                            if e.get("endpoint") == "cr:merge"]
            self.assertEqual(len(merge_events), 1)
            # job_id is on the audit row so post-hoc traceability
            # works (find the CR that triggered a given job).
            self.assertEqual(merge_events[0].get("new_hash"), "job_zzz")


# ─── Dispatch table contract ────────────────────────────────────
class DispatchContractTests(unittest.TestCase):

    def test_run_jobs_now_in_dispatch_table(self):
        self.assertIn(TARGET_RUN_JOBS, apply_mod._APPLY_DISPATCH)

    def test_dispatch_table_covers_every_valid_target_type(self):
        from core.change_request import VALID_TARGET_TYPES
        self.assertEqual(
            set(apply_mod._APPLY_DISPATCH.keys()),
            set(VALID_TARGET_TYPES),
            "every target_type the CR schema accepts must have an "
            "apply handler — otherwise proposers can file CRs that "
            "can never merge",
        )


if __name__ == "__main__":
    unittest.main()
