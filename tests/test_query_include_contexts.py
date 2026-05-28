"""`/query/` admin-only `include_contexts` field — #65 phase 3.

The endpoint admin-gates exposure of `retrieved_contexts` so the chunk
texts that fed the LLM never leak to non-admin callers. RAGAS `--live`
mode is the intended consumer.

These tests are source-level + Pydantic-level — they don't spin up a
server. Live integration is verified by the operator running
`python eval/ragas/run_ragas.py --live --check` against the JAMES
server (see PR #66 verification list); the contract tests here ensure a
future refactor cannot silently break the admin gate.

Run:
  python -m unittest tests.test_query_include_contexts
  python tests/test_query_include_contexts.py
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class QueryRequestSchemaTests(unittest.TestCase):
    """Pydantic model accepts the new field with the documented default."""

    def test_default_include_contexts_is_false(self):
        from server_llmwiki import QueryRequest
        m = QueryRequest(api_key="x", question="hello")
        self.assertEqual(m.include_contexts, False)

    def test_explicit_include_contexts_true(self):
        from server_llmwiki import QueryRequest
        m = QueryRequest(api_key="x", question="hello", include_contexts=True)
        self.assertEqual(m.include_contexts, True)

    def test_response_schema_carries_optional_retrieved_contexts(self):
        from server_llmwiki import QueryResponse
        # Default omits the field (None); explicit list passes through.
        m1 = QueryResponse(question="q", answer="a", sources=[])
        self.assertIsNone(m1.retrieved_contexts)
        m2 = QueryResponse(question="q", answer="a", sources=[],
                           retrieved_contexts=["chunk1", "chunk2"])
        self.assertEqual(m2.retrieved_contexts, ["chunk1", "chunk2"])


class AdminGateContractTests(unittest.TestCase):
    """Source-level contract: the admin gate must remain in place.

    A future refactor could plausibly move the gate into a helper or
    drop the role check entirely. These checks force a reviewer to
    consciously decide before that happens — same pattern as
    `tests/test_policy_quarantine.py::PipelineIntegrationTests`.
    """

    def test_endpoint_admin_gates_retrieved_contexts(self):
        from tests._server_split_helpers import combined_server_source
        src = combined_server_source()
        # The exposure must be gated on BOTH the request flag AND the role.
        self.assertIn(
            'data.include_contexts and role == "admin"',
            src,
            "/query/ must gate retrieved_contexts on (include_contexts=True "
            "AND role==admin) — see #65 phase 3 admin-gate contract.",
        )
        # And the field name must match what RAGAS --live reads.
        self.assertIn(
            'response["retrieved_contexts"]',
            src,
            "endpoint response key must be `retrieved_contexts` — RAGAS "
            "--live looks for this exact key.",
        )

    def test_pipeline_result_carries_retrieved_contexts(self):
        # The pipeline result is the source of truth — even if the endpoint
        # is bypassed (e.g. import-level callers), the chunk texts must be
        # available for downstream consumers.
        from tests._pipeline_src import pipeline_source
        src = pipeline_source()
        self.assertIn(
            '"retrieved_contexts":',
            src,
            "pipeline.py result dict must include `retrieved_contexts` — "
            "see #65 phase 3 RAGAS hook.",
        )


class RunRagasLiveModeTests(unittest.TestCase):
    """Smoke-level: --live flag is wired and the loader accepts a sparse
    fixture (only `user_input` + `reference`).

    Doesn't actually drive a live server (the verification step does that).
    """

    def test_loader_accepts_sparse_fixture_in_live_mode(self):
        import json, tempfile
        from pathlib import Path
        from eval.ragas.run_ragas import _load_fixture

        sparse = {
            "version": "test",
            "rows": [
                {"user_input": "Q1?", "reference": "A1."},
                {"user_input": "Q2?", "reference": "A2."},
            ],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8",
        ) as f:
            json.dump(sparse, f)
            path = Path(f.name)
        try:
            rows_offline_should_fail = None
            try:
                _load_fixture(path, live=False)
            except RuntimeError as e:
                rows_offline_should_fail = str(e)
            self.assertIsNotNone(
                rows_offline_should_fail,
                "offline mode must reject a sparse fixture (no retrieved_contexts)",
            )

            rows = _load_fixture(path, live=True)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["user_input"], "Q1?")
            self.assertEqual(rows[1]["reference"],  "A2.")
        finally:
            path.unlink()

    def test_drive_live_dispatches_post_with_admin_payload(self):
        # Stub `requests.post` to capture the payload the runner sends to
        # /query/. Asserts include_contexts=True and api_key threaded.
        from eval.ragas import run_ragas
        from unittest.mock import patch

        captured = {}

        class _StubResp:
            status_code = 200
            def json(self_inner):
                return {
                    "answer":              "live answer",
                    "retrieved_contexts": ["chunk1", "chunk2"],
                    "blocked":             False,
                }

        def _stub_post(url, json=None, timeout=None):
            captured["url"]     = url
            captured["payload"] = json
            captured["timeout"] = timeout
            return _StubResp()

        with patch.object(run_ragas, "_load_api_key", return_value="dummy-key"), \
             patch("requests.post", side_effect=_stub_post):
            out = run_ragas._drive_live(
                rows=[{"user_input": "Q?", "reference": "A."}],
                base_url="http://127.0.0.1:8000",
                timeout=120,
            )

        self.assertEqual(captured["url"], "http://127.0.0.1:8000/query/")
        self.assertEqual(captured["payload"]["question"], "Q?")
        self.assertEqual(captured["payload"]["api_key"], "dummy-key")
        self.assertTrue(captured["payload"]["include_contexts"],
                        "live driver must send include_contexts=True")
        self.assertTrue(captured["payload"]["session_id"].startswith("ragas_live_"),
                        "session_id must be unique per row to isolate memory")

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["response"], "live answer")
        self.assertEqual(out[0]["retrieved_contexts"], ["chunk1", "chunk2"])
        self.assertEqual(out[0]["reference"], "A.")


if __name__ == "__main__":
    unittest.main()
