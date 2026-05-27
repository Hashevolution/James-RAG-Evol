"""F9.1 — unit tests for scripts/research/query_rewriter_audit.py.

The audit script itself does not modify production; these tests cover
the heuristic logic (anchor classification + bucket aggregation +
report-card output shape) so the audit's verdict stays trustworthy
across reruns.

What the audit script does (recap)
----------------------------------

1. Runs a curated fixture of queries through ``QueryRewriter.rewrite(
   force=True)``.
2. For each row, classifies anchor outcome into one of four states:
   ``already_present`` / ``added`` / ``dropped`` / ``absent``.
3. Aggregates per-bucket (anchor_added_rate, anchor_dropped_rate,
   latency_ms_mean).
4. Writes a per-run report card to
   ``reports/research-runs/query-rewriter-audit-<stamp>.json``.

What these tests cover
----------------------

- The substring matcher (``_anchors_in_text``) is case-insensitive and
  handles the KO/EN mixed-token edge case (no whitespace between
  Hangul and Latin) the F9 fixture explicitly designs around.
- ``_classify_anchor_outcome`` produces the four expected anchor lists
  + the ``added_count`` / ``dropped_count`` aggregates the bucket
  summary depends on.
- The fixture itself is shaped correctly: each row has the required
  keys + a bucket from the documented set + a non-empty anchor list.
  Catches drift if someone tweaks the fixture without keeping the
  audit script's invariants.
- ``_bucket_summary`` aggregates correctly across mixed-state rows
  (one bucket has both an "added" row and a "dropped" row).

These tests do NOT cover the LLM-backed ``_audit_one`` (which is what
the operator runs against a live Ollama). The unit test for the
rewriter LLM dispatch already lives in ``tests/test_query_rewriter.py``.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_audit_module():
    """Import the audit script as a module without installing it."""
    spec = importlib.util.spec_from_file_location(
        "query_rewriter_audit",
        ROOT / "scripts" / "research" / "query_rewriter_audit.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit_mod = _load_audit_module()


class AnchorMatcherTests(unittest.TestCase):
    """Case-insensitive substring matcher with mixed-script handling."""

    def test_exact_match_returns_anchor(self):
        got = audit_mod._anchors_in_text("MCP 설계자", ["MCP"])
        self.assertEqual(got, ["MCP"])

    def test_case_insensitive(self):
        got = audit_mod._anchors_in_text("mcp protocol", ["MCP"])
        self.assertEqual(got, ["MCP"])

    def test_mixed_script_no_whitespace_token(self):
        # F9 fixture edge case: "MCP설계자" has no whitespace between
        # Latin (MCP) and Hangul (설계자). Substring matcher must still
        # find the anchor.
        got = audit_mod._anchors_in_text("MCP설계자에 대해 설명", ["MCP"])
        self.assertEqual(got, ["MCP"])

    def test_returns_all_anchors_present(self):
        got = audit_mod._anchors_in_text(
            "Anthropic의 MCP 설계자",
            ["MCP", "Anthropic", "OpenAI"],
        )
        self.assertEqual(sorted(got), sorted(["MCP", "Anthropic"]))

    def test_no_anchors_present(self):
        got = audit_mod._anchors_in_text("팔란티어 CEO", ["MCP", "Anthropic"])
        self.assertEqual(got, [])

    def test_empty_text_returns_empty(self):
        self.assertEqual(audit_mod._anchors_in_text("", ["MCP"]), [])
        self.assertEqual(audit_mod._anchors_in_text(None, ["MCP"]), [])

    def test_empty_anchor_skipped(self):
        # Defensive — empty string anchor matches everything if we let
        # it through, which would make the heuristic useless.
        got = audit_mod._anchors_in_text("any text", ["", "MCP"])
        self.assertEqual(got, [])

    def test_whitespace_within_multi_word_anchor(self):
        got = audit_mod._anchors_in_text(
            "Model Context Protocol 설명",
            ["Model Context Protocol"],
        )
        self.assertEqual(got, ["Model Context Protocol"])


class AnchorOutcomeClassifierTests(unittest.TestCase):
    """The four states (already_present / added / dropped / absent)."""

    ANCHORS = ["MCP", "Model Context Protocol", "Anthropic"]

    def test_added_when_in_rewritten_not_original(self):
        out = audit_mod._classify_anchor_outcome(
            original="David Soria Parra가 누구야?",
            rewritten="David Soria Parra (MCP, Anthropic 관련) 누구야?",
            anchors=self.ANCHORS,
        )
        self.assertEqual(sorted(out["anchors_added"]), sorted(["MCP", "Anthropic"]))
        self.assertEqual(out["anchors_dropped"], [])
        self.assertEqual(out["anchors_already_present"], [])
        self.assertEqual(out["anchors_absent"], ["Model Context Protocol"])
        self.assertEqual(out["added_count"], 2)
        self.assertEqual(out["dropped_count"], 0)

    def test_already_present_when_in_both(self):
        out = audit_mod._classify_anchor_outcome(
            original="MCP 설계자 David Soria Parra",
            rewritten="MCP 설계자 (Model Context Protocol) David Soria Parra",
            anchors=self.ANCHORS,
        )
        # "MCP" was already present; rewriter preserved it →
        # already_present, NOT added. Strict guard the bucket
        # summary depends on.
        self.assertIn("MCP", out["anchors_already_present"])
        self.assertNotIn("MCP", out["anchors_added"])
        # "Model Context Protocol" was net-new in the rewrite → added
        self.assertIn("Model Context Protocol", out["anchors_added"])

    def test_dropped_when_in_original_not_rewritten(self):
        out = audit_mod._classify_anchor_outcome(
            original="MCP 설계자 David Soria Parra",
            rewritten="David Soria Parra가 누구야?",   # rewriter stripped MCP
            anchors=self.ANCHORS,
        )
        self.assertEqual(out["anchors_dropped"], ["MCP"])
        self.assertEqual(out["dropped_count"], 1)
        self.assertEqual(out["anchors_added"], [])

    def test_absent_when_in_neither(self):
        out = audit_mod._classify_anchor_outcome(
            original="팔란티어 CEO 누구야?",
            rewritten="Palantir CEO는?",
            anchors=self.ANCHORS,
        )
        self.assertEqual(sorted(out["anchors_absent"]), sorted(self.ANCHORS))
        self.assertEqual(out["anchors_added"], [])
        self.assertEqual(out["anchors_dropped"], [])
        self.assertEqual(out["anchors_already_present"], [])

    def test_identity_rewrite_no_added_no_dropped(self):
        # When rewriter returns the original unchanged (env off / parse
        # fail / too short), anchors are preserved trivially — but the
        # "added" count must stay zero.
        out = audit_mod._classify_anchor_outcome(
            original="MCP 설계자",
            rewritten="MCP 설계자",
            anchors=self.ANCHORS,
        )
        self.assertEqual(out["anchors_added"], [])
        self.assertEqual(out["anchors_dropped"], [])
        self.assertIn("MCP", out["anchors_already_present"])


class FixtureShapeTests(unittest.TestCase):
    """The fixture catalogs four buckets; each row must satisfy the
    audit script's per-row invariants."""

    REQUIRED_KEYS = {"id", "bucket", "text", "expected_anchors", "notes"}
    KNOWN_BUCKETS = {
        "bare_proper_noun",
        "name_with_concept",
        "pure_concept",
        "multi_hop_control",
    }

    def test_every_row_has_required_keys(self):
        for r in audit_mod._FIXTURE:
            self.assertEqual(self.REQUIRED_KEYS - r.keys(), set(),
                             f"row {r.get('id', '?')} missing keys")

    def test_every_row_has_known_bucket(self):
        for r in audit_mod._FIXTURE:
            self.assertIn(r["bucket"], self.KNOWN_BUCKETS,
                          f"row {r['id']} bucket={r['bucket']!r} unknown")

    def test_every_row_has_non_empty_anchor_list(self):
        for r in audit_mod._FIXTURE:
            self.assertTrue(
                r["expected_anchors"],
                f"row {r['id']} has empty expected_anchors — heuristic would always say 'absent'",
            )

    def test_every_row_has_unique_id(self):
        ids = [r["id"] for r in audit_mod._FIXTURE]
        self.assertEqual(len(ids), len(set(ids)),
                         f"duplicate ids: {[i for i in ids if ids.count(i) > 1]}")

    def test_all_four_buckets_represented(self):
        present = {r["bucket"] for r in audit_mod._FIXTURE}
        self.assertEqual(present, self.KNOWN_BUCKETS,
                         "the audit's by-bucket summary needs every bucket populated")

    def test_bare_proper_noun_rows_carry_concept_anchors(self):
        # The diagnosis bucket — these rows by construction must list
        # concept anchors (not other names) since "name in rewrite"
        # would be trivial and not the F9 signal we want.
        for r in audit_mod._FIXTURE:
            if r["bucket"] != "bare_proper_noun":
                continue
            # At least one anchor must not be a substring of the
            # original — otherwise the row can't possibly score "added".
            original_low = r["text"].lower()
            net_new_anchors = [
                a for a in r["expected_anchors"]
                if a.lower() not in original_low
            ]
            self.assertTrue(
                net_new_anchors,
                f"row {r['id']} bare_proper_noun: every anchor already in original — anchor_added impossible",
            )


class BucketSummaryTests(unittest.TestCase):
    """``_bucket_summary`` aggregates per-bucket; mixed states must
    flow into the right counters."""

    def _row(self, *, bucket, added=None, dropped=None, attempted=True,
             changed=True, latency_ms=100):
        added = added or []
        dropped = dropped or []
        return {
            "id":              f"r-{bucket}",
            "bucket":          bucket,
            "anchors_added":   added,
            "anchors_dropped": dropped,
            "attempted":       attempted,
            "changed":         changed,
            "latency_ms":      latency_ms,
        }

    def test_single_bucket_added(self):
        rows = [self._row(bucket="X", added=["MCP"], latency_ms=200)]
        s = audit_mod._bucket_summary(rows)
        self.assertEqual(s["X"]["n"], 1)
        self.assertEqual(s["X"]["anchor_added"], 1)
        self.assertEqual(s["X"]["anchor_dropped"], 0)
        self.assertEqual(s["X"]["anchor_added_rate"], 1.0)
        self.assertEqual(s["X"]["latency_ms_mean"], 200.0)

    def test_mixed_bucket_added_and_dropped(self):
        # One bucket with three rows: 1 added, 1 dropped, 1 no-op
        rows = [
            self._row(bucket="X", added=["MCP"]),
            self._row(bucket="X", dropped=["Anthropic"]),
            self._row(bucket="X"),
        ]
        s = audit_mod._bucket_summary(rows)
        self.assertEqual(s["X"]["n"], 3)
        self.assertEqual(s["X"]["anchor_added"], 1)
        self.assertEqual(s["X"]["anchor_dropped"], 1)
        self.assertAlmostEqual(s["X"]["anchor_added_rate"], 0.333, places=3)
        self.assertAlmostEqual(s["X"]["anchor_dropped_rate"], 0.333, places=3)

    def test_multi_bucket_isolation(self):
        rows = [
            self._row(bucket="X", added=["MCP"], latency_ms=100),
            self._row(bucket="Y", added=[], latency_ms=200),
        ]
        s = audit_mod._bucket_summary(rows)
        self.assertEqual(s["X"]["anchor_added_rate"], 1.0)
        self.assertEqual(s["Y"]["anchor_added_rate"], 0.0)
        self.assertEqual(s["X"]["latency_ms_mean"], 100.0)
        self.assertEqual(s["Y"]["latency_ms_mean"], 200.0)

    def test_skipped_rows_excluded_from_latency(self):
        # A row with attempted=False (env-off or too-short) should NOT
        # contribute to the latency mean — including it would skew the
        # operator's read of "what does the rewriter actually cost when
        # it runs".
        rows = [
            self._row(bucket="X", attempted=True,  latency_ms=300),
            self._row(bucket="X", attempted=False, latency_ms=0),
        ]
        s = audit_mod._bucket_summary(rows)
        self.assertEqual(s["X"]["latency_ms_mean"], 300.0)
        self.assertEqual(s["X"]["attempted"], 1)

    def test_empty_input_returns_empty(self):
        self.assertEqual(audit_mod._bucket_summary([]), {})


if __name__ == "__main__":
    unittest.main()
