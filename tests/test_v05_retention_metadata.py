"""v0.5 G4 — retention-metadata tests.

Covers:

  * Constants + `validate_retention_class` accept the 4 fixed
    values and well-formed `custom:<ISO>`; reject everything else.
  * `expiry_for` — fixed-duration math (7y / 3y / 90d) + absolute
    `custom:` semantic + `permanent` returns None.
  * `is_past_retention` — tz-awareness invariant + boundary
    semantics (now == expiry → past).
  * `row_retention_class` — regex extraction from JSON payload
    string, robust to absence + malformed.
  * `emit_lifecycle_event` integration — `retention_class` stamps
    payload + invalid values cause emit to return False (safer
    than silently stamping garbage).
  * `pending_retention_review` — scans audit_log SQLite DB for
    rows whose retention_class is past; respects `limit`; returns
    empty list on missing DB.

Uses a temporary SQLite DB built in `setUpClass` so the predicate
walks real rows, not a mock.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from core.lifecycle.replay_audit import (
    EVT_SUPERSEDE_EDGE_CREATED,
    emit_lifecycle_event,
)
from core.lifecycle.retention import (
    RETENTION_3Y,
    RETENTION_7Y,
    RETENTION_CUSTOM_PREFIX,
    RETENTION_PERMANENT,
    RETENTION_PILOT,
    VALID_RETENTION_FIXED,
    expiry_for,
    is_past_retention,
    pending_retention_review,
    row_retention_class,
    validate_retention_class,
)


class ValidateRetentionClassTests(unittest.TestCase):
    def test_four_fixed_classes_valid(self):
        for value in VALID_RETENTION_FIXED:
            with self.subTest(value=value):
                self.assertTrue(validate_retention_class(value))

    def test_custom_with_iso_valid(self):
        self.assertTrue(validate_retention_class(
            "custom:2027-01-01T00:00:00+00:00"
        ))

    def test_custom_with_z_suffix_valid(self):
        self.assertTrue(validate_retention_class("custom:2027-01-01T00:00:00Z"))

    def test_custom_naive_iso_valid(self):
        # _parse_iso treats naive as UTC.
        self.assertTrue(validate_retention_class("custom:2027-01-01T00:00:00"))

    def test_custom_with_malformed_iso_invalid(self):
        self.assertFalse(validate_retention_class("custom:not-a-date"))
        self.assertFalse(validate_retention_class("custom:"))

    def test_unrecognised_string_invalid(self):
        for value in ("forever", "10y", "1d", "0", ""):
            with self.subTest(value=value):
                self.assertFalse(validate_retention_class(value))

    def test_non_string_invalid(self):
        for value in (None, 0, 7, [], {}):
            with self.subTest(value=value):
                self.assertFalse(validate_retention_class(value))  # type: ignore[arg-type]


class ExpiryForTests(unittest.TestCase):
    def test_permanent_returns_none(self):
        self.assertIsNone(expiry_for(RETENTION_PERMANENT,
                                     "2026-01-01T00:00:00+00:00"))

    def test_7y_returns_7y_later(self):
        ts = "2026-01-01T00:00:00+00:00"
        expiry = expiry_for(RETENTION_7Y, ts)
        self.assertIsNotNone(expiry)
        # 7 * 365 = 2555 days.
        delta = expiry - datetime.fromisoformat(ts)
        self.assertEqual(delta, timedelta(days=2555))

    def test_3y_returns_3y_later(self):
        ts = "2026-01-01T00:00:00+00:00"
        expiry = expiry_for(RETENTION_3Y, ts)
        delta = expiry - datetime.fromisoformat(ts)
        self.assertEqual(delta, timedelta(days=1095))

    def test_pilot_returns_90d_later(self):
        ts = "2026-01-01T00:00:00+00:00"
        expiry = expiry_for(RETENTION_PILOT, ts)
        delta = expiry - datetime.fromisoformat(ts)
        self.assertEqual(delta, timedelta(days=90))

    def test_custom_returns_suffix_absolute(self):
        # Custom is ABSOLUTE — the suffix IS the expiry, regardless
        # of row_timestamp. Verify the row_timestamp is NOT added in.
        expiry = expiry_for(
            f"{RETENTION_CUSTOM_PREFIX}2027-06-15T12:00:00+00:00",
            "2026-01-01T00:00:00+00:00",
        )
        self.assertEqual(
            expiry,
            datetime(2027, 6, 15, 12, 0, tzinfo=timezone.utc),
        )

    def test_malformed_class_returns_none(self):
        self.assertIsNone(expiry_for("forever", "2026-01-01T00:00:00+00:00"))
        self.assertIsNone(expiry_for("custom:bad", "2026-01-01T00:00:00+00:00"))

    def test_malformed_timestamp_returns_none(self):
        self.assertIsNone(expiry_for(RETENTION_7Y, "not-a-timestamp"))


class IsPastRetentionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    def test_permanent_never_past(self):
        # Even a row from year 2000 with permanent class is "not past".
        self.assertFalse(is_past_retention(
            RETENTION_PERMANENT, "2000-01-01T00:00:00+00:00", self.now,
        ))

    def test_pilot_row_from_yesterday_not_past(self):
        ts = (self.now - timedelta(days=1)).isoformat()
        self.assertFalse(is_past_retention(RETENTION_PILOT, ts, self.now))

    def test_pilot_row_from_91d_ago_past(self):
        ts = (self.now - timedelta(days=91)).isoformat()
        self.assertTrue(is_past_retention(RETENTION_PILOT, ts, self.now))

    def test_naive_now_raises(self):
        with self.assertRaises(ValueError):
            is_past_retention(RETENTION_PILOT,
                              self.now.isoformat(), datetime(2026, 6, 1))

    def test_non_datetime_now_raises(self):
        with self.assertRaises(ValueError):
            is_past_retention(RETENTION_PILOT, "x", "2026-06-01")  # type: ignore[arg-type]

    def test_malformed_returns_false(self):
        # Both malformed class and malformed timestamp gracefully
        # return False rather than raise.
        self.assertFalse(is_past_retention(
            "bogus", "2025-01-01T00:00:00+00:00", self.now,
        ))
        self.assertFalse(is_past_retention(
            RETENTION_PILOT, "not-a-time", self.now,
        ))


class RowRetentionClassExtractionTests(unittest.TestCase):
    def test_extracts_value_from_well_formed_payload(self):
        payload = json.dumps(
            {"edge_id": "e_x", "retention_class": "7y"},
            sort_keys=True,
        )
        self.assertEqual(row_retention_class(payload), "7y")

    def test_extracts_value_from_payload_with_custom(self):
        payload = json.dumps(
            {"retention_class": "custom:2027-01-01T00:00:00+00:00"},
            sort_keys=True,
        )
        self.assertEqual(
            row_retention_class(payload),
            "custom:2027-01-01T00:00:00+00:00",
        )

    def test_returns_none_when_key_absent(self):
        payload = json.dumps({"edge_id": "e_x"})
        self.assertIsNone(row_retention_class(payload))

    def test_returns_none_on_non_string(self):
        self.assertIsNone(row_retention_class(None))  # type: ignore[arg-type]
        self.assertIsNone(row_retention_class(123))  # type: ignore[arg-type]

    def test_handles_unicode_payload(self):
        payload = json.dumps(
            {"edge_id": "엔티티", "retention_class": "pilot"},
            ensure_ascii=False, sort_keys=True,
        )
        self.assertEqual(row_retention_class(payload), "pilot")


def _make_temp_db_with_audit_schema() -> str:
    """Create a fresh SQLite DB with the audit_log schema for tests."""
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


class EmitWithRetentionClassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = _make_temp_db_with_audit_schema()

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls.db_path)
        except OSError:
            pass

    def test_emit_with_valid_retention_class_succeeds(self):
        ok = emit_lifecycle_event(
            EVT_SUPERSEDE_EDGE_CREATED,
            {"edge_id": "e_y"},
            db_path=self.db_path,
            retention_class=RETENTION_7Y,
        )
        self.assertTrue(ok)

    def test_emit_stamps_retention_class_into_payload(self):
        ok = emit_lifecycle_event(
            EVT_SUPERSEDE_EDGE_CREATED,
            {"edge_id": "e_z"},
            db_path=self.db_path,
            retention_class=RETENTION_PILOT,
        )
        self.assertTrue(ok)
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT event_payload FROM audit_log "
                "WHERE event_payload LIKE '%e_z%'"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row_retention_class(row[0]), RETENTION_PILOT)

    def test_emit_with_invalid_retention_class_returns_false(self):
        ok = emit_lifecycle_event(
            EVT_SUPERSEDE_EDGE_CREATED,
            {"edge_id": "e_bad"},
            db_path=self.db_path,
            retention_class="forever",
        )
        self.assertFalse(ok)

    def test_emit_without_retention_class_unchanged(self):
        ok = emit_lifecycle_event(
            EVT_SUPERSEDE_EDGE_CREATED,
            {"edge_id": "e_no_retention"},
            db_path=self.db_path,
        )
        self.assertTrue(ok)
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT event_payload FROM audit_log "
                "WHERE event_payload LIKE '%e_no_retention%'"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertIsNone(row_retention_class(row[0]))

    def test_emit_does_not_mutate_caller_payload(self):
        caller_payload = {"edge_id": "e_purity"}
        emit_lifecycle_event(
            EVT_SUPERSEDE_EDGE_CREATED,
            caller_payload,
            db_path=self.db_path,
            retention_class=RETENTION_PILOT,
        )
        self.assertNotIn("retention_class", caller_payload)


class PendingRetentionReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = _make_temp_db_with_audit_schema()
        cls.now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        # Seed rows directly so we control timestamps without
        # depending on the emit function's default ts.
        conn = sqlite3.connect(cls.db_path)
        try:
            seeds = [
                # 1: pilot 91d ago → PAST
                ("2026-03-01T00:00:00+00:00",
                 json.dumps({"retention_class": "pilot"})),
                # 2: 7y row from 2018 → PAST (now=2026)
                ("2018-01-01T00:00:00+00:00",
                 json.dumps({"retention_class": "7y"})),
                # 3: permanent → not past
                ("2018-01-01T00:00:00+00:00",
                 json.dumps({"retention_class": "permanent"})),
                # 4: pilot 30d ago → not past
                ("2026-05-01T00:00:00+00:00",
                 json.dumps({"retention_class": "pilot"})),
                # 5: no retention_class key → ignored
                ("2018-01-01T00:00:00+00:00",
                 json.dumps({"edge_id": "x"})),
                # 6: custom with absolute past expiry
                ("2026-01-01T00:00:00+00:00",
                 json.dumps({"retention_class": "custom:2026-05-01T00:00:00+00:00"})),
            ]
            for ts, payload in seeds:
                conn.execute(
                    "INSERT INTO audit_log "
                    "(timestamp, user_role, endpoint, blocked, "
                    " event_type, event_payload) "
                    "VALUES (?, 'system', 'evt', 0, 'lifecycle.t', ?)",
                    (ts, payload),
                )
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls.db_path)
        except OSError:
            pass

    def test_returns_expected_past_row_ids(self):
        ids = pending_retention_review(self.now, db_path=self.db_path)
        # Rows 1 (pilot past), 2 (7y past), 6 (custom past) → 3 ids.
        # Rows 3 (permanent), 4 (pilot fresh), 5 (no class) → excluded.
        self.assertEqual(len(ids), 3)
        # IDs ascending.
        self.assertEqual(ids, sorted(ids))

    def test_respects_limit(self):
        ids = pending_retention_review(self.now, db_path=self.db_path,
                                       limit=2)
        self.assertEqual(len(ids), 2)

    def test_missing_db_returns_empty(self):
        ids = pending_retention_review(
            self.now, db_path="/nonexistent/path.db",
        )
        self.assertEqual(ids, [])

    def test_naive_now_raises(self):
        with self.assertRaises(ValueError):
            pending_retention_review(datetime(2026, 6, 1),
                                     db_path=self.db_path)


if __name__ == "__main__":
    unittest.main()
