"""α-7: top-K filter for graph DFS entity surface.

Bound the per-query entity surface to the K highest-ranked entities
by their existing ``_dfs_score`` (populated in
``core.graph_engine.GraphEngine.expand_dynamic``). Drop the
corresponding reasoning paths whose tail entity is filtered out.

Rationale (α-6 Phase 1 §3 finding):

The DFS uses a score-threshold ACT halting policy (``DFS_SCORE_THRESHOLD``)
but no upper bound on the number of entities surfaced. On the
931-entity MultiHop-RAG workspace this yields 41-161 entities per
query. Even though ``build_graph_context_str`` already truncates the
LLM-facing display to ``graph_entities[:10]``, the truncation is in
**DFS visit order**, not **score order** — so the 10 entities the
LLM sees are not always the 10 best.

α-7 ships two complementary changes:

1. Post-DFS top-K filter (this module) — entities returned from
   ``expand_dynamic`` are sorted by ``_dfs_score`` desc and capped
   at ``DEFAULT_TOP_K``. Paths whose tail entity is filtered get
   dropped to keep the entity / path correspondence honest.
2. ``DFS_SCORE_THRESHOLD`` tightened 0.05 → 0.08 in
   ``core.graph_engine`` — fewer marginal entities reach the
   filter input.

These two changes complement: the threshold tighten reduces noise at
the source; the top-K guarantees a hard upper bound.

Design notes:

- Operator-tunable via ``DEFAULT_TOP_K`` (= 10) — production default
  chosen at the empirical inflection point where the
  build_graph_context_str's downstream cap (10) becomes a no-op
  (because the input is already ≤ 10).
- Path tail matching is name-based, not ID-based, because the
  path-string format produced by ``expand_dynamic`` doesn't embed
  entity IDs. Name collisions across entities are tolerated — both
  entities survive if at least one ranks in the top-K (paths to the
  surviving copy are kept).
- The filter is idempotent: applying it twice yields the same output.
"""

from typing import Dict, List, Tuple

# Production default. Aligned with ``build_graph_context_str``'s
# downstream display cap of 10 so the filter is the upper bound and
# the display cap becomes a no-op.
DEFAULT_TOP_K: int = 10


def top_k_filter(
    entities: List[Dict],
    paths: List[str],
    k: int = DEFAULT_TOP_K,
) -> Tuple[List[Dict], List[str]]:
    """Return at most ``k`` entities (by ``_dfs_score`` desc) and the
    subset of ``paths`` whose tail entity name survives the filter.

    Ties on ``_dfs_score`` are broken by DFS visit order (original list
    position) so the filter is deterministic given the same input.

    If ``len(entities) <= k`` the input is returned unchanged.
    """
    if k <= 0:
        # Defensive — caller asked for nothing.
        return [], []
    if len(entities) <= k:
        return entities, paths

    # (-score, original_position) → ascending sort puts highest score
    # first, ties broken by original DFS visit order.
    indexed = list(enumerate(entities))
    indexed.sort(key=lambda iv: (-float(iv[1].get("_dfs_score", 0.0)), iv[0]))
    kept = [iv[1] for iv in indexed[:k]]

    kept_names = {e.get("name") for e in kept if isinstance(e, dict)}
    kept_paths = [p for p in paths if _path_tail_name(p) in kept_names]
    return kept, kept_paths


def _path_tail_name(path_str: str) -> str:
    """Extract the tail entity *name* from a reasoning path string.

    Path format (per ``expand_dynamic``):
        ``"<source> -[<REL>(w=<w>)]→ <tail>"``
    Multi-hop paths chain with the same separator:
        ``"<A> -[X]→ <B> -[Y]→ <C>"``

    The trailing token after the last ``→`` is the tail entity name.
    Returns an empty string if the path is empty or malformed.
    """
    if not path_str:
        return ""
    parts = path_str.split("→")
    if len(parts) < 2:
        return ""
    return parts[-1].strip()
