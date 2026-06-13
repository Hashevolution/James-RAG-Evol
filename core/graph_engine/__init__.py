"""PROJECT JAMES - Graph Engine (Phase 4.5)

[REFACTOR] graph_rag_engine.py 분리 — DFS + Graph 책임 전담

책임:
  - DFS 탐색 (expand_graph_dynamic)
  - Node ranking (weight-based)
  - Entity map snapshot
  - Entity loading / matching
  - Graph integrity validation
  - Reasoning path verification
  - Ontology strict enforcement

호출 관계:
  reasoning_engine.py → GraphEngine
  retrieval_engine.py → GraphEngine (entity match)

## v0.6 package split (CLAUDE.md rule #5)

The legacy single-file ``core/graph_engine.py`` (21.0 KB) sat over
the 20 KB cap. Splitting into a package preserves the public +
private import surface byte-identically — every caller
(``core/reasoning/engine.py`` for ``GraphEngine`` /
``tests/test_a5d_doc_source_gate.py`` for ``_doc_outgoing_hop_valid`` +
``GraphEngine.expand_dynamic`` source-text /
``core/retrieval/entity_anchor_expander.py`` for ``GraphEngine``)
keeps working through this façade:

  * :mod:`core.graph_engine.constants` — ``CONFIDENCE_THRESHOLD``,
    ``MAX_DEPTH``, ``DFS_SCORE_THRESHOLD``, ``DEPTH_DECAY``
  * :mod:`core.graph_engine.doc_hop_rule` — ``_doc_outgoing_hop_valid``
    (the [#A5-D] document→entity hop gate)
  * :mod:`core.graph_engine.engine` — ``GraphEngine`` class
  * this ``__init__.py`` — re-exports
"""
from __future__ import annotations

# ─── re-exports — preserves the pre-split import surface ─────────

from core.graph_engine.constants import (  # noqa: F401
    CONFIDENCE_THRESHOLD,
    DEPTH_DECAY,
    DFS_SCORE_THRESHOLD,
    MAX_DEPTH,
)
from core.graph_engine.doc_hop_rule import (  # noqa: F401
    _doc_outgoing_hop_valid,
)
from core.graph_engine.engine import (  # noqa: F401
    GraphEngine,
)


__all__ = [
    "GraphEngine",
    "CONFIDENCE_THRESHOLD",
    "MAX_DEPTH",
    "DFS_SCORE_THRESHOLD",
    "DEPTH_DECAY",
]
