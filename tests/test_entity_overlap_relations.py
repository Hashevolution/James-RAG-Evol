"""v0.4 Sprint 1 #1 — token-level entity-name overlap detection.

Operator surfaced 2026-05-25: "비트코인 spot ETF 11개 일괄 승인"
event was ingested without any link to the existing "비트코인"
concept. Root cause: LLM extractor only emits explicit (source,
target) relation pairs from the document body; entity-name
overlap is not detected at ingestion time.

This module tests the fix:
  - `_frontmatter._build_overlap_snapshot` returns the
    `{normalized_name: (canonical, eid, type)}` lookup
  - `_merge._infer_overlap_relations` emits RELATED_TO
    relations for tokens matching another entity
  - self-link prevention (entity matching its own normalized name)
  - duplicate suppression (same target + label)
  - inferred=True + sources[].role="inferred-overlap" markers
  - single-token entity names only (multi-word is follow-up)
"""

from __future__ import annotations


def _make_mixin():
    """Construct a minimal object that includes _infer_overlap_relations
    without booting the full wiki_generator stack (which loads disk
    state)."""
    from core.wiki_generator._merge import WikiMergeMixin

    class _Harness(WikiMergeMixin):
        def __init__(self):
            pass

        # _build_entity_relations uses _inverse_label_for but our
        # overlap tests only touch _infer_overlap_relations so the
        # full mixin is loaded but only one method exercised.
        @staticmethod
        def _inverse_label_for(label):
            return label

    return _Harness()


# ─── _infer_overlap_relations behaviour ───────────────────────────


def test_overlap_emits_relation_for_matching_token():
    """The canonical case — event "비트코인 spot ETF 11개 일괄 승인"
    contains "비트코인" token; with the concept entity registered in
    the snapshot, the helper emits a RELATED_TO relation to it."""
    h = _make_mixin()
    snapshot = {
        "비트코인": ("비트코인", "e_concept_de6c70ec", "concept"),
    }
    out = h._infer_overlap_relations(
        "비트코인 spot ETF 11개 일괄 승인", snapshot,
        doc_id="doc_test", ts="2026-05-25T00:00:00",
    )
    assert len(out) == 1
    rel = out[0]
    assert rel["target"] == "비트코인"
    assert rel["target_id"] == "e_concept_de6c70ec"
    assert rel["target_type"] == "concept"
    assert rel["label"] == "관련"
    assert rel["confidence"] == 0.5
    assert rel["inferred"] is True
    assert rel["sources"][0]["role"] == "inferred-overlap"


def test_overlap_no_match_returns_empty():
    """Source name with no token matching any snapshot entry → []."""
    h = _make_mixin()
    snapshot = {
        "비트코인": ("비트코인", "e_concept_X", "concept"),
    }
    assert h._infer_overlap_relations(
        "completely unrelated event name", snapshot,
    ) == []


def test_overlap_skips_self_match():
    """An entity whose own normalized name appears in the snapshot
    (e.g. re-ingest) does NOT relate to itself."""
    h = _make_mixin()
    snapshot = {
        "비트코인": ("비트코인", "e_concept_X", "concept"),
    }
    out = h._infer_overlap_relations("비트코인", snapshot)
    assert out == []


def test_overlap_skips_single_char_tokens():
    """Tokens shorter than 2 characters (digits, single letters) are
    dropped — prevents spurious matches on "i", "a", etc."""
    h = _make_mixin()
    snapshot = {
        "i": ("i", "e_concept_BAD", "concept"),
        "a": ("a", "e_concept_BAD2", "concept"),
    }
    out = h._infer_overlap_relations("event a i 3 single chars", snapshot)
    assert out == []


def test_overlap_dedups_repeated_token():
    """If the same token appears twice in source_name, the helper
    emits one relation (not two)."""
    h = _make_mixin()
    snapshot = {
        "btc": ("BTC", "e_concept_btc", "concept"),
    }
    out = h._infer_overlap_relations(
        "BTC analysis BTC summary BTC overview",
        snapshot,
    )
    assert len(out) == 1
    assert out[0]["target"] == "BTC"


def test_overlap_dedups_same_target_via_different_aliases():
    """If two snapshot entries point at the same canonical entity
    (one via name, one via alias), only one relation is emitted —
    the (target_canonical, label) seen-set dedups."""
    h = _make_mixin()
    snapshot = {
        "bitcoin":  ("비트코인", "e_concept_btc", "concept"),
        "btc":      ("비트코인", "e_concept_btc", "concept"),
        "비트코인":  ("비트코인", "e_concept_btc", "concept"),
    }
    out = h._infer_overlap_relations(
        "Bitcoin BTC 비트코인 all three forms in one name",
        snapshot,
    )
    assert len(out) == 1
    assert out[0]["target"] == "비트코인"


def test_overlap_emits_multiple_distinct_entities():
    """Different entities in the same source name → multiple
    relations (one per distinct canonical target)."""
    h = _make_mixin()
    snapshot = {
        "비트코인":  ("비트코인", "e_concept_btc", "concept"),
        "이더리움":  ("이더리움", "e_concept_eth", "concept"),
    }
    out = h._infer_overlap_relations(
        "비트코인 이더리움 가격 분석", snapshot,
    )
    assert len(out) == 2
    targets = {r["target"] for r in out}
    assert targets == {"비트코인", "이더리움"}


def test_overlap_no_doc_id_omits_sources():
    """When doc_id is not supplied (legacy / direct call) the
    sources field is omitted — consistent with
    `_build_entity_relations`."""
    h = _make_mixin()
    snapshot = {
        "비트코인": ("비트코인", "e_concept_X", "concept"),
    }
    out = h._infer_overlap_relations("비트코인 event", snapshot)
    assert len(out) == 1
    assert "sources" not in out[0]


def test_overlap_handles_empty_inputs():
    """Empty source_name or empty snapshot → empty result."""
    h = _make_mixin()
    assert h._infer_overlap_relations("", {"foo": ("foo", "e_X", "concept")}) == []
    assert h._infer_overlap_relations("anything", {}) == []
    assert h._infer_overlap_relations(None, {}) == []


# ─── _build_overlap_snapshot regression ──────────────────────────


def test_overlap_snapshot_includes_aliases():
    """`_build_overlap_snapshot` walks `entity_id_index`, reads each
    frontmatter, and records both the canonical normalized name AND
    every alias's normalized form. Tests via a fake WikiGenerator."""
    from core.wiki_generator._frontmatter import WikiFrontmatterMixin

    class _Fake(WikiFrontmatterMixin):
        def __init__(self):
            self.entity_id_index = {
                "e_concept_btc": "fake/path/bitcoin.md",
            }

        def _read_frontmatter(self, path):
            return {
                "entity_id":       "e_concept_btc",
                "entity_type":     "concept",
                "name":            "비트코인",
                "normalized_name": "비트코인",
                "aliases":         ["BTC", "Bitcoin"],
            }

    snapshot = _Fake()._build_overlap_snapshot()
    # Canonical normalized name present
    assert "비트코인" in snapshot
    # Aliases also indexed under their normalized form
    assert "btc" in snapshot
    assert "bitcoin" in snapshot
    # All point to the same canonical name + entity_id
    for v in snapshot.values():
        assert v == ("비트코인", "e_concept_btc", "concept")


def test_overlap_snapshot_first_write_wins():
    """If two entities share a normalized name (rare edge case), the
    first one in `entity_id_index` iteration order wins."""
    from core.wiki_generator._frontmatter import WikiFrontmatterMixin

    class _Fake(WikiFrontmatterMixin):
        def __init__(self):
            # OrderedDict-like ordering (Python 3.7+ dict preserves insert order)
            self.entity_id_index = {
                "e_org_first":  "fake/first.md",
                "e_org_second": "fake/second.md",
            }

        def _read_frontmatter(self, path):
            if "first" in str(path):
                return {
                    "entity_id":       "e_org_first",
                    "entity_type":     "org",
                    "name":            "Acme",
                    "normalized_name": "acme",
                    "aliases":         [],
                }
            return {
                "entity_id":       "e_org_second",
                "entity_type":     "org",
                "name":            "Acme",
                "normalized_name": "acme",
                "aliases":         [],
            }

    snapshot = _Fake()._build_overlap_snapshot()
    assert snapshot["acme"][1] == "e_org_first"
