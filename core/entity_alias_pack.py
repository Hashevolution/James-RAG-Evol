"""Cross-lingual entity alias pack — graph-level entity resolution.

D5.D (2026-05-25). Complement to PR #472's keyword-level
`_SYNONYM_MAP` (`core/query_expander.py`). The two layers solve
the same Korean/English mismatch problem at different stages of
the RAG pipeline:

  • `_SYNONYM_MAP` runs at *query expansion* time — token-level
    augmentation so the multilingual-MiniLM embedding has cross-
    lingual surface forms in the vector search input.
  • `_ENTITY_ALIAS_PACK` (this module) runs at *graph entity
    resolution* time — after `entity_extract` produces an entity
    name, `graph_engine.build_entity_map_snapshot` consults this
    pack to augment the wiki-entity lookup table with KO↔EN
    surface forms that the operator hasn't (yet) added to the
    wiki entity's `aliases:` frontmatter.

Why a separate module from `_SYNONYM_MAP`:
  The query expander runs on *every* token of *every* query, with
  hard limits (TOKEN_HARD_LIMIT=50, TIMEOUT_SEC=3.0). The entity
  alias pack runs *once per entity-map-snapshot rebuild* (i.e. on
  wiki ingestion, not per query) and is meant to grow to a few
  thousand entries for common entities. Different cost profiles →
  different data structure + different runtime location.

Backward compat:
  Wiki entities with explicit `aliases:` in their frontmatter take
  precedence (that's already snapshot-merged in
  `graph_engine.build_entity_map_snapshot`). This pack adds
  surface forms only when neither wiki frontmatter nor existing
  snapshot has them. Removing this module reverts to the v0.3
  alias-from-frontmatter-only behavior.
"""

from __future__ import annotations

from typing import Final, List, Tuple


# Each tuple: (canonical_entity_name, [alias_surface_form, ...])
#
# `canonical_entity_name` is the wiki entity's `name:` field as it
# would appear in `wiki/entity/prod/{type}/*.md`. Normalization
# happens in the consumer (graph_engine) via
# `wiki_generator._normalize_name` so we don't pre-normalize here.
#
# The list is augmented as new high-traffic entities are observed
# (D5.D scope: the 4 entities the 2026-05-25 cross-lingual diagnostic
# called out — Palantir, Tesla, Nvidia, Apple — plus the same 28
# companies the PR #472 keyword map already covers, where a wiki
# entity exists in the typical JAMES install).
_ENTITY_ALIAS_PACK: Final[List[Tuple[str, List[str]]]] = [
    # ─── Tech / AI ─────────────────────────────────────────
    ("Palantir Technologies (PLTR)", ["팔란티어", "Palantir", "PLTR"]),
    ("PLTR", ["팔란티어", "Palantir"]),
    ("Tesla, Inc. (TSLA)", ["테슬라", "Tesla", "TSLA"]),
    ("엔비디아", ["Nvidia", "NVIDIA", "NVDA"]),
    ("Apple", ["애플", "AAPL"]),
    ("Microsoft", ["마이크로소프트", "마소", "MSFT"]),
    ("Google", ["구글", "Alphabet", "GOOGL", "GOOG"]),
    ("Alphabet", ["알파벳", "Google", "GOOGL"]),
    ("Meta", ["메타"]),
    ("Amazon", ["아마존", "AMZN"]),
    ("Anthropic", ["앤트로픽", "Claude"]),
    ("Claude", ["클로드", "Anthropic"]),
    ("OpenAI", ["오픈에이아이", "오픈AI", "ChatGPT"]),
    ("AMD", ["에이엠디", "Advanced Micro Devices"]),
    ("Advanced Micro Devices, Inc.", ["AMD", "에이엠디"]),
    ("BYD", ["비야디"]),
    ("BlackRock", ["블랙록"]),
    ("Citi", ["시티", "Citigroup"]),
    ("Citigroup", ["시티", "Citi"]),
    ("Archer Aviation", ["아처", "아처 에이비에이션"]),
    ("Bouygues Telecom", ["부이그", "Bouygues"]),
    ("Cursor", ["커서"]),
    # ─── Institutions ─────────────────────────────────────
    ("FOMC", ["연준", "연방준비제도", "Federal Reserve", "Fed"]),
    ("Federal Reserve", ["연준", "Fed", "FOMC"]),
    ("White House", ["백악관"]),
    ("Pentagon", ["펜타곤"]),
]


def iter_entity_aliases() -> List[Tuple[str, List[str]]]:
    """Return the alias pack as a list of (canonical_name, aliases) pairs.

    Returns a shallow copy so callers can iterate without worrying
    about concurrent modification. The list is small (~30 entries)
    so the copy cost is negligible.

    Consumed by `core.graph_engine.build_entity_map_snapshot` to
    augment the wiki-entity lookup table with KO↔EN surface forms.
    """
    return list(_ENTITY_ALIAS_PACK)
