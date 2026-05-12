"""[PR-CR-B2, 2026-05-12] wiki_entity apply path + merge orchestrator.

CR-B2 plugs the state machine from CR-B1 into a real target —
markdown files under ``wiki/entity/``. The apply layer:

  - resolves ``target_id`` to a path UNDER ``wiki/entity/`` (path-
    traversal guard, must end ``.md``, no ``..``),
  - reads the current file and verifies ``base_hash`` (invariant #3),
  - atomically replaces the file via ``tempfile + os.replace``,
  - returns an ``ApplyResult`` the orchestrator turns into a
    ``status='merged'`` transition.

This suite covers the apply layer end-to-end, including invariants
#3 (base_hash mismatch → superseded, no write), #5 (apply failure
leaves status='open'), and #7 (merge writes one audit row).

Run:
    python -m unittest tests.test_change_request_wiki_apply
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.change_request as cr_mod              # noqa: E402
import core.change_request_apply as apply_mod     # noqa: E402
from core.change_request import (                 # noqa: E402
    STATUS_OPEN, STATUS_MERGED, STATUS_SUPERSEDED,
    TARGET_WIKI_ENTITY,
    init_db, create_cr, get_cr, compute_base_hash,
)
from core.change_request_apply import (           # noqa: E402
    apply_cr, merge_cr,
)


def _fresh_environment():
    """Returns (db_path, wiki_root, target_rel_path, current_bytes).

    Builds a self-contained wiki tree with one concept entity and
    points the apply module's WIKI_ROOT at it for the duration of
    this test. Caller is responsible for cleanup of returned paths
    (unittest tearDown).
    """
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="cr_test_")
    os.close(fd)
    init_db(db_path)
    wiki_root = tempfile.mkdtemp(prefix="cr_wiki_")
    concept_dir = os.path.join(wiki_root, "entity", "prod", "concept")
    os.makedirs(concept_dir)
    rel_path  = "entity/prod/concept/test_entity.md"
    abs_path  = os.path.join(wiki_root, rel_path)
    content   = (
        b"---\n"
        b"entity_id: e_concept_test\n"
        b"aliases:\n- Test Entity\n"
        b"---\n"
        b"# Test Entity\n\nOriginal body line.\n"
    )
    with open(abs_path, "wb") as f:
        f.write(content)
    return db_path, wiki_root, rel_path, content


class _ApplyEnv:
    """Context manager that swaps in a temp wiki root and tears down
    every fixture on exit."""
    def __init__(self):
        self.db_path: str = ""
        self.wiki_root: str = ""
        self.rel: str = ""
        self.original: bytes = b""
        self._prev_root: str = ""

    def __enter__(self):
        self.db_path, self.wiki_root, self.rel, self.original = _fresh_environment()
        self._prev_root = apply_mod._WIKI_ROOT
        apply_mod._WIKI_ROOT = os.path.realpath(self.wiki_root)
        return self

    def __exit__(self, *exc):
        apply_mod._WIKI_ROOT = self._prev_root
        try:
            os.unlink(self.db_path)
        except OSError:
            pass
        try:
            # Clean the wiki tree.
            import shutil
            shutil.rmtree(self.wiki_root, ignore_errors=True)
        except Exception:
            pass

    def abs_target(self) -> str:
        return os.path.join(self.wiki_root, self.rel)

    def make_cr(self, *, body_text: str = "# NEW body\n",
                proposer: str = "alice",
                target_id: str = None) -> str:
        """Helper — create a CR proposing to replace the target's
        body with ``body_text``. Returns cr_id."""
        bh = compute_base_hash(self.original)
        cr = create_cr(
            target_type=TARGET_WIKI_ENTITY,
            target_id=target_id or self.rel,
            title="t", proposed_diff={"op": "replace", "body": body_text},
            base_hash=bh, proposer=proposer,
            db_path=self.db_path,
        )
        return cr.cr_id


# ─── Path resolution (invariant: no traversal, must be under wiki/entity/) ─
class WikiPathResolutionTests(unittest.TestCase):

    def test_normal_path_resolves(self):
        with _ApplyEnv() as env:
            resolved = apply_mod._resolve_wiki_path(env.rel)
            self.assertTrue(resolved.endswith(env.rel.replace("/", os.sep)))

    def test_rejects_dotdot_traversal(self):
        with _ApplyEnv():
            with self.assertRaises(ValueError):
                apply_mod._resolve_wiki_path("entity/../etc/passwd")

    def test_rejects_path_outside_entity_subtree(self):
        with _ApplyEnv():
            with self.assertRaises(ValueError):
                apply_mod._resolve_wiki_path("synonyms.yaml")
            with self.assertRaises(ValueError):
                apply_mod._resolve_wiki_path("../etc/passwd")

    def test_rejects_non_md_extension(self):
        with _ApplyEnv():
            with self.assertRaises(ValueError):
                apply_mod._resolve_wiki_path("entity/prod/concept/x.py")

    def test_rejects_empty_target_id(self):
        with _ApplyEnv():
            with self.assertRaises(ValueError):
                apply_mod._resolve_wiki_path("")

    def test_accepts_windows_separator(self):
        # Proposers on Windows clients sometimes ship a backslash —
        # we normalise it (no traversal injection possible since '..'
        # check happens on the normalised form).
        with _ApplyEnv() as env:
            backslashed = env.rel.replace("/", "\\")
            resolved = apply_mod._resolve_wiki_path(backslashed)
            self.assertTrue(os.path.exists(resolved))


# ─── apply_cr — wiki_entity dispatch ─────────────────────────────
class ApplyDispatchTests(unittest.TestCase):

    def test_unknown_target_type_raises(self):
        # Reaching the dispatcher with an unknown type means someone
        # smuggled a row past create_cr — must fail loud.
        from dataclasses import replace
        with _ApplyEnv() as env:
            cr_id = env.make_cr()
            cr = get_cr(cr_id, db_path=env.db_path)
            broken = replace(cr, target_type="legal_clause")
            with self.assertRaises(ValueError):
                apply_cr(broken)

    def test_apply_replaces_file_on_match(self):
        with _ApplyEnv() as env:
            cr_id = env.make_cr(body_text="# NEW body\n")
            cr = get_cr(cr_id, db_path=env.db_path)
            result = apply_cr(cr)
            self.assertTrue(result.applied)
            self.assertFalse(result.superseded)
            self.assertIsNotNone(result.new_hash)
            with open(env.abs_target(), "rb") as f:
                self.assertEqual(f.read(), b"# NEW body\n")

    def test_apply_supersedes_on_hash_mismatch(self):
        # Pre-condition: target file has shifted since the CR was
        # proposed. apply MUST return supersede + leave the file
        # untouched.
        with _ApplyEnv() as env:
            cr_id = env.make_cr(body_text="# would-be new\n")
            # Outside writer mutates the target.
            with open(env.abs_target(), "wb") as f:
                f.write(b"# someone else's edit\n")
            cr = get_cr(cr_id, db_path=env.db_path)
            result = apply_cr(cr)
            self.assertTrue(result.superseded)
            self.assertFalse(result.applied)
            self.assertIn("rebase", result.reason.lower())
            # The outsider's content stays.
            with open(env.abs_target(), "rb") as f:
                self.assertEqual(f.read(), b"# someone else's edit\n")

    def test_apply_raises_on_missing_target(self):
        with _ApplyEnv() as env:
            cr_id = env.make_cr()
            os.unlink(env.abs_target())
            cr = get_cr(cr_id, db_path=env.db_path)
            with self.assertRaises(FileNotFoundError):
                apply_cr(cr)

    def test_apply_rejects_unsupported_op(self):
        with _ApplyEnv() as env:
            # Bypass create_cr's validation by writing the row directly
            # — we want to exercise the apply-side guard.
            import sqlite3, time
            bh = compute_base_hash(env.original)
            conn = sqlite3.connect(env.db_path)
            now = int(time.time())
            conn.execute(
                "INSERT INTO change_requests "
                "(cr_id, target_type, target_id, title, "
                " proposed_diff, base_hash, proposer, status, "
                " created_at, updated_at) "
                "VALUES (?, ?, ?, 't', ?, ?, 'alice', 'open', ?, ?)",
                ("cr_bad", "wiki_entity", env.rel,
                 json.dumps({"op": "delete"}), bh, now, now),
            )
            conn.commit()
            conn.close()
            cr = get_cr("cr_bad", db_path=env.db_path)
            with self.assertRaises(ValueError):
                apply_cr(cr)

    def test_apply_rejects_non_string_body(self):
        with _ApplyEnv() as env:
            import sqlite3, time
            bh = compute_base_hash(env.original)
            conn = sqlite3.connect(env.db_path)
            now = int(time.time())
            conn.execute(
                "INSERT INTO change_requests "
                "(cr_id, target_type, target_id, title, "
                " proposed_diff, base_hash, proposer, status, "
                " created_at, updated_at) "
                "VALUES (?, ?, ?, 't', ?, ?, 'alice', 'open', ?, ?)",
                ("cr_bad2", "wiki_entity", env.rel,
                 json.dumps({"op": "replace", "body": 12345}),
                 bh, now, now),
            )
            conn.commit()
            conn.close()
            cr = get_cr("cr_bad2", db_path=env.db_path)
            with self.assertRaises(ValueError):
                apply_cr(cr)

    def test_apply_preserves_utf8(self):
        with _ApplyEnv() as env:
            korean_body = "# 한국어 본문\n\n변경된 내용입니다.\n"
            cr_id = env.make_cr(body_text=korean_body)
            cr = get_cr(cr_id, db_path=env.db_path)
            apply_cr(cr)
            with open(env.abs_target(), "rb") as f:
                self.assertEqual(f.read().decode("utf-8"), korean_body)


# ─── merge_cr — orchestrator + invariants ────────────────────────
class MergeOrchestratorTests(unittest.TestCase):

    def test_merge_transitions_to_merged(self):
        with _ApplyEnv() as env:
            cr_id = env.make_cr()
            out = merge_cr(cr_id, approver="bob", db_path=env.db_path)
            self.assertEqual(out.status, STATUS_MERGED)
            self.assertEqual(out.merged_by, "bob")
            self.assertIsNotNone(out.merged_at)

    def test_merge_blocks_self_approval(self):
        with _ApplyEnv() as env:
            cr_id = env.make_cr(proposer="alice")
            with self.assertRaises(ValueError):
                merge_cr(cr_id, approver="alice", db_path=env.db_path)
            # CR stays open.
            self.assertEqual(
                get_cr(cr_id, db_path=env.db_path).status, STATUS_OPEN)

    def test_merge_routes_supersede_on_base_hash_mismatch(self):
        with _ApplyEnv() as env:
            cr_id = env.make_cr()
            with open(env.abs_target(), "wb") as f:
                f.write(b"# someone else edited\n")
            out = merge_cr(cr_id, approver="bob", db_path=env.db_path)
            self.assertEqual(out.status, STATUS_SUPERSEDED)
            # Outsider's bytes survive — apply must NOT have written.
            with open(env.abs_target(), "rb") as f:
                self.assertEqual(f.read(), b"# someone else edited\n")

    def test_merge_apply_failure_leaves_open(self):
        # Target missing on disk → apply raises FileNotFoundError →
        # invariant #5 says CR stays open.
        with _ApplyEnv() as env:
            cr_id = env.make_cr()
            os.unlink(env.abs_target())
            with self.assertRaises(FileNotFoundError):
                merge_cr(cr_id, approver="bob", db_path=env.db_path)
            self.assertEqual(
                get_cr(cr_id, db_path=env.db_path).status, STATUS_OPEN)

    def test_merge_blocks_already_merged(self):
        with _ApplyEnv() as env:
            cr_id = env.make_cr()
            merge_cr(cr_id, approver="bob", db_path=env.db_path)
            with self.assertRaises(ValueError):
                merge_cr(cr_id, approver="bob", db_path=env.db_path)

    def test_merge_blocks_rejected_cr(self):
        with _ApplyEnv() as env:
            cr_id = env.make_cr()
            cr_mod.reject_cr(cr_id, reviewer="bob",
                             db_path=env.db_path)
            with self.assertRaises(ValueError):
                merge_cr(cr_id, approver="carol", db_path=env.db_path)

    def test_merge_missing_cr(self):
        with _ApplyEnv() as env:
            with self.assertRaises(ValueError):
                merge_cr("cr_does_not_exist", approver="bob",
                         db_path=env.db_path)

    def test_merge_requires_approver(self):
        with _ApplyEnv() as env:
            cr_id = env.make_cr()
            with self.assertRaises(ValueError):
                merge_cr(cr_id, approver="", db_path=env.db_path)


# ─── Audit invariant #7 — merge writes one cr:merge row ──────────
class MergeAuditTests(unittest.TestCase):

    def test_merge_emits_one_audit_row(self):
        from core import audit_bridge
        with _ApplyEnv() as env:
            cr_id = env.make_cr()
            captured = []
            orig = audit_bridge.mirror_to_audit_db

            def _cap(entry, **kw):
                captured.append(dict(entry))
                return True
            audit_bridge.mirror_to_audit_db = _cap
            try:
                merge_cr(cr_id, approver="bob", db_path=env.db_path)
            finally:
                audit_bridge.mirror_to_audit_db = orig
            # Exactly one cr:merge event from this merge call.
            merge_events = [e for e in captured
                            if e.get("endpoint") == "cr:merge"]
            self.assertEqual(len(merge_events), 1)
            self.assertEqual(merge_events[0]["event"], "cr.merge")
            self.assertEqual(merge_events[0]["target"], cr_id)

    def test_supersede_path_emits_cr_supersede_not_cr_merge(self):
        from core import audit_bridge
        with _ApplyEnv() as env:
            cr_id = env.make_cr()
            with open(env.abs_target(), "wb") as f:
                f.write(b"# drifted\n")
            captured = []
            orig = audit_bridge.mirror_to_audit_db

            def _cap(entry, **kw):
                captured.append(dict(entry))
                return True
            audit_bridge.mirror_to_audit_db = _cap
            try:
                merge_cr(cr_id, approver="bob", db_path=env.db_path)
            finally:
                audit_bridge.mirror_to_audit_db = orig
            kinds = {e.get("endpoint") for e in captured}
            self.assertIn("cr:supersede", kinds)
            self.assertNotIn("cr:merge", kinds)


# ─── Module size + import contract ───────────────────────────────
class ModuleContractTests(unittest.TestCase):

    def test_apply_module_under_size_gate(self):
        size = Path(apply_mod.__file__).stat().st_size
        self.assertLess(size, 20 * 1024,
            f"core/change_request_apply.py = {size}B; "
            "CLAUDE.md rule #5 caps at 20 KB")

    def test_state_module_still_under_gate(self):
        # If merge_cr ever migrates into change_request.py this test
        # is the canary that catches the regression.
        size = Path(cr_mod.__file__).stat().st_size
        self.assertLess(size, 20 * 1024,
            f"core/change_request.py = {size}B; over the gate")

    def test_apply_dispatch_matches_valid_target_types(self):
        # The dispatch table must cover every v0.2.x target_type
        # the schema allows — adding a target_type without an apply
        # handler would let proposers file CRs that can never merge.
        # ``run_jobs`` joined in PR-CR-D; see
        # tests/test_change_request_jobs_apply.py for that target's
        # behaviour suite.
        from core.change_request import VALID_TARGET_TYPES
        self.assertEqual(
            set(apply_mod._APPLY_DISPATCH.keys()),
            set(VALID_TARGET_TYPES),
        )


if __name__ == "__main__":
    unittest.main()
