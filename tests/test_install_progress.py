"""Model install progress tracker (item #A8-8, 2026-05-09).

User feedback: "<이 pc에 맞는 llm 모델 설치> 할 때에는 설치 진행과정이
표시 되어야하며, 설치시 챗 페이지 이동이 가능하도록 개선".

Backend:
  - _install_progress dict + _install_lock for thread-safe writes
  - _start_install_with_progress(model) spawns a daemon thread that
    streams Ollama's POST /api/pull NDJSON output and writes
    {status, percent, completed, total, error, done} to the dict.
  - POST /llm/install/ now resets dict + starts the thread (was
    subprocess.Popen fire-and-forget).
  - GET /admin/llm/install-progress?model=X returns the snapshot.

Frontend:
  - triggerModelInstall starts a 2.5s setInterval polling the new
    endpoint. Button text updates live: "📦 X 설치" → "⏳ 23.5% (X)"
    → "✅ X 설치 완료". Page navigation doesn't kill the server-side
    thread (operator can move to chat while download runs).

Run:
  python -m unittest tests.test_install_progress
"""
from __future__ import annotations

import inspect
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class BackendTrackerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.srv = srv
        cls.src = inspect.getsource(srv)

    def test_progress_dict_exists(self):
        self.assertTrue(hasattr(self.srv, "_install_progress"),
            "_install_progress dict must be a module-level variable")
        self.assertIsInstance(self.srv._install_progress, dict)

    def test_start_install_helper_exists(self):
        self.assertTrue(hasattr(self.srv, "_start_install_with_progress"),
            "_start_install_with_progress helper must exist")

    def test_helper_uses_threading(self):
        h = inspect.getsource(self.srv._start_install_with_progress)
        self.assertIn("threading", h,
            "must use threading.Thread for non-blocking install")
        self.assertIn("daemon=True", h,
            "thread must be daemon so it doesn't block server shutdown")
        self.assertIn("ollama", h.lower())

    def test_helper_streams_ollama_pull(self):
        h = inspect.getsource(self.srv._start_install_with_progress)
        # Hits Ollama's /api/pull with stream:true.
        self.assertIn("/api/pull", h,
            "must POST to Ollama /api/pull endpoint")
        self.assertIn('"stream": True', h,
            "must request streaming NDJSON response")

    def test_helper_computes_percent(self):
        h = inspect.getsource(self.srv._start_install_with_progress)
        # percent = completed / total when both numeric.
        self.assertIn("completed", h)
        self.assertIn("total", h)
        self.assertIn("percent", h)

    def test_helper_records_error_on_exception(self):
        h = inspect.getsource(self.srv._start_install_with_progress)
        self.assertIn("except Exception", h,
            "must catch exception (network blip, bad model name)")
        self.assertIn('"error"', h,
            "error path must populate error field for client visibility")


class InstallEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.src = inspect.getsource(srv)

    def _endpoint_body(self) -> str:
        idx = self.src.index('@app.post("/llm/install/"')
        rest = self.src[idx + 1:]
        m = re.search(r"\n@app\.", rest)
        end = idx + 1 + m.start() if m else idx + 5000
        return self.src[idx:end]

    def test_endpoint_uses_thread_helper_not_subprocess(self):
        body = self._endpoint_body()
        self.assertIn("_start_install_with_progress", body,
            "endpoint must call the threading helper")
        # subprocess.Popen for ollama pull is gone.
        self.assertNotIn('subprocess.Popen(\n            ["ollama", "pull"', body,
            "old fire-and-forget Popen path must be replaced")

    def test_endpoint_resets_progress_state(self):
        body = self._endpoint_body()
        self.assertIn("_install_progress[model] = {", body,
            "must seed a fresh progress entry so polling returns "
            "'starting' immediately, not 'idle'")
        self.assertIn('"status":    "starting"', body,
            "initial state should be 'starting'")


class ProgressEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.src = inspect.getsource(srv)

    def test_get_endpoint_registered(self):
        self.assertIn('@app.get("/admin/llm/install-progress"', self.src,
            "GET /admin/llm/install-progress must be registered")

    def test_endpoint_admin_gated(self):
        idx = self.src.index('@app.get("/admin/llm/install-progress"')
        rest = self.src[idx + 1:]
        m = re.search(r"\n@app\.", rest)
        end = idx + 1 + m.start() if m else idx + 3000
        body = self.src[idx:end]
        self.assertIn("_require_admin", body,
            "progress endpoint must be admin-gated")

    def test_endpoint_returns_idle_for_unknown_model(self):
        idx = self.src.index('@app.get("/admin/llm/install-progress"')
        rest = self.src[idx + 1:]
        m = re.search(r"\n@app\.", rest)
        end = idx + 1 + m.start() if m else idx + 3000
        body = self.src[idx:end]
        self.assertIn('"status": "idle"', body,
            "unknown / never-installed model should return 'idle' status")


class FrontendPollingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "chat.js").read_text(encoding="utf-8")

    def test_poll_helper_present(self):
        self.assertIn("function _pollInstallProgress", self.js,
            "polling helper missing")
        self.assertIn("/admin/llm/install-progress", self.js,
            "must hit the progress endpoint")

    def test_poll_uses_setInterval(self):
        idx = self.js.index("async function triggerModelInstall")
        m = re.search(r"\nasync function|\nfunction\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 4500
        body = self.js[idx:end]
        self.assertIn("setInterval", body,
            "must poll on an interval (every 2.5s)")
        # Non-blocking — interval doesn't await per tick.
        self.assertIn("_installPollTimer", body,
            "must store the timer handle so it can be cleared on success/failure")

    def test_poll_clears_on_done(self):
        idx = self.js.index("function _pollInstallProgress")
        m = re.search(r"\nasync function|\nfunction\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 4500
        body = self.js[idx:end]
        self.assertIn("p.done", body,
            "must check the done flag")
        self.assertIn("_stopInstallPoll", body,
            "must call _stopInstallPoll on success/failure")

    def test_poll_updates_button_label(self):
        idx = self.js.index("function _pollInstallProgress")
        body = self.js[idx:idx + 3000]
        # Live progress label.
        self.assertIn("p.percent", body,
            "must read percent from response")
        self.assertIn("⏳", body)
        self.assertIn("✅", body,
            "must flip to ✅ when done")

    def test_confirm_message_mentions_navigation(self):
        # User wants explicit confirmation that navigation is OK during install.
        idx = self.js.index("async function triggerModelInstall")
        body = self.js[idx:idx + 3000]
        self.assertIn("페이지 이동", body,
            "confirm dialog should mention page navigation is OK during install")


if __name__ == "__main__":
    unittest.main()
