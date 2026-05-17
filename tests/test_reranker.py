"""Phase 1 PR-1 — cross-encoder reranker unit tests.

ARCHITECTURE.md §5.7.1 Reranker: cross-encoder reordering of top-k.
These tests use a mocked CrossEncoder (no model download) so they
run in CI without network or GPU. The real model is exercised by
the user's STEP 7 spot-check after merge.

Coverage:
  * disabled via JAMES_DISABLE_RERANK=1 → identity (top_k truncation only)
  * model load failure → identity, sticky (no retry)
  * happy path: docs reorder by cross-encoder score (desc), top_k applied
  * annotation: each returned doc gains rerank_score + vector_score
  * empty input → empty output
  * predict failure mid-call → fallback to vector-score order
  * env override JAMES_RERANKER_MODEL respected at init time
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


def _docs(n=4):
    """Build n docs with descending vector scores (0.9, 0.7, 0.5, 0.3)."""
    return [
        {"text": f"doc {i} text", "source": f"d{i}.md", "score": 0.9 - 0.2 * i}
        for i in range(n)
    ]


class DisabledTests(unittest.TestCase):

    def setUp(self):
        self._saved = os.environ.get("JAMES_DISABLE_RERANK")
        os.environ["JAMES_DISABLE_RERANK"] = "1"

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("JAMES_DISABLE_RERANK", None)
        else:
            os.environ["JAMES_DISABLE_RERANK"] = self._saved

    def test_disabled_returns_input_truncated(self):
        from core.retrieval.rerank import Reranker
        r = Reranker()
        docs = _docs(8)
        out = r.rerank("query", docs, top_k=5)
        self.assertEqual(len(out), 5)
        # original order preserved (vector-score desc)
        self.assertEqual([d["source"] for d in out],
                         ["d0.md", "d1.md", "d2.md", "d3.md", "d4.md"])
        # no rerank_score annotation when disabled
        for d in out:
            self.assertNotIn("rerank_score", d)


class LoadFailureTests(unittest.TestCase):

    def test_load_failure_returns_input_unchanged(self):
        from core.retrieval.rerank import Reranker
        r = Reranker()
        # Force the lazy load to fail by making CrossEncoder unimportable.
        with patch("sentence_transformers.CrossEncoder",
                   side_effect=RuntimeError("oom")):
            out = r.rerank("q", _docs(4), top_k=5)
        self.assertEqual(len(out), 4)
        self.assertTrue(r._load_failed)
        # sticky: second call must not retry
        with patch("sentence_transformers.CrossEncoder") as ce:
            r.rerank("q", _docs(2), top_k=5)
            ce.assert_not_called()


class HappyPathTests(unittest.TestCase):
    """Inject a fake model directly into the instance to skip the real
    download. The fake returns scores in reverse-input order so we can
    verify the sort runs.
    """

    def _backend_with_fake(self, scores):
        from core.retrieval.rerank import Reranker
        r = Reranker()
        fake = MagicMock()
        fake.predict.return_value = scores
        r._model = fake
        return r, fake

    def test_reorders_by_cross_encoder_score(self):
        # Inputs in vector-score order (d0 > d1 > d2 > d3).
        # Cross-encoder says the reverse: d3 > d2 > d1 > d0.
        r, fake = self._backend_with_fake([0.1, 0.4, 0.7, 0.95])
        out = r.rerank("q", _docs(4), top_k=5)
        self.assertEqual([d["source"] for d in out],
                         ["d3.md", "d2.md", "d1.md", "d0.md"])

    def test_top_k_truncation_applied(self):
        r, fake = self._backend_with_fake([0.1, 0.4, 0.7, 0.95])
        out = r.rerank("q", _docs(4), top_k=2)
        self.assertEqual(len(out), 2)
        self.assertEqual([d["source"] for d in out], ["d3.md", "d2.md"])

    def test_annotations_added(self):
        r, fake = self._backend_with_fake([0.5, 0.9, 0.3])
        out = r.rerank("q", _docs(3), top_k=5)
        for d in out:
            self.assertIn("rerank_score", d)
            self.assertIn("vector_score", d)
            # vector_score captures the v0.3.0 ordering signal so
            # downstream code can still read the original ranking
            self.assertIsInstance(d["vector_score"], float)

    def test_empty_input_empty_output(self):
        r, fake = self._backend_with_fake([])
        self.assertEqual(r.rerank("q", [], top_k=5), [])
        fake.predict.assert_not_called()

    def test_predict_failure_falls_back_to_vector_order(self):
        from core.retrieval.rerank import Reranker
        r = Reranker()
        fake = MagicMock()
        fake.predict.side_effect = RuntimeError("gpu memory full")
        r._model = fake
        out = r.rerank("q", _docs(4), top_k=5)
        # Fall back: original order kept, no annotation
        self.assertEqual([d["source"] for d in out],
                         ["d0.md", "d1.md", "d2.md", "d3.md"])
        for d in out:
            self.assertNotIn("rerank_score", d)


class ScorePairsTests(unittest.TestCase):

    def test_score_pairs_returns_one_score_per_doc(self):
        from core.retrieval.rerank import Reranker
        r = Reranker()
        fake = MagicMock()
        fake.predict.return_value = [0.5, 0.6, 0.7]
        r._model = fake
        scores = r.score_pairs("q", _docs(3))
        self.assertEqual(len(scores), 3)
        self.assertEqual(scores, [0.5, 0.6, 0.7])

    def test_score_pairs_empty_docs(self):
        from core.retrieval.rerank import Reranker
        r = Reranker()
        # model not even loaded — empty docs short-circuits
        self.assertEqual(r.score_pairs("q", []), [])

    def test_score_pairs_fallback_returns_vector_scores(self):
        from core.retrieval.rerank import Reranker
        r = Reranker()
        with patch("sentence_transformers.CrossEncoder",
                   side_effect=RuntimeError("no")):
            scores = r.score_pairs("q", _docs(3))
        self.assertEqual(scores, [0.9, 0.7, 0.5])


class EnvOverrideTests(unittest.TestCase):

    def test_model_id_default(self):
        from core.retrieval.rerank import Reranker, DEFAULT_MODEL
        os.environ.pop("JAMES_RERANKER_MODEL", None)
        r = Reranker()
        self.assertEqual(r._model_id, DEFAULT_MODEL)

    def test_model_id_env_override(self):
        from core.retrieval.rerank import Reranker
        with patch.dict(os.environ, {"JAMES_RERANKER_MODEL": "BAAI/bge-reranker-base"}):
            r = Reranker()
        self.assertEqual(r._model_id, "BAAI/bge-reranker-base")

    def test_constructor_arg_wins_over_env(self):
        from core.retrieval.rerank import Reranker
        with patch.dict(os.environ, {"JAMES_RERANKER_MODEL": "env-model"}):
            r = Reranker(model_id="explicit-model")
        self.assertEqual(r._model_id, "explicit-model")


class SingletonTests(unittest.TestCase):

    def test_get_reranker_returns_same_instance(self):
        from core.retrieval.rerank import get_reranker, _clear_singleton_for_tests
        _clear_singleton_for_tests()
        a = get_reranker()
        b = get_reranker()
        self.assertIs(a, b)


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
