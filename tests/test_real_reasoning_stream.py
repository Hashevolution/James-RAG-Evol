"""Real reasoning stream — client-supplied trace_id + /trace/poll/.

Replaces the v0.2.0 fake 2.5s timer placeholder with actual per-stage
events streamed from the trace JSONL file. User feedback 2026-05-08:
"형식적으로 만들어놓은 거 말고 클로드 방식을 따라 실제 추론과정을
표시될 수 있도록 개선".

Coverage:
  - QueryRequest accepts trace_id field; default empty.
  - /query/ uses client-supplied trace_id when valid; falls back to
    server-generated when empty / invalid.
  - Path-traversal guard rejects malformed trace_ids both at /query/
    and /trace/poll/.
  - /trace/poll/{trace_id} requires api_key but NOT admin role
    (capability-token model: trace_id itself is the secret).
  - /trace/poll/ filters events by `after_ns` (incremental polling
    avoids redundant transfer).
  - /trace/poll/ flags `complete` when a 'complete' stage exists.
  - Behavioral: write a few stages via log_stage, then verify the
    polling endpoint returns them in order with correct fields.
  - Frontend contract: appendTyping accepts a traceId arg and polls
    /trace/poll/.

Run:
  python -m unittest tests.test_real_reasoning_stream
"""
from __future__ import annotations

import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


def _admin_headers():
    from core.auth import create_token
    return {"Authorization": f"Bearer {create_token('test-admin', 'admin')}"}


def _api_key():
    env_v = os.environ.get("JAMES_API_KEY")
    if env_v:
        return env_v.strip()
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("JAMES_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


class QueryRequestTraceIdTests(unittest.TestCase):
    """Source-level: QueryRequest must accept trace_id; /query/
    uses client-supplied id when valid, generates own when empty."""

    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.src = inspect.getsource(srv)

    def test_querryrequest_has_trace_id_field(self):
        # Locate QueryRequest body — bounded by next class or function def.
        import re
        m = re.search(
            r"class QueryRequest\(BaseModel\):(.+?)(?=\nclass |\n@app\.|\nasync def )",
            self.src, re.DOTALL,
        )
        self.assertIsNotNone(m, "QueryRequest class block not found")
        body = m.group(1)
        self.assertIn("trace_id", body,
                      "QueryRequest must declare trace_id field")
        # Default must be empty string (back-compat).
        self.assertTrue(re.search(r'trace_id\s*:\s*str\s*=\s*""', body),
                        "trace_id must default to empty string for back-compat")

    def test_query_endpoint_validates_and_uses_client_trace_id(self):
        idx = self.src.index('@app.post("/query/"')
        body = self.src[idx:idx + 2500]
        # Sanity-check format must be enforced (path traversal guard).
        self.assertIn(r'fullmatch(r"[A-Za-z0-9_\-]{8,64}"', body,
                      "/query/ must regex-validate client_tid format "
                      "before passing to start_trace()")
        # Both branches present: with valid id, fallback when not.
        self.assertIn("start_trace(client_tid)", body)
        self.assertIn("start_trace()", body,
                      "fallback to server-generated id on empty/invalid")


class TracePollEndpointSourceTests(unittest.TestCase):
    """The new GET /trace/poll/{trace_id} endpoint must require
    api_key (NOT admin), validate trace_id format, return events
    newer than after_ns, and flag completion."""

    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.src = inspect.getsource(srv)

    def test_poll_endpoint_registered(self):
        self.assertIn('@app.get("/trace/poll/{trace_id}"', self.src,
                      "polling endpoint must be GET /trace/poll/{trace_id}")

    def test_poll_endpoint_uses_api_key_not_admin(self):
        idx = self.src.index('@app.get("/trace/poll/{trace_id}"')
        body = self.src[idx:idx + 2500]
        self.assertIn("verify_api_key(api_key)", body,
                      "must validate api_key")
        # Must NOT be admin-gated — the user wouldn't be able to see
        # their own reasoning stream otherwise.
        self.assertNotIn("_require_admin(", body,
                         "polling endpoint must NOT be admin-gated; "
                         "trace_id capability-token model is sufficient")

    def test_poll_endpoint_validates_trace_id_format(self):
        idx = self.src.index('@app.get("/trace/poll/{trace_id}"')
        body = self.src[idx:idx + 2500]
        self.assertIn(r'fullmatch(r"[A-Za-z0-9_\-]{8,64}"', body,
                      "trace_id path arg must be regex-validated to "
                      "prevent traversal into reports/trace/")
        self.assertIn("status_code=400", body,
                      "invalid trace_id must return 400")

    def test_poll_endpoint_filters_by_after_ns(self):
        idx = self.src.index('@app.get("/trace/poll/{trace_id}"')
        body = self.src[idx:idx + 2500]
        self.assertIn("after_ns", body,
                      "polling endpoint must accept after_ns param "
                      "for incremental fetching")
        self.assertIn('"complete"', body,
                      "response must flag complete=true when 'complete' "
                      "stage is present, so the client can stop polling")


class TracePollBehavioralTests(unittest.TestCase):
    """End-to-end via TestClient: write events via log_stage, poll
    them back. Uses a tmpdir trace root so we don't disturb
    reports/trace/."""

    def setUp(self):
        from core.observability import set_trace_root, current_trace_id
        self._tmp = tempfile.TemporaryDirectory()
        set_trace_root(Path(self._tmp.name))
        current_trace_id.set("")
        self._api_key = _api_key()
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing; cannot exercise endpoint")

    def tearDown(self):
        from core.observability import set_trace_root
        set_trace_root(None)
        self._tmp.cleanup()

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def test_invalid_trace_id_format_400(self):
        client = self._client()
        for bad in ("short", "..", "../etc/passwd", "a" * 100, ""):
            r = client.get(
                f"/trace/poll/{bad}",
                params={"api_key": self._api_key},
            )
            self.assertNotEqual(r.status_code, 200,
                                f"bad trace_id {bad!r} must not return 200")

    def test_polling_returns_events_in_order(self):
        from core.observability import start_trace, log_stage
        # Use a CLIENT-style trace_id so we mirror real usage.
        client_tid = "abcd1234efgh5678ijkl9012mnop3456"
        tid = start_trace(client_tid)
        log_stage("auth", role="admin", allowed=True)
        log_stage("retrieve", top_k=8, top_vector_score=0.82)
        log_stage("graph", entities_extracted=3, paths_walked=15)
        log_stage("answer", latency_ms=1820, answer_len=412)
        log_stage("complete", elapsed_ms=2200)

        client = self._client()
        r = client.get(
            f"/trace/poll/{tid}",
            params={"api_key": self._api_key},
        )
        self.assertEqual(r.status_code, 200, f"poll failed: {r.text}")
        data = r.json()
        self.assertEqual(data["trace_id"], tid)
        self.assertTrue(data["complete"], "complete must be True after 'complete' stage")
        self.assertEqual(data["total"], 5)
        stages = [e["stage"] for e in data["events"]]
        self.assertEqual(stages, ["auth", "retrieve", "graph", "answer", "complete"])

    def test_after_ns_filters_already_seen(self):
        from core.observability import start_trace, log_stage
        client_tid = "ffff1111eeee2222dddd3333cccc4444"
        start_trace(client_tid)
        log_stage("auth")
        log_stage("retrieve", top_k=8)
        client = self._client()

        # First poll: no after_ns → both events.
        r = client.get(
            f"/trace/poll/{client_tid}",
            params={"api_key": self._api_key},
        )
        self.assertEqual(len(r.json()["events"]), 2)
        last_ts = r.json()["events"][-1]["ts_ns"]

        # Add a third event.
        log_stage("graph", paths_walked=10)

        # Poll with after_ns = previous last → only the new one.
        r2 = client.get(
            f"/trace/poll/{client_tid}",
            params={"api_key": self._api_key, "after_ns": last_ts},
        )
        evs = r2.json()["events"]
        self.assertEqual(len(evs), 1, f"after_ns filter failed: {evs}")
        self.assertEqual(evs[0]["stage"], "graph")


class FrontendChatJsContractTests(unittest.TestCase):
    """chat.js must:
      - Generate a client-side trace_id and send it in the /query/ body
      - Pass that trace_id to appendTyping()
      - appendTyping calls /trace/poll/{trace_id} on a recurring poll
    """

    @classmethod
    def setUpClass(cls):
        cls.js = (Path(__file__).resolve().parent.parent
                  / "frontend" / "static" / "chat.js"
                  ).read_text(encoding="utf-8")

    def test_send_message_generates_trace_id(self):
        idx = self.js.index("async function sendMessage")
        body = self.js[idx:idx + 2500]
        self.assertIn("crypto.randomUUID", body,
                      "sendMessage should use crypto.randomUUID() for trace_id "
                      "(falls back to manual id when missing)")
        self.assertIn("trace_id:", body,
                      "/query/ body must include trace_id field")
        self.assertIn("appendTyping(traceId)", body,
                      "appendTyping must receive the trace_id so it knows "
                      "which trace to poll")

    def test_append_typing_polls_real_trace(self):
        idx = self.js.index("function appendTyping(traceId)")
        body = self.js[idx:idx + 4000]
        self.assertIn("/trace/poll/", body,
                      "appendTyping must poll /trace/poll/{traceId}")
        self.assertIn("after_ns=", body,
                      "polling must use after_ns for incremental fetching")
        # The fake 2.5s setInterval timer must be GONE.
        self.assertNotIn("2500", body,
                         "fake 2.5s placeholder timer must be removed")
        # A complete-flag check must stop the polling loop.
        self.assertIn("complete", body,
                      "polling loop must stop on data.complete = true")

    def test_stage_metadata_displayed(self):
        idx = self.js.index("function appendTyping(traceId)")
        body = self.js[idx:idx + 4000]
        # Real per-stage labels must replace the static three-step UI.
        for stage_token in ("retrieve", "graph", "answer", "complete"):
            self.assertIn(f'{stage_token}:', body,
                          f"stage {stage_token!r} must have its own metadata mapping")


if __name__ == "__main__":
    unittest.main()
