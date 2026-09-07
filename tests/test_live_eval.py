"""Real-use evaluation harness (scripts/live_eval.py) — v0.6.1.

Covers the capture→report→promote loop against synthetic fixtures:
  * audit_log rows in a temp sqlite DB (same schema as
    server_llmwiki._init_audit_db)
  * feedback_shadow.jsonl entries (same fields FeedbackEngine.accumulate
    writes)
  * promotion into the bench.py-compatible suite JSON, including the
    merge-safety guarantees (stable ids, no overwrite of operator
    enrichment, idempotent re-promotion).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.live_eval import (  # noqa: E402
    build_report,
    collect_candidates,
    format_report_md,
    load_audit_rows,
    load_feedback_entries,
    load_suite,
    promote_queries,
)


def _make_audit_db(path: Path, rows):
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE audit_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT    NOT NULL,
            user_role    TEXT    NOT NULL,
            endpoint     TEXT    NOT NULL,
            query        TEXT,
            answer       TEXT,
            graph_paths  TEXT,
            blocked      INTEGER   DEFAULT 0,
            security_event TEXT,
            elapsed_sec  REAL,
            ip_address   TEXT
        )
    """)
    conn.executemany(
        """INSERT INTO audit_log
           (timestamp, user_role, endpoint, query, answer, graph_paths,
            blocked, security_event, elapsed_sec, ip_address)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    conn.close()


def _now(offset_min: int = 0) -> str:
    return (datetime.now() + timedelta(minutes=offset_min)).isoformat()


class LoadersTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_db_and_shadow_return_empty(self):
        since = datetime.now() - timedelta(days=7)
        self.assertEqual(load_audit_rows(self.dir / "nope.db", since), [])
        self.assertEqual(
            load_feedback_entries(self.dir / "nope.jsonl", since), [])

    def test_audit_rows_filtered_by_endpoint_and_time(self):
        db = self.dir / "a.db"
        old = (datetime.now() - timedelta(days=30)).isoformat()
        _make_audit_db(db, [
            (_now(), "admin", "/query/", "질문1", "답1", "[]", 0, "", 3.2, ""),
            (_now(), "admin", "/login/", "", "", "[]", 0, "", 0.1, ""),
            (old, "admin", "/query/", "옛질문", "답", "[]", 0, "", 1.0, ""),
        ])
        since = datetime.now() - timedelta(days=7)
        rows = load_audit_rows(db, since)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query"], "질문1")

    def test_feedback_tolerates_torn_line(self):
        p = self.dir / "s.jsonl"
        good = {"direction_id": "d1", "signal": "explicit_negative",
                "delta": -1.0, "score": -1.0, "query": "질문1",
                "time": _now()}
        p.write_text(json.dumps(good, ensure_ascii=False) +
                     "\n{torn-line", encoding="utf-8")
        since = datetime.now() - timedelta(days=1)
        entries = load_feedback_entries(p, since)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["signal"], "explicit_negative")


class ReportTests(unittest.TestCase):
    def _rows(self):
        return [
            {"timestamp": _now(), "endpoint": "/query/", "query": "q-ok",
             "answer": "정상 답변입니다", "blocked": 0, "elapsed_sec": 2.0},
            {"timestamp": _now(), "endpoint": "/query/", "query": "q-abst",
             "answer": "제공된 자료에는 없습니다", "blocked": 0,
             "elapsed_sec": 4.0},
            {"timestamp": _now(), "endpoint": "/query/", "query": "q-err",
             "answer": "[Gemma 오류] 응답 시간 초과 (120s)", "blocked": 0,
             "elapsed_sec": 120.0},
            {"timestamp": _now(), "endpoint": "/query/", "query": "q-block",
             "answer": "차단", "blocked": 1, "elapsed_sec": 0.0},
        ]

    def _feedback(self):
        return [
            {"signal": "explicit_negative", "query": "q-err", "time": _now()},
            {"signal": "explicit_positive", "query": "q-ok", "time": _now()},
        ]

    def test_counts_and_rates(self):
        rep = build_report(self._rows(), self._feedback(), window_days=7)
        self.assertEqual(rep["total_queries"], 4)
        self.assertEqual(rep["blocked"], 1)
        self.assertEqual(rep["answered"], 1)
        self.assertEqual(rep["abstention"], 1)
        self.assertEqual(rep["llm_errors"], 1)
        self.assertEqual(rep["feedback"]["negative"], 1)
        self.assertEqual(rep["feedback"]["positive"], 1)
        self.assertEqual(
            rep["negative_feedback_queries"][0]["query"], "q-err")

    def test_latency_percentiles_exclude_blocked(self):
        rep = build_report(self._rows(), [], window_days=7)
        self.assertEqual(rep["latency"]["max"], 120.0)
        self.assertGreaterEqual(rep["latency"]["p50"], 2.0)

    def test_markdown_renders_key_sections(self):
        rep = build_report(self._rows(), self._feedback(), window_days=7)
        md = format_report_md(rep)
        self.assertIn("실사용 평가 리포트", md)
        self.assertIn("부정 피드백 질의", md)
        self.assertIn("q-err", md)
        self.assertIn("bench.py --suite=live_queries", md)

    def test_empty_window_does_not_crash(self):
        rep = build_report([], [], window_days=7)
        self.assertEqual(rep["total_queries"], 0)
        self.assertIn("실사용 평가 리포트", format_report_md(rep))


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.suite_path = Path(self.tmp.name) / "live_queries_queries.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _rows(self):
        return [
            {"timestamp": _now(), "endpoint": "/query/",
             "query": "실패한 질문입니다", "answer": "…", "blocked": 0,
             "elapsed_sec": 5.0},
            {"timestamp": _now(), "endpoint": "/query/",
             "query": "잘 된 질문", "answer": "…", "blocked": 0,
             "elapsed_sec": 1.0},
        ]

    def _neg_feedback(self):
        return [{"signal": "explicit_negative",
                 "query": "실패한 질문입니다", "time": _now()}]

    def test_candidates_default_negative_only(self):
        cands = collect_candidates(self._rows(), self._neg_feedback())
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["reason"], "negative_feedback")
        self.assertEqual(cands[0]["text"], "실패한 질문입니다")

    def test_candidates_all_samples_window(self):
        cands = collect_candidates(self._rows(), self._neg_feedback(),
                                   include_all=True, limit=10)
        texts = {c["text"] for c in cands}
        self.assertIn("잘 된 질문", texts)
        self.assertEqual(len(cands), 2)  # dedup vs feedback candidate

    def test_promote_creates_bench_compatible_suite(self):
        suite = load_suite(self.suite_path)
        suite = promote_queries(
            suite, collect_candidates(self._rows(), self._neg_feedback()))
        # bench.py contract: endpoint block + queries[].id / .text
        self.assertEqual(suite["endpoint"]["url"], "/query/")
        self.assertEqual(len(suite["queries"]), 1)
        q = suite["queries"][0]
        self.assertEqual(q["id"], 1)
        self.assertEqual(q["text"], "실패한 질문입니다")
        self.assertEqual(q["promoted"]["reason"], "negative_feedback")

    def test_promotion_idempotent_and_preserves_enrichment(self):
        suite = load_suite(self.suite_path)
        cands = collect_candidates(self._rows(), self._neg_feedback())
        suite = promote_queries(suite, cands)
        # Operator later enriches the entry:
        suite["queries"][0]["gold_signals"] = [{"term": "정답",
                                                "aliases": []}]
        # Re-promoting the same query must not duplicate or overwrite.
        suite = promote_queries(suite, cands)
        suite.pop("_last_promotion_added", None)
        self.assertEqual(len(suite["queries"]), 1)
        self.assertEqual(suite["queries"][0]["gold_signals"][0]["term"],
                         "정답")

    def test_ids_stay_stable_across_promotions(self):
        suite = load_suite(self.suite_path)
        suite = promote_queries(
            suite, [{"text": "첫 질문", "reason": "operator",
                     "first_seen": _now()}])
        suite = promote_queries(
            suite, [{"text": "둘째 질문", "reason": "operator",
                     "first_seen": _now()}])
        ids = [q["id"] for q in suite["queries"]]
        self.assertEqual(ids, [1, 2])


if __name__ == "__main__":
    unittest.main()
