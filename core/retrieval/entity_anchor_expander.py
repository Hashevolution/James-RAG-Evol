"""F9.2 — Entity Anchor Expander (corpus-aware query expansion).

Sits BEFORE the LLM-based ``QueryRewriter`` at pipeline STEP 0.5a
(reserved slot — wiring is the F9.3 follow-up PR). Solves a problem
the LLM rewriter cannot solve: **bare proper-noun queries that need
corpus-specific concept anchors to retrieve the matching chunk**.

The q15 8-cycle diagnosis pinned this concretely. With BL-9 (bge-m3)
swap active, the chroma probe reports:

  "David Soria Parra가 누구야?" → not in top-20
  "MCP 설계자 David Soria Parra" → rank 1 (score 0.81)

The matching MCP PDF chunk vector is dominated by concept tokens
(MCP / Model Context Protocol / Anthropic); the person-name fragment
"David Soria Parra와 Justin Spahr-Summers" occupies ~80 chars of a
~2 KB chunk. ANY 1024-dim multilingual pooling embedding has the
same weakness — concept anchor in the **query** is the missing piece,
not encoder capacity.

The F9.1 audit (PR #545) confirmed the LLM rewriter cannot fix this:
0 / 3 anchor-adds on the ``bare_proper_noun`` bucket. The LLM has no
knowledge of "David Soria Parra → MCP" because that relation does
not appear in its training corpus — it appears in the operator's
ingested wiki.

What this module does
---------------------

For a query like ``"David Soria Parra가 누구야?"``:

  1. Scan the query for any surface form that appears in the
     **wiki entity index** (canonical names + frontmatter aliases +
     the D5.D cross-lingual alias pack).
  2. For each matched entity, read its ``relations[].target`` from
     the wiki frontmatter — these are corpus-verified concept anchors.
  3. Filter out anchors that already appear in the query (no point
     adding "MCP" when the operator typed "MCP 설계자 David Soria
     Parra").
  4. Append the top-N remaining anchors to the query in a
     reader-friendly form: ``"<original> (관련: MCP)"``.

What this module is NOT
-----------------------

- **Not an LLM.** Zero token cost, ~0.1ms per call once the surface
  index is warmed.
- **Not the production wiring.** This module ships with a
  ``QueryRewriter``-shaped public surface (singleton + ``.expand``
  method) but is not yet called from ``pipeline.py``. The wiring
  + ``JAMES_ENABLE_ENTITY_ANCHOR=1`` flag land at F9.3.
- **Not a graph traversal.** Reads only the immediately adjacent
  ``relations`` list on the matched entity. Multi-hop expansion
  (entity → relation → next-entity → relation) is a future
  optimisation; the q15 case the audit pinned is solved at hop-0.
- **Not a chroma probe.** F9.1 verdict spent some words explaining
  why option B (chroma neighborhood probe) was rejected: the bare
  name finds wrong chunks (F6 finding — top chunks for "David Soria
  Parra" were finance/FOMC), so anchors extracted from those chunks
  would be wrong. This module reads from the **structured graph**
  (wiki entity frontmatter), bypassing chroma's known failure mode.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Default anchor budget — kept small to avoid query-noise inflation.
# The bge-m3 probe showed adding ONE concept anchor moved q15 from
# zero-recall to rank 1; three is plenty of headroom while remaining
# below the legacy query_rewriter MAX_EXPANSION_RATIO=3 guard.
DEFAULT_TOP_N = 3

# Minimum surface-form length to consider for matching. Guards
# against absurd matches like an entity literally named "MC" lighting
# up on every query containing "MCP". Two characters is the operator-
# chosen threshold (covers short tickers like "BL", "TI" while still
# excluding single-char noise).
MIN_SURFACE_LENGTH = 2


class EntityAnchorExpander:
    """Corpus-aware query expansion via the wiki entity graph.

    The expander caches a reverse index ``surface_form → entity_id``
    on first use. Re-indexing requires explicit
    ``invalidate_index()`` — the production wiki is append-only in
    the steady state, and re-scanning every query would defeat the
    "deterministic, ~0ms" cost profile.

    Tests inject a fake ``graph_engine`` so the suite does not depend
    on the operator's prod wiki. Production code lets the constructor
    lazy-build the real ``GraphEngine``.
    """

    def __init__(self, graph_engine: Optional[object] = None) -> None:
        self._graph_engine = graph_engine
        self._surface_index: Optional[Dict[str, str]] = None
        self._lock = threading.Lock()

    # ─── Index lifecycle ─────────────────────────────────────────

    def _ensure_indexed(self) -> None:
        if self._surface_index is not None:
            return
        with self._lock:
            if self._surface_index is not None:
                return
            if self._graph_engine is None:
                # Lazy import — GraphEngine() instantiates a
                # WikiGenerator() which scans the wiki dir. Holding
                # off until first use means importing this module
                # in a unit-test that mocks the engine doesn't pull
                # the whole wiki ingest into the import graph.
                from core.graph_engine import GraphEngine
                self._graph_engine = GraphEngine()
            self._surface_index = self._build_surface_index()

    def invalidate_index(self) -> None:
        """Force re-build on the next ``expand`` call. Operator hook
        for wiki ingestion paths that add new entities mid-process."""
        with self._lock:
            self._surface_index = None

    def _build_surface_index(self) -> Dict[str, str]:
        """Construct ``{surface_form: entity_id}`` from three sources
        in priority order (first-write wins so wiki-explicit aliases
        beat alias-pack guesses):

          1. wiki entity frontmatter ``name`` (canonical)
          2. wiki entity frontmatter ``aliases:`` list
          3. ``core.entity_alias_pack.iter_entity_aliases`` (D5.D)
        """
        ge = self._graph_engine
        if ge is None:
            return {}
        wg = getattr(ge, "wiki_generator", None)
        if wg is None or not hasattr(wg, "entity_id_index"):
            return {}

        index: Dict[str, str] = {}
        for eid, filepath in wg.entity_id_index.items():
            try:
                fm = wg._read_frontmatter(Path(filepath))
            except Exception:
                continue
            if not fm or not isinstance(fm, dict):
                continue
            name = fm.get("name", "")
            if isinstance(name, str) and len(name) >= MIN_SURFACE_LENGTH:
                index.setdefault(name, eid)
            for alias in fm.get("aliases", []) or []:
                if isinstance(alias, str) and len(alias) >= MIN_SURFACE_LENGTH:
                    index.setdefault(alias, eid)

        # Cross-lingual alias pack — D5.D. Wraps in its own try
        # block so a missing pack import never breaks indexing.
        try:
            from core.entity_alias_pack import iter_entity_aliases
        except Exception:
            iter_entity_aliases = None  # type: ignore

        if iter_entity_aliases is not None:
            # Build a {canonical_name: eid} lookup from the index we
            # just constructed so we can attach pack aliases to the
            # matching wiki entity.
            name_to_eid: Dict[str, str] = {}
            for eid, filepath in wg.entity_id_index.items():
                try:
                    fm = wg._read_frontmatter(Path(filepath))
                except Exception:
                    continue
                if not fm:
                    continue
                canonical = fm.get("name", "")
                if isinstance(canonical, str) and canonical:
                    name_to_eid.setdefault(canonical, eid)

            try:
                for canonical, aliases in iter_entity_aliases():
                    eid = name_to_eid.get(canonical)
                    if not eid:
                        continue
                    for alias in aliases or []:
                        if isinstance(alias, str) and len(alias) >= MIN_SURFACE_LENGTH:
                            index.setdefault(alias, eid)
            except Exception:
                # Pack iteration shouldn't break index build —
                # fall through with what we already collected.
                pass

        return index

    # ─── Public surface ──────────────────────────────────────────

    def expand(
        self,
        query: str,
        *,
        top_n: int = DEFAULT_TOP_N,
    ) -> Tuple[str, List[str], bool]:
        """Return ``(expanded_query, anchors_added, hit)``.

        - ``expanded_query``: the query with ``" (관련: <anchors>)"``
          appended, or the original query unchanged when no entities
          matched or no novel anchors were available.
        - ``anchors_added``: ordered list of the appended anchor
          strings. Empty when ``hit`` is False or when every candidate
          anchor was already a substring of the original query.
        - ``hit``: True iff at least one entity surface form matched
          AND at least one novel anchor was added. False on either
          "no entity matched" OR "matched but all anchors already
          present" — both cases mean the query is unchanged.

        Args:
            query: user query text. Empty / short / non-string inputs
                are returned untouched with ``hit=False``.
            top_n: max number of anchors to append. Pass <= 0 to
                disable the cap (rarely useful — the legacy
                ``MAX_EXPANSION_RATIO=3`` guard in ``QueryRewriter``
                would clip an over-expanded query downstream).

        Determinism:
            For a fixed surface index, identical ``query`` + ``top_n``
            produce identical output (anchor ordering follows the
            iteration order of the matched entities and their
            relations lists). The surface index iteration uses the
            insertion order of ``wiki_generator.entity_id_index``,
            which is stable within a process.
        """
        if not query or not isinstance(query, str) or not query.strip():
            return (query, [], False)

        self._ensure_indexed()
        idx = self._surface_index or {}
        if not idx:
            return (query, [], False)

        query_low = query.lower()

        # Phase 1 — find every entity whose surface form appears in
        # the query. Order preserved via list+set so the anchor
        # output respects index iteration order.
        matched_eids: List[str] = []
        seen_eids: set = set()
        for surface, eid in idx.items():
            if surface.lower() in query_low and eid not in seen_eids:
                seen_eids.add(eid)
                matched_eids.append(eid)

        if not matched_eids:
            return (query, [], False)

        # Phase 2 — collect novel anchors from each matched entity's
        # relations list. "Novel" = not already a substring of the
        # original query.
        anchors: List[str] = []
        seen_anchors: set = set()

        ge = self._graph_engine
        load_entity = getattr(ge, "load_entity", None)
        if load_entity is None:
            return (query, [], False)

        cap = top_n if top_n and top_n > 0 else 10**9
        for eid in matched_eids:
            if len(anchors) >= cap:
                break
            entity = load_entity(eid)
            if not entity:
                continue
            for rel in entity.get("relations", []) or []:
                if not isinstance(rel, dict):
                    continue
                target = rel.get("target", "")
                if not isinstance(target, str) or not target:
                    continue
                target_norm = target.strip()
                if not target_norm:
                    continue
                # Skip targets already mentioned in the query —
                # adding the user's own words back is noise.
                if target_norm.lower() in query_low:
                    continue
                if target_norm in seen_anchors:
                    continue
                seen_anchors.add(target_norm)
                anchors.append(target_norm)
                if len(anchors) >= cap:
                    break

        if not anchors:
            return (query, [], False)

        expanded = f"{query} (관련: {', '.join(anchors)})"
        return (expanded, anchors, True)


# ─── Module-level singleton ──────────────────────────────────────────
#
# Mirrors the ``query_rewriter.get_query_rewriter`` pattern — one
# expander per process. Tests that need a fresh instance call
# ``_clear_singleton_for_tests`` (production code never does).

_SINGLETON: Optional[EntityAnchorExpander] = None
_SINGLETON_LOCK = threading.Lock()


def get_entity_anchor_expander() -> EntityAnchorExpander:
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = EntityAnchorExpander()
    return _SINGLETON


def _clear_singleton_for_tests() -> None:
    """Test helper. Production code never calls this."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        _SINGLETON = None


__all__ = [
    "DEFAULT_TOP_N",
    "MIN_SURFACE_LENGTH",
    "EntityAnchorExpander",
    "get_entity_anchor_expander",
]
