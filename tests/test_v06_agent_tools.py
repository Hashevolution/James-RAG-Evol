"""v0.6.1 Phase C — agent tool registry / dispatcher / built-ins +
backend abstraction + agent chat endpoint.

LLM HTTP calls are stubbed; no real Anthropic / Ollama traffic.

Run:
  python -m unittest tests.test_v06_agent_tools
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _reset_sandbox_state():
    import tools.code.sandbox as sb
    sb._USER_REGISTERED_PATHS.clear()
    sb._USER_PATHS_LOADED = False


# ── Registry + dispatcher ─────────────────────────────────────────

class RegistryTests(unittest.TestCase):
    def test_builtins_registered(self):
        from core.agent_tools import list_tools, get_tool
        names = [t.name for t in list_tools()]
        for expected in ("list_files", "read_file", "write_file",
                         "edit_file", "glob_files", "grep_files"):
            self.assertIn(expected, names)
        self.assertIsNotNone(get_tool("list_files"))

    def test_register_invalid_name_rejected(self):
        from core.agent_tools.registry import register_tool, Tool
        with self.assertRaises(ValueError):
            register_tool(Tool(
                name="bad/name", description="x",
                input_schema={"type": "object"}, handler=lambda a, r: None,
            ))


class DispatchUnknownToolTests(unittest.TestCase):
    def test_unknown_returns_error_dict(self):
        from core.agent_tools import dispatch
        r = dispatch("no_such_tool", {}, "admin")
        self.assertFalse(r["ok"])
        self.assertIn("unknown tool", r["error"])

    def test_args_must_be_dict(self):
        from core.agent_tools import dispatch
        r = dispatch("list_files", "not-a-dict", "admin")
        self.assertFalse(r["ok"])
        self.assertIn("dict", r["error"])


class BuiltinsRoundTripTests(unittest.TestCase):
    def setUp(self):
        _reset_sandbox_state()
        self._tmp = tempfile.mkdtemp(prefix="james_at_b_")
        from tools.code.sandbox import register_user_path
        register_user_path(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)
        _reset_sandbox_state()

    def test_write_then_read(self):
        from core.agent_tools import dispatch
        target = os.path.join(self._tmp, "note.md")
        w = dispatch("write_file", {"path": target, "content": "hello"}, "admin")
        self.assertTrue(w["ok"], w)
        r = dispatch("read_file", {"path": target}, "admin")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["output"]["content"], "hello")

    def test_edit_unique_match(self):
        from core.agent_tools import dispatch
        target = os.path.join(self._tmp, "x.md")
        dispatch("write_file", {"path": target, "content": "alpha beta"}, "admin")
        e = dispatch("edit_file", {"path": target,
                                    "old_string": "beta",
                                    "new_string": "GAMMA"}, "admin")
        self.assertTrue(e["ok"], e)
        r = dispatch("read_file", {"path": target}, "admin")
        self.assertEqual(r["output"]["content"], "alpha GAMMA")

    def test_edit_ambiguous_rejected(self):
        from core.agent_tools import dispatch
        target = os.path.join(self._tmp, "x.md")
        dispatch("write_file",
                 {"path": target, "content": "x x x"}, "admin")
        e = dispatch("edit_file",
                     {"path": target, "old_string": "x", "new_string": "y"},
                     "admin")
        self.assertFalse(e["ok"])
        self.assertIn("not unique", e["error"])

    def test_path_outside_allowed_rejected(self):
        from core.agent_tools import dispatch
        # writing to repo workspace (which is allowed by ALLOWED_PATHS)
        # is fine; writing to system root is not.
        if os.name == "nt":
            target = "C:\\Windows\\should_not_write.txt"
        else:
            target = "/etc/should_not_write.txt"
        r = dispatch("write_file", {"path": target, "content": "x"}, "admin")
        self.assertFalse(r["ok"])

    def test_glob_and_grep(self):
        from core.agent_tools import dispatch
        for n in ("a.md", "b.md", "c.txt"):
            dispatch("write_file",
                     {"path": os.path.join(self._tmp, n),
                      "content": "hello world"}, "admin")
        g = dispatch("glob_files",
                     {"pattern": "*.md", "path": self._tmp}, "admin")
        self.assertTrue(g["ok"])
        self.assertEqual(len(g["output"]), 2)
        gr = dispatch("grep_files",
                      {"pattern": "world", "path": self._tmp}, "admin")
        self.assertTrue(gr["ok"])
        self.assertEqual(len(gr["output"]), 3)


# ── Backend factory ────────────────────────────────────────────────

class BackendFactoryTests(unittest.TestCase):
    def setUp(self):
        self._prev_b = os.environ.pop("JAMES_AGENT_BACKEND", None)
        self._prev_k = os.environ.pop("ANTHROPIC_API_KEY", None)
        self._prev_c = os.environ.pop("JAMES_AGENT_ALLOW_CLOUD", None)

    def tearDown(self):
        if self._prev_b is not None:
            os.environ["JAMES_AGENT_BACKEND"] = self._prev_b
        if self._prev_k is not None:
            os.environ["ANTHROPIC_API_KEY"] = self._prev_k
        if self._prev_c is not None:
            os.environ["JAMES_AGENT_ALLOW_CLOUD"] = self._prev_c

    def test_default_is_ollama(self):
        from core.agent_tools.backends import get_backend, OllamaBackend
        b = get_backend()
        self.assertIsInstance(b, OllamaBackend)

    def test_anthropic_requires_key(self):
        from core.agent_tools.backends import BackendError, get_backend
        os.environ["JAMES_AGENT_BACKEND"] = "anthropic"
        os.environ["JAMES_AGENT_ALLOW_CLOUD"] = "1"  # bypass gate
        with self.assertRaises(BackendError):
            get_backend()

    def test_unknown_backend_rejected(self):
        from core.agent_tools.backends import BackendError, get_backend
        with self.assertRaises(BackendError):
            get_backend("madeup")

    def test_risk_2_anthropic_gated_by_allow_cloud(self):
        """Risk #2 (2026-06-15) — without JAMES_AGENT_ALLOW_CLOUD=1
        the anthropic backend refuses to construct even if the API
        key is present (it bypasses §5.7.12)."""
        from core.agent_tools.backends import BackendError, get_backend
        os.environ["JAMES_AGENT_BACKEND"] = "anthropic"
        os.environ["ANTHROPIC_API_KEY"] = "sk-fake"
        os.environ.pop("JAMES_AGENT_ALLOW_CLOUD", None)
        with self.assertRaises(BackendError) as ctx:
            get_backend()
        self.assertIn("disabled by default", str(ctx.exception))
        self.assertIn("§5.7.12", str(ctx.exception))


# ── Agent chat endpoint (HTTP, with stubbed backend) ──────────────

class _FakeBackend:
    name = "fake"

    def __init__(self, *replies):
        # `replies` are dicts the loop returns one-per-iteration.
        self._replies = list(replies)

    def chat_with_tools(self, messages, tools, *, system=None, max_tokens=1024):
        if not self._replies:
            return {"stop_reason": "end_turn", "text": "(done)", "tool_calls": [], "raw": {}}
        return self._replies.pop(0)


def _make_client(role="admin"):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routes.agent_chat as ac
    from routes._helpers import get_role_from_request

    app = FastAPI()
    app.include_router(ac.router)
    app.dependency_overrides[get_role_from_request] = lambda: role
    ac._bearer_username = lambda request: "admin"
    ac._require_admin = lambda api_key, role: None if role == "admin" else (_ for _ in ()).throw(
        __import__("fastapi").HTTPException(status_code=403, detail="admin only")
    )
    return TestClient(app), ac


class AgentChatEndpointTests(unittest.TestCase):
    def setUp(self):
        _reset_sandbox_state()
        self._tmp = tempfile.mkdtemp(prefix="james_ac_")
        from tools.code.sandbox import register_user_path
        register_user_path(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)
        _reset_sandbox_state()

    def test_empty_message_rejected(self):
        client, _ = _make_client()
        r = client.post("/agent/chat/",
                        json={"api_key": "x", "message": "   "})
        self.assertEqual(r.status_code, 400)

    def test_forbidden_for_non_admin(self):
        client, _ = _make_client(role="user")
        r = client.post("/agent/chat/",
                        json={"api_key": "x", "message": "hi"})
        self.assertEqual(r.status_code, 403)

    def test_no_tool_use_returns_text(self):
        client, ac = _make_client()
        fake = _FakeBackend({"stop_reason": "end_turn",
                              "text": "hello back", "tool_calls": [], "raw": {}})
        ac.get_backend = lambda name=None, model=None: fake
        # patch import path the endpoint uses
        import core.agent_tools.backends as be
        orig_get = be.get_backend
        be.get_backend = lambda name=None, model=None: fake
        try:
            r = client.post("/agent/chat/",
                            json={"api_key": "x", "message": "hi"})
        finally:
            be.get_backend = orig_get
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["stop_reason"], "end_turn")
        self.assertIn("hello back", body["text"])
        self.assertEqual(body["tool_trace"], [])

    def test_tool_use_loop_runs_dispatch_then_finishes(self):
        client, ac = _make_client()
        # First reply asks for write_file; second is end_turn.
        target = os.path.join(self._tmp, "agent.md")
        fake = _FakeBackend(
            {"stop_reason": "tool_use",
             "text": "I'll write that file.",
             "tool_calls": [{
                 "id": "u1", "name": "write_file",
                 "input": {"path": target, "content": "hi from agent"},
             }],
             "raw": {}},
            {"stop_reason": "end_turn",
             "text": "Wrote it.",
             "tool_calls": [], "raw": {}},
        )
        import core.agent_tools.backends as be
        orig = be.get_backend
        be.get_backend = lambda name=None, model=None: fake
        try:
            r = client.post("/agent/chat/",
                            json={"api_key": "x",
                                  "message": "write hi from agent to agent.md"})
        finally:
            be.get_backend = orig
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["stop_reason"], "end_turn")
        self.assertEqual(len(body["tool_trace"]), 1)
        self.assertTrue(body["tool_trace"][0]["ok"])
        self.assertEqual(body["tool_trace"][0]["name"], "write_file")
        # And the file actually got written:
        with open(target, encoding="utf-8") as f:
            self.assertEqual(f.read(), "hi from agent")


class ServerRegistrationTests(unittest.TestCase):
    def test_agent_chat_route_wired(self):
        import server_llmwiki
        paths = {getattr(r, "path", None) for r in server_llmwiki.app.routes}
        self.assertIn("/agent/chat/", paths)


if __name__ == "__main__":
    unittest.main()
