"""v0.6.1 Phase C — agent tool registry / dispatcher / built-ins +
backend abstraction + agent chat endpoint.

LLM HTTP calls are stubbed; no real Anthropic / Ollama traffic.

Run:
  python -m unittest tests.test_v06_agent_tools
"""
from __future__ import annotations

import json
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
        # cloud_allowed() is DB-first now; pin to env-only so a stray DB
        # row can't flip these gate tests.
        self._prev_db = os.environ.get("JAMES_SETTINGS_USE_DB")
        os.environ["JAMES_SETTINGS_USE_DB"] = "0"

    def tearDown(self):
        # Restore the prior value, OR remove the var entirely if it
        # wasn't set before — otherwise an env we added (e.g.
        # JAMES_AGENT_BACKEND=anthropic) leaks into later test classes.
        for var, prev in (("JAMES_AGENT_BACKEND", self._prev_b),
                          ("ANTHROPIC_API_KEY", self._prev_k),
                          ("JAMES_AGENT_ALLOW_CLOUD", self._prev_c)):
            if prev is not None:
                os.environ[var] = prev
            else:
                os.environ.pop(var, None)
        if self._prev_db is not None:
            os.environ["JAMES_SETTINGS_USE_DB"] = self._prev_db
        else:
            os.environ.pop("JAMES_SETTINGS_USE_DB", None)

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

    def test_claude_cli_gated_by_allow_cloud(self):
        """claude_cli (Max-plan CLI, no API key) is still cloud egress →
        refuses without JAMES_AGENT_ALLOW_CLOUD=1."""
        from core.agent_tools.backends import BackendError, get_backend
        os.environ.pop("JAMES_AGENT_ALLOW_CLOUD", None)
        with self.assertRaises(BackendError) as ctx:
            get_backend("claude_cli")
        self.assertIn("ALLOW_CLOUD", str(ctx.exception))
        self.assertIn("no API key", str(ctx.exception))

    def test_claude_cli_no_api_key_required(self):
        """With ALLOW_CLOUD set, claude_cli constructs even with NO
        ANTHROPIC_API_KEY (unlike the anthropic HTTP backend)."""
        from core.agent_tools.backends import get_backend, ClaudeCliBackend
        os.environ["JAMES_AGENT_ALLOW_CLOUD"] = "1"
        os.environ.pop("ANTHROPIC_API_KEY", None)
        b = get_backend("claude_cli")
        self.assertIsInstance(b, ClaudeCliBackend)

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


class ClaudeCliBackendTests(unittest.TestCase):
    """claude_cli wraps `claude -p` (Max-plan login). The CLI returns
    plain text, so the backend folds the tools into the system prompt and
    the loop's _extract_text_tool_call recovers the JSON call."""

    def setUp(self):
        os.environ["JAMES_AGENT_ALLOW_CLOUD"] = "1"
        self._prev_db = os.environ.get("JAMES_SETTINGS_USE_DB")
        os.environ["JAMES_SETTINGS_USE_DB"] = "0"   # env-only cloud gate

    def tearDown(self):
        os.environ.pop("JAMES_AGENT_ALLOW_CLOUD", None)
        if self._prev_db is not None:
            os.environ["JAMES_SETTINGS_USE_DB"] = self._prev_db
        else:
            os.environ.pop("JAMES_SETTINGS_USE_DB", None)

    def test_transcript_and_tool_prompt_and_recovery(self):
        import core.reasoning.backends.claude_code_cli as cli
        captured = {}

        class _Res:
            text = '{"name": "list_files", "arguments": {"path": "/x"}}'
            error = None

        class _FakeCli:
            def complete(self, prompt, *, system="", model=None,
                         max_tokens=1024, timeout=60.0, **o):
                captured["prompt"] = prompt
                captured["system"] = system
                captured["model"] = model
                captured["opts"] = o
                return _Res()

        orig = cli.ClaudeCodeCliBackend
        cli.ClaudeCodeCliBackend = _FakeCli
        try:
            from core.agent_tools.backends import ClaudeCliBackend
            b = ClaudeCliBackend(model="claude-opus-4-8")
            tools = [{"name": "list_files", "description": "list",
                      "input_schema": {"type": "object",
                                       "properties": {"path": {"type": "string"}}}}]
            r = b.chat_with_tools(
                messages=[{"role": "user", "content": "list files"}],
                tools=tools, system="base", max_tokens=64)
        finally:
            cli.ClaudeCodeCliBackend = orig
        self.assertIn("list_files", captured["system"])     # tools described
        self.assertIn("User: list files", captured["prompt"])
        self.assertEqual(captured["model"], "claude-opus-4-8")
        # The CLI must be told to disable its own tools (so it doesn't run
        # agentic file ops in its sandbox and ignore the operator folder).
        self.assertTrue(captured["opts"].get("disallow_tools"))
        self.assertEqual(r["stop_reason"], "end_turn")
        from routes.agent_chat import _extract_text_tool_call
        fb = _extract_text_tool_call(r["text"], {"list_files"})
        self.assertEqual(fb["name"], "list_files")
        self.assertEqual(fb["input"]["path"], "/x")

    def test_cli_error_surfaces_as_backend_error(self):
        import core.reasoning.backends.claude_code_cli as cli

        class _Res:
            text = ""
            error = "claude CLI not found"

        class _FakeCli:
            def complete(self, *a, **k):
                return _Res()

        orig = cli.ClaudeCodeCliBackend
        cli.ClaudeCodeCliBackend = _FakeCli
        try:
            from core.agent_tools.backends import ClaudeCliBackend, BackendError
            b = ClaudeCliBackend()
            with self.assertRaises(BackendError):
                b.chat_with_tools(
                    messages=[{"role": "user", "content": "x"}],
                    tools=[], system="", max_tokens=8)
        finally:
            cli.ClaudeCodeCliBackend = orig


class ClaudeCliDisallowToolsArgvTests(unittest.TestCase):
    """The CLI backend must add `--disallowedTools *` when disallow_tools
    is set (so `claude -p` is a pure text completer), and NOT otherwise."""

    def _run(self, **kw):
        from unittest.mock import patch
        from core.reasoning.backends.claude_code_cli import ClaudeCodeCliBackend
        be = ClaudeCodeCliBackend(cli_path="/fake/claude")
        captured = {}

        class _Proc:
            returncode = 0

            def communicate(self, input=None, timeout=None):
                return ("ok", "")

        def _fake_popen(argv, **kwargs):
            captured["argv"] = argv
            return _Proc()

        with patch("subprocess.Popen", side_effect=_fake_popen):
            be.complete("hi", **kw)
        return captured["argv"]

    def test_flag_present_when_disallow(self):
        argv = self._run(disallow_tools=True)
        self.assertIn("--disallowedTools", argv)
        self.assertEqual(argv[argv.index("--disallowedTools") + 1], "*")

    def test_flag_absent_by_default(self):
        argv = self._run()
        self.assertNotIn("--disallowedTools", argv)


class OllamaMessageAdaptTests(unittest.TestCase):
    """Multi-block (Anthropic-style) messages must become Ollama's
    string-content + tool_calls + role:tool shape, else Ollama 400s with
    'cannot unmarshal array into ... content of type string'."""

    def test_string_content_passthrough(self):
        from core.agent_tools.backends import _to_ollama_messages
        out = _to_ollama_messages([{"role": "user", "content": "hi"}])
        self.assertEqual(out, [{"role": "user", "content": "hi"}])

    def test_assistant_tool_use_becomes_tool_calls(self):
        from core.agent_tools.backends import _to_ollama_messages
        out = _to_ollama_messages([{"role": "assistant", "content": [
            {"type": "text", "text": "ok"},
            {"type": "tool_use", "id": "1", "name": "list_files",
             "input": {"path": "/x"}}]}])
        self.assertEqual(out[0]["role"], "assistant")
        self.assertEqual(out[0]["content"], "ok")
        fn = out[0]["tool_calls"][0]["function"]
        self.assertEqual(fn["name"], "list_files")
        self.assertEqual(fn["arguments"], {"path": "/x"})

    def test_tool_result_becomes_tool_role(self):
        from core.agent_tools.backends import _to_ollama_messages
        out = _to_ollama_messages([{"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "1",
             "content": {"files": ["a"]}}]}])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["role"], "tool")
        self.assertIn("files", out[0]["content"])   # dict stringified

    def test_no_list_content_survives(self):
        from core.agent_tools.backends import _to_ollama_messages
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "1", "name": "x", "input": {}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "1", "content": "done"}]},
        ]
        for m in _to_ollama_messages(msgs):
            self.assertIsInstance(m["content"], str)


class TextToolCallFallbackTests(unittest.TestCase):
    """A model that narrates a tool call as JSON text (no native
    tool_call) must still be recovered + dispatched."""

    def test_extract_arguments_key(self):
        from routes.agent_chat import _extract_text_tool_call
        txt = 'Sure: ' + json.dumps(
            {"name": "list_files", "arguments": {"path": "C:\\x"}})
        fb = _extract_text_tool_call(txt, {"list_files"})
        self.assertEqual(fb["name"], "list_files")
        self.assertEqual(fb["input"]["path"], "C:\\x")

    def test_extract_parameters_and_input_keys(self):
        from routes.agent_chat import _extract_text_tool_call
        a = _extract_text_tool_call(
            json.dumps({"name": "read_file", "parameters": {"path": "a"}}),
            {"read_file"})
        self.assertEqual(a["input"]["path"], "a")
        b = _extract_text_tool_call(
            json.dumps({"name": "read_file", "input": {"path": "b"}}),
            {"read_file"})
        self.assertEqual(b["input"]["path"], "b")

    def test_extract_unknown_name_is_none(self):
        from routes.agent_chat import _extract_text_tool_call
        self.assertIsNone(_extract_text_tool_call(
            json.dumps({"name": "nope", "arguments": {}}), {"list_files"}))

    def test_extract_plain_text_is_none(self):
        from routes.agent_chat import _extract_text_tool_call
        self.assertIsNone(_extract_text_tool_call("just a normal answer", {"list_files"}))


class TextFallbackEndpointTests(unittest.TestCase):
    def setUp(self):
        _reset_sandbox_state()
        self._tmp = tempfile.mkdtemp(prefix="james_fb_")
        from tools.code.sandbox import register_user_path
        register_user_path(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)
        _reset_sandbox_state()

    def test_text_tool_call_is_dispatched(self):
        client, ac = _make_client()
        narrated = json.dumps(
            {"name": "list_files", "arguments": {"path": self._tmp}})
        fake = _FakeBackend(
            {"stop_reason": "end_turn", "text": narrated,
             "tool_calls": [], "raw": {}},
            {"stop_reason": "end_turn", "text": "Here are the files.",
             "tool_calls": [], "raw": {}},
        )
        import core.agent_tools.backends as be
        orig = be.get_backend
        be.get_backend = lambda name=None, model=None: fake
        try:
            r = client.post("/agent/chat/",
                            json={"api_key": "x", "message": "list files"})
        finally:
            be.get_backend = orig
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(len(body["tool_trace"]), 1)
        self.assertEqual(body["tool_trace"][0]["name"], "list_files")
        self.assertTrue(body["tool_trace"][0]["ok"], body["tool_trace"])

    def test_system_prompt_lists_allowed_folders(self):
        client, ac = _make_client()

        class _Cap:
            name = "cap"
            def __init__(self): self.system = None
            def chat_with_tools(self, messages, tools, *, system=None, max_tokens=1024):
                self.system = system
                return {"stop_reason": "end_turn", "text": "ok",
                        "tool_calls": [], "raw": {}}

        cap = _Cap()
        import core.agent_tools.backends as be
        orig = be.get_backend
        be.get_backend = lambda name=None, model=None: cap
        try:
            client.post("/agent/chat/", json={"api_key": "x", "message": "hi"})
        finally:
            be.get_backend = orig
        self.assertIsNotNone(cap.system)
        self.assertIn(self._tmp, cap.system)


class ServerRegistrationTests(unittest.TestCase):
    def test_agent_chat_route_wired(self):
        import server_llmwiki
        paths = {getattr(r, "path", None) for r in server_llmwiki.app.routes}
        self.assertIn("/agent/chat/", paths)


if __name__ == "__main__":
    unittest.main()
