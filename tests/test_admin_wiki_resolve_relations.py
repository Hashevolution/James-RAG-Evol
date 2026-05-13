"""POST /admin/wiki/resolve-relations — manual UNRESOLVED grand sweep.

Context: PR #253 wired `WikiGenerator.resolve_pending_relations()` into
every ingest so each new document's relations get filled in against the
post-ingest entity index. This endpoint exposes the same primitive as
an on-demand admin action — used after migrations, bulk imports, or
hand edits to wiki files that introduce new entities that existing
UNRESOLVED relations could now point at.

The functional contract of `resolve_pending_relations()` itself is
covered by `tests/test_wiki_resolve_unresolved.py`. This file pins
only the endpoint wiring: route signature, admin gate, source_type
guard, and the response shape callers can rely on.

Run:
  python -m unittest tests.test_admin_wiki_resolve_relations
"""
from __future__ import annotations

import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class EndpointWiringTests(unittest.TestCase):
    """Route is registered as POST, admin-gated, calls the resolver,
    returns the documented shape."""

    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.src = inspect.getsource(srv)

    def _window(self) -> str:
        idx = self.src.index('@app.post("/admin/wiki/resolve-relations"')
        # The next decorator (admin_graph_snapshot) bounds the handler.
        end = self.src.index("@app.", idx + 1)
        return self.src[idx:end]

    def test_route_is_registered_as_post(self):
        # POST because the endpoint mutates wiki files (writes back
        # resolved target_id to frontmatter). A GET would be misleading
        # and would let intermediaries cache or replay the call.
        self.assertIn('@app.post("/admin/wiki/resolve-relations"', self.src,
            "endpoint must be registered as POST so admins can trigger "
            "the grand sweep explicitly and intermediaries don't cache it")

    def test_handler_is_admin_gated(self):
        win = self._window()
        self.assertIn('_require_feature(api_key, role, "admin.data")', win,
            "handler must gate on admin.data — the same feature flag the "
            "neighbouring /admin/wiki and /admin/graph endpoints use")

    def test_handler_accepts_source_type_query_param(self):
        win = self._window()
        self.assertIn("source_type:", win,
            "handler must accept source_type so operators can sweep the "
            "test wiki in isolation from prod")
        # source_type guarded to {prod, test}.
        self.assertIn('"prod"', win)
        self.assertIn('"test"', win)

    def test_handler_calls_resolve_pending_relations(self):
        win = self._window()
        self.assertIn("resolve_pending_relations()", win,
            "handler must invoke WikiGenerator.resolve_pending_relations() "
            "— that is the whole point of the endpoint")

    def test_handler_returns_resolved_count_and_source_type(self):
        win = self._window()
        # Caller contract: {"resolved": <int>, "source_type": "prod"|"test"}.
        # Anything wider would surface internal WikiGenerator state to the
        # admin UI prematurely.
        self.assertIn('"resolved"', win,
            "response must expose the count of relations resolved so the "
            "admin UI can show 'N relations linked' feedback")
        self.assertIn('"source_type"', win,
            "response must echo source_type so the UI can label whether "
            "prod or test was swept")

    def test_handler_reuses_shared_wiki_generator_when_possible(self):
        # When source_type matches the live engine's bound source, reuse
        # `rag_engine.wiki_generator` so the running engine's
        # entity_id_index reflects the sweep without restart. Only
        # cross-source sweeps construct a fresh generator.
        win = self._window()
        self.assertIn("rag_engine.wiki_generator", win,
            "handler must reuse the shared engine generator when "
            "source_type matches so the running engine sees the sweep "
            "immediately (no restart needed)")
        self.assertIn("from core.wiki_generator import WikiGenerator", win,
            "handler must still construct a scoped WikiGenerator for "
            "cross-source sweeps so test/prod stay isolated")


if __name__ == "__main__":
    unittest.main()
