"""v0.6 — routes/templating.py tests (PR-3).

Builds a minimal FastAPI app with just the templating router, overrides
the role dependency, stubs the JWT subject + the LLM call, and isolates
the workspace to a temp dir. Covers the full lifecycle + owner scoping +
login gate + the server registers the routes.

Run:
  python -m unittest tests.test_v06_templating_routes
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_client(user="alice", role="admin"):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routes.templating as tr
    from routes._helpers import get_role_from_request

    app = FastAPI()
    app.include_router(tr.router)
    app.dependency_overrides[get_role_from_request] = lambda: role
    tr._bearer_username = lambda request: user  # noqa: stub JWT subject
    return TestClient(app), tr


class TemplatingRoutesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="james_tpl_routes_")
        self._prev = os.environ.get("JAMES_WORKSPACE")
        os.environ["JAMES_WORKSPACE"] = self._tmp
        # Stub the LLM so apply() is deterministic + offline.
        import llm.router as router
        self._orig_call = router.call_router
        router.call_router = lambda prompt, **kw: "# Filled\nfrom raw content"
        self._router = router

    def tearDown(self):
        self._router.call_router = self._orig_call
        if self._prev is None:
            os.environ.pop("JAMES_WORKSPACE", None)
        else:
            os.environ["JAMES_WORKSPACE"] = self._prev

    def test_full_lifecycle(self):
        client, _ = _make_client(user="alice")
        # create
        r = client.post("/templates/", json={
            "name": "My Report", "raw_text": "# Title\n{{author}}\n",
            "mode": "text"})
        self.assertEqual(r.status_code, 200, r.text)
        tid = r.json()["id"]
        self.assertTrue(tid.startswith("my-report-"))

        # list
        r = client.get("/templates/mine/list")
        self.assertEqual([m["id"] for m in r.json()["items"]], [tid])

        # detail w/ parsed spec
        r = client.get(f"/templates/{tid}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("author", r.json()["spec"]["placeholders"])

        # apply
        r = client.post(f"/templates/{tid}/apply", json={
            "raw_content": "author is Jane", "fmt": "md"})
        self.assertEqual(r.status_code, 200, r.text)
        out_id = r.json()["out_id"]
        self.assertIn("Filled", r.json()["preview"])

        # download
        r = client.get(f"/templates/{tid}/output/{out_id}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers.get("content-disposition", ""))
        self.assertIn(b"Filled", r.content)

        # delete
        r = client.delete(f"/templates/{tid}")
        self.assertEqual(r.status_code, 200)
        r = client.get(f"/templates/{tid}")
        self.assertEqual(r.status_code, 404)

    def test_owner_scoping_404_for_other_user(self):
        client_a, _ = _make_client(user="alice")
        tid = client_a.post("/templates/", json={
            "name": "t", "raw_text": "# A\n"}).json()["id"]
        client_b, _ = _make_client(user="bob")
        self.assertEqual(client_b.get(f"/templates/{tid}").status_code, 404)
        self.assertEqual(client_b.get("/templates/mine/list").json()["items"], [])

    def test_login_required(self):
        client, tr = _make_client(user="alice")
        tr._bearer_username = lambda request: None  # no JWT subject
        r = client.get("/templates/mine/list")
        self.assertEqual(r.status_code, 401)

    def test_bad_fmt_rejected(self):
        client, _ = _make_client(user="alice")
        tid = client.post("/templates/", json={
            "name": "t", "raw_text": "# A\n"}).json()["id"]
        r = client.post(f"/templates/{tid}/apply", json={
            "raw_content": "x", "fmt": "pdf"})
        self.assertEqual(r.status_code, 400)

    def test_traversal_id_rejected(self):
        client, _ = _make_client(user="alice")
        # path-encoded traversal won't match the route; a literal bad id
        # that does route is rejected 400 by the store validator.
        r = client.get("/templates/BAD_UPPER")
        self.assertEqual(r.status_code, 400)

    def test_ingest_image_returns_ocr_text(self):
        client, tr = _make_client(user="alice")
        # Stub the OCR so the route is deterministic + offline.
        orig = tr.ingest_image
        tr.ingest_image = lambda path: "# Form\n{{name}}\n"
        try:
            r = client.post(
                "/templates/ingest-image",
                files={"file": ("form.png", b"\x89PNG\r\n", "image/png")},
            )
        finally:
            tr.ingest_image = orig
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["mode"], "image")
        self.assertIn("Form", r.json()["raw_text"])

    def test_ingest_image_login_required(self):
        client, tr = _make_client(user="alice")
        tr._bearer_username = lambda request: None
        r = client.post(
            "/templates/ingest-image",
            files={"file": ("form.png", b"\x89PNG\r\n", "image/png")},
        )
        self.assertEqual(r.status_code, 401)

    # ── v0.6.1 — instruction passthrough + .docx output + doc ingest ──

    def test_apply_with_instruction_reaches_formatter(self):
        """instruction in the request body must arrive in the LLM prompt."""
        client, tr = _make_client(user="alice")
        captured = {}
        orig = self._router.call_router
        self._router.call_router = lambda prompt, **kw: (
            captured.update(prompt=prompt) or "# out"
        )
        try:
            tid = client.post("/templates/", json={
                "name": "t", "raw_text": "# A\n"}).json()["id"]
            r = client.post(f"/templates/{tid}/apply", json={
                "raw_content": "x", "fmt": "md",
                "instruction": "use formal tone"})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertIn("formal tone", captured["prompt"])
            self.assertIn("===== USER GUIDANCE", captured["prompt"])
        finally:
            self._router.call_router = orig

    def test_apply_docx_downloads_zip(self):
        """fmt='docx' produces a downloadable .docx (ZIP magic header)."""
        client, _ = _make_client(user="alice")
        tid = client.post("/templates/", json={
            "name": "t", "raw_text": "# A\n"}).json()["id"]
        r = client.post(f"/templates/{tid}/apply", json={
            "raw_content": "raw", "fmt": "docx"})
        self.assertEqual(r.status_code, 200, r.text)
        out_id = r.json()["out_id"]
        self.assertTrue(r.json()["filename"].endswith(".docx"))
        r = client.get(f"/templates/{tid}/output/{out_id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content[:2], b"PK")

    def test_ingest_document_returns_extracted_text(self):
        client, tr = _make_client(user="alice")
        orig = tr.ingest_document
        tr.ingest_document = lambda path: "# 회의록\n{{date}}\n"
        try:
            r = tr.ingest_document  # noqa: silence
            r = client.post(
                "/templates/ingest-document",
                files={"file": ("form.docx", b"PK\x03\x04binary",
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
        finally:
            tr.ingest_document = orig
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["mode"], "document")
        self.assertIn("회의록", r.json()["raw_text"])

    def test_ingest_document_login_required(self):
        client, tr = _make_client(user="alice")
        tr._bearer_username = lambda request: None
        r = client.post(
            "/templates/ingest-document",
            files={"file": ("a.docx", b"PK\x03\x04", "application/octet-stream")},
        )
        self.assertEqual(r.status_code, 401)

    def test_ingest_document_rejects_unknown_ext(self):
        client, _ = _make_client(user="alice")
        r = client.post(
            "/templates/ingest-document",
            files={"file": ("evil.exe", b"MZ\x00\x00", "application/octet-stream")},
        )
        self.assertEqual(r.status_code, 400)


class ServerRegistrationTests(unittest.TestCase):
    def test_routes_registered_on_app(self):
        import server_llmwiki
        paths = {getattr(r, "path", None) for r in server_llmwiki.app.routes}
        for p in ("/templates/", "/templates/mine/list",
                  "/templates/ingest-image",
                  "/templates/ingest-document",
                  "/templates/{template_id}",
                  "/templates/{template_id}/apply",
                  "/templates/{template_id}/output/{out_id}"):
            self.assertIn(p, paths, f"missing template route: {p}")


if __name__ == "__main__":
    unittest.main()
