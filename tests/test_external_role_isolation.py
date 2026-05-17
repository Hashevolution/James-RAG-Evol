"""PR-O5 (cycle 12) — external role isolation via query.internal_rag.

Handover §3 item ④: 비로그인/external 사용자는 일상 챗만 허용하고 내부
자료 (vector + graph) 는 차단한다. PR-O5 ships this via a new
``query.internal_rag`` feature in the catalog plus an engine-level
gate that re-routes denied requests to ``handle_chat`` instead of the
full retrieval pipeline.

Tests:
  * Feature catalog entry exists with the correct default_allowed
  * Default decision: admin/manager/employee allowed, external denied
  * Admin override (set_override → external True) makes the engine
    path through retrieval again
  * Engine source contains the gate
  * Engine source routes denied requests to handle_chat (not the
    retrieval pipeline)
  * Runtime: with default state, ReasoningEngine.query(user_role=
    "external", mode_override="retrieval") never reaches
    run_retrieval_pipeline; instead handle_chat fires
  * Runtime: with default state + user_role="employee", the engine
    DOES enter run_retrieval_pipeline (no regression for internal staff)
"""
from __future__ import annotations

import inspect
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


class FeatureCatalogTests(unittest.TestCase):

    def test_query_internal_rag_exists_in_catalog(self):
        from core.feature_registry import FEATURES
        self.assertIn("query.internal_rag", FEATURES,
            "PR-O5 must add query.internal_rag to the feature catalog")

    def test_query_internal_rag_default_excludes_external(self):
        from core.feature_registry import FEATURES
        feat = FEATURES["query.internal_rag"]
        self.assertIn("admin",    feat.default_allowed)
        self.assertIn("manager",  feat.default_allowed)
        self.assertIn("employee", feat.default_allowed)
        self.assertNotIn("external", feat.default_allowed,
            "external must be DENIED internal_rag by default — admin "
            "matrix override is the only way to grant it")


class PolicyEngineDecisionTests(unittest.TestCase):

    def test_default_allows_employee(self):
        from core.policy_engine import default_engine
        dec = default_engine.can_use_feature("employee", "query.internal_rag")
        self.assertTrue(dec.allowed)

    def test_default_denies_external(self):
        from core.policy_engine import default_engine
        dec = default_engine.can_use_feature("external", "query.internal_rag")
        self.assertFalse(dec.allowed)


class EngineGateSourceTests(unittest.TestCase):
    """Structural shape — the engine source contains the gate and
    re-routes to handle_chat. Catches a future refactor that drops
    the check.
    """

    @classmethod
    def setUpClass(cls):
        from core.reasoning import engine as _engine
        cls.src = inspect.getsource(_engine)

    def test_gate_calls_can_use_feature_with_internal_rag(self):
        # The gate must consult the catalog by id, not duplicate the
        # role check inline.
        self.assertIn(
            'can_use_feature(user_role, "query.internal_rag")',
            self.src,
            "engine must consult the policy engine for query.internal_rag "
            "rather than hard-coding role==external",
        )

    def test_gate_routes_denied_to_handle_chat(self):
        # The denied path must invoke handle_chat (NOT
        # run_retrieval_pipeline). Look at the block following the
        # can_use_feature call.
        gate_idx = self.src.index('can_use_feature(user_role, "query.internal_rag")')
        block = self.src[gate_idx:gate_idx + 800]
        self.assertIn("handle_chat(", block,
            "denied path must re-route to handle_chat instead of "
            "run_retrieval_pipeline so the answer is generated without "
            "internal RAG context")

    def test_gate_precedes_retrieval_dispatch(self):
        gate_idx = self.src.index('can_use_feature(user_role, "query.internal_rag")')
        retrieval_idx = self.src.index("from core.reasoning.pipeline import run_retrieval_pipeline")
        self.assertLess(gate_idx, retrieval_idx,
            "PR-O5 gate must run BEFORE the retrieval dispatch")


class RuntimeRoutingTests(unittest.TestCase):
    """Mock the heavy collaborators and verify that on default-state
    external requests, run_retrieval_pipeline is not called; handle_chat
    IS called instead. Employee requests still flow through the
    pipeline (no regression).
    """

    def _make_engine(self):
        """Build a ReasoningEngine with all heavyweight collaborators
        stubbed out. Only the dispatch logic exercises real code.

        Patches target the symbols inside the ``core.reasoning.engine``
        namespace (where ``from X import Y`` resolved them) — patching
        the original modules' attributes after engine.py imported them
        would not change the bound names.
        """
        from core.reasoning.engine import ReasoningEngine

        with patch("core.reasoning.engine.GraphEngine", return_value=MagicMock()), \
             patch("core.reasoning.engine.RetrievalEngine", return_value=MagicMock()), \
             patch("llm.router.RouterWrapper", return_value=MagicMock()), \
             patch("core.reasoning.engine.SecurityLayer", return_value=MagicMock()):
            eng = ReasoningEngine()
        # The security pre/post check must let everything through so
        # the dispatch path runs.
        eng.security.pre_check.return_value = {"allowed": True, "query": "test query"}
        eng.security.post_check.return_value = {"allowed": True, "context": ""}
        eng.security.abac_consistency_check.return_value = {
            "consistent": True, "violations": [],
        }
        return eng

    def _run_query_capturing_handle_chat(self, user_role):
        from core.reasoning import pipeline as _pipeline

        # Stub both handle_chat (from inside engine.modes import) and
        # run_retrieval_pipeline so we can see which one fired.
        # The engine.py imports `from core.reasoning.modes import handle_chat`
        # at module load, so patch on the engine module namespace.
        from core.reasoning import engine as _engine

        called = {"handle_chat": False, "run_retrieval_pipeline": False}

        def _fake_chat(*a, **kw):
            called["handle_chat"] = True
            return {"answer": "chat-stub", "mode": "chat"}

        def _fake_pipeline(*a, **kw):
            called["run_retrieval_pipeline"] = True
            return {"answer": "rag-stub", "mode": "retrieval"}

        eng = self._make_engine()
        with patch.object(_engine, "handle_chat", _fake_chat), \
             patch.object(_pipeline, "run_retrieval_pipeline", _fake_pipeline), \
             patch("core.memory.MemoryStore") as _store_cls, \
             patch("core.query_router.QueryRouter") as _qr_cls, \
             patch("core.character_profile.CharacterProfile") as _cp_cls:
            # MemoryStore stub — return strings the engine expects
            store = MagicMock()
            store.get_system_prompt.return_value = ""
            store.get_context.return_value = ""
            store.get_history_context.return_value = ""
            store.get_long_term_context.return_value = ""
            _store_cls.return_value = store
            # Force the router to pick "retrieval" so the gate is what
            # matters (not the mode dispatch).
            _qr_cls.return_value.route.return_value = "retrieval"
            _cp_cls.return_value.get_prompt_modifiers.return_value = ""

            eng.query("어떤 자료 있어?", user_role=user_role,
                      source_type="prod", session_id="t1")

        return called

    def test_external_routes_to_handle_chat_not_pipeline(self):
        called = self._run_query_capturing_handle_chat("external")
        self.assertTrue(called["handle_chat"],
            "external must fall back to handle_chat when "
            "query.internal_rag is denied")
        self.assertFalse(called["run_retrieval_pipeline"],
            "external must NOT reach run_retrieval_pipeline by default")

    def test_employee_still_uses_pipeline(self):
        called = self._run_query_capturing_handle_chat("employee")
        self.assertFalse(called["handle_chat"],
            "employee retrieval queries must reach the pipeline "
            "(no regression from PR-O5)")
        self.assertTrue(called["run_retrieval_pipeline"],
            "employee retrieval queries must reach run_retrieval_pipeline")

    def test_admin_override_lets_external_through(self):
        """When an admin grants external the query.internal_rag override,
        the engine path through retrieval restores.
        """
        from core.feature_registry import set_override, clear_override
        try:
            self.assertTrue(
                set_override("query.internal_rag", "external", True,
                             updated_by="test")
            )
            called = self._run_query_capturing_handle_chat("external")
            self.assertTrue(called["run_retrieval_pipeline"],
                "admin override must let external through to the "
                "retrieval pipeline")
            self.assertFalse(called["handle_chat"])
        finally:
            clear_override("query.internal_rag", "external")


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
