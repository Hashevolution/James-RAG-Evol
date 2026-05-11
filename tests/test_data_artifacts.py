"""W7-A — data artifact lifecycle + admin/own endpoints.

Three layers:
  1. core.data_artifacts helpers — pure DB roundtrip.
  2. backfill_from_uploads_dir — first-boot scan idempotence.
  3. HTTP endpoints — admin.data + data.view_own feature gates,
     own-only scoping (cross-user 404 defense), JSON shapes.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault(
    "JAMES_JWT_SECRET",
    "test-secret-for-data-artifacts-32chars-min",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


def _api_key() -> str:
    env_v = os.environ.get("JAMES_API_KEY")
    if env_v:
        return env_v.strip()
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("JAMES_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


class _DataDBFixture(unittest.TestCase):
    """Point ``core.data_artifacts._DB_PATH`` at a fresh tmp file +
    create the schema. Restored in tearDown so tests don't leak state."""

    def setUp(self):
        from core import data_artifacts as da
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db = self._tmp.name
        self._saved = da._DB_PATH
        da._DB_PATH = self.db
        # _init_db only ran at module import (against the live path) —
        # explicitly create the schema in the tmp db.
        da._init_db()

    def tearDown(self):
        from core import data_artifacts as da
        da._DB_PATH = self._saved
        Path(self.db).unlink(missing_ok=True)


class HelperTests(_DataDBFixture):
    def test_register_returns_artifact_id_and_persists(self):
        from core.data_artifacts import register_artifact, get_artifact
        aid = register_artifact(
            origin_path="uploads/x_a.pdf",
            origin_name="a.pdf",
            origin_size=1024,
            uploaded_by="alice",
        )
        self.assertTrue(aid)
        row = get_artifact(aid)
        self.assertIsNotNone(row)
        self.assertEqual(row["origin_name"], "a.pdf")
        self.assertEqual(row["uploaded_by"], "alice")
        self.assertEqual(row["status"], "uploaded")
        self.assertEqual(row["entities"], [])

    def test_register_rejects_unknown_status(self):
        from core.data_artifacts import register_artifact
        with self.assertRaises(ValueError):
            register_artifact("uploads/x", "x", 0, "alice", status="garbage")

    def test_update_status_moves_through_lifecycle(self):
        from core.data_artifacts import (
            register_artifact, update_status, get_artifact,
        )
        aid = register_artifact("uploads/x", "x", 0, "alice")
        for st in ("extracted", "indexed", "failed"):
            self.assertTrue(update_status(aid, st))
            self.assertEqual(get_artifact(aid)["status"], st)

    def test_update_status_unknown_id_returns_false(self):
        from core.data_artifacts import update_status
        self.assertFalse(update_status("no-such-id", "indexed"))

    def test_link_entity_idempotent(self):
        from core.data_artifacts import (
            register_artifact, link_entity, get_artifact,
        )
        aid = register_artifact("uploads/x", "x", 0, "alice")
        self.assertTrue(link_entity(aid, "ent_001"))
        # Second link to the same pair is a no-op (PK conflict).
        self.assertFalse(link_entity(aid, "ent_001"))
        self.assertTrue(link_entity(aid, "ent_002"))
        row = get_artifact(aid)
        self.assertEqual(sorted(row["entities"]), ["ent_001", "ent_002"])

    def test_get_artifact_owner_scope(self):
        from core.data_artifacts import register_artifact, get_artifact
        aid = register_artifact("uploads/x", "x", 0, "alice")
        # Owner view works.
        self.assertIsNotNone(get_artifact(aid, requester_username="alice"))
        # Other user is denied (None — caller surfaces 404).
        self.assertIsNone(get_artifact(aid, requester_username="bob"))
        # Admin (no requester) sees the row.
        self.assertIsNotNone(get_artifact(aid))


class ListAndCountTests(_DataDBFixture):
    def setUp(self):
        super().setUp()
        from core.data_artifacts import register_artifact
        register_artifact("uploads/1", "alice-report.pdf", 100, "alice", "indexed")
        register_artifact("uploads/2", "alice-notes.txt", 200, "alice", "uploaded")
        register_artifact("uploads/3", "bob-data.csv", 300, "bob", "indexed")

    def test_list_admin_view_returns_all(self):
        from core.data_artifacts import list_artifacts, count_artifacts
        self.assertEqual(count_artifacts(), 3)
        self.assertEqual(len(list_artifacts()), 3)

    def test_list_scoped_to_username(self):
        from core.data_artifacts import list_artifacts, count_artifacts
        rows = list_artifacts(username="alice")
        self.assertEqual({r["origin_name"] for r in rows},
                         {"alice-report.pdf", "alice-notes.txt"})
        self.assertEqual(count_artifacts(username="alice"), 2)
        self.assertEqual(count_artifacts(username="bob"), 1)

    def test_status_filter(self):
        from core.data_artifacts import list_artifacts
        names = [r["origin_name"] for r in list_artifacts(status="indexed")]
        self.assertEqual(sorted(names), ["alice-report.pdf", "bob-data.csv"])

    def test_q_substring(self):
        from core.data_artifacts import list_artifacts
        names = [r["origin_name"] for r in list_artifacts(q="alice")]
        self.assertEqual(len(names), 2)
        self.assertTrue(all("alice" in n for n in names))

    def test_sort_newest_first(self):
        from core.data_artifacts import register_artifact, list_artifacts
        # uploaded_at is unix-second precision; sleep > 1s so the
        # next insert lands in a later bucket regardless of how fast
        # the prior setUp inserts ran.
        time.sleep(1.1)
        register_artifact("uploads/late", "late.pdf", 999, "alice", "indexed")
        names = [r["origin_name"] for r in list_artifacts()]
        self.assertEqual(names[0], "late.pdf",
                         "newest insertion must surface first")

    def test_entity_count_in_list(self):
        from core.data_artifacts import (
            register_artifact, link_entity, list_artifacts,
        )
        aid = register_artifact("uploads/x", "x.pdf", 0, "alice", "indexed")
        link_entity(aid, "ent_1")
        link_entity(aid, "ent_2")
        row = next(r for r in list_artifacts() if r["origin_name"] == "x.pdf")
        self.assertEqual(row["entity_count"], 2)


class BackfillTests(_DataDBFixture):
    def test_inserts_files_with_legacy_owner(self):
        from core.data_artifacts import (
            backfill_from_uploads_dir, list_artifacts,
        )
        with tempfile.TemporaryDirectory() as ud:
            for name in ("aaa_first.pdf", "bbb_second.txt"):
                with open(os.path.join(ud, name), "w") as f:
                    f.write("x")
            n = backfill_from_uploads_dir(ud)
            self.assertEqual(n, 2)
            rows = list_artifacts()
            self.assertEqual({r["uploaded_by"] for r in rows}, {"legacy"})
            self.assertEqual({r["origin_name"] for r in rows},
                             {"first.pdf", "second.txt"})
            self.assertTrue(all(r["status"] == "indexed" for r in rows),
                            "backfill should mark indexed — files are in corpus")

    def test_idempotent_on_second_run(self):
        from core.data_artifacts import (
            backfill_from_uploads_dir, count_artifacts,
        )
        with tempfile.TemporaryDirectory() as ud:
            with open(os.path.join(ud, "u_a.pdf"), "w") as f:
                f.write("x")
            n1 = backfill_from_uploads_dir(ud)
            n2 = backfill_from_uploads_dir(ud)
            self.assertEqual(n1, 1)
            self.assertEqual(n2, 0,
                             "rerun must not double-insert legacy rows")
            self.assertEqual(count_artifacts(), 1)

    def test_no_underscore_filename_keeps_full_name(self):
        from core.data_artifacts import backfill_from_uploads_dir, list_artifacts
        with tempfile.TemporaryDirectory() as ud:
            with open(os.path.join(ud, "naked.pdf"), "w") as f:
                f.write("x")
            backfill_from_uploads_dir(ud)
            self.assertEqual(list_artifacts()[0]["origin_name"], "naked.pdf")

    def test_missing_dir_returns_zero(self):
        from core.data_artifacts import backfill_from_uploads_dir
        self.assertEqual(backfill_from_uploads_dir("/no/such/path"), 0)


class EndpointTests(_DataDBFixture):
    @classmethod
    def setUpClass(cls):
        cls._api_key = _api_key()

    def setUp(self):
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing")
        super().setUp()
        from core.data_artifacts import register_artifact
        self.alice_aid = register_artifact(
            "uploads/u1_alice.pdf", "alice.pdf", 100, "alice", "indexed",
        )
        self.bob_aid = register_artifact(
            "uploads/u2_bob.pdf", "bob.pdf", 200, "bob", "indexed",
        )

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def _hdr(self, username: str, role: str):
        from core.auth import create_token
        return {"Authorization": f"Bearer {create_token(username, role)}"}

    # ── admin view ────────────────────────────────────────────────
    def test_admin_list_sees_all_users(self):
        r = self._client().get(
            "/admin/artifacts/list",
            params={"api_key": self._api_key},
            headers=self._hdr("test-admin", "admin"),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["total"], 2)
        uploaders = {it["uploaded_by"] for it in body["items"]}
        self.assertEqual(uploaders, {"alice", "bob"})

    def test_admin_list_blocked_for_employee(self):
        r = self._client().get(
            "/admin/artifacts/list",
            params={"api_key": self._api_key},
            headers=self._hdr("emp1", "employee"),
        )
        self.assertEqual(r.status_code, 403)

    def test_admin_detail_returns_full_row(self):
        r = self._client().get(
            f"/admin/artifacts/{self.alice_aid}",
            params={"api_key": self._api_key},
            headers=self._hdr("test-admin", "admin"),
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["origin_name"], "alice.pdf")

    def test_admin_detail_404_unknown(self):
        r = self._client().get(
            "/admin/artifacts/no-such-id",
            params={"api_key": self._api_key},
            headers=self._hdr("test-admin", "admin"),
        )
        self.assertEqual(r.status_code, 404)

    # ── own (mine) view ───────────────────────────────────────────
    def test_mine_list_scoped_to_jwt_subject(self):
        # alice JWT — sees only alice's row.
        r = self._client().get(
            "/artifacts/mine/list",
            params={"api_key": self._api_key},
            headers=self._hdr("alice", "employee"),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["uploaded_by"], "alice")

    def test_mine_list_requires_jwt(self):
        r = self._client().get(
            "/artifacts/mine/list",
            params={"api_key": self._api_key},
        )
        self.assertEqual(r.status_code, 401)

    def test_mine_detail_own_path_works(self):
        r = self._client().get(
            f"/artifacts/mine/{self.alice_aid}",
            params={"api_key": self._api_key},
            headers=self._hdr("alice", "employee"),
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["uploaded_by"], "alice")

    def test_mine_detail_cross_user_returns_404_not_403(self):
        # bob asks for alice's artifact id — must surface as 404,
        # not 403. 403 leaks the existence of the id.
        r = self._client().get(
            f"/artifacts/mine/{self.alice_aid}",
            params={"api_key": self._api_key},
            headers=self._hdr("bob", "employee"),
        )
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
