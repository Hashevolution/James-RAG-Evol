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
