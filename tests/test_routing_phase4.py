"""v0.6.1 Phase 4 — privacy gate + cost cap unit tests.

Covers the design memo §5 test plan items 1-4. Surface lock-tests
live in ``test_measurement_critical_surfaces.py`` (item 5); pre-
flight wiring lives in ``scripts/research/pre_flight_check.py``
(item 6).
"""
from __future__ import annotations

import json
import os
import unittest

from core.routing import (
    CostBudget,
    PrivacyCheck,
    check_cap,
    check_query_privacy,
    default_budget,
    detect_pii,
)
from core.routing.cost_cap import _SCHEMA_VERSION, _current_month


# ───────────────────────── privacy ───────────────────────────────


class DetectPiiTests(unittest.TestCase):
    """Pattern hits + misses + redaction safety (memo §5.1)."""

    def test_empty_returns_empty(self):
        self.assertEqual(detect_pii(""), [])
        self.assertEqual(detect_pii(None), [])  # type: ignore[arg-type]
        self.assertEqual(detect_pii(123), [])   # type: ignore[arg-type]

    def test_korean_rrn_match(self):
        out = detect_pii("주민번호 900101-1234567 입니다")
        names = [n for n, _ in out]
        self.assertIn("korean_rrn", names)
        # redacted span never carries the raw value
        for name, redacted in out:
            if name == "korean_rrn":
                self.assertNotIn("1234567", redacted)
                self.assertNotIn("900101-1234567", redacted)
                self.assertIn("…", redacted)

    def test_phone_kr_match(self):
        out = detect_pii("연락처는 010-1234-5678 입니다")
        names = [n for n, _ in out]
        self.assertIn("phone_kr", names)

    def test_email_match(self):
        out = detect_pii("contact: alice.bob@example.com")
        names = [n for n, _ in out]
        self.assertIn("email", names)
        for name, redacted in out:
            if name == "email":
                self.assertNotIn("alice.bob@example.com", redacted)

    def test_card_number_match(self):
        out = detect_pii("카드번호 4111-1111-1111-1111 확인")
        names = [n for n, _ in out]
        self.assertIn("card_number", names)

    def test_clean_text_no_match(self):
        self.assertEqual(detect_pii("오늘 날씨 어때?"), [])
        self.assertEqual(
            detect_pii("Find the latest research papers."), []
        )

    def test_multiple_patterns_same_text(self):
        out = detect_pii(
            "이름 김철수 이메일 kim@a.co 전화 010-1111-2222"
        )
        names = {n for n, _ in out}
        self.assertIn("email", names)
        self.assertIn("phone_kr", names)


class CheckQueryPrivacyTests(unittest.TestCase):
    """force_local matrix (memo §5.2)."""

    def setUp(self):
        self._env = {
            k: os.environ.pop(k)
            for k in (
                "JAMES_PRIVACY_FORCE_LOCAL",
                "JAMES_PRIVACY_PII_PATTERNS_EXTRA",
            )
            if k in os.environ
        }

    def tearDown(self):
        for k in ("JAMES_PRIVACY_FORCE_LOCAL",
                  "JAMES_PRIVACY_PII_PATTERNS_EXTRA"):
            os.environ.pop(k, None)
        for k, v in self._env.items():
            os.environ[k] = v

    def test_flag_off_match_does_not_block(self):
        os.environ.pop("JAMES_PRIVACY_FORCE_LOCAL", None)
        out = check_query_privacy("주민번호 900101-1234567")
        self.assertIsInstance(out, PrivacyCheck)
        self.assertFalse(out.force_local)
        self.assertIn("korean_rrn", out.reasons)

    def test_flag_on_match_blocks(self):
        os.environ["JAMES_PRIVACY_FORCE_LOCAL"] = "1"
        out = check_query_privacy("주민번호 900101-1234567")
        self.assertTrue(out.force_local)
        self.assertIn("korean_rrn", out.reasons)

    def test_flag_on_no_match_does_not_block(self):
        os.environ["JAMES_PRIVACY_FORCE_LOCAL"] = "1"
        out = check_query_privacy("오늘 날씨 어때")
        self.assertFalse(out.force_local)
        self.assertEqual(out.reasons, [])

    def test_explicit_flag_overrides_env(self):
        os.environ.pop("JAMES_PRIVACY_FORCE_LOCAL", None)
        out = check_query_privacy(
            "이메일 a@b.co", force_local_flag=True,
        )
        self.assertTrue(out.force_local)

    def test_extra_pattern_env_extends(self):
        os.environ["JAMES_PRIVACY_FORCE_LOCAL"] = "1"
        os.environ["JAMES_PRIVACY_PII_PATTERNS_EXTRA"] = (
            r"secret_token:SK-[A-Z0-9]{8}"
        )
        out = check_query_privacy("api key SK-ABCD1234 here")
        self.assertTrue(out.force_local)
        self.assertIn("secret_token", out.reasons)

    def test_invalid_extra_pattern_skipped(self):
        os.environ["JAMES_PRIVACY_PII_PATTERNS_EXTRA"] = (
            r"bad:[unclosed"
        )
        # Must not raise.
        out = check_query_privacy("alice@example.com")
        self.assertIn("email", out.reasons)


# ───────────────────────── cost cap ──────────────────────────────


class CostBudgetTests(unittest.TestCase):
    """Atomic write + rollover + fresh-on-error (memo §5.3)."""

    def setUp(self):
        self.tmpdir = self._mktmp()
        self.path = os.path.join(self.tmpdir, ".james_cost.json")

    def tearDown(self):
        for p in (self.path, self.path + ".tmp"):
            try:
                os.remove(p)
            except OSError:
                pass
        for f in os.listdir(self.tmpdir):
            try:
                os.remove(os.path.join(self.tmpdir, f))
            except OSError:
                pass
        try:
            os.rmdir(self.tmpdir)
        except OSError:
            pass

    @staticmethod
    def _mktmp() -> str:
        import tempfile
        return tempfile.mkdtemp(prefix="james_cost_test_")

    def test_fresh_status_no_cap(self):
        b = CostBudget(self.path, cap_usd=0.0)
        s = b.status()
        self.assertTrue(s.under_cap)
        self.assertEqual(s.used_tokens, 0)
        self.assertEqual(s.used_usd_est, 0.0)
        self.assertIn("no_cap", s.reasons)

    def test_record_persists_atomic(self):
        b = CostBudget(self.path, cap_usd=10.0)
        b.record(tokens=1000, usd_est=0.5)
        with open(self.path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["tokens"], 1000)
        self.assertAlmostEqual(data["usd_est"], 0.5)
        self.assertEqual(data["schema"], _SCHEMA_VERSION)
        self.assertEqual(data["month"], _current_month())

    def test_record_accumulates(self):
        b = CostBudget(self.path, cap_usd=10.0)
        b.record(100, 0.1)
        b.record(200, 0.2)
        s = b.status()
        self.assertEqual(s.used_tokens, 300)
        self.assertAlmostEqual(s.used_usd_est, 0.3)

    def test_month_rollover_resets(self):
        b = CostBudget(self.path, cap_usd=10.0)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(
                {"month": "1999-01", "tokens": 999,
                 "usd_est": 99.9, "schema": _SCHEMA_VERSION},
                fh,
            )
        s = b.status()
        self.assertEqual(s.used_tokens, 0)
        self.assertEqual(s.used_usd_est, 0.0)
        self.assertEqual(s.month, _current_month())

    def test_schema_mismatch_resets(self):
        b = CostBudget(self.path, cap_usd=10.0)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(
                {"month": _current_month(), "tokens": 999,
                 "usd_est": 99.9, "schema": 999},
                fh,
            )
        s = b.status()
        self.assertEqual(s.used_tokens, 0)

    def test_malformed_file_fresh_tally(self):
        b = CostBudget(self.path, cap_usd=10.0)
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{ this is not json")
        s = b.status()
        self.assertEqual(s.used_tokens, 0)


class CheckCapTests(unittest.TestCase):
    """Boundary + env (memo §5.4)."""

    def setUp(self):
        self._env = {
            k: os.environ.pop(k)
            for k in (
                "JAMES_COST_CAP_MONTHLY_USD",
                "JAMES_COST_CAP_FILE",
            )
            if k in os.environ
        }
        import tempfile
        self.tmpdir = tempfile.mkdtemp(prefix="james_cap_test_")
        self.path = os.path.join(self.tmpdir, ".james_cost.json")

    def tearDown(self):
        for k in ("JAMES_COST_CAP_MONTHLY_USD",
                  "JAMES_COST_CAP_FILE"):
            os.environ.pop(k, None)
        for k, v in self._env.items():
            os.environ[k] = v
        try:
            os.remove(self.path)
        except OSError:
            pass
        try:
            os.rmdir(self.tmpdir)
        except OSError:
            pass

    def test_no_cap_always_under(self):
        b = CostBudget(self.path, cap_usd=0.0)
        s = check_cap(1_000_000, budget=b, usd_estimate=999.0)
        self.assertTrue(s.under_cap)

    def test_under_cap_projection(self):
        b = CostBudget(self.path, cap_usd=10.0)
        b.record(0, 5.0)
        s = check_cap(100, budget=b, usd_estimate=4.0)
        self.assertTrue(s.under_cap)

    def test_over_cap_projection(self):
        b = CostBudget(self.path, cap_usd=10.0)
        b.record(0, 5.0)
        s = check_cap(100, budget=b, usd_estimate=6.0)
        self.assertFalse(s.under_cap)
        self.assertIn("over_cap", s.reasons)

    def test_default_budget_reads_env(self):
        os.environ["JAMES_COST_CAP_FILE"] = self.path
        os.environ["JAMES_COST_CAP_MONTHLY_USD"] = "12.50"
        b = default_budget()
        self.assertEqual(b.path, self.path)
        self.assertAlmostEqual(b.cap_usd, 12.5)

    def test_default_budget_bad_cap_falls_to_zero(self):
        os.environ["JAMES_COST_CAP_MONTHLY_USD"] = "not-a-number"
        b = default_budget()
        self.assertEqual(b.cap_usd, 0.0)


if __name__ == "__main__":
    unittest.main()
