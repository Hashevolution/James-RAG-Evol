"""Run-identity isolation for the adversarial sweep.

Ali Afana's fourth finding (2026-08-19): *"Salt your run identities.
Ours were keyed by a human-readable name, and the stack silently
find-or-created the same conversations across four sweeps — turning what
were labelled before and after columns into turns 2 to 5 of a single
conversation."*

The same shape was live here. ``scripts/adversarial_sweep.py`` posted
only ``{"question": ...}``; ``routes/query.py`` defaults ``session_id``
to the literal ``"default"``, ``core/reasoning/engine_memory.py``
injects that session's last five turns into the prompt, and
``routes/query.py`` writes every answered turn back — so every case of a
sweep, and every earlier sweep, shared one conversation.

Two things are pinned here:

1. the sweep now mints a per-case, per-run conversation key, and
2. the store-level mechanism that made the shared key harmful — so a
   future change that reintroduces a constant session id fails loudly
   rather than quietly re-contaminating a measurement.

The re-measurement itself needs a live server and Ollama and is
operator-gated; see
``reports/research-runs/track-2c-run-identity-contamination-20260819.md``.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from adversarial_sweep import (  # noqa: E402
    _RUN_SALT,
    _session_id_for,
)


class TestSweepSessionKeys(unittest.TestCase):

    def test_distinct_cases_get_distinct_sessions(self):
        self.assertNotEqual(_session_id_for("bidi_01"),
                            _session_id_for("bidi_02"))

    def test_same_case_is_stable_within_a_run(self):
        self.assertEqual(_session_id_for("poison_01"),
                         _session_id_for("poison_01"))

    def test_key_carries_the_run_salt(self):
        self.assertIn(_RUN_SALT, _session_id_for("bidi_01"))

    def test_salt_is_random_hex_not_a_readable_name(self):
        # A human-readable key is precisely what let four sweeps
        # find-or-create the same conversation.
        self.assertRegex(_RUN_SALT, r"^[0-9a-f]{8}$")

    def test_key_is_never_the_bare_default(self):
        for case_id in ("bidi_01", "", "poison_05"):
            self.assertNotEqual(_session_id_for(case_id), "default")

    def test_empty_case_id_still_yields_a_key(self):
        self.assertTrue(_session_id_for("").startswith("advsweep-"))

    def test_prefix_is_greppable_in_audit_logs(self):
        self.assertRegex(_session_id_for("x"), r"^advsweep-[0-9a-f]{8}-x$")


class TestHistoryBleedMechanism(unittest.TestCase):
    """Why a constant session id contaminates a sweep, at store level."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        db = os.path.join(self._tmp, "t.db")
        import core.memory.db as memdb
        self._orig = memdb.DB_PATH
        memdb.DB_PATH = db
        memdb.init_db()
        import core.memory.conversation as conv
        self.conv = conv

    def tearDown(self):
        import core.memory.db as memdb
        memdb.DB_PATH = self._orig

    def test_shared_session_id_bleeds_earlier_turns(self):
        # Two "cases" run under one key — the pre-fix shape.
        self.conv.save_turn("default", "case one question", "answer one")
        ctx = self.conv.get_history_context("default", limit=5)
        self.assertIn("case one question", ctx,
                      "a later case would see the earlier one in its prompt")

    def test_distinct_session_ids_are_isolated(self):
        self.conv.save_turn(_session_id_for("case_a"), "question A", "answer A")
        ctx_b = self.conv.get_history_context(_session_id_for("case_b"),
                                              limit=5)
        self.assertEqual(ctx_b, "",
                         "a salted per-case key must start from empty history")

    def test_turns_accumulate_under_one_key(self):
        for i in range(3):
            self.conv.save_turn("default", f"q{i}", f"a{i}")
        ctx = self.conv.get_history_context("default", limit=5)
        for i in range(3):
            self.assertIn(f"q{i}", ctx)


class TestRunnerStillPostsRawText(unittest.TestCase):
    """The salt must not disturb the normalization discipline: the
    runner still sends the fixture payload byte-for-byte, because the
    bidi cases test the server-side gate."""

    def test_post_query_does_not_normalise(self):
        src = (Path(__file__).resolve().parent.parent /
               "scripts" / "adversarial_sweep.py").read_text(encoding="utf-8")
        body = re.search(r"def _post_query.*?\n(?=\ndef )", src, re.S)
        self.assertIsNotNone(body)
        fn = body.group(0)
        self.assertIn('"question": text', fn,
                      "the raw fixture text must go on the wire unchanged")
        for forbidden in ("normalize(", ".lower()", "strip()"):
            self.assertNotIn(forbidden, fn,
                             f"_post_query must not {forbidden}")


if __name__ == "__main__":
    unittest.main()
