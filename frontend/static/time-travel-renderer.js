/* PROJECT JAMES — Time-Travel corpus-state renderer (Track F.1 TT.b).
 *
 * Listens for the `james:timetravel:set` / `james:timetravel:clear`
 * CustomEvents that TT.a dispatches, fetches the audit-only graph
 * snapshot from `GET /admin/graph/reconstruct-at?t=<iso>`, and paints
 * a summary overlay on the /graph page. Where edge IDs in the live
 * graph snapshot match the audit-replay snapshot, links are decorated
 * with status colour (active / superseded / invalidated).
 *
 * Per `docs/handovers/v0.5-close-2026-06-12.md` §5.6 F.1 TT.b. UI is
 * domain-agnostic (mother-platform per CLAUDE.md rule #1). The audit
 * primitive is `reconstruct_graph_at` (T5.B, PR #712) — its docstring
 * notes that production audit_logs may have no lifecycle rows pre-
 * mutation-wiring, so the renderer handles the empty-snapshot case
 * gracefully ("No lifecycle events recorded up to this moment").
 *
 * Plain ES5 — same convention as `time-travel.js` (TT.a) and
 * `index-init.js` (UI #4 PR #855).
 *
 * Loading order: this file must load AFTER `graph.js` (so the
 * ForceGraph instance exists) AND AFTER `time-travel.js` (so the
 * window.JAMES_TimeTravel singleton is registered + we receive
 * the initial sync event).
 */
(function () {
  'use strict';

  var EVENT_SET = 'james:timetravel:set';
  var EVENT_CLEAR = 'james:timetravel:clear';
  var PANEL_ID = 'time-travel-replay-panel';
  var ENDPOINT = '/admin/graph/reconstruct-at';
  var DEFAULT_LIMIT = 1000;

  // Per-edge / per-chain projection of the most-recent successful
  // replay. Downstream code (TT.d diff view) consumes via
  // window.JAMES_TimeTravelRenderer.lastSnapshot().
  var lastSnapshot = null;

  function $(id) { return document.getElementById(id); }

  function t(key, fallback) {
    if (typeof window.t === 'function') {
      try { return window.t(key) || fallback; } catch (_) { return fallback; }
    }
    return fallback;
  }

  function ensurePanel() {
    var existing = $(PANEL_ID);
    if (existing) return existing;
    var stage = document.querySelector('.stage');
    if (!stage) return null;
    var div = document.createElement('div');
    div.id = PANEL_ID;
    // Positioned as a top-right overlay just below the counts overlay
    // (overlay-counts is at top:8px; this sits at top:62px so the two
    // don't visually overlap on phones). Visibility starts hidden;
    // the set handler shows it.
    div.className = 'overlay tt-replay';
    div.setAttribute('role', 'status');
    div.setAttribute('aria-live', 'polite');
    div.style.cssText =
      'position:absolute;right:8px;top:62px;max-width:280px;' +
      'background:var(--surface-2);border:1px solid var(--border);' +
      'border-radius:7px;padding:10px 12px;color:var(--text-soft);' +
      'font-family:var(--font-mono);font-size:11px;line-height:1.55;' +
      'letter-spacing:.2px;z-index:20;display:none;' +
      'box-shadow:0 2px 10px rgba(0,0,0,.4)';
    stage.appendChild(div);
    return div;
  }

  function hidePanel() {
    var panel = $(PANEL_ID);
    if (panel) panel.style.display = 'none';
  }

  function renderLoading() {
    var panel = ensurePanel();
    if (!panel) return;
    panel.style.display = 'block';
    panel.innerHTML =
      '<div style="font-weight:600;color:var(--accent-fg);' +
      'margin-bottom:6px;letter-spacing:.4px">' +
      escapeHtml(t('graph.timetravel.replay.title', 'Replay state')) +
      '</div>' +
      '<div style="color:var(--muted)">' +
      escapeHtml(t('graph.timetravel.replay.loading', 'Loading replay…')) +
      '</div>';
  }

  function renderError(detail) {
    var panel = ensurePanel();
    if (!panel) return;
    panel.style.display = 'block';
    var safeDetail = detail ? ' — ' + escapeHtml(detail) : '';
    panel.innerHTML =
      '<div style="font-weight:600;color:var(--accent-fg);' +
      'margin-bottom:6px;letter-spacing:.4px">' +
      escapeHtml(t('graph.timetravel.replay.title', 'Replay state')) +
      '</div>' +
      '<div style="color:var(--danger,#e06)">' +
      escapeHtml(t('graph.timetravel.replay.error',
                   'Replay unavailable')) + safeDetail +
      '</div>';
  }

  function escapeHtml(s) {
    if (s === null || typeof s === 'undefined') return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function renderSnapshot(snap) {
    var panel = ensurePanel();
    if (!panel) return;
    panel.style.display = 'block';

    var eventsLabel = t('graph.timetravel.replay.events', 'Lifecycle events');
    var activeLabel = t('graph.timetravel.replay.active', 'Active edges');
    var invalidLabel = t('graph.timetravel.replay.invalidated', 'Invalidated');
    var chainsLabel = t('graph.timetravel.replay.chains', 'Supersede chains');
    var packsLabel = t('graph.timetravel.replay.packs', 'Mounted packs');
    var emptyLabel = t('graph.timetravel.replay.empty',
                       'No lifecycle events recorded up to this moment.');
    var truncatedLabel = t('graph.timetravel.replay.truncated',
                           '(capped at limit — partial view)');

    var edgesCount = countKeys(snap.edges);
    var chainCount = countKeys(snap.supersede_chains);
    var invalidCount = snap.invalidated_count || 0;
    var packs = snap.mounted_pack_ids || [];

    var rows = '';
    rows += rowHtml(eventsLabel, snap.event_count);
    rows += rowHtml(activeLabel, edgesCount);
    rows += rowHtml(invalidLabel, invalidCount);
    rows += rowHtml(chainsLabel, chainCount);
    if (packs.length > 0) {
      rows += rowHtml(packsLabel, packs.length);
      rows += '<div style="margin:4px 0 0 8px;color:var(--muted);' +
              'font-size:10px;word-break:break-all">' +
              escapeHtml(packs.join(', ')) + '</div>';
    }

    var body = rows;
    if (snap.event_count === 0) {
      body += '<div style="margin-top:8px;color:var(--muted);' +
              'font-style:italic">' + escapeHtml(emptyLabel) + '</div>';
    }
    if (snap.truncated) {
      body += '<div style="margin-top:6px;color:var(--muted);' +
              'font-size:10px">' + escapeHtml(truncatedLabel) + '</div>';
    }

    panel.innerHTML =
      '<div style="font-weight:600;color:var(--accent-fg);' +
      'margin-bottom:6px;letter-spacing:.4px">' +
      escapeHtml(t('graph.timetravel.replay.title', 'Replay state')) +
      '</div>' + body;
  }

  function rowHtml(label, value) {
    return '<div style="display:flex;justify-content:space-between;' +
           'gap:8px">' +
           '<span>' + escapeHtml(label) + '</span>' +
           '<span style="color:var(--text);font-weight:600">' +
           escapeHtml(String(value)) + '</span></div>';
  }

  function countKeys(o) {
    if (!o) return 0;
    var n = 0;
    for (var k in o) {
      if (Object.prototype.hasOwnProperty.call(o, k)) n++;
    }
    return n;
  }

  // ─── decoration of the live ForceGraph links ────────────────────
  //
  // The live snapshot's link keys are (src_id, tgt_id, relation_type)
  // tuples (entity-level). The audit snapshot's edges are keyed by
  // edge_id (supersede-edge level). The two share an ID space only
  // after the live wiki edges carry a supersede-chain edge_id field,
  // which arrives with later T5.A.b mutation-site wiring. Until then
  // we have no direct join key — so the renderer surfaces the audit
  // snapshot as a summary overlay only and leaves link colours
  // unchanged. Once the join key lands (likely a `link.edge_id`
  // field), the body of paintLinks() below activates.
  function paintLinks(snap) {
    if (!snap) return;
    var graph = window.JAMES_GraphInstance;
    if (!graph || typeof graph.linkColor !== 'function') return;

    var invalidated = {};
    var arr = snap.invalidated_ids || [];
    for (var i = 0; i < arr.length; i++) invalidated[arr[i]] = true;

    var activeEdges = snap.edges || {};

    graph.linkColor(function (link) {
      var liveColor = link.__liveColor || link.color || '#7faecf';
      var edgeId = link && link.edge_id;
      if (!edgeId) return liveColor;
      if (invalidated[edgeId]) return '#e06b6b'; // invalidated → red
      if (activeEdges[edgeId]) return '#9be7c0'; // active at T → mint
      return '#7c7c8c';                          // present in live but
                                                 // unknown to audit
    });
  }

  function clearPaint() {
    var graph = window.JAMES_GraphInstance;
    if (!graph || typeof graph.linkColor !== 'function') return;
    graph.linkColor(function (link) {
      return link.__liveColor || link.color || '#7faecf';
    });
  }

  // ─── HTTP fetch ─────────────────────────────────────────────────

  function getCreds() {
    var apiKey = (window.localStorage &&
                  window.localStorage.getItem('james_api_key')) || '';
    var token = (window.localStorage &&
                 window.localStorage.getItem('james_token')) || '';
    return { apiKey: apiKey, token: token };
  }

  function fetchReplay(iso, opts) {
    var creds = getCreds();
    if (!creds.apiKey) {
      // Anonymous viewer — endpoint requires admin. Surface a
      // friendly inline error rather than 401 noise.
      renderError('admin login required');
      return;
    }

    var url = ENDPOINT +
              '?api_key=' + encodeURIComponent(creds.apiKey) +
              '&t=' + encodeURIComponent(iso) +
              '&limit=' + DEFAULT_LIMIT;

    renderLoading();

    var headers = { 'Accept': 'application/json' };
    if (creds.token) {
      headers['Authorization'] = 'Bearer ' + creds.token;
    }

    var xhr = new XMLHttpRequest();
    xhr.open('GET', url, true);
    for (var k in headers) {
      if (Object.prototype.hasOwnProperty.call(headers, k)) {
        xhr.setRequestHeader(k, headers[k]);
      }
    }
    xhr.onload = function () {
      if (xhr.status >= 200 && xhr.status < 300) {
        var parsed;
        try { parsed = JSON.parse(xhr.responseText); }
        catch (e) { renderError('parse error'); return; }
        if (!parsed || parsed.ok !== true) {
          renderError((parsed && parsed.detail) || 'malformed response');
          return;
        }
        lastSnapshot = parsed;
        renderSnapshot(parsed);
        paintLinks(parsed);
      } else if (xhr.status === 401 || xhr.status === 403) {
        renderError('admin login required');
      } else if (xhr.status === 400) {
        renderError('invalid timestamp');
      } else {
        renderError('HTTP ' + xhr.status);
      }
    };
    xhr.onerror = function () { renderError('network error'); };
    xhr.send();
  }

  // ─── event wiring ───────────────────────────────────────────────

  function onSet(ev) {
    var iso = (ev && ev.detail && ev.detail.iso) || '';
    if (!iso) { onClear(); return; }
    fetchReplay(iso);
    // paintLinks(snap) is intentionally NOT called here — see the
    // paintLinks docstring above. The join key (link.edge_id) lands
    // with later T5.A.b mutation-site wiring; until then auto-paint
    // would destructively replace graph.js's active-path colourer.
    // TT.c / TT.d call paintLinks explicitly when the operator
    // requests the per-link decoration view.
  }

  function onClear() {
    lastSnapshot = null;
    hidePanel();
    // clearPaint() also gated — see onSet rationale. The live
    // graph.js colourer survives untouched across set/clear cycles.
  }

  function wire() {
    window.addEventListener(EVENT_SET, onSet);
    window.addEventListener(EVENT_CLEAR, onClear);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }

  // Expose for tests + downstream (TT.c / TT.d) code.
  window.JAMES_TimeTravelRenderer = {
    fetchReplay: fetchReplay,
    renderSnapshot: renderSnapshot,
    renderError: renderError,
    hidePanel: hidePanel,
    clearPaint: clearPaint,
    paintLinks: paintLinks,
    lastSnapshot: function () { return lastSnapshot; },
    PANEL_ID: PANEL_ID,
    ENDPOINT: ENDPOINT
  };
})();
