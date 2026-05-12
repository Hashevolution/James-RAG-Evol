"""[PR-CR-B2, 2026-05-12] Change Request HTTP endpoints.

Six endpoints under ``/admin/cr/`` back the CR primitive:

  POST   /admin/cr/                  propose       (auth user)
  GET    /admin/cr/                  list          (auth user)
  GET    /admin/cr/{cr_id}           detail        (auth user)
  POST   /admin/cr/{cr_id}/approve   merge target  (admin only)
  POST   /admin/cr/{cr_id}/reject    reject CR     (admin only)
  POST   /admin/cr/{cr_id}/review    comment       (auth user)

Each endpoint:
  - takes identity from the JWT subject claim (never from the
    request body — anti-impersonation),
  - returns 401 for missing JWT, 403 for non-admin trying to
    approve/reject, 400 for state-machine refusals,
  - mirrors transitions to ``audit_log`` via core.audit_bridge.

This suite drives the FastAPI app through ``TestClient`` to exercise
the end-to-end path: HTTP framing, auth, body parsing, state
machine, apply, and the JSON shape the workspace UI (CR-C) will
read.

Run:
    python -m unittest tests.test_change_request_endpoints
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault(
    "JAMES_JWT_SECRET",
    "test-secret-for-cr-endpoints-suite-32chars",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

import core.change_request as _cr_mod              # noqa: E402
import core.change_request_apply as _cr_apply      # noqa: E402
from core.change_request import compute_base_hash  # noqa: E402


def _read_api_key() -> str:
    env_v = os.environ.get("JAMES_API_KEY")
    if env_v:
        return env_v.strip()
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("JAMES_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


class _CrEndpointEnv:
    """Sets up a self-contained temp CR DB + temp wiki tree, swaps
    them into the production modules for the duration of one test,
    and tears everything back down on exit."""

    def __init__(self):
        self.cr_db: str = ""
        self.wiki_root: str = ""
        self.rel: str = ""
        self.original: bytes = b""
        self._prev_db: str = ""
        self._prev_wiki: str = ""

    def __enter__(self):
        # Temp CR DB.
        fd, self.cr_db = tempfile.mkstemp(suffix=".db", prefix="cr_ep_")
        os.close(fd)
        _cr_mod.init_db(self.cr_db)
        self._prev_db = _cr_mod._DEFAULT_DB
        _cr_mod._DEFAULT_DB = self.cr_db

        # Temp wiki tree with one concept entity.
        self.wiki_root = tempfile.mkdtemp(prefix="cr_ep_wiki_")
        target_dir = os.path.join(self.wiki_root, "entity", "prod", "concept")
        os.makedirs(target_dir)
        self.rel = "entity/prod/concept/ep_entity.md"
        self.original = (
            b"---\n"
            b"entity_id: e_concept_ep\n"
            b"---\n"
            b"# Original body\n"
        )
        with open(os.path.join(self.wiki_root, self.rel), "wb") as f:
            f.write(self.original)
        self._prev_wiki = _cr_apply._WIKI_ROOT
        _cr_apply._WIKI_ROOT = os.path.realpath(self.wiki_root)
        return self

    def __exit__(self, *exc):
        _cr_mod._DEFAULT_DB = self._prev_db
        _cr_apply._WIKI_ROOT = self._prev_wiki
        try:
            os.unlink(self.cr_db)
        except OSError:
            pass
        import shutil
        shutil.rmtree(self.wiki_root, ignore_errors=True)

    def base_hash(self) -> str:
        return compute_base_hash(self.original)


class EndpointTests(unittest.TestCase):
    """HTTP layer end-to-end. Skips when JAMES_API_KEY is not in env
    (matches the pattern used by test_admin_users_endpoints)."""

    @classmethod
    def setUpClass(cls):
        from core.auth import create_token
        cls._admin_token = create_token("admin-alice", "admin")
        cls._user_token  = create_token("user-bob",    "employee")
        cls._other_user_token = create_token("user-carol", "employee")
        cls._api_key     = _read_api_key()

    def setUp(self):
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing; cannot exercise admin route")

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def _admin(self):
        return {"Authorization": f"Bearer {self._admin_token}"}

    def _bob(self):
        return {"Authorization": f"Bearer {self._user_token}"}

    def _carol(self):
        return {"Authorization": f"Bearer {self._other_user_token}"}

    # ── propose ─────────────────────────────────────────────────
    def test_propose_creates_cr(self):
        with _CrEndpointEnv() as env:
            r = self._client().post(
                "/admin/cr/",
                json={
                    "api_key":     self._api_key,
                    "target_type": "wiki_entity",
                    "target_id":   env.rel,
                    "title":       "Update body",
                    "description": "minor",
                    "proposed_diff": {"op": "replace", "body": "# new\n"},
                    "base_hash":   env.base_hash(),
                    "labels":      ["docs"],
                },
                headers=self._bob(),
            )
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()
            self.assertTrue(body["ok"])
            cr = body["cr"]
            self.assertEqual(cr["status"],   "open")
            self.assertEqual(cr["proposer"], "user-bob")
            self.assertEqual(cr["title"],    "Update body")
            self.assertEqual(cr["labels"],   "docs")

    def test_propose_requires_jwt(self):
        # api_key alone isn't enough — body has no proposer field.
        with _CrEndpointEnv() as env:
            r = self._client().post(
                "/admin/cr/",
                json={
                    "api_key":     self._api_key,
                    "target_type": "wiki_entity",
                    "target_id":   env.rel,
                    "title":       "x",
                    "proposed_diff": {"op": "replace", "body": "x"},
                    "base_hash":   env.base_hash(),
                },
                # No Authorization header.
            )
            self.assertEqual(r.status_code, 401)

    def test_propose_rejects_unknown_target_type(self):
        with _CrEndpointEnv() as env:
            r = self._client().post(
                "/admin/cr/",
                json={
                    "api_key":     self._api_key,
                    "target_type": "legal_clause",
                    "target_id":   env.rel,
                    "title":       "x",
                    "proposed_diff": {"op": "replace", "body": "x"},
                    "base_hash":   env.base_hash(),
                },
                headers=self._bob(),
            )
            self.assertEqual(r.status_code, 400)

    # ── list ────────────────────────────────────────────────────
    def test_list_non_admin_sees_only_own_proposals(self):
        with _CrEndpointEnv() as env:
            client = self._client()
            for hdr, who in ((self._bob(),   "bob"),
                             (self._carol(), "carol")):
                client.post(
                    "/admin/cr/",
                    json={
                        "api_key":     self._api_key,
                        "target_type": "wiki_entity",
                        "target_id":   env.rel,
                        "title":       f"by {who}",
                        "proposed_diff": {"op": "replace", "body": who},
                        "base_hash":   env.base_hash(),
                    },
                    headers=hdr,
                )
            # Bob sees only his own; admin sees both.
            r_bob = client.get(
                "/admin/cr/",
                params={"api_key": self._api_key},
                headers=self._bob(),
            )
            self.assertEqual(r_bob.status_code, 200, r_bob.text)
            bob_titles = [c["title"] for c in r_bob.json()["items"]]
            self.assertEqual(bob_titles, ["by bob"])

            r_adm = client.get(
                "/admin/cr/",
                params={"api_key": self._api_key},
                headers=self._admin(),
            )
            self.assertEqual(len(r_adm.json()["items"]), 2)

    # ── detail ──────────────────────────────────────────────────
    def test_detail_404_when_missing(self):
        with _CrEndpointEnv():
            r = self._client().get(
                "/admin/cr/cr_does_not_exist",
                params={"api_key": self._api_key},
                headers=self._admin(),
            )
            self.assertEqual(r.status_code, 404)

    def test_detail_blocks_unrelated_user(self):
        # carol can't see bob's CR (not proposer, not reviewer).
        with _CrEndpointEnv() as env:
            client = self._client()
            r = client.post(
                "/admin/cr/",
                json={
                    "api_key":     self._api_key,
                    "target_type": "wiki_entity",
                    "target_id":   env.rel,
                    "title":       "secret",
                    "proposed_diff": {"op": "replace", "body": "x"},
                    "base_hash":   env.base_hash(),
                },
                headers=self._bob(),
            )
            cr_id = r.json()["cr"]["cr_id"]
            r2 = client.get(
                f"/admin/cr/{cr_id}",
                params={"api_key": self._api_key},
                headers=self._carol(),
            )
            self.assertEqual(r2.status_code, 403)

    def test_detail_includes_reviews(self):
        with _CrEndpointEnv() as env:
            client = self._client()
            r = client.post(
                "/admin/cr/",
                json={
                    "api_key":     self._api_key,
                    "target_type": "wiki_entity",
                    "target_id":   env.rel,
                    "title":       "t",
                    "proposed_diff": {"op": "replace", "body": "x"},
                    "base_hash":   env.base_hash(),
                },
                headers=self._bob(),
            )
            cr_id = r.json()["cr"]["cr_id"]
            client.post(
                f"/admin/cr/{cr_id}/review",
                json={"api_key": self._api_key,
                      "decision": "comment", "body": "hi"},
                headers=self._carol(),
            )
            r2 = client.get(
                f"/admin/cr/{cr_id}",
                params={"api_key": self._api_key},
                headers=self._admin(),
            )
            self.assertEqual(r2.status_code, 200, r2.text)
            self.assertEqual(len(r2.json()["reviews"]), 1)

    # ── approve / reject ────────────────────────────────────────
    def test_approve_requires_admin(self):
        with _CrEndpointEnv() as env:
            client = self._client()
            r = client.post(
                "/admin/cr/",
                json={
                    "api_key":     self._api_key,
                    "target_type": "wiki_entity",
                    "target_id":   env.rel,
                    "title":       "t",
                    "proposed_diff": {"op": "replace", "body": "# new\n"},
                    "base_hash":   env.base_hash(),
                },
                headers=self._bob(),
            )
            cr_id = r.json()["cr"]["cr_id"]
            r2 = client.post(
                f"/admin/cr/{cr_id}/approve",
                json={"api_key": self._api_key},
                headers=self._carol(),       # employee, not admin
            )
            self.assertEqual(r2.status_code, 403)

    def test_approve_merges_and_writes_file(self):
        with _CrEndpointEnv() as env:
            client = self._client()
            r = client.post(
                "/admin/cr/",
                json={
                    "api_key":     self._api_key,
                    "target_type": "wiki_entity",
                    "target_id":   env.rel,
                    "title":       "t",
                    "proposed_diff": {"op": "replace", "body": "# new content\n"},
                    "base_hash":   env.base_hash(),
                },
                headers=self._bob(),
            )
            cr_id = r.json()["cr"]["cr_id"]
            r2 = client.post(
                f"/admin/cr/{cr_id}/approve",
                json={"api_key": self._api_key},
                headers=self._admin(),
            )
            self.assertEqual(r2.status_code, 200, r2.text)
            self.assertEqual(r2.json()["cr"]["status"],    "merged")
            self.assertEqual(r2.json()["cr"]["merged_by"], "admin-alice")
            # File on disk got rewritten.
            with open(os.path.join(env.wiki_root, env.rel), "rb") as f:
                self.assertEqual(f.read(), b"# new content\n")

    def test_approve_409_on_missing_target(self):
        with _CrEndpointEnv() as env:
            client = self._client()
            r = client.post(
                "/admin/cr/",
                json={
                    "api_key":     self._api_key,
                    "target_type": "wiki_entity",
                    "target_id":   env.rel,
                    "title":       "t",
                    "proposed_diff": {"op": "replace", "body": "x"},
                    "base_hash":   env.base_hash(),
                },
                headers=self._bob(),
            )
            cr_id = r.json()["cr"]["cr_id"]
            os.unlink(os.path.join(env.wiki_root, env.rel))
            r2 = client.post(
                f"/admin/cr/{cr_id}/approve",
                json={"api_key": self._api_key},
                headers=self._admin(),
            )
            self.assertEqual(r2.status_code, 409)

    def test_approve_400_on_self_approval(self):
        # Admin propose + admin approve = self-approval.
        with _CrEndpointEnv() as env:
            client = self._client()
            r = client.post(
                "/admin/cr/",
                json={
                    "api_key":     self._api_key,
                    "target_type": "wiki_entity",
                    "target_id":   env.rel,
                    "title":       "self",
                    "proposed_diff": {"op": "replace", "body": "x"},
                    "base_hash":   env.base_hash(),
                },
                headers=self._admin(),
            )
            cr_id = r.json()["cr"]["cr_id"]
            r2 = client.post(
                f"/admin/cr/{cr_id}/approve",
                json={"api_key": self._api_key},
                headers=self._admin(),
            )
            self.assertEqual(r2.status_code, 400)

    def test_reject_requires_admin(self):
        with _CrEndpointEnv() as env:
            client = self._client()
            r = client.post(
                "/admin/cr/",
                json={
                    "api_key":     self._api_key,
                    "target_type": "wiki_entity",
                    "target_id":   env.rel,
                    "title":       "t",
                    "proposed_diff": {"op": "replace", "body": "x"},
                    "base_hash":   env.base_hash(),
                },
                headers=self._bob(),
            )
            cr_id = r.json()["cr"]["cr_id"]
            r2 = client.post(
                f"/admin/cr/{cr_id}/reject",
                json={"api_key": self._api_key, "reason": "no"},
                headers=self._bob(),
            )
            self.assertEqual(r2.status_code, 403)

    def test_reject_transitions_to_rejected(self):
        with _CrEndpointEnv() as env:
            client = self._client()
            r = client.post(
                "/admin/cr/",
                json={
                    "api_key":     self._api_key,
                    "target_type": "wiki_entity",
                    "target_id":   env.rel,
                    "title":       "t",
                    "proposed_diff": {"op": "replace", "body": "x"},
                    "base_hash":   env.base_hash(),
                },
                headers=self._bob(),
            )
            cr_id = r.json()["cr"]["cr_id"]
            r2 = client.post(
                f"/admin/cr/{cr_id}/reject",
                json={"api_key": self._api_key, "reason": "not now"},
                headers=self._admin(),
            )
            self.assertEqual(r2.status_code, 200, r2.text)
            self.assertEqual(r2.json()["cr"]["status"],        "rejected")
            self.assertEqual(r2.json()["cr"]["reject_reason"], "not now")

    # ── review ──────────────────────────────────────────────────
    def test_review_comment_does_not_change_status(self):
        with _CrEndpointEnv() as env:
            client = self._client()
            r = client.post(
                "/admin/cr/",
                json={
                    "api_key":     self._api_key,
                    "target_type": "wiki_entity",
                    "target_id":   env.rel,
                    "title":       "t",
                    "proposed_diff": {"op": "replace", "body": "x"},
                    "base_hash":   env.base_hash(),
                },
                headers=self._bob(),
            )
            cr_id = r.json()["cr"]["cr_id"]
            r2 = client.post(
                f"/admin/cr/{cr_id}/review",
                json={"api_key": self._api_key,
                      "decision": "comment", "body": "lgtm"},
                headers=self._carol(),
            )
            self.assertEqual(r2.status_code, 200, r2.text)
            # CR still open.
            r3 = client.get(
                f"/admin/cr/{cr_id}",
                params={"api_key": self._api_key},
                headers=self._admin(),
            )
            self.assertEqual(r3.json()["cr"]["status"], "open")

    def test_review_rejects_unknown_decision(self):
        with _CrEndpointEnv() as env:
            client = self._client()
            r = client.post(
                "/admin/cr/",
                json={
                    "api_key":     self._api_key,
                    "target_type": "wiki_entity",
                    "target_id":   env.rel,
                    "title":       "t",
                    "proposed_diff": {"op": "replace", "body": "x"},
                    "base_hash":   env.base_hash(),
                },
                headers=self._bob(),
            )
            cr_id = r.json()["cr"]["cr_id"]
            r2 = client.post(
                f"/admin/cr/{cr_id}/review",
                json={"api_key": self._api_key,
                      "decision": "lgtm-ish"},
                headers=self._carol(),
            )
            self.assertEqual(r2.status_code, 400)


if __name__ == "__main__":
    unittest.main()
