"""BL-9 (2026-05-27) — contract tests for `scripts/migrate_embedding.py`.

Pins the helpers the runner depends on, without needing the
heavyweight HF model download or a populated chroma collection.
The end-to-end migration is verified by the operator's BL-9
acceptance gate run (post-swap q15 chroma probe + step7 v4).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.migrate_embedding import (  # noqa: E402
    _LEGACY_MINILM_TAG,
    _target_chroma_dir,
)


def test_target_chroma_dir_rejects_legacy_tag():
    """A no-op migration (target == legacy) would silently clobber the
    source. The runner refuses up front."""
    with pytest.raises(ValueError, match="legacy MiniLM"):
        _target_chroma_dir(_LEGACY_MINILM_TAG)


def test_target_chroma_dir_uses_short_slug_suffix():
    """Per-model chroma dir = `<CHROMA_DIR>_<short>` — the slug
    is filesystem-safe (lower / underscores) so the path holds on
    Windows + Linux alike. Pins the suffix shape for bge-m3 and
    multilingual-e5-large since those are the announced BL-9
    candidates."""
    from config import CHROMA_DIR
    bge = _target_chroma_dir("BAAI/bge-m3")
    e5  = _target_chroma_dir("intfloat/multilingual-e5-large")
    assert bge == f"{CHROMA_DIR}_bge_m3"
    assert e5  == f"{CHROMA_DIR}_multilingual_e5_large"


def test_target_chroma_dir_handles_unknown_provider():
    """Any HF-style id should produce a safe slug, not crash. Pins
    that future-candidate models (e.g. `Qwen/Qwen3-Embedding-8B`) can
    be passed without code changes here."""
    out = _target_chroma_dir("Qwen/Qwen3-Embedding-8B")
    assert out.endswith("_qwen3_embedding_8b")
    assert "/" not in out.rsplit("/", 1)[-1]  # no slashes in the basename
