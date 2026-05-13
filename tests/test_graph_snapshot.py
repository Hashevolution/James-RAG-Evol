"""GET /admin/graph/snapshot — reasoning graph 3D visualization snapshot.

v0.2 Axis 3 (Observability/Explainability) — read-only enumeration of every
wiki entity + ontology edge for the /admin/graph 3D visualizer.

Coverage:
  - core.graph_snapshot.build_snapshot returns the documented
    {nodes, edges, meta} shape.
  - Sensitive nodes (sensitivity == "sensitive") are filtered when
    include_sensitive=False.
  - Sensitive edges (RELATION_TYPES[*].sensitive == True, e.g.
    HAS_SECRET, KNOWS_PASSWORD, HAS_CREDENTIAL, OWNS_PRIVATE) are
    filtered when include_sensitive=False.
  - Edges whose endpoint nodes were dropped are themselves dropped.
  - Cache key invalidates when any wiki file's mtime changes.
  - Server route /admin/graph/snapshot exists, is admin-gated, and
    accepts source_type + include_sensitive query params.
  - Server route /admin/graph (the HTML page) is registered.
  - Frontend artifacts (graph.html, graph.js) exist with the
    documented globals (ForceGraph3D loaded from CDN, askQuestion
    handler, parsePath logic).

Run:
  python -m unittest tests.test_graph_snapshot
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────────────────────
# Synthetic WikiGenerator-shaped fixture.
#
# build_snapshot only depends on three attributes/methods of the
# wiki_generator argument:
#   .entity_path          (Path)
#   .entity_types         (List[str])
#   .entity_id_index      (Dict[entity_id, file_path])
#   ._read_frontmatter(path) -> dict | None
#
# Faking these lets us exercise the snapshot logic without booting
# ChromaDB / Ollama / the full RAGEngine.
# ─────────────────────────────────────────────────────────────

class _FakeWiki:
    def __init__(self, root: Path, entities: dict):
        self.entity_path  = root / "entity" / "prod"
        self.entity_types = ["person", "concept", "org", "document"]
        self.source_type  = "prod"
        self.entity_id_index = {}
        for eid, fm in entities.items():
            etype = fm.get("entity_type", "concept")
            d = self.entity_path / etype
            d.mkdir(parents=True, exist_ok=True)
            f = d / (eid + ".md")
            # Trivial frontmatter file — _read_frontmatter is overridden
            # so the on-disk content is never parsed; we just need an
            # mtime-bearing file so _scan_max_mtime works.
            f.write_text("---\nentity_id: " + eid + "\n---\n", encoding="utf-8")
            self.entity_id_index[eid] = f
        self._fm = entities

    def _read_frontmatter(self, path):
        # Path → entity_id reverse-lookup; exercises the same code path.
        for eid, p in self.entity_id_index.items():
            if Path(p) == Path(path):
                return self._fm[eid]
        return None


def _mk_entity(eid, name, etype="concept", sensitivity="internal", relations=None):
    return {
        "entity_id":   eid,
        "name":        name,
        "entity_type": etype,
        "sensitivity": sensitivity,
        "relations":   relations or [],
    }


def _mk_rel(target_id, rel_type="WORKS_AT", confidence=0.9, target_name=""):
    return {
        "target":      target_name or target_id,
        "target_id":   target_id,
        "type":        rel_type,
        "confidence":  confidence,
    }


# ─────────────────────────────────────────────────────────────
class SnapshotShapeTests(unittest.TestCase):

    def setUp(self):
        from core.graph_snapshot import invalidate_cache
        invalidate_cache()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_basic_shape(self):
        from core.graph_snapshot import build_snapshot
        ents = {
            "e_person_aaaaaaaa": _mk_entity(
                "e_person_aaaaaaaa", "Alice", "person",
                relations=[_mk_rel("e_org_bbbbbbbb", "WORKS_AT", 0.9)],
            ),
            "e_org_bbbbbbbb": _mk_entity("e_org_bbbbbbbb", "Acme", "org"),
        }
        wiki = _FakeWiki(self.root, ents)
        snap = build_snapshot(wiki)
        self.assertIn("nodes", snap)
        self.assertIn("edges", snap)
        self.assertIn("meta",  snap)
        self.assertEqual(len(snap["nodes"]), 2)
        self.assertEqual(len(snap["edges"]), 1)
        self.assertEqual(snap["meta"]["node_count"], 2)
        self.assertEqual(snap["meta"]["edge_count"], 1)
        self.assertFalse(snap["meta"]["truncated"])
        # Edge points to existing nodes.
        e = snap["edges"][0]
        ids = {n["id"] for n in snap["nodes"]}
        self.assertIn(e["s"], ids)
        self.assertIn(e["t"], ids)
        self.assertEqual(e["type"], "WORKS_AT")

    def test_sensitive_node_filtered(self):
        from core.graph_snapshot import build_snapshot
        ents = {
            "e_person_aaaaaaaa": _mk_entity("e_person_aaaaaaaa", "Alice", "person"),
            "e_concept_cccccccc": _mk_entity(
                "e_concept_cccccccc", "TopSecret", "concept",
                sensitivity="sensitive",
            ),
        }
        wiki = _FakeWiki(self.root, ents)
        snap = build_snapshot(wiki, include_sensitive=False)
        names = {n["name"] for n in snap["nodes"]}
        self.assertIn("Alice", names)
        self.assertNotIn("TopSecret", names,
                         "sensitivity=sensitive node must be dropped")

    def test_sensitive_relation_filtered(self):
        from core.graph_snapshot import build_snapshot
        ents = {
            "e_person_aaaaaaaa": _mk_entity(
                "e_person_aaaaaaaa", "Alice", "person",
                relations=[
                    _mk_rel("e_concept_cccccccc", "HAS_SECRET", 0.9),
                    _mk_rel("e_org_bbbbbbbb",     "WORKS_AT",   0.9),
                ],
            ),
            "e_org_bbbbbbbb":     _mk_entity("e_org_bbbbbbbb", "Acme", "org"),
            "e_concept_cccccccc": _mk_entity("e_concept_cccccccc", "Hush", "concept"),
        }
        wiki = _FakeWiki(self.root, ents)
        snap = build_snapshot(wiki, include_sensitive=False)
        types = {e["type"] for e in snap["edges"]}
        self.assertNotIn("HAS_SECRET", types,
                         "sensitive relation type must be dropped")
        self.assertIn("WORKS_AT", types)

    def test_unresolved_targets_dropped(self):
        from core.graph_snapshot import build_snapshot
        ents = {
            "e_person_aaaaaaaa": _mk_entity(
                "e_person_aaaaaaaa", "Alice", "person",
                relations=[
                    _mk_rel("UNRESOLVED",      "RELATED_TO", 0.9),
                    _mk_rel("e_org_bbbbbbbb",  "WORKS_AT",   0.9),
                ],
            ),
            "e_org_bbbbbbbb": _mk_entity("e_org_bbbbbbbb", "Acme", "org"),
        }
        wiki = _FakeWiki(self.root, ents)
        snap = build_snapshot(wiki)
        # UNRESOLVED edge dropped → only one survives.
        self.assertEqual(len(snap["edges"]), 1)

    def test_degree_count_accurate(self):
        from core.graph_snapshot import build_snapshot
        # Alice has 2 outgoing relations; degree on each endpoint is +1
        # for the edge it touches.
        ents = {
            "e_person_aaaaaaaa": _mk_entity(
                "e_person_aaaaaaaa", "Alice", "person",
                relations=[
                    _mk_rel("e_org_bbbbbbbb",  "WORKS_AT",   0.9),
                    _mk_rel("e_concept_cccccccc", "STUDIES", 0.9),
                ],
            ),
            "e_org_bbbbbbbb":     _mk_entity("e_org_bbbbbbbb", "Acme", "org"),
            "e_concept_cccccccc": _mk_entity("e_concept_cccccccc", "X", "concept"),
        }
        wiki = _FakeWiki(self.root, ents)
        snap = build_snapshot(wiki)
        by_id = {n["id"]: n for n in snap["nodes"]}
        self.assertEqual(by_id["e_person_aaaaaaaa"]["degree"], 2)
        self.assertEqual(by_id["e_org_bbbbbbbb"]["degree"],     1)
        self.assertEqual(by_id["e_concept_cccccccc"]["degree"], 1)

    def test_cache_invalidates_on_mtime_change(self):
        from core.graph_snapshot import build_snapshot
        ents = {
            "e_person_aaaaaaaa": _mk_entity("e_person_aaaaaaaa", "Alice", "person"),
        }
        wiki = _FakeWiki(self.root, ents)
        snap1 = build_snapshot(wiki)
        h1 = snap1["meta"]["snapshot_hash"]

        # Bump the file's mtime to the future (simulate a wiki edit).
        f = wiki.entity_id_index["e_person_aaaaaaaa"]
        future = time.time() + 5
        os.utime(f, (future, future))

        # Add a new entity to materially change content.
        ents2 = dict(ents)
        ents2["e_org_bbbbbbbb"] = _mk_entity("e_org_bbbbbbbb", "Acme", "org")
        wiki2 = _FakeWiki(self.root, ents2)
        # Bump the new file's mtime as well.
        f2 = wiki2.entity_id_index["e_org_bbbbbbbb"]
        os.utime(f2, (future, future))

        snap2 = build_snapshot(wiki2)
        self.assertNotEqual(h1, snap2["meta"]["snapshot_hash"],
                            "snapshot_hash must change when mtime + content changes")
        self.assertEqual(snap2["meta"]["node_count"], 2)

    def test_snapshot_picks_up_files_written_outside_index(self):
        """Regression for the 'wiki entity added → /graph stale until
        server restart' bug.

        Root cause: `tools.web.web_searcher.save_as_longterm` (장기기억
        promotion path) constructs its own throwaway `RAGEngine` and
        writes new entity files via that engine's `WikiGenerator`. The
        server's shared `rag_engine.wiki_generator` never learns about
        those files, so its `entity_id_index` stays stale. Even though
        `_scan_max_mtime` notices the disk change and invalidates the
        snapshot cache, the rebuild iterates the stale index and the
        new entities silently vanish from `/admin/graph/snapshot`.

        The fix: on cache miss, ask the wiki_generator to re-scan disk
        before rebuilding. This test simulates the bug by writing a new
        .md to disk without registering it in `entity_id_index`, then
        teaches the fake how `refresh_entity_map` should behave.
        """
        from core.graph_snapshot import build_snapshot
        ents = {
            "e_person_aaaaaaaa": _mk_entity(
                "e_person_aaaaaaaa", "Alice", "person",
            ),
        }
        wiki = _FakeWiki(self.root, ents)
        snap1 = build_snapshot(wiki)
        self.assertEqual(snap1["meta"]["node_count"], 1)

        # Simulate a *different* RAGEngine instance writing a new entity
        # file to disk. The new file exists on the filesystem; this
        # wiki_generator's in-memory index still has only the original
        # entity (mirrors the save_as_longterm cross-instance race).
        new_eid  = "e_org_bbbbbbbb"
        new_fm   = _mk_entity(new_eid, "Acme", "org")
        new_dir  = wiki.entity_path / "org"
        new_dir.mkdir(parents=True, exist_ok=True)
        new_path = new_dir / (new_eid + ".md")
        new_path.write_text(
            "---\nentity_id: " + new_eid + "\n---\n", encoding="utf-8",
        )
        # Bump mtime so _scan_max_mtime sees the disk change even on
        # filesystems with coarse timestamp precision.
        future = time.time() + 5
        os.utime(new_path, (future, future))

        # The real WikiGenerator.refresh_entity_map re-scans disk and
        # rebuilds the index from each frontmatter. Mirror that for the
        # fake: discover the new file, register it in the index, and
        # remember its frontmatter so _read_frontmatter can return it.
        def _refresh():
            for t in wiki.entity_types:
                d = wiki.entity_path / t
                if not d.exists():
                    continue
                for f in d.glob("*.md"):
                    eid = f.stem
                    if eid not in wiki.entity_id_index:
                        wiki.entity_id_index[eid] = f
                        if eid == new_eid:
                            wiki._fm[eid] = new_fm
        wiki.refresh_entity_map = _refresh

        snap2 = build_snapshot(wiki)
        self.assertEqual(
            snap2["meta"]["node_count"], 2,
            "snapshot must re-scan disk on cache miss and surface "
            "entity files written by another engine instance — "
            "without this, /admin/graph remains stale until restart",
        )
        names = {n["name"] for n in snap2["nodes"]}
        self.assertIn("Acme", names,
                      "newly-written entity must appear by name in the "
                      "rebuilt snapshot")


# ─────────────────────────────────────────────────────────────
class ServerRouteContractTests(unittest.TestCase):
    """The /admin/graph and /admin/graph/snapshot routes are registered
    with the right shape and the admin gate.

    Reads server_llmwiki.py as text rather than importing it, so this
    contract test runs in environments without FastAPI (e.g. lint-only
    CI containers) — same pattern but more resilient than the peer
    test_admin_entities suite.
    """

    @classmethod
    def setUpClass(cls):
        srv_path = Path(__file__).resolve().parent.parent / "server_llmwiki.py"
        cls.src = srv_path.read_text(encoding="utf-8")

    def test_html_route_registered(self):
        self.assertIn('@app.get("/admin/graph"', self.src,
                      "/admin/graph HTML page route must be registered")
        self.assertIn("graph.html", self.src,
                      "/admin/graph must serve frontend/graph.html")

    def test_snapshot_route_registered_and_admin_gated(self):
        idx = self.src.index('@app.get("/admin/graph/snapshot"')
        window = self.src[idx:idx + 2500]
        self.assertIn("source_type", window,
                      "snapshot must accept source_type query param")
        self.assertIn("include_sensitive", window,
                      "snapshot must accept include_sensitive query param")
        self.assertTrue("_require_admin(api_key, role)" in window or "_require_feature(api_key, role" in window,
                      "snapshot endpoint must be admin-gated")
        self.assertIn("build_snapshot", window,
                      "snapshot must call build_snapshot helper")

    def test_sensitive_locked_off_in_v0_2(self):
        # v0.2 has no elevated-role definition yet, so the gate hard-locks
        # include_sensitive to False regardless of the query param. When a
        # superadmin role lands later, this test should be updated together
        # with the gate.
        idx = self.src.index('@app.get("/admin/graph/snapshot"')
        window = self.src[idx:idx + 2500]
        self.assertIn("include_sens = False", window,
                      "sensitive payloads must be locked off until an "
                      "elevated role exists")


# ─────────────────────────────────────────────────────────────
class FrontendArtifactTests(unittest.TestCase):
    """The graph.html page + graph.js exist with the documented globals."""

    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent / "frontend"
        cls.html = (root / "graph.html").read_text(encoding="utf-8")
        cls.js   = (root / "static" / "graph.js").read_text(encoding="utf-8")

    def test_html_loads_three_and_force_graph(self):
        self.assertIn("three@0.160", self.html,
                      "graph.html must pin a Three.js version on the CDN")
        self.assertIn("3d-force-graph", self.html,
                      "graph.html must load the 3d-force-graph library")

    # [W2 2026-05-10] qbox / askQuestion 제거 — graph 페이지에서 질문
    # 인터페이스 사라짐 (/chat 으로 이관). parsePath / animatePaths 도
    # 질문 답변 path 시각화 전용 → 동시 제거. spawnPulse 는 exploreFromNode
    # 에서 여전히 사용되므로 별도 검증.

    def test_html_has_canvas_and_legend(self):
        self.assertIn('id="graph-canvas"', self.html)
        self.assertIn('class="legend"', self.html)
        self.assertIn('data-i18n="graph.legend.person"', self.html)

    def test_js_has_pulse_spawner(self):
        # spawnPulse 는 exploreFromNode (이웃 시각화) 에서 사용되므로 유지.
        self.assertIn("spawnPulse", self.js,
                      "graph.js must define a sprite pulse spawner")

    def test_js_uses_admin_snapshot_endpoint(self):
        self.assertIn("/admin/graph/snapshot", self.js,
                      "graph.js must hit the admin snapshot endpoint")
        self.assertIn("api_key=", self.js,
                      "graph.js must forward the admin api_key")

    def test_js_posts_to_query_endpoint(self):
        self.assertIn("/query/", self.js,
                      "graph.js must POST to /query/ to drive the animation")

    def test_js_separates_api_key_from_jwt(self):
        # Regression — earlier the auth mistakenly stored a JWT into
        # localStorage.james_api_key, which both overwrote the chat-side
        # API key AND failed verify_api_key on the next admin call. The
        # login flow must now match admin.js: JWT → james_token, used
        # via Authorization: Bearer; api_key stays untouched in
        # james_api_key for the ?api_key= query param.
        self.assertIn("james_token", self.js,
                      "graph.js must store the JWT under james_token "
                      "(NOT james_api_key)")
        self.assertIn("'Authorization': 'Bearer ' + token", self.js,
                      "admin requests must send the JWT as a Bearer header")
        self.assertIn("access_token || j.token", self.js,
                      "graph.js must read access_token (or token) from "
                      "the /login/ response — not a non-existent api_key field")

    def test_html_login_modal_has_apikey_field(self):
        self.assertIn('id="login-apikey"', self.html,
                      "login modal must accept an API key in case the "
                      "user lands here without visiting the chat page first")


if __name__ == "__main__":
    unittest.main()
