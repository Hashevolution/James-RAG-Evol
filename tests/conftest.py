"""Test-suite session setup — pre-import slow modules once.

## Why this file exists

Several legacy test fixtures use ``unittest.mock.patch(...)`` against
attributes inside heavy modules such as ``core.vector_store.VectorStore``
or ``llm.router.RouterWrapper``. ``patch(...)`` resolves its dotted
target by importing the parent module if it isn't already in
``sys.modules``. ``core.vector_store`` pulls in
``sentence_transformers`` + ``torch`` + ``transformers`` at module load
(~5s cold). So the FIRST ``patch("core.vector_store.VectorStore")`` in
any given pytest process pays that 5s cost during ``setUp``.

On CI runners with no Python bytecode cache and a ``--timeout=30`` per
test, the first test in any class that uses this fixture is one slow
runner away from timing out mid-``setUp``. When that happens,
``tearDown`` never runs, the ``patch("llm.router.RouterWrapper")``
already started in the same ``setUp`` is **leaked**, and downstream
tests in the same pytest process import a ``MagicMock`` instead of the
real ``RouterWrapper`` — visible as e.g.
``test_native_done_reason::test_router_wrapper_call_gemma_meta_dispatches_to_call_router_meta``
failing with *"Expected 'call_router_meta' to be called once. Called 0
times."*

## The fix

Pre-import the heavy modules at session start (module-level code in
this file runs when pytest collects ``tests/conftest.py``, before any
test). After that, every ``patch("core.vector_store.VectorStore")`` is
a fast attribute lookup against an already-cached module, and per-test
``setUp`` stays well under the 30s budget.

Six test files were observed using this fixture pattern (2026-05-26):
  - tests/test_entity_name_markdown_strip.py  (was the canary failure)
  - tests/test_wiki_summary_body_sync.py
  - tests/test_attributes_summary_cleanup.py
  - tests/test_event_ingest_emit.py
  - tests/test_phase_b_ingestion_sources.py
  - tests/test_phase_d_modify_cascade.py

All six benefit from this warm-up; no test source changes required.

Cost: ~5s of session-start overhead instead of ~5s of per-test
``setUp`` overhead on cold runners. The session pays the import once;
no test pays it.

## 2026-05-29 extension — flaky-fix follow-up

The original conftest (above) pre-imported the four heavy modules but
two tests still failed intermittently on cold CI runners:

  - ``test_entity_name_markdown_strip::test_all_markdown_falls_back_to_unknown``
    — timeout (>30s)
  - ``test_native_done_reason::test_router_wrapper_call_gemma_meta_dispatches_to_call_router_meta``
    — cascade failure when the entity-name test's setUp times out and
    leaks ``patch("llm.router.RouterWrapper")``

Two additions to cover the remaining lazy-import paths that fire
during ``WikiFrontmatterMixin.create_entity_file``:

  - ``core.ontology`` / ``core.graph_node_editor`` — both `from … import`
    lazily inside the create_entity_file method body, so the first test
    that drives that path pays their first-import cost. Pre-importing
    here lifts that out of per-test ``setUp``.
  - A ``WikiGenerator`` warm-up instantiation forces every mixin
    ``__init__`` (Frontmatter / Merge / Ingestion) to run once at
    session start, priming any LRU caches or class-level lazy attrs.
    Wrapped in try/except — instantiation side-effects (filesystem,
    config) are recoverable; we just want the cache primed.

## What this does NOT do

This is not a global patch / mock — it just imports. Module identity
is preserved, so existing ``patch(...)`` calls keep working unchanged.
If a future test relies on a fresh import of one of these modules, it
should use ``importlib.reload(...)`` explicitly rather than dropping
the entry from ``sys.modules``.
"""
from __future__ import annotations

# Targets selected by surveying tests/ for `patch("...")` strings whose
# resolution forces a heavy first-import. Order is irrelevant — each
# import is independent. Failures here would block test collection
# entirely, which is intentional: a broken import here means tests
# couldn't run anyway, so fail loudly rather than silently slow.
import core.memory  # noqa: F401 — pre-import to warm sys.modules
import core.vector_store  # noqa: F401 — pulls torch / transformers (~5s cold)
import core.wiki_generator  # noqa: F401 — pre-import to warm sys.modules
import llm.router  # noqa: F401 — pre-import to warm sys.modules

# 2026-05-29 — additional pre-imports for create_entity_file lazy paths.
import core.graph_node_editor  # noqa: F401 — lazy-imported in _frontmatter.py:310
import core.ontology  # noqa: F401 — lazy-imported in _frontmatter.py:336

# 2026-05-29 — warm-up WikiGenerator so every mixin __init__ runs once
# at session start. Side-effects are recoverable; we only need caches
# primed for create_entity_file's first call to stay under 30s on cold
# CI runners.
try:
    from core.wiki_generator import WikiGenerator
    WikiGenerator(source_type="test")
except Exception:
    # Instantiation side-effects (filesystem, network, config) are not
    # required to succeed — the goal is just to trigger any lazy
    # imports / one-shot setup the class performs. Tests that need a
    # working instance build their own under isolated tmp dirs.
    pass
