/* PROJECT JAMES — Change Review Workspace list page (Track F.2 CR.a).
 *
 * Surfaces `core/change_request.py` CR primitive as a non-developer
 * review surface. Approve/reject captures forensic principal evidence
 * via the G2.a `current_approval_evidence` resolver (POSIX or
 * explicit) — wire-in lands in CR.d (separate PR).
 *
 * Per `docs/handovers/v0.5-close-2026-06-12.md` §5.6 F.2 — UI shell
 * only. This PR:
 *
 *   1. Renders the CR list table on /admin → Change Requests tab.
 *   2. Wires the status filter + search input.
 *   3. Updates the row count + status indicator (aria-live polite).
 *   4. Renders a "View" action button per row (dispatches a
 *      `james:cr:view` CustomEvent for CR.b detail-modal consumer).
 *
 * Backend HTTP endpoint (`GET /admin/change-requests`) does NOT
 * exist yet. This module uses a **deterministic mock fallback** so
 * the operator can see the table shape pre-backend-wiring. When the
 * HTTP endpoint lands, replace `_fetchMock()` with the real
 * `fetch('/admin/change-requests')`.
 *
 * Plain ES5 — consistent with `index-init.js` (UI #4 PR #855) and
 * `time-travel.js` (TT.a PR #865). Enterprise IT-locked browser
 * compatible.
 *
 * Mother-platform per CLAUDE.md rule #1 — no domain content. The
 * table schema (id / title / target / proposer / age / status /
 * actions) is content-agnostic. Customer-pilot theming lives in
 * Track D CR.e (LOI-conditional).
 */
(function () {
  'use strict';

  var EVENT_VIEW = 'james:cr:view';

  // Deterministic mock — 4 CRs covering each status. Real schema:
  // { cr_id, target_type, target_id, title, proposer, status,
  //   created_at, updated_at, labels }
  // Generated once at module-load so re-renders are stable.
  var _MOCK_CRS = [
    {
      cr_id: 'cr_001_a3f',
      target_type: 'entity',
      target_id: 'e_alice',
      title: 'Update entity Alice: organisation affiliation',
      proposer: 'alice@example.org',
      status: 'open',
      created_at: Date.now() - 1000 * 60 * 30,  // 30 min ago
      labels: 'entity,affiliation'
    },
    {
      cr_id: 'cr_002_b7e',
      target_type: 'policy',
      target_id: 'pol_security_v2',
      title: 'Tighten retention policy on PII rows',
      proposer: 'admin',
      status: 'open',
      created_at: Date.now() - 1000 * 60 * 60 * 4,  // 4h ago
      labels: 'policy,gdpr'
    },
    {
      cr_id: 'cr_003_c9d',
      target_type: 'entity',
      target_id: 'e_acme_corp',
      title: 'Correct AcmeCorp founding date',
      proposer: 'jiwon',
      status: 'merged',
      created_at: Date.now() - 1000 * 60 * 60 * 24 * 2,  // 2d ago
      labels: 'entity,correction'
    },
    {
      cr_id: 'cr_004_d2a',
      target_type: 'graph',
      target_id: 'edge_e_acme_e_jiwon_FOUNDED_BY',
      title: 'Add FOUNDED_BY edge: Acme ← Jiwon',
      proposer: 'jiwon',
      status: 'rejected',
      created_at: Date.now() - 1000 * 60 * 60 * 24 * 7,  // 7d ago
      labels: 'graph,founder'
    }
  ];

  function $(id) { return document.getElementById(id); }

  function escHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function relativeAge(timestamp) {
    var deltaMs = Date.now() - timestamp;
    var min = Math.floor(deltaMs / 60000);
    if (min < 1) return 'just now';
    if (min < 60) return min + 'm ago';
    var hr = Math.floor(min / 60);
    if (hr < 24) return hr + 'h ago';
    var d = Math.floor(hr / 24);
    return d + 'd ago';
  }

  function statusBadge(status) {
    var colors = {
      open:       'background:rgba(255,183,77,.12);color:#ffb74d;border:1px solid rgba(255,183,77,.35);',
      merged:     'background:rgba(76,175,125,.12);color:#4caf7d;border:1px solid rgba(76,175,125,.35);',
      rejected:   'background:rgba(239,68,68,.12);color:#fca5a5;border:1px solid rgba(239,68,68,.35);',
      superseded: 'background:rgba(138,141,153,.12);color:var(--muted);border:1px solid rgba(138,141,153,.35);'
    };
    var style = colors[status] || colors.superseded;
    return '<span style="' + style +
           'padding:3px 9px;border-radius:6px;' +
           'font-size:11px;font-family:var(--font-mono);' +
           'letter-spacing:.3px">' + escHtml(status) + '</span>';
  }

  function renderRow(cr) {
    var ageText = relativeAge(cr.created_at);
    var targetText = cr.target_type + '/' + cr.target_id;
    return [
      '<tr data-cr-id="' + escHtml(cr.cr_id) + '">',
      '<td class="muted-12" style="font-family:var(--font-mono)">',
      escHtml(cr.cr_id),
      '</td>',
      '<td>' + escHtml(cr.title) + '</td>',
      '<td class="muted-12" style="font-family:var(--font-mono)">',
      escHtml(targetText),
      '</td>',
      '<td class="muted-12">' + escHtml(cr.proposer) + '</td>',
      '<td class="muted-12">' + escHtml(ageText) + '</td>',
      '<td>' + statusBadge(cr.status) + '</td>',
      '<td>',
      '<button class="btn btn-primary"',
      ' data-action="cr-view" data-cr-id="' + escHtml(cr.cr_id) + '"',
      ' aria-label="View CR ' + escHtml(cr.cr_id) + '"',
      ' style="padding:5px 12px;font-size:11px">View</button>',
      '</td>',
      '</tr>'
    ].join('');
  }

  function _fetchMock() {
    // Returns a Promise that resolves to the mock list (with a small
    // synthetic delay so the Loading... state is visible). When the
    // real backend lands, replace with:
    //   return fetch('/admin/change-requests')
    //     .then(function (r) { return r.json(); })
    //     .then(function (data) { return data.items || []; });
    return new Promise(function (resolve) {
      setTimeout(function () {
        resolve(_MOCK_CRS.slice());
      }, 150);
    });
  }

  function applyFilter(items) {
    var statusFilter = $('cr-status-filter');
    var searchInput = $('cr-search');
    var status = statusFilter ? statusFilter.value : 'all';
    var query = (searchInput ? (searchInput.value || '').trim().toLowerCase() : '');
    return items.filter(function (cr) {
      if (status !== 'all' && cr.status !== status) return false;
      if (query) {
        var haystack = (
          cr.cr_id + ' ' + cr.title + ' ' + cr.target_id + ' ' +
          cr.proposer + ' ' + (cr.labels || '')
        ).toLowerCase();
        if (haystack.indexOf(query) === -1) return false;
      }
      return true;
    });
  }

  function renderTable(items) {
    var body = $('cr-list-body');
    var counter = $('cr-counter');
    if (!body) return;
    if (!items.length) {
      body.innerHTML =
        '<tr><td colspan="7" class="muted-12"' +
        ' style="text-align:center;padding:18px">' +
        'No change requests match this filter.</td></tr>';
    } else {
      body.innerHTML = items.map(renderRow).join('');
    }
    if (counter) {
      counter.textContent = items.length + ' shown';
    }
  }

  function _allItems() { return _fetchMock(); }

  var _lastFetch = null;  // cache the last fetch promise resolution
  function refresh() {
    if (!_lastFetch) {
      _lastFetch = _allItems();
    }
    _lastFetch.then(function (items) {
      renderTable(applyFilter(items));
    });
  }

  function wireHandlers() {
    var statusFilter = $('cr-status-filter');
    var searchInput = $('cr-search');
    var body = $('cr-list-body');
    if (statusFilter) statusFilter.addEventListener('change', refresh);
    if (searchInput) searchInput.addEventListener('input', refresh);
    if (body) {
      body.addEventListener('click', function (ev) {
        var btn = ev.target;
        while (btn && btn !== body) {
          if (btn.getAttribute &&
              btn.getAttribute('data-action') === 'cr-view') {
            var crId = btn.getAttribute('data-cr-id');
            window.dispatchEvent(new CustomEvent(EVENT_VIEW, {
              detail: { cr_id: crId }
            }));
            return;
          }
          btn = btn.parentNode;
        }
      });
    }
  }

  function activatePageIfVisible() {
    // The admin SPA reveals pages via `data-action="show-page"`. We
    // refresh on each activation so the operator gets fresh data.
    var page = $('page-change-requests');
    if (!page) return;
    if (page.classList.contains('active')) {
      refresh();
    }
    // Watch for class changes (admin.js toggles `.active`).
    if (typeof MutationObserver === 'function') {
      var observer = new MutationObserver(function () {
        if (page.classList.contains('active')) {
          _lastFetch = null;  // force re-fetch on each activation
          refresh();
        }
      });
      observer.observe(page, { attributes: true, attributeFilter: ['class'] });
    }
  }

  function init() {
    wireHandlers();
    activatePageIfVisible();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose for tests + downstream consumers.
  window.JAMES_ChangeRequests = {
    refresh: refresh,
    applyFilter: applyFilter,
    renderTable: renderTable,
    EVENT_VIEW: EVENT_VIEW,
    _setMockItems: function (items) {
      _MOCK_CRS = items;
      _lastFetch = null;
    }
  };
})();
