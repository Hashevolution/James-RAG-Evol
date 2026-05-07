"""meta mode — internal-data inventory routing + handler.

Coverage:
  - intent_classifier.classify_fast routes inventory-style queries
    ("어떤 자료가 있어?", "wiki 목록 보여줘", "list all entities") to
    `meta` and does NOT route specific-topic retrieval queries
    ("BlackRock 정보 알려줘") to `meta`.
  - intent_classifier.ROLE_ALLOWED includes `meta` for external,
    employee, manager, admin (no role gate — entity *names* are not
    ABAC-protected; the read content still flows through retrieval +
    role filter).
  - handle_meta returns a non-empty answer with mode='meta' and
    graph_paths=[] (short-circuits before retrieval/graph).
  - Source-level: engine.query() dispatches mode=='meta' to
    handle_meta. STEP 7 baseline q13 invariants present.

Run:
  python -m unittest tests.test_meta_mode
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FastPatternRoutingTests(unittest.TestCase):
    """The fast-path classifier must catch inventory queries before
    they fall through to retrieval. v2 (2026-05-08 follow-up): user
    reported the chat page didn't trigger meta mode — root cause was
    the v1 patterns covered only formal phrasings ('wiki 목록 보여줘')
    and missed the casual ones a real user actually types
    ('데이터 뭐 있는지 보여줘', 'what data do you have'). v2 adds 7
    more patterns covering casual KO + flexible EN forms."""

    def test_korean_formal_inventory_phrasings_route_to_meta(self):
        from core.intent_classifier import IntentClassifier
        cls = IntentClassifier()
        for q in (
            "wiki 목록 보여줘",
            "wiki 목록",
            "내부 자료 목록 보여줘",
            "내부 자료 목록",
            "어떤 자료가 있어?",
            "무슨 문서가 있는지 알려줘",
            "보유 자료 리스트 보여줘",
        ):
            mode = cls.classify_fast(q)
            self.assertEqual(mode, "meta",
                             f"formal inventory should route to meta: {q!r}, got {mode!r}")

    def test_korean_casual_inventory_phrasings_route_to_meta(self):
        # v2 — these are the phrasings the user actually typed in
        # chat that fell through to retrieval and produced hallucinated
        # answers. Must now route to meta via fast pattern (no LLM
        # latency, no misclassification risk).
        from core.intent_classifier import IntentClassifier
        cls = IntentClassifier()
        for q in (
            "내부에 무슨 자료 있는지 알려줘",
            "데이터 뭐 있는지 보여줘",
            "문서 뭐가 있어?",
            "저장된 데이터 보여줘",
            "갖고 있는 자료 알려줘",
            "아는거 뭐 있어?",
            "내부에 어떤 데이터 있어",
        ):
            mode = cls.classify_fast(q)
            self.assertEqual(mode, "meta",
                             f"casual inventory should route to meta: {q!r}, got {mode!r}")

    def test_english_inventory_phrasings_route_to_meta(self):
        from core.intent_classifier import IntentClassifier
        cls = IntentClassifier()
        for q in (
            "list all entities",
            "show all wiki",
            "show me your knowledge base",
            "what do you have?",
            "what do you know about",
            "what data do you have",          # v2 — earlier missed this
            "your knowledge base",            # v2 — noun-phrase pattern
        ):
            mode = cls.classify_fast(q)
            self.assertEqual(mode, "meta",
                             f"english inventory should route to meta: {q!r}, got {mode!r}")

    def test_specific_topic_does_NOT_route_to_meta(self):
        # "BlackRock 정보 알려줘" — specific topic retrieval. Must NOT
        # be hijacked by the meta pattern (the user wants content, not
        # an inventory). The v2 broader patterns increase the risk of
        # hijacking — this test guards that risk.
        from core.intent_classifier import IntentClassifier
        cls = IntentClassifier()
        for q in (
            "BlackRock 정보 알려줘",
            "비트코인에 대해 설명해줘",
            "RAG가 무엇인가?",
            "Anthropic은 어떤 회사인가?",
            "BTC ETF 출시한 회사 목록",   # specific-topic + 목록
            "OpenAI의 최신 모델 전략",
        ):
            mode = cls.classify_fast(q)
            self.assertNotEqual(mode, "meta",
                                f"specific-topic query must NOT route to meta: {q!r}")

    def test_too_short_or_ambiguous_falls_through_to_llm(self):
        # "뭐 있어?" alone is ambiguous (could be office / dinner /
        # anything). It should NOT be hijacked into meta — let the LLM
        # classifier decide based on full context. "안녕" is a clear chat.
        from core.intent_classifier import IntentClassifier
        cls = IntentClassifier()
        # "안녕" has its own chat fast-pattern (not meta).
        self.assertEqual(cls.classify_fast("안녕"), "chat")
        # "뭐 있어?" too vague — must NOT match meta. (May or may not
        # match other patterns; we only assert it's not meta.)
        self.assertNotEqual(cls.classify_fast("뭐 있어?"), "meta")


class RoleAllowedTests(unittest.TestCase):
    def test_meta_allowed_for_all_roles(self):
        from core.intent_classifier import ROLE_ALLOWED
        for role in ("admin", "manager", "employee", "external"):
            self.assertIn("meta", ROLE_ALLOWED[role],
                          f"meta must be allowed for {role!r} — entity names are not ABAC-protected")


class HandleMetaTests(unittest.TestCase):
    """Handler-level: handle_meta short-circuits the RAG pipeline.

    We don't spin up the real engine — we pass a stub with the minimal
    surface (._log, ._elapsed) and assert the return shape. The actual
    list_entities() call hits the real wiki/ dir; if empty we still
    expect a graceful 'no data' message rather than an exception.
    """

    class _StubEngine:
        def _log(self, *a, **kw): pass
        def _elapsed(self, t, label): return 0.0

    def test_returns_meta_mode_and_no_graph_paths(self):
        from core.reasoning.modes import handle_meta
        import time as _t
        result = handle_meta(
            self._StubEngine(),
            safe_query="wiki 목록 보여줘",
            system_prompt="",
            user_role="external",
            t_start=_t.time(),
        )
        self.assertEqual(result["mode"], "meta")
        self.assertEqual(result["graph_paths"], [])
        self.assertEqual(result["graph_used"], 0)
        self.assertFalse(result["blocked"])
        self.assertIn("answer", result)
        self.assertIsInstance(result["answer"], str)
        # Either a populated bucket summary OR the empty-corpus fallback.
        # In both cases the answer must be non-empty.
        self.assertTrue(result["answer"].strip(),
                        "handle_meta must always return a non-empty answer")


class EngineDispatchContractTests(unittest.TestCase):
    """Source-level: engine.query() must dispatch mode=='meta' to
    handle_meta. A future refactor that drops the meta branch will
    fail here and require a conscious choice."""

    def test_engine_imports_handle_meta(self):
        import core.reasoning.engine as eng
        import inspect
        src = inspect.getsource(eng)
        self.assertIn("handle_meta", src,
                      "engine.py must import handle_meta")
        self.assertIn('if mode == "meta":', src,
                      "engine.query() must branch on mode=='meta'")
        self.assertIn("return handle_meta(self,", src,
                      "engine.query() must dispatch meta to handle_meta()")


class Step7BaselineQ13Tests(unittest.TestCase):
    """The STEP 7 suite was extended to 13 queries. q13 = inventory.
    A regression here means the baseline file was reverted or the
    suite count drifted."""

    def test_step7_queries_has_q13_meta(self):
        path = Path(__file__).resolve().parent.parent / "eval" / "regression" / "step7_queries.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(data["queries"]), 13,
                         "step7_queries.json must now have 13 queries")
        q13 = next(q for q in data["queries"] if q["id"] == 13)
        self.assertEqual(q13["category"], "meta")
        self.assertTrue(q13["text"].strip(), "q13 text must not be blank")

    def test_step7_baseline_locks_q13_invariants(self):
        path = Path(__file__).resolve().parent.parent / "eval" / "regression" / "step7_baseline.json"
        bl = json.loads(path.read_text(encoding="utf-8"))
        q13 = next(q for q in bl["queries"] if q["id"] == 13)
        self.assertEqual(q13["expected_mode"], "meta",
                         "q13 must lock expected_mode='meta'")
        self.assertEqual(q13["graph_paths_max"], 0,
                         "q13 must lock graph_paths=0 (handle_meta short-circuits)")
        self.assertFalse(q13["blocked"],
                         "q13 must NOT be blocked (it's a legitimate inventory query)")
        self.assertGreaterEqual(q13.get("answer_len_min", 0), 40,
                                "q13 answer_len gate must be >= 40 (formatted summary, not hallucination)")


if __name__ == "__main__":
    unittest.main()
