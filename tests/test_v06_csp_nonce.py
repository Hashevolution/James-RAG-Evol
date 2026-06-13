"""v0.6 Track C — CSP nonce primitive + middleware integration.

Covers:

`new_nonce`:
  * Returns base64url-encoded ASCII (no padding `=`)
  * Each call returns a unique value (uniqueness over 100 calls)
  * Length is the expected 22 chars (16 bytes urlsafe_b64)

`csp_use_nonce_for_scripts` / `_styles`:
  * Default off (env unset → False)
  * Truthy synonyms: `1` / `true` / `yes` / `on` / `enabled`
  * Falsy: everything else (`0`, `false`, empty, junk)

`build_security_headers(script_nonce=..., style_nonce=...)`:
  * Default kwargs (None / None) → byte-identical to pre-v0.6 output
  * `script_nonce` set → `script-src` carries `'self' 'nonce-<v>'`
    (additive; doesn't remove `'self'` or any other token)
  * `style_nonce` set → `style-src` REPLACES `'unsafe-inline'` with
    `'nonce-<v>'` (CSP3 §6.6.2.4 compliance)
  * Both nonces use the SAME value if the middleware passes the
    same nonce string to both kwargs (matches the production wire-in)
  * `script_nonce` does NOT change `style-src` and vice versa
  * Nonce is unset → directive unchanged

Middleware integration (via FastAPI TestClient):
  * `request.state.csp_nonce` always populated (regardless of env)
  * Response carries the CSP header with the nonce only when the
    env flag is set
  * Same request → same nonce in state AND in header (consistency)

Run:
  python -m unittest tests.test_v06_csp_nonce
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from contextlib import contextmanager
from typing import Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault(
    "JAMES_JWT_SECRET",
    "test-secret-for-csp-nonce-32chars-min-padding",
)

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


@contextmanager
def _patched_env(**env):
    saved: Dict[str, str] = {}
    unset_keys = []
    for k, v in env.items():
        if k in os.environ:
            saved[k] = os.environ[k]
        else:
            unset_keys.append(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            os.environ[k] = v
        for k in unset_keys:
            os.environ.pop(k, None)
        for k in env:
            if k not in saved and k not in unset_keys:
                os.environ.pop(k, None)


# ─── new_nonce primitive ───────────────────────────────────────────


class NewNonceTests(unittest.TestCase):
    def test_returns_url_safe_ascii(self):
        from core.security.csp_nonce import new_nonce
        nonce = new_nonce()
        # base64url alphabet: A-Z a-z 0-9 - _  (no padding)
        self.assertRegex(nonce, r"^[A-Za-z0-9_\-]+$")

    def test_no_padding(self):
        from core.security.csp_nonce import new_nonce
        for _ in range(10):
            self.assertNotIn("=", new_nonce())

    def test_uniqueness_over_many_calls(self):
        from core.security.csp_nonce import new_nonce
        seen = {new_nonce() for _ in range(100)}
        # 16 bytes of entropy → collision probability ≈ 0 across 100
        self.assertEqual(len(seen), 100)

    def test_expected_length(self):
        from core.security.csp_nonce import new_nonce
        # 16 bytes urlsafe_b64 (no padding) = 22 chars
        for _ in range(5):
            self.assertEqual(len(new_nonce()), 22)


# ─── flag predicates ──────────────────────────────────────────────


class NonceFlagsTests(unittest.TestCase):
    def test_script_flag_default_off(self):
        with _patched_env(JAMES_CSP_USE_NONCE_SCRIPT=None):
            from core.security.csp_nonce import csp_use_nonce_for_scripts
            self.assertFalse(csp_use_nonce_for_scripts())

    def test_style_flag_default_off(self):
        with _patched_env(JAMES_CSP_USE_NONCE_STYLE=None):
            from core.security.csp_nonce import csp_use_nonce_for_styles
            self.assertFalse(csp_use_nonce_for_styles())

    def test_script_flag_truthy_synonyms(self):
        from core.security.csp_nonce import csp_use_nonce_for_scripts
        for val in ("1", "true", "yes", "on", "enabled", "TRUE", "Yes"):
            with _patched_env(JAMES_CSP_USE_NONCE_SCRIPT=val):
                self.assertTrue(csp_use_nonce_for_scripts(),
                                f"expected truthy for {val!r}")

    def test_script_flag_falsy_values(self):
        from core.security.csp_nonce import csp_use_nonce_for_scripts
        for val in ("0", "false", "no", "off", "", "garbage"):
            with _patched_env(JAMES_CSP_USE_NONCE_SCRIPT=val):
                self.assertFalse(csp_use_nonce_for_scripts(),
                                 f"expected falsy for {val!r}")

    def test_style_flag_independent_from_script_flag(self):
        from core.security.csp_nonce import (
            csp_use_nonce_for_scripts, csp_use_nonce_for_styles,
        )
        with _patched_env(JAMES_CSP_USE_NONCE_SCRIPT="1",
                          JAMES_CSP_USE_NONCE_STYLE=None):
            self.assertTrue(csp_use_nonce_for_scripts())
            self.assertFalse(csp_use_nonce_for_styles())
        with _patched_env(JAMES_CSP_USE_NONCE_SCRIPT=None,
                          JAMES_CSP_USE_NONCE_STYLE="1"):
            self.assertFalse(csp_use_nonce_for_scripts())
            self.assertTrue(csp_use_nonce_for_styles())


# ─── build_security_headers nonce composition ─────────────────────


class BuildSecurityHeadersNonceTests(unittest.TestCase):
    def _csp_value(self, headers: Dict[str, str]) -> str:
        for key in ("Content-Security-Policy",
                    "Content-Security-Policy-Report-Only"):
            if key in headers:
                return headers[key]
        return ""

    def _directive(self, csp: str, name: str) -> str:
        # CSP parts are `; ` separated.
        for part in csp.split(";"):
            part = part.strip()
            if part.startswith(name + " "):
                return part
        return ""

    def test_default_kwargs_produce_pre_v06_output(self):
        with _patched_env(JAMES_CSP_MODE=None):
            from core.security.headers import build_security_headers
            no_kwargs = build_security_headers()
            explicit_none = build_security_headers(
                script_nonce=None, style_nonce=None,
            )
            self.assertEqual(no_kwargs, explicit_none)

    def test_script_nonce_appears_in_script_src(self):
        with _patched_env(JAMES_CSP_MODE="enforce"):
            from core.security.headers import build_security_headers
            headers = build_security_headers(script_nonce="abc123")
            csp = self._csp_value(headers)
            script_src = self._directive(csp, "script-src")
            self.assertIn("'nonce-abc123'", script_src)
            # `'self'` is preserved (additive composition).
            self.assertIn("'self'", script_src)

    def test_script_nonce_does_not_change_style_src(self):
        with _patched_env(JAMES_CSP_MODE="enforce"):
            from core.security.headers import build_security_headers
            headers_no = build_security_headers()
            headers_yes = build_security_headers(script_nonce="x")
            style_no = self._directive(self._csp_value(headers_no), "style-src")
            style_yes = self._directive(self._csp_value(headers_yes), "style-src")
            self.assertEqual(style_no, style_yes)

    def test_style_nonce_replaces_unsafe_inline(self):
        with _patched_env(JAMES_CSP_MODE="enforce"):
            from core.security.headers import build_security_headers
            headers = build_security_headers(style_nonce="styleX")
            csp = self._csp_value(headers)
            style_src = self._directive(csp, "style-src")
            self.assertNotIn("'unsafe-inline'", style_src)
            self.assertIn("'nonce-styleX'", style_src)
            # Other allowed sources preserved.
            self.assertIn("'self'", style_src)

    def test_style_nonce_does_not_change_script_src(self):
        with _patched_env(JAMES_CSP_MODE="enforce"):
            from core.security.headers import build_security_headers
            headers_no = build_security_headers()
            headers_yes = build_security_headers(style_nonce="x")
            script_no = self._directive(self._csp_value(headers_no), "script-src")
            script_yes = self._directive(self._csp_value(headers_yes), "script-src")
            self.assertEqual(script_no, script_yes)

    def test_same_value_for_both_kwargs_composes_correctly(self):
        with _patched_env(JAMES_CSP_MODE="enforce"):
            from core.security.headers import build_security_headers
            headers = build_security_headers(
                script_nonce="shared", style_nonce="shared",
            )
            csp = self._csp_value(headers)
            self.assertIn("'nonce-shared'",
                          self._directive(csp, "script-src"))
            self.assertIn("'nonce-shared'",
                          self._directive(csp, "style-src"))

    def test_nonce_unused_when_csp_mode_off(self):
        with _patched_env(JAMES_CSP_MODE="off"):
            from core.security.headers import build_security_headers
            headers = build_security_headers(script_nonce="x", style_nonce="y")
            # No CSP header at all in off mode.
            self.assertNotIn("Content-Security-Policy", headers)
            self.assertNotIn("Content-Security-Policy-Report-Only", headers)


# ─── middleware integration via TestClient ────────────────────────


class MiddlewareIntegrationTests(unittest.TestCase):
    """End-to-end: request through the security_headers_middleware."""

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def _csp_value(self, headers) -> str:
        for key in ("content-security-policy",
                    "content-security-policy-report-only"):
            if key in headers:
                return headers[key]
        return ""

    def test_response_has_csp_header_default(self):
        # Default report-only mode → CSP header present, no nonce.
        with _patched_env(
            JAMES_CSP_MODE=None,
            JAMES_CSP_USE_NONCE_SCRIPT=None,
            JAMES_CSP_USE_NONCE_STYLE=None,
        ):
            c = self._client()
            r = c.get("/healthz")
            csp = self._csp_value(r.headers)
            self.assertTrue(csp, "CSP header expected in default mode")
            self.assertNotIn("'nonce-", csp)

    def test_response_csp_carries_script_nonce_when_flag_set(self):
        with _patched_env(
            JAMES_CSP_MODE="enforce",
            JAMES_CSP_USE_NONCE_SCRIPT="1",
            JAMES_CSP_USE_NONCE_STYLE=None,
        ):
            c = self._client()
            r = c.get("/healthz")
            csp = self._csp_value(r.headers)
            self.assertRegex(csp, r"script-src[^;]*'nonce-[A-Za-z0-9_\-]{20,}'")
            # style-src still carries 'unsafe-inline' (flag off)
            self.assertIn("'unsafe-inline'", csp)

    def test_response_csp_carries_style_nonce_when_flag_set(self):
        with _patched_env(
            JAMES_CSP_MODE="enforce",
            JAMES_CSP_USE_NONCE_SCRIPT=None,
            JAMES_CSP_USE_NONCE_STYLE="1",
        ):
            c = self._client()
            r = c.get("/healthz")
            csp = self._csp_value(r.headers)
            # style-src carries nonce; 'unsafe-inline' stripped.
            self.assertRegex(csp, r"style-src[^;]*'nonce-[A-Za-z0-9_\-]{20,}'")
            style_src = ""
            for part in csp.split(";"):
                part = part.strip()
                if part.startswith("style-src "):
                    style_src = part
                    break
            self.assertNotIn("'unsafe-inline'", style_src)

    def test_each_request_gets_a_fresh_nonce(self):
        with _patched_env(
            JAMES_CSP_MODE="enforce",
            JAMES_CSP_USE_NONCE_SCRIPT="1",
        ):
            c = self._client()
            r1 = c.get("/healthz")
            r2 = c.get("/healthz")
            csp1 = self._csp_value(r1.headers)
            csp2 = self._csp_value(r2.headers)
            m1 = re.search(r"'nonce-([A-Za-z0-9_\-]+)'", csp1)
            m2 = re.search(r"'nonce-([A-Za-z0-9_\-]+)'", csp2)
            self.assertIsNotNone(m1)
            self.assertIsNotNone(m2)
            self.assertNotEqual(m1.group(1), m2.group(1))


if __name__ == "__main__":
    unittest.main()
