"""v0.4 Sprint 4 BL-9 prep — embedding model abstraction contract.

Pins the **default-off byte-identical invariant** + the swap path
for the upcoming MiniLM → bge-m3 / multilingual-e5-large swap.
The actual swap + measurement lands in a follow-up PR; this prep
shipping the abstraction means the swap PR can flip a single env
var without touching call sites.

Three guarantees pinned here:

  1. With ``JAMES_EMBEDDING_MODEL`` unset, every file path the
     vector store touches matches pre-#BL-9-prep: ``models/miniLM``
     for the local cache, ``chroma_db`` for the persistent DB. An
     operator who has never set the env variable sees zero filesystem
     change after this PR lands.

  2. With ``JAMES_EMBEDDING_MODEL`` set to a non-legacy tag (e.g.
     ``BAAI/bge-m3``), both paths split: ``models/<short>`` for the
     cache, ``chroma_db_<short>`` for the persistent DB. The legacy
     ``chroma_db/`` keeps its MiniLM embeddings intact and can be
     reloaded by clearing the env — so the prep is fully reversible.

  3. ``_embedding_short_name`` produces filesystem-safe slugs for
     every HuggingFace-style model id we plan to measure
     (BAAI/bge-m3, intfloat/multilingual-e5-large, plus the legacy
     paraphrase tag). The slug is stable across processes.

The test patches the env BEFORE re-importing ``core.vector_store``
because the module reads ``EMBEDDING_MODEL`` from ``config`` at
import time. Module-level re-import is the only way to exercise
the "env set when the module first loads" code path.
"""
from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


_LEGACY_TAG = "paraphrase-multilingual-MiniLM-L12-v2"


def _reload_with_env(env_value):
    """Set/clear JAMES_EMBEDDING_MODEL and reload config + vector_store.

    Returns the freshly-reloaded ``core.vector_store`` module so the
    test can read its module-level constants (LOCAL_MODEL_PATH,
    FALLBACK_MODEL, _chroma_dir_for_model). The test driver should
    restore the original env in tearDown."""
    if env_value is None:
        os.environ.pop("JAMES_EMBEDDING_MODEL", None)
    else:
        os.environ["JAMES_EMBEDDING_MODEL"] = env_value
    import config
    importlib.reload(config)
    # vector_store imports from config at module load, so re-import too.
    if "core.vector_store" in sys.modules:
        importlib.reload(sys.modules["core.vector_store"])
    import core.vector_store as vs
    return vs, config


class EmbeddingShortNameTests(unittest.TestCase):
    """The slug helper is the foundation of both path resolutions —
    pin it on the exact ids the Sprint 4 swap PR will measure."""

    def test_minilm_tag_slug(self):
        from config import _embedding_short_name
        # Note: the swap-PR resolver short-circuits the legacy tag to
        # `models/miniLM` so the slug below is mostly relevant for
        # *other* tags. Still pin it to catch a regex regression.
        slug = _embedding_short_name(_LEGACY_TAG)
        self.assertEqual(slug, "paraphrase_multilingual_minilm_l12_v2",
            "MiniLM slug must be filesystem-safe lowercase with - → _")

    def test_bge_m3_slug(self):
        from config import _embedding_short_name
        self.assertEqual(_embedding_short_name("BAAI/bge-m3"), "bge_m3",
            "HF org prefix stripped + dashes underscored")

    def test_multilingual_e5_large_slug(self):
        from config import _embedding_short_name
        self.assertEqual(
            _embedding_short_name("intfloat/multilingual-e5-large"),
            "multilingual_e5_large",
        )


class DefaultOffBackwardCompatTests(unittest.TestCase):
    """Without the env var, paths must match pre-BL-9-prep."""

    def setUp(self):
        self._orig = os.environ.get("JAMES_EMBEDDING_MODEL")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("JAMES_EMBEDDING_MODEL", None)
        else:
            os.environ["JAMES_EMBEDDING_MODEL"] = self._orig
        # Reset import state so other test files re-import a fresh module.
        if "core.vector_store" in sys.modules:
            importlib.reload(sys.modules["core.vector_store"])
        import config
        importlib.reload(config)

    def test_unset_env_resolves_legacy_minilm_paths(self):
        vs, cfg = _reload_with_env(None)
        # Default model id matches the legacy tag.
        self.assertEqual(cfg.EMBEDDING_MODEL, _LEGACY_TAG)
        # Local cache path ends in ".../models/miniLM" (the directory
        # the v0.3.x cycle has been writing to).
        self.assertTrue(
            vs.LOCAL_MODEL_PATH.replace("\\", "/").endswith("models/miniLM"),
            f"Default LOCAL_MODEL_PATH ({vs.LOCAL_MODEL_PATH!r}) "
            "must keep the legacy 'models/miniLM' suffix so existing "
            "operators don't trigger a HuggingFace re-download.",
        )

    def test_unset_env_chroma_dir_unchanged(self):
        vs, cfg = _reload_with_env(None)
        # Simulate a VectorStore constructor with base_dir provided.
        legacy = "C:/some/base/chroma_db"
        resolved = vs._chroma_dir_for_model(legacy)
        self.assertEqual(resolved, legacy,
            "Default-off invariant: chroma_dir resolver returns the "
            "input path unchanged when the legacy MiniLM tag is "
            "configured — operator's existing chroma_db/ stays "
            "authoritative.")


class SwapPathTests(unittest.TestCase):
    """With the env var set to a non-legacy tag, paths must split."""

    def setUp(self):
        self._orig = os.environ.get("JAMES_EMBEDDING_MODEL")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("JAMES_EMBEDDING_MODEL", None)
        else:
            os.environ["JAMES_EMBEDDING_MODEL"] = self._orig
        if "core.vector_store" in sys.modules:
            importlib.reload(sys.modules["core.vector_store"])
        import config
        importlib.reload(config)

    def test_bge_m3_uses_per_model_paths(self):
        vs, cfg = _reload_with_env("BAAI/bge-m3")
        self.assertEqual(cfg.EMBEDDING_MODEL, "BAAI/bge-m3")
        self.assertTrue(
            vs.LOCAL_MODEL_PATH.replace("\\", "/").endswith("models/bge_m3"),
            f"BAAI/bge-m3 → LOCAL_MODEL_PATH should end in "
            f"'models/bge_m3'; got {vs.LOCAL_MODEL_PATH!r}.",
        )

    def test_bge_m3_chroma_dir_is_per_model(self):
        vs, cfg = _reload_with_env("BAAI/bge-m3")
        legacy = "C:/some/base/chroma_db"
        resolved = vs._chroma_dir_for_model(legacy)
        self.assertEqual(resolved, "C:/some/base/chroma_db_bge_m3",
            "BAAI/bge-m3 must use a sibling chroma_db_bge_m3/ "
            "directory so the legacy MiniLM 384-dim embeddings in "
            "chroma_db/ aren't clobbered.")

    def test_e5_large_chroma_dir_isolation(self):
        vs, cfg = _reload_with_env("intfloat/multilingual-e5-large")
        legacy = "/tmp/chroma_db"
        self.assertEqual(
            vs._chroma_dir_for_model(legacy),
            "/tmp/chroma_db_multilingual_e5_large",
        )

    def test_fallback_model_follows_env(self):
        vs, cfg = _reload_with_env("BAAI/bge-m3")
        self.assertEqual(vs.FALLBACK_MODEL, "BAAI/bge-m3",
            "FALLBACK_MODEL is what _load_model passes to "
            "SentenceTransformer when the local cache miss. It must "
            "follow the env so the right model downloads.")


if __name__ == "__main__":
    unittest.main()
