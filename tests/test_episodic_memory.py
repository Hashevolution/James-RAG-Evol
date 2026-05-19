"""Tests for ``core/memory/episodic.py`` (Cognitive Phase 3 PR-9a).

Covers the 10-item test plan in ``docs/design/v0.3-episodic-memory.md``
§"Test plan". Every test uses a temp DB so the suite is hermetic and
parallel-safe.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.memory.episodic import (  # noqa: E402
    EpisodicEvent,
    EpisodicMemory,
    KNOWN_STAGES,
    MAX_SUMMARY_CHARS,
)


def _fresh_store() -> EpisodicMemory:
    """One EpisodicMemory pointing at a freshly-created temp DB."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return EpisodicMemory(db_path=f.name)


class RecordTests(unittest.TestCase):

    def test_record_returns_sortable_id(self):
        """Plan item 1 — event_id sorts chronologically by ts."""
        em = _fresh_store()
        ids = []
        for i in range(5):
            ids.append(em.record(
                session_id="s1", turn_id="t1", stage="synth",
                summary=f"event {i}",
            ))
            # Force a millisecond gap so the ts-prefix differs.
            time.sleep(0.002)
        self.assertEqual(ids, sorted(ids),
            "event_ids must be sortable in chronological order — "
            "the ULID-shaped ts-prefix is the guarantee replay relies on")

    def test_record_validates_stage(self):
        """Plan item 6 — unknown stage raises ValueError."""
        em = _fresh_store()
        with self.assertRaises(ValueError) as ctx:
            em.record(session_id="s1", turn_id="t1",
                      stage="snyth", summary="oops")
        self.assertIn("unknown stage", str(ctx.exception))

    def test_record_truncates_long_summary(self):
        """Plan item 7 — summary > MAX_SUMMARY_CHARS lands truncated."""
        em = _fresh_store()
        big = "x" * 5000
        eid = em.record(session_id="s1", turn_id="t1",
                        stage="synth", summary=big)
        events = em.events_for_turn("s1", "t1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_id, eid)
        self.assertEqual(len(events[0].summary), MAX_SUMMARY_CHARS)

    def test_record_rejects_empty_session_id(self):
        em = _fresh_store()
        with self.assertRaises(ValueError):
            em.record(session_id="", turn_id="t1",
                      stage="synth", summary="x")

    def test_record_rejects_empty_turn_id(self):
        em = _fresh_store()
        with self.assertRaises(ValueError):
            em.record(session_id="s1", turn_id="",
                      stage="synth", summary="x")

    def test_record_accepts_extras_and_trace_id(self):
        em = _fresh_store()
        eid = em.record(
            session_id="s1", turn_id="t1", stage="synth",
            summary="ok", extras={"foo": 1, "bar": [1, 2]},
            trace_id="abc-123",
        )
        events = em.events_for_turn("s1", "t1")
        self.assertEqual(events[0].event_id, eid)
        self.assertEqual(events[0].extras, {"foo": 1, "bar": [1, 2]})
        self.assertEqual(events[0].trace_id, "abc-123")

    def test_record_handles_non_string_summary_gracefully(self):
        """A misused wiring point that passes a non-string summary
        should land as a coerced empty/string row, not crash the writer.
        """
        em = _fresh_store()
        em.record(session_id="s1", turn_id="t1",
                  stage="synth", summary=None)
        em.record(session_id="s1", turn_id="t1",
                  stage="synth", summary=42)   # type: ignore[arg-type]
        events = em.events_for_turn("s1", "t1")
        self.assertEqual(len(events), 2)


class ReadTests(unittest.TestCase):

    def test_events_for_turn_returns_chronological(self):
        """Plan item 2 — events_for_turn sorted by event_id ASC."""
        em = _fresh_store()
        recorded = []
        for i in range(4):
            recorded.append(em.record(
                session_id="s1", turn_id="t1", stage="synth",
                summary=f"event {i}",
            ))
            time.sleep(0.002)
        events = em.events_for_turn("s1", "t1")
        self.assertEqual([e.event_id for e in events], recorded)

    def test_recent_events_respects_limit(self):
        """Plan item 3 — recent_events honors `limit` and `stages`."""
        em = _fresh_store()
        for i in range(10):
            em.record(session_id="s1", turn_id=f"t{i}",
                      stage="synth", summary=f"e{i}")
            time.sleep(0.001)
        events = em.recent_events("s1", limit=3)
        self.assertEqual(len(events), 3)
        # The 3 most recent → events 7/8/9 (chronological order).
        self.assertEqual([e.summary for e in events], ["e7", "e8", "e9"])

    def test_recent_events_filters_by_stage(self):
        em = _fresh_store()
        em.record(session_id="s1", turn_id="t1",
                  stage="synth", summary="synth1")
        em.record(session_id="s1", turn_id="t1",
                  stage="plan", summary="plan1")
        em.record(session_id="s1", turn_id="t2",
                  stage="reflect", summary="reflect1")
        em.record(session_id="s1", turn_id="t2",
                  stage="plan", summary="plan2")
        plans = em.recent_events("s1", limit=20, stages=("plan",))
        self.assertEqual(len(plans), 2)
        self.assertEqual({e.summary for e in plans}, {"plan1", "plan2"})

    def test_recent_events_zero_limit_returns_empty(self):
        em = _fresh_store()
        em.record(session_id="s1", turn_id="t1",
                  stage="synth", summary="x")
        self.assertEqual(em.recent_events("s1", limit=0), [])

    def test_get_by_trace_id_within_session(self):
        """Plan item 9 — record made with trace_id is retrievable."""
        em = _fresh_store()
        em.record(session_id="s1", turn_id="t1", stage="synth",
                  summary="a", trace_id="trace-1")
        em.record(session_id="s1", turn_id="t2", stage="reflect",
                  summary="b", trace_id="trace-1")
        em.record(session_id="s1", turn_id="t3", stage="verify",
                  summary="c", trace_id="trace-2")
        out = em.get_by_trace_id("s1", "trace-1")
        self.assertEqual({e.summary for e in out}, {"a", "b"})

    def test_get_by_trace_id_empty_returns_empty(self):
        em = _fresh_store()
        em.record(session_id="s1", turn_id="t1", stage="synth",
                  summary="a", trace_id="trace-1")
        self.assertEqual(em.get_by_trace_id("s1", ""), [])


class SessionIsolationTests(unittest.TestCase):
    """Plan item 5 — the §5.7.6 'writes never escape upward' invariant.
    Every reader filters on session_id at the SQL layer; a session B
    must never observe session A's rows.
    """

    def test_recent_events_isolated_per_session(self):
        em = _fresh_store()
        em.record(session_id="A", turn_id="t1",
                  stage="synth", summary="from A")
        em.record(session_id="B", turn_id="t1",
                  stage="synth", summary="from B")
        a_events = em.recent_events("A", limit=20)
        b_events = em.recent_events("B", limit=20)
        self.assertEqual(len(a_events), 1)
        self.assertEqual(a_events[0].summary, "from A")
        self.assertEqual(len(b_events), 1)
        self.assertEqual(b_events[0].summary, "from B")

    def test_events_for_turn_isolated_per_session(self):
        em = _fresh_store()
        em.record(session_id="A", turn_id="t1",
                  stage="synth", summary="from A")
        em.record(session_id="B", turn_id="t1",   # same turn_id!
                  stage="synth", summary="from B")
        a = em.events_for_turn("A", "t1")
        b = em.events_for_turn("B", "t1")
        self.assertEqual([e.summary for e in a], ["from A"])
        self.assertEqual([e.summary for e in b], ["from B"])

    def test_get_by_trace_id_isolated_per_session(self):
        em = _fresh_store()
        em.record(session_id="A", turn_id="t1", stage="synth",
                  summary="from A", trace_id="shared-trace")
        em.record(session_id="B", turn_id="t1", stage="synth",
                  summary="from B", trace_id="shared-trace")
        # Same trace_id in both sessions — must still isolate.
        self.assertEqual(
            [e.summary for e in em.get_by_trace_id("A", "shared-trace")],
            ["from A"],
        )
        self.assertEqual(
            [e.summary for e in em.get_by_trace_id("B", "shared-trace")],
            ["from B"],
        )

    def test_clear_session_only_removes_targeted_session(self):
        em = _fresh_store()
        em.record(session_id="A", turn_id="t1",
                  stage="synth", summary="from A")
        em.record(session_id="B", turn_id="t1",
                  stage="synth", summary="from B")
        removed = em.clear_session("A")
        self.assertEqual(removed, 1)
        self.assertEqual(em.recent_events("A", limit=20), [])
        # B's row survives.
        self.assertEqual(len(em.recent_events("B", limit=20)), 1)


class LifecycleTests(unittest.TestCase):

    def test_clear_session_returns_rows_removed(self):
        """Plan item 4 — clear_session removes exactly that session."""
        em = _fresh_store()
        for i in range(3):
            em.record(session_id="A", turn_id=f"t{i}",
                      stage="synth", summary=f"e{i}")
        removed = em.clear_session("A")
        self.assertEqual(removed, 3)
        self.assertEqual(em.clear_session("A"), 0)   # idempotent

    def test_prune_older_than_removes_old_rows(self):
        """Plan item 10 — retention sweep deletes rows older than the
        cutoff and keeps newer ones.
        """
        em = _fresh_store()
        em.record(session_id="s1", turn_id="t1",
                  stage="synth", summary="recent")
        # Backdate one row by 30 days. Direct SQL since record()
        # always stamps with time.time(); the backdating is a test-
        # only mutation to simulate the retention edge.
        with em._connect() as conn:
            conn.execute(
                "INSERT INTO episodic_events "
                "(event_id, session_id, turn_id, ts, stage, summary, "
                "score, extras_json, trace_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "old-1",
                    "s1", "t-old",
                    time.time() - (30 * 86400),
                    "synth", "old", 0.0, "{}", "",
                ),
            )
        removed = em.prune_older_than(max_age_days=7)
        self.assertEqual(removed, 1)
        remaining = em.recent_events("s1", limit=20)
        self.assertEqual([e.summary for e in remaining], ["recent"])

    def test_prune_negative_or_zero_age_raises(self):
        em = _fresh_store()
        with self.assertRaises(ValueError):
            em.prune_older_than(max_age_days=0)
        with self.assertRaises(ValueError):
            em.prune_older_than(max_age_days=-3)

    def test_idempotent_schema_init(self):
        """Plan item 8 — re-running __init__ on an existing DB is a no-op."""
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        em1 = EpisodicMemory(db_path=f.name)
        em1.record(session_id="s1", turn_id="t1",
                   stage="synth", summary="pre-reinit")
        # Spinning up a second instance against the same file must
        # not drop / recreate the table.
        em2 = EpisodicMemory(db_path=f.name)
        events = em2.recent_events("s1", limit=20)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].summary, "pre-reinit")


class EventDataclassTests(unittest.TestCase):

    def test_event_is_frozen(self):
        em = _fresh_store()
        em.record(session_id="s1", turn_id="t1",
                  stage="synth", summary="x")
        ev = em.events_for_turn("s1", "t1")[0]
        with self.assertRaises(Exception):
            # frozen dataclass disallows attribute assignment
            ev.summary = "tampered"   # type: ignore[misc]

    def test_known_stages_non_empty(self):
        # Guard against an accidental edit emptying the stage set
        # and turning every record() validation into a no-op.
        self.assertGreater(len(KNOWN_STAGES), 0)
        # The cognitive middleware's named stages must all be present.
        for stage in ("retrieve", "plan", "reflect",
                      "verify", "synth", "tool_call", "error"):
            self.assertIn(stage, KNOWN_STAGES)


class EventDataclassFieldShapeTests(unittest.TestCase):
    """Spot-checks for the EpisodicEvent surface — a future schema
    change that drops one of these fields must update consumers
    (PR-9b and the design doc) rather than land silently.
    """

    def test_required_fields_present(self):
        em = _fresh_store()
        em.record(session_id="s1", turn_id="t1",
                  stage="synth", summary="x")
        ev = em.events_for_turn("s1", "t1")[0]
        self.assertIsInstance(ev, EpisodicEvent)
        for attr in ("event_id", "session_id", "turn_id", "ts",
                     "stage", "summary", "score", "extras", "trace_id"):
            self.assertTrue(hasattr(ev, attr),
                            f"EpisodicEvent missing attribute {attr!r}")


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
