"""GET /admin/entities — search + paging + detail (item #1).

Coverage:
  - Source-level: route signatures (q, etype, limit, offset) + admin
    gate + response shape (entities, type_counts, total, total_all,
    limit, offset, filters).
  - /admin/entities/{entity_id} detail route exists, admin-gated,
    returns frontmatter + body + relations + 404 on missing.
  - Frontend admin.html has search input + paging buttons + detail
    modal placeholder.
  - Frontend admin.js has loadEntities reading the 4 query params,
    debounced search input handler, and openEntityDetail modal flow.

Run:
  python -m unittest tests.test_admin_entities
"""
from __future__ import annotations

import inspect
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class BackendEndpointContractTests(unittest.TestCase):
    """The list endpoint accepts q / etype / limit / offset, the
    detail endpoint exists, both are admin-gated, response shapes
    match the documented dict."""

    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.src = inspect.getsource(srv)

    def test_list_endpoint_accepts_query_filters(self):
        # Find the /admin/entities decorator + handler.
        idx = self.src.index('@app.get("/admin/entities"')
        # 4000 chars covers the full handler body. The next decorator
        # `@app.get("/admin/entities/{entity_id}"` arrives after that.
        window = self.src[idx:idx + 4000]
        for kw in ("q:", "etype:", "limit:", "offset:"):
            self.assertIn(kw, window,
                          f"/admin/entities must accept {kw} query param")
        # Admin-gated.
        self.assertTrue("_require_admin(api_key, role)" in window or "_require_feature(api_key, role" in window)
        # Response shape contract — these keys must appear in the return dict.
        for shape_key in ('"entities"', '"type_counts"', '"total"',
                          '"total_all"', '"limit"', '"offset"', '"filters"'):
            self.assertIn(shape_key, window,
                          f"response must include {shape_key}")

    def test_list_endpoint_clamps_limit(self):
        idx = self.src.index('@app.get("/admin/entities"')
        # 4000 chars covers the full handler body. The next decorator
        # `@app.get("/admin/entities/{entity_id}"` arrives after that.
        window = self.src[idx:idx + 4000]
        # The 500 hard cap (and the 1 floor) are documented in the code.
        self.assertIn("min(int(limit or 100), 500)", window,
                      "limit must clamp to [1, 500]")

    def test_list_filters_applied_after_counting(self):
        # type_counts must be corpus-wide, not post-filter — so
        # operators always see total counts even when filtering.
        idx = self.src.index('@app.get("/admin/entities"')
        # 4000 chars covers the full handler body. The next decorator
        # `@app.get("/admin/entities/{entity_id}"` arrives after that.
        window = self.src[idx:idx + 4000]
        self.assertIn("Apply filters AFTER counting", window,
                      "comment must explain the count-before-filter ordering — "
                      "so a future refactor doesn't accidentally invert it")

    def test_detail_endpoint_exists_and_admin_gated(self):
        idx = self.src.index('@app.get("/admin/entities/{entity_id}"')
        self.assertGreater(idx, 0,
                           "/admin/entities/{entity_id} detail endpoint missing")
        window = self.src[idx:idx + 1500]
        self.assertTrue("_require_admin(api_key, role)" in window or "_require_feature(api_key, role" in window)
        # Must 404 on missing entity (no silent empty response).
        self.assertIn("status_code=404", window,
                      "detail endpoint must 404 on missing entity")
        # Response shape.
        for key in ('"entity_id"', '"name"', '"entity_type"',
                    '"frontmatter"', '"relations"', '"body"'):
            self.assertIn(key, window,
                          f"detail response must include {key}")


class FrontendAdminContractTests(unittest.TestCase):
    """admin.html has the search input + paging buttons + modal,
    admin.js wires loadEntities to read all four query params, and
    a debounced search handler exists."""

    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent / "frontend"
        cls.html = (root / "admin.html").read_text(encoding="utf-8")
        cls.js   = (root / "static" / "admin.js").read_text(encoding="utf-8")

    def test_html_has_search_input(self):
        self.assertIn('id="entities-search"', self.html)
        self.assertIn('oninput="onEntitiesSearchInput()"', self.html,
                      "search input must wire to the debounced handler")

    def test_html_has_etype_filter(self):
        self.assertIn('id="entities-etype-filter"', self.html)
        self.assertIn('onchange="loadEntities()"', self.html)

    def test_html_has_paging_buttons(self):
        self.assertIn('onclick="entitiesPage(-1)"', self.html)
        self.assertIn('onclick="entitiesPage(1)"', self.html)
        self.assertIn('id="entities-page-label"', self.html)

    def test_html_has_detail_modal(self):
        self.assertIn('id="entity-detail-modal"', self.html)
        self.assertIn('id="entity-detail-title"', self.html)
        self.assertIn('id="entity-detail-body"', self.html)

    def test_js_loadentities_reads_query_filters(self):
        idx = self.js.index("async function loadEntities")
        body = self.js[idx:idx + 2000]
        # Reads q, etype, limit, offset and forwards them.
        self.assertIn("entities-search", body,
                      "loadEntities must read the search input value")
        self.assertIn("entities-etype-filter", body,
                      "loadEntities must read the etype filter value")
        self.assertIn("limit=", body)
        self.assertIn("offset=", body)
        # Calls the new endpoint with query string.
        self.assertIn("/admin/entities?", body,
                      "loadEntities must use querystring form (not just /admin/entities)")

    def test_js_has_debounced_search_handler(self):
        self.assertIn("function onEntitiesSearchInput", self.js,
                      "debounced search handler missing")
        self.assertIn("setTimeout", self.js,
                      "debounce setTimeout missing")

    def test_js_has_open_entity_detail(self):
        self.assertIn("async function openEntityDetail", self.js)
        self.assertIn("/admin/entities/", self.js,
                      "openEntityDetail must hit the detail endpoint")
        self.assertIn("escapeHtml", self.js,
                      "openEntityDetail must escape relations / names "
                      "to avoid XSS in operator-controlled wiki content")


if __name__ == "__main__":
    unittest.main()
