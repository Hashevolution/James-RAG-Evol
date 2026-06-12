"""v0.5 G1.a — tenant_id primitive contract tests.

Covers:

  * `current_tenant_id()` resolution order — override > env > None.
  * `with_tenant_id()` push/pop semantics + nesting + exception
    safety + explicit None override.
  * `is_tenant_isolation_enforced()` truthy / falsy parsing.
  * Emit integration — explicit kwarg / override / env all stamp;
    enforce mode rejects unstamped emits; emit returns False when
    enforce + no tenant resolvable; payload not mutated in place.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from typing import Dict

from core.lifecycle.replay_audit import (
    EVT_SUPERSEDE_EDGE_CREATED,
    emit_lifecycle_event,
)
from core.lifecycle.tenant import (
    current_tenant_id,
    is_tenant_isolation_enforced,
    with_tenant_id,
)


@contextmanager
def _patched_env(**env: str):
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


def _make_temp_db_with_audit_schema() -> str:
    fd, path = tempfile.mkstemp(suffix=".db", prefix="james-test-")
    os.close(fd)
    conn = sqlite3.connect(path)
    try:
        conn.execute("""
            CREATE TABLE audit_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL,
                user_role       TEXT,
                endpoint        TEXT,
                query           TEXT,
                answer          TEXT,
                graph_paths     TEXT,
                blocked         INTEGER NOT NULL DEFAULT 0,
                security_event  TEXT,
                elapsed_sec     REAL,
                ip_address      TEXT,
                event_type      TEXT,
                event_payload   TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()
    return path


def _last_payload(db_path: str, marker: str) -> str:
    """Fetch the most recent audit_log payload matching `marker`."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT event_payload FROM audit_log "
            "WHERE event_payload LIKE ? "
            "ORDER BY id DESC LIMIT 1",
            (f"%{marker}%",),
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else ""


class CurrentTenantIdResolutionTests(unittest.TestCase):
    def test_returns_none_when_unset(self):
        with _patched_env(JAMES_TENANT_ID=None):
            self.assertIsNone(current_tenant_id())

    def test_env_var_resolved(self):
        with _patched_env(JAMES_TENANT_ID="tenant_acme"):
            self.assertEqual(current_tenant_id(), "tenant_acme")

    def test_empty_env_treated_as_none(self):
        with _patched_env(JAMES_TENANT_ID=""):
            self.assertIsNone(current_tenant_id())

    def test_whitespace_env_treated_as_none(self):
        with _patched_env(JAMES_TENANT_ID="   "):
            self.assertIsNone(current_tenant_id())

    def test_env_whitespace_trimmed(self):
        with _patched_env(JAMES_TENANT_ID="  acme  "):
            self.assertEqual(current_tenant_id(), "acme")


class WithTenantIdTests(unittest.TestCase):
    def test_override_takes_precedence_over_env(self):
        with _patched_env(JAMES_TENANT_ID="env_tenant"):
            with with_tenant_id("override_tenant"):
                self.assertEqual(current_tenant_id(), "override_tenant")
            # After exit, falls back to env.
            self.assertEqual(current_tenant_id(), "env_tenant")

    def test_nested_override_innermost_wins(self):
        with with_tenant_id("outer"):
            with with_tenant_id("inner"):
                self.assertEqual(current_tenant_id(), "inner")
            self.assertEqual(current_tenant_id(), "outer")

    def test_explicit_none_override_nulls_env(self):
        with _patched_env(JAMES_TENANT_ID="env_tenant"):
            with with_tenant_id(None):
                self.assertIsNone(current_tenant_id())
            self.assertEqual(current_tenant_id(), "env_tenant")

    def test_exception_safe_pop(self):
        # Stack must restore even if the with-block raises.
        try:
            with with_tenant_id("doomed"):
                raise RuntimeError("simulated")
        except RuntimeError:
            pass
        self.assertIsNone(current_tenant_id())


class IsTenantIsolationEnforcedTests(unittest.TestCase):
    def test_default_false(self):
        with _patched_env(JAMES_REQUIRE_TENANT_ID=None):
            self.assertFalse(is_tenant_isolation_enforced())

    def test_truthy_values(self):
        for value in ("1", "true", "yes", "on", "enabled"):
            with self.subTest(value=value):
                with _patched_env(JAMES_REQUIRE_TENANT_ID=value):
                    self.assertTrue(is_tenant_isolation_enforced())

    def test_falsy_values(self):
        for value in ("0", "false", "no", "off", "disabled", ""):
            with self.subTest(value=value):
                with _patched_env(JAMES_REQUIRE_TENANT_ID=value):
                    self.assertFalse(is_tenant_isolation_enforced())

    def test_arbitrary_value_falsy(self):
        with _patched_env(JAMES_REQUIRE_TENANT_ID="maybe"):
            self.assertFalse(is_tenant_isolation_enforced())


class EmitIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = _make_temp_db_with_audit_schema()

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls.db_path)
        except OSError:
            pass

    def test_explicit_kwarg_stamps_payload(self):
        ok = emit_lifecycle_event(
            EVT_SUPERSEDE_EDGE_CREATED,
            {"edge_id": "e_k1_" + str(time.time())},
            db_path=self.db_path,
            tenant_id="kwarg_tenant",
        )
        self.assertTrue(ok)
        payload = _last_payload(self.db_path, "e_k1_")
        self.assertIn("kwarg_tenant", payload)
        self.assertEqual(
            json.loads(payload)["tenant_id"], "kwarg_tenant",
        )

    def test_override_stamps_payload_when_kwarg_absent(self):
        with with_tenant_id("override_tenant"):
            ok = emit_lifecycle_event(
                EVT_SUPERSEDE_EDGE_CREATED,
                {"edge_id": "e_o1_" + str(time.time())},
                db_path=self.db_path,
            )
        self.assertTrue(ok)
        payload = _last_payload(self.db_path, "e_o1_")
        self.assertEqual(
            json.loads(payload)["tenant_id"], "override_tenant",
        )

    def test_env_stamps_payload_when_kwarg_and_override_absent(self):
        with _patched_env(JAMES_TENANT_ID="env_tenant"):
            ok = emit_lifecycle_event(
                EVT_SUPERSEDE_EDGE_CREATED,
                {"edge_id": "e_e1_" + str(time.time())},
                db_path=self.db_path,
            )
        self.assertTrue(ok)
        payload = _last_payload(self.db_path, "e_e1_")
        self.assertEqual(
            json.loads(payload)["tenant_id"], "env_tenant",
        )

    def test_no_stamp_when_nothing_set(self):
        ok = emit_lifecycle_event(
            EVT_SUPERSEDE_EDGE_CREATED,
            {"edge_id": "e_n1_" + str(time.time())},
            db_path=self.db_path,
        )
        self.assertTrue(ok)
        payload = _last_payload(self.db_path, "e_n1_")
        self.assertNotIn("tenant_id", payload)

    def test_enforce_mode_rejects_when_no_tenant_resolvable(self):
        with _patched_env(JAMES_REQUIRE_TENANT_ID="1",
                          JAMES_TENANT_ID=None):
            ok = emit_lifecycle_event(
                EVT_SUPERSEDE_EDGE_CREATED,
                {"edge_id": "e_reject"},
                db_path=self.db_path,
            )
        self.assertFalse(ok)

    def test_enforce_mode_succeeds_with_explicit_kwarg(self):
        with _patched_env(JAMES_REQUIRE_TENANT_ID="1",
                          JAMES_TENANT_ID=None):
            ok = emit_lifecycle_event(
                EVT_SUPERSEDE_EDGE_CREATED,
                {"edge_id": "e_enforce_kwarg"},
                db_path=self.db_path,
                tenant_id="explicit",
            )
        self.assertTrue(ok)

    def test_enforce_mode_succeeds_with_env(self):
        with _patched_env(JAMES_REQUIRE_TENANT_ID="1",
                          JAMES_TENANT_ID="env_t"):
            ok = emit_lifecycle_event(
                EVT_SUPERSEDE_EDGE_CREATED,
                {"edge_id": "e_enforce_env"},
                db_path=self.db_path,
            )
        self.assertTrue(ok)

    def test_caller_payload_not_mutated(self):
        caller_payload = {"edge_id": "e_purity_" + str(time.time())}
        emit_lifecycle_event(
            EVT_SUPERSEDE_EDGE_CREATED,
            caller_payload,
            db_path=self.db_path,
            tenant_id="t",
        )
        self.assertNotIn("tenant_id", caller_payload)

    def test_tenant_id_composes_with_retention_class(self):
        from core.lifecycle.retention import RETENTION_7Y
        ok = emit_lifecycle_event(
            EVT_SUPERSEDE_EDGE_CREATED,
            {"edge_id": "e_combo_" + str(time.time())},
            db_path=self.db_path,
            retention_class=RETENTION_7Y,
            tenant_id="combo_tenant",
        )
        self.assertTrue(ok)
        payload = _last_payload(self.db_path, "e_combo_")
        parsed = json.loads(payload)
        self.assertEqual(parsed["retention_class"], RETENTION_7Y)
        self.assertEqual(parsed["tenant_id"], "combo_tenant")


class ThreadLocalIsolationTests(unittest.TestCase):
    def test_override_does_not_leak_across_threads(self):
        results = {}

        def worker():
            results["thread"] = current_tenant_id()

        with with_tenant_id("main_thread_tenant"):
            t = threading.Thread(target=worker)
            t.start()
            t.join()

        # Main thread set override; worker thread should NOT see it.
        self.assertIsNone(results["thread"])


if __name__ == "__main__":
    unittest.main()
