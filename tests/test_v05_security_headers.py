"""v0.5 — security headers contract tests.

Covers:

  * Default CSP mode = report-only → header name is
    `Content-Security-Policy-Report-Only`.
  * `JAMES_CSP_MODE=enforce` → header name flips to
    `Content-Security-Policy`.
  * `JAMES_CSP_MODE=off` → no CSP header at all.
  * CSP directive list — every required directive present + value
    matches the documented contract.
  * Always-on headers (X-Frame-Options / X-Content-Type-Options /
    Referrer-Policy / Permissions-Policy) present regardless of
    CSP mode.
  * HSTS opt-in semantics — absent by default, present when
    `JAMES_HSTS_MAX_AGE` is set, includes `includeSubDomains` /
    `preload` when their respective env flags are set.
  * `JAMES_CSP_REPORT_URI` appears as `report-uri` directive when
    set.
  * Env-flag truthiness parser — covers `1` / `true` / `yes` /
    `on` plus the falsy variants.
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from typing import Dict


@contextmanager
def _patched_env(**env: str):
    """Temporarily override env vars; restore afterwards.

    Variables passed as `None` are unset (instead of set to the
    string "None"). This is the operator-facing test ergonomic.
    """
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


def _headers(**env: str) -> Dict[str, str]:
    """Build headers under a patched env, no module import order
    side effects."""
    from core.security.headers import build_security_headers
    with _patched_env(**env):
        return build_security_headers()


class CspModeTests(unittest.TestCase):
    def test_default_mode_report_only(self):
        # No env set → defaults to report-only.
        h = _headers(JAMES_CSP_MODE=None)
        self.assertIn("Content-Security-Policy-Report-Only", h)
        self.assertNotIn("Content-Security-Policy", h)

    def test_explicit_report_only(self):
        h = _headers(JAMES_CSP_MODE="report-only")
        self.assertIn("Content-Security-Policy-Report-Only", h)

    def test_enforce_mode_flips_header_name(self):
        h = _headers(JAMES_CSP_MODE="enforce")
        self.assertIn("Content-Security-Policy", h)
        self.assertNotIn("Content-Security-Policy-Report-Only", h)

    def test_off_mode_omits_csp_entirely(self):
        h = _headers(JAMES_CSP_MODE="off")
        self.assertNotIn("Content-Security-Policy", h)
        self.assertNotIn("Content-Security-Policy-Report-Only", h)

    def test_off_synonyms(self):
        for value in ("disable", "disabled", "0", "false", "no"):
            with self.subTest(value=value):
                h = _headers(JAMES_CSP_MODE=value)
                self.assertNotIn("Content-Security-Policy", h)
                self.assertNotIn("Content-Security-Policy-Report-Only", h)

    def test_enforce_synonyms(self):
        for value in ("enforced", "strict", "on", "1", "true", "yes"):
            with self.subTest(value=value):
                h = _headers(JAMES_CSP_MODE=value)
                self.assertIn("Content-Security-Policy", h)

    def test_unrecognised_value_falls_through_to_report_only(self):
        h = _headers(JAMES_CSP_MODE="bogus")
        self.assertIn("Content-Security-Policy-Report-Only", h)


class CspContentTests(unittest.TestCase):
    def setUp(self):
        self.h = _headers(JAMES_CSP_MODE="enforce")
        self.csp = self.h["Content-Security-Policy"]

    def test_default_src_self(self):
        self.assertIn("default-src 'self'", self.csp)

    def test_script_src_self_only(self):
        # Strict-mode-ready: no unsafe-inline / unsafe-eval.
        self.assertIn("script-src 'self'", self.csp)
        # No 'unsafe-inline' / 'unsafe-eval' in script-src directive.
        script_part = next(
            (p for p in self.csp.split(";") if "script-src" in p), "",
        )
        self.assertNotIn("unsafe-inline", script_part)
        self.assertNotIn("unsafe-eval", script_part)

    def test_style_src_has_unsafe_inline_for_now(self):
        # Documented in audit doc §3 — 409 inline `style="..."`
        # attributes still present; style-src needs 'unsafe-inline'
        # until nonce middleware OR mass conversion lands.
        self.assertIn("style-src", self.csp)
        style_part = next(
            (p for p in self.csp.split(";") if "style-src" in p), "",
        )
        self.assertIn("'unsafe-inline'", style_part)

    def test_frame_ancestors_none(self):
        self.assertIn("frame-ancestors 'none'", self.csp)

    def test_object_src_none(self):
        self.assertIn("object-src 'none'", self.csp)

    def test_base_uri_self(self):
        self.assertIn("base-uri 'self'", self.csp)

    def test_form_action_self(self):
        self.assertIn("form-action 'self'", self.csp)

    def test_upgrade_insecure_requests(self):
        self.assertIn("upgrade-insecure-requests", self.csp)

    def test_img_src_allows_data(self):
        # Brain-pulse SVG icons use data: URLs.
        self.assertIn("img-src 'self' data:", self.csp)

    def test_font_src_allows_google_fonts(self):
        # tokens.css @import URL.
        self.assertIn("font-src 'self' https://fonts.gstatic.com", self.csp)

    def test_report_uri_set_when_env_set(self):
        h = _headers(
            JAMES_CSP_MODE="enforce",
            JAMES_CSP_REPORT_URI="https://example.com/csp-report",
        )
        self.assertIn(
            "report-uri https://example.com/csp-report",
            h["Content-Security-Policy"],
        )

    def test_report_uri_absent_by_default(self):
        self.assertNotIn("report-uri", self.csp)


class AlwaysOnHeadersTests(unittest.TestCase):
    """Headers that are present regardless of CSP mode."""

    def test_x_frame_options_deny(self):
        for mode in ("off", "report-only", "enforce"):
            with self.subTest(mode=mode):
                h = _headers(JAMES_CSP_MODE=mode)
                self.assertEqual(h["X-Frame-Options"], "DENY")

    def test_x_content_type_options_nosniff(self):
        for mode in ("off", "report-only", "enforce"):
            with self.subTest(mode=mode):
                h = _headers(JAMES_CSP_MODE=mode)
                self.assertEqual(h["X-Content-Type-Options"], "nosniff")

    def test_referrer_policy_strict_origin(self):
        h = _headers(JAMES_CSP_MODE="off")
        self.assertEqual(
            h["Referrer-Policy"], "strict-origin-when-cross-origin",
        )

    def test_permissions_policy_blocks_sensors(self):
        h = _headers(JAMES_CSP_MODE="off")
        pp = h["Permissions-Policy"]
        for sensor in ("accelerometer", "camera", "geolocation",
                       "gyroscope", "magnetometer", "microphone",
                       "payment", "usb"):
            with self.subTest(sensor=sensor):
                self.assertIn(f"{sensor}=()", pp)


class HstsTests(unittest.TestCase):
    def test_absent_by_default(self):
        h = _headers(JAMES_HSTS_MAX_AGE=None)
        self.assertNotIn("Strict-Transport-Security", h)

    def test_zero_max_age_omits_header(self):
        h = _headers(JAMES_HSTS_MAX_AGE="0")
        self.assertNotIn("Strict-Transport-Security", h)

    def test_negative_max_age_omits_header(self):
        h = _headers(JAMES_HSTS_MAX_AGE="-1")
        self.assertNotIn("Strict-Transport-Security", h)

    def test_malformed_max_age_omits_header(self):
        h = _headers(JAMES_HSTS_MAX_AGE="not-a-number")
        self.assertNotIn("Strict-Transport-Security", h)

    def test_positive_max_age_emits_header(self):
        h = _headers(JAMES_HSTS_MAX_AGE="31536000")
        self.assertEqual(
            h["Strict-Transport-Security"], "max-age=31536000",
        )

    def test_include_subdomains_flag(self):
        h = _headers(
            JAMES_HSTS_MAX_AGE="31536000",
            JAMES_HSTS_INCLUDE_SUBDOMAINS="1",
        )
        self.assertIn("includeSubDomains", h["Strict-Transport-Security"])

    def test_preload_flag(self):
        h = _headers(
            JAMES_HSTS_MAX_AGE="63072000",
            JAMES_HSTS_PRELOAD="1",
        )
        self.assertIn("preload", h["Strict-Transport-Security"])

    def test_full_preload_ready(self):
        h = _headers(
            JAMES_HSTS_MAX_AGE="63072000",
            JAMES_HSTS_INCLUDE_SUBDOMAINS="1",
            JAMES_HSTS_PRELOAD="1",
        )
        self.assertEqual(
            h["Strict-Transport-Security"],
            "max-age=63072000; includeSubDomains; preload",
        )

    def test_truthy_synonyms_for_flags(self):
        for value in ("1", "true", "yes", "on", "enabled"):
            with self.subTest(value=value):
                h = _headers(
                    JAMES_HSTS_MAX_AGE="31536000",
                    JAMES_HSTS_INCLUDE_SUBDOMAINS=value,
                )
                self.assertIn(
                    "includeSubDomains", h["Strict-Transport-Security"],
                )

    def test_falsy_flags_omit_directive(self):
        for value in ("0", "false", "no", "off", ""):
            with self.subTest(value=value):
                h = _headers(
                    JAMES_HSTS_MAX_AGE="31536000",
                    JAMES_HSTS_INCLUDE_SUBDOMAINS=value,
                )
                self.assertNotIn(
                    "includeSubDomains", h["Strict-Transport-Security"],
                )


if __name__ == "__main__":
    unittest.main()
