"""[#A5-D] Document → entity hop validity gate.

Extracted from the legacy single-file ``core/graph_engine.py`` during
the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour is
byte-identical to the pre-split file; only the location moved.

External callers (``tests/test_a5d_doc_source_gate.py`` imports
``ge._doc_outgoing_hop_valid``) keep working through the re-export
façade in ``core/graph_engine/__init__.py``.
"""
from __future__ import annotations


def _doc_outgoing_hop_valid(source_entity: dict, target_entity: dict) -> bool:
    """[#A5-D, 2026-05-09] Document → entity hop validity gate.

    Background — Palantir → 비트코인 spurious path
    -----------------------------------------------
    The wiki_generator emits two kinds of relations on a document
    entity's `relations` list:
      (a) the document's PRIMARY entity (the one whose `sources:` list
          contains this document) — the doc IS about this entity;
      (b) entities merely MENTIONED in the document — these get a
          `RELATED_TO` edge with conf 0.7 but the document is NOT a
          source for them.
    Old DFS treated both kinds the same and freely traversed (a) and
    (b) outbound from a document. This produced cross-domain false
    paths like:

        Palantir → PLTR_03(doc) → Morgan Stanley → MSBT → 비트코인

    The PLTR_03 → Morgan Stanley hop is type-(b): PLTR_03 mentions
    Morgan Stanley but is NOT a Morgan Stanley source document
    (Morgan Stanley's sources field lists only `09_MorganStanley_*`).

    Rule
    ----
    From a document, only follow outgoing edges where the target
    entity has THIS document in its `sources` field. Type-(a) hops
    pass; type-(b) hops are blocked. The rule does not apply when
    the source entity is non-document — entity → entity inferred
    edges (the bulk of the graph backbone, 78% at conf 0.7) are
    untouched, avoiding the over-cut that broke option 1's bench.

    Source vs target asymmetry
    --------------------------
    `entity.sources` carries filenames with extension (e.g.
    `PLTR_03_밸류에이션_리스크_분석.pdf`); document entity's `name`
    is the stem (`PLTR_03_밸류에이션_리스크_분석`). Match by stem
    contained in any source filename.
    """
    if not source_entity or source_entity.get("entity_type") != "document":
        return True   # rule only applies when source is a document

    if not target_entity:
        return True   # missing data — be permissive (other gates apply)

    src_name = (source_entity.get("name") or "").strip()
    if not src_name:
        return True

    target_sources = target_entity.get("sources") or []
    if not isinstance(target_sources, list):
        return True   # malformed — let other gates handle

    for s in target_sources:
        if not isinstance(s, str):
            continue
        # Match by stem (PLTR_03_…)  in source filename (PLTR_03_….pdf).
        if src_name in s:
            return True

    return False


__all__ = ["_doc_outgoing_hop_valid"]
