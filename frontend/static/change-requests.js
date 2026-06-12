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

  // ─── v0.5 Track F.2 CR.b — Detail modal + side-by-side diff ─────
  //
  // Listens for `james:cr:view` (dispatched by the row's View button)
  // and opens the modal with the CR's metadata + before/after diff.
  // Pure UI shell — no backend fetch. For the mock CRs, generates a
  // deterministic synthetic before/after string per `target_type` so
  // the operator can see the diff renderer's two-column layout.
  //
  // ARIA: the modal carries role=dialog + aria-modal + aria-labelledby
  // (set in the HTML); `a11y-modal.js` (UI #1 PR #852) auto-wires
  // focus-trap + Escape close + focus restoration via MutationObserver
  // on `display:none` → `display:flex`. No extra wiring here.

  function _findCr(crId) {
    for (var i = 0; i < _MOCK_CRS.length; i++) {
      if (_MOCK_CRS[i].cr_id === crId) return _MOCK_CRS[i];
    }
    return null;
  }

  function _isoFromUnix(ms) {
    try {
      return new Date(ms).toISOString();
    } catch (_) {
      return String(ms);
    }
  }

  function _renderMetaRow(label, value) {
    return (
      '<div class="muted-12">' + escHtml(label) + '</div>' +
      '<div style="color:var(--text);word-break:break-all">' +
      escHtml(value) + '</div>'
    );
  }

  function _renderMeta(cr) {
    var meta = $('cr-detail-meta');
    if (!meta) return;
    meta.innerHTML = (
      _renderMetaRow('CR ID',       cr.cr_id) +
      _renderMetaRow('Target',      cr.target_type + '/' + cr.target_id) +
      _renderMetaRow('Proposer',    cr.proposer) +
      _renderMetaRow('Status',      cr.status) +
      _renderMetaRow('Created',     _isoFromUnix(cr.created_at)) +
      _renderMetaRow('Labels',      cr.labels || '(none)')
    );
  }

  // Mock-only synthetic diff. When the backend lands, the real CR's
  // `proposed_diff` JSON + the loaded base version provide the
  // before/after content; this synth path goes away.
  function _syntheticDiff(cr) {
    if (cr.target_type === 'entity') {
      return {
        before: '{\n  "entity_id": "' + cr.target_id + '",\n' +
                '  "name": "Alice",\n' +
                '  "affiliation": "Acme Corp"\n}',
        after: '{\n  "entity_id": "' + cr.target_id + '",\n' +
               '  "name": "Alice",\n' +
               '  "affiliation": "Acme Corp"\n' +
               '  "title": "Founder"\n}'
      };
    }
    if (cr.target_type === 'policy') {
      return {
        before: 'retention_days: 365\n' +
                'pii_redact: false\n' +
                'audit_class: standard',
        after: 'retention_days: 2555  # 7y per GDPR Art. 17\n' +
               'pii_redact: true\n' +
               'audit_class: standard\n' +
               'retention_class: 7y     # v0.5 G4'
      };
    }
    if (cr.target_type === 'graph') {
      return {
        before: '# (no edge present)',
        after: 'source: e_acme_corp\n' +
               'type:   FOUNDED_BY\n' +
               'target: e_jiwon\n' +
               'weight: 1.0\n' +
               'sensitive: false'
      };
    }
    return {
      before: '(before content)\n' + JSON.stringify({
        title: cr.title, proposer: cr.proposer
      }, null, 2),
      after: '(after content)\n' + JSON.stringify({
        title: cr.title, proposer: cr.proposer,
        proposed: true
      }, null, 2)
    };
  }

  // v0.5 Track F.2 CR.c — Contradiction-arbiter visualisation.
  //
  // Surfaces the 4-rule deterministic classifier output (rules 1..4
  // from `core/lifecycle/contradiction_arbiter.py::classify_contradiction`)
  // as a visible badge + a toggle-expandable explanation panel.
  //
  // Without a backend call, this synthesises a deterministic
  // classification per `target_type` so the operator can see the
  // visualisation shape pre-backend wiring. When the real HTTP
  // endpoint lands (alongside CR.d's merge button), replace
  // `_syntheticArbiterResult` with the real fetch.
  //
  // The 4 labels per `ContradictionClass` Literal in the arbiter:
  //   B_supersede  — world genuinely changed; new edge created,
  //                  old preserved for replay
  //   A_invalidate — retroactive correction; old edge was wrong
  //                  even in its own time window
  //   ignore       — duplicate / equivalent observation
  //   B_supersede  — default (rule 4, safer-than-CASCADE)

  function _syntheticArbiterResult(cr) {
    // Deterministic per target_type so re-renders are stable.
    var classifications = {
      entity:   { rule: 'B_supersede', why: 'rule_1_new_validity_after_old' },
      policy:   { rule: 'A_invalidate', why: 'rule_2_retroactive_correction' },
      graph:    { rule: 'B_supersede', why: 'rule_4_default_safer_than_cascade' },
    };
    return classifications[cr.target_type] ||
      { rule: 'B_supersede', why: 'rule_4_default_safer_than_cascade' };
  }

  function _arbiterRuleExplanation(why) {
    // i18n-friendly later; static for now.
    var map = {
      rule_1_new_validity_after_old:
        'Rule 1 (B_supersede): the proposed change\'s valid_from ' +
        'is strictly later than the current edge\'s valid_until. ' +
        'The world moved on — preserve the old edge for replay; ' +
        'the new one is the current truth.',
      rule_2_retroactive_correction:
        'Rule 2 (A_invalidate): the proposed change carries ' +
        'higher-confidence sources AND its timestamp is at-or-' +
        'before the existing edge\'s valid_from. The old edge ' +
        'was wrong even in its own time window.',
      rule_3_duplicate:
        'Rule 3 (ignore): the proposed change\'s timestamp falls ' +
        'inside the existing edge\'s validity window with no ' +
        'confidence delta. Duplicate observation, not a ' +
        'contradiction.',
      rule_4_default_safer_than_cascade:
        'Rule 4 (B_supersede, default): edge cases (missing ' +
        'timestamps, missing confidence) fall through to a safer-' +
        'than-CASCADE default. History preserved; trivial rollback.',
    };
    return map[why] || '(no explanation available)';
  }

  function _ruleBadgeStyle(rule) {
    if (rule === 'A_invalidate') {
      return 'background:rgba(239,68,68,.12);color:#fca5a5;' +
             'border:1px solid rgba(239,68,68,.45);';
    }
    if (rule === 'ignore') {
      return 'background:rgba(138,141,153,.12);color:var(--muted);' +
             'border:1px solid rgba(138,141,153,.35);';
    }
    // B_supersede — accent-tinted (the most common path)
    return 'background:rgba(107,231,208,.10);color:var(--accent-fg);' +
           'border:1px solid rgba(107,231,208,.30);';
  }

  function _renderArbiterSlot(cr) {
    var slot = $('cr-detail-arbiter-slot');
    if (!slot) return;
    var result = _syntheticArbiterResult(cr);
    var explanation = _arbiterRuleExplanation(result.why);
    var badgeStyle = _ruleBadgeStyle(result.rule);
    var explanationId = 'cr-arbiter-explanation-' + cr.cr_id;
    slot.innerHTML = [
      '<div style="display:flex;align-items:center;gap:10px;',
      'flex-wrap:wrap;font-family:var(--font-mono);font-size:11px">',
      '<span class="muted-12" style="font-family:var(--font-mono)">',
      'Contradiction classifier:',
      '</span>',
      '<span style="' + badgeStyle + 'padding:3px 10px;',
      'border-radius:6px;font-weight:600;letter-spacing:.4px">',
      escHtml(result.rule),
      '</span>',
      '<button data-action="cr-arbiter-toggle"',
      ' data-target="' + explanationId + '"',
      ' aria-label="Toggle arbiter explanation"',
      ' aria-expanded="false"',
      ' style="padding:3px 8px;background:transparent;',
      'border:1px solid var(--border);border-radius:4px;',
      'color:var(--muted);cursor:pointer;font-size:10px;',
      'font-family:var(--font-mono)">',
      'Why?',
      '</button>',
      '</div>',
      '<div id="' + explanationId + '"',
      ' style="display:none;margin-top:8px;padding:8px 10px;',
      'background:var(--surface);border:1px solid var(--border-2);',
      'border-radius:6px;font-size:11px;line-height:1.6;',
      'color:var(--text-soft);font-family:var(--font-ui)">',
      escHtml(explanation),
      '</div>',
    ].join('');
  }

  function _toggleArbiterExplanation(targetId) {
    var el = document.getElementById(targetId);
    if (!el) return;
    var btn = document.querySelector(
      '[data-action="cr-arbiter-toggle"][data-target="' +
      targetId + '"]'
    );
    var isHidden = el.style.display === 'none';
    el.style.display = isHidden ? 'block' : 'none';
    if (btn) {
      btn.setAttribute('aria-expanded', isHidden ? 'true' : 'false');
    }
  }

  // v0.5 Track F.2 CR.d — Approve / Reject buttons + fetch wire.
  //
  // Fills `#cr-detail-actions-slot` with a reviewer-name input
  // + Approve + Reject buttons. The buttons call the backend
  // endpoint (`POST /admin/change-requests/<id>/merge|reject`);
  // on 404 (endpoint not yet wired), the UI falls back to mock
  // behaviour so the operator sees the round-trip pattern.
  //
  // The reviewer string is captured client-side. The actual
  // `ApprovalEvidence` resolution (POSIX / explicit / OIDC) per
  // G2.a (`core/security/approval_evidence.py`) happens
  // server-side when the real endpoint lands — the UI just sends
  // the reviewer name; the server binds it to its current
  // principal.
  //
  // CR.e customer-specific theming (e.g. "Compliance Officer"
  // button label, vertical-specific reject reasons) is
  // LOI-conditional and lives under Track D.

  function _readReviewerHint() {
    // Best-effort default for the reviewer name input. Reads
    // the existing admin localStorage keys; falls back to empty.
    try {
      var role = localStorage.getItem('james_role') || '';
      if (role) return role;
    } catch (_) {}
    return '';
  }

  function _renderActionsSlot(cr) {
    var slot = $('cr-detail-actions-slot');
    if (!slot) return;
    // CR is not open → show terminal state, no actions.
    if (cr.status !== 'open') {
      slot.innerHTML = (
        '<span class="muted-12" style="font-family:var(--font-mono)">' +
        'CR is ' + escHtml(cr.status) + ' — no actions available.' +
        '</span>'
      );
      return;
    }
    var hint = _readReviewerHint();
    slot.innerHTML = [
      '<div style="display:flex;gap:8px;align-items:center;',
      'width:100%;flex-wrap:wrap">',
      '<input id="cr-reviewer-input" type="text"',
      ' value="' + escHtml(hint) + '"',
      ' placeholder="reviewer username"',
      ' aria-label="Reviewer username"',
      ' style="flex:1;min-width:140px;padding:7px 10px;',
      'background:var(--bg);border:1px solid var(--border);',
      'border-radius:6px;color:var(--text);font-size:12px;',
      'font-family:var(--font-mono)">',
      '<button class="btn btn-approve"',
      ' data-action="cr-approve"',
      ' data-cr-id="' + escHtml(cr.cr_id) + '"',
      ' aria-label="Approve change request"',
      ' style="padding:7px 14px;font-size:12px;background:rgba(76,175,125,.15);',
      'color:#4caf7d;border:1px solid rgba(76,175,125,.45);',
      'border-radius:6px;cursor:pointer;font-weight:600;',
      'font-family:var(--font-mono);letter-spacing:.4px">',
      'Approve',
      '</button>',
      '<button class="btn btn-reject"',
      ' data-action="cr-reject"',
      ' data-cr-id="' + escHtml(cr.cr_id) + '"',
      ' aria-label="Reject change request"',
      ' style="padding:7px 14px;font-size:12px;background:rgba(239,68,68,.10);',
      'color:#fca5a5;border:1px solid rgba(239,68,68,.45);',
      'border-radius:6px;cursor:pointer;font-weight:600;',
      'font-family:var(--font-mono);letter-spacing:.4px">',
      'Reject',
      '</button>',
      '</div>',
      '<div id="cr-action-status"',
      ' role="status" aria-live="polite"',
      ' style="margin-top:8px;font-size:11px;line-height:1.5;',
      'font-family:var(--font-mono);color:var(--muted);',
      'min-height:14px"></div>',
    ].join('');
  }

  function _setActionStatus(msg, isError) {
    var el = $('cr-action-status');
    if (!el) return;
    el.textContent = msg || '';
    el.style.color = isError ? '#fca5a5' : 'var(--muted)';
  }

  function _getReviewer() {
    var input = $('cr-reviewer-input');
    if (!input) return '';
    return (input.value || '').trim();
  }

  function _markMock(crId, status) {
    // Mutate the in-memory mock so the next list refresh shows
    // the new state (until the real backend lands).
    for (var i = 0; i < _MOCK_CRS.length; i++) {
      if (_MOCK_CRS[i].cr_id === crId) {
        _MOCK_CRS[i] = Object.assign({}, _MOCK_CRS[i], {
          status: status,
        });
        break;
      }
    }
    _lastFetch = null;
  }

  function _approveCr(crId) {
    var reviewer = _getReviewer();
    if (!reviewer) {
      _setActionStatus('Reviewer required.', true);
      return;
    }
    _setActionStatus('Submitting…', false);
    var body = JSON.stringify({ reviewer: reviewer });
    fetch('/admin/change-requests/' + encodeURIComponent(crId) +
          '/merge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body,
    }).then(function (r) {
      if (r.status === 404) {
        // Backend endpoint not yet wired — fall back to mock.
        _markMock(crId, 'merged');
        _setActionStatus('Merged (mock — backend not wired)', false);
        setTimeout(function () {
          _closeDetail();
          refresh();
        }, 700);
        return;
      }
      if (!r.ok) {
        return r.text().then(function (t) {
          _setActionStatus('Merge failed: ' + (t || r.status), true);
        });
      }
      _markMock(crId, 'merged');
      _setActionStatus('Merged.', false);
      setTimeout(function () {
        _closeDetail();
        refresh();
      }, 500);
    }).catch(function (err) {
      _setActionStatus('Merge error: ' + err.message, true);
    });
  }

  function _rejectCr(crId) {
    var reviewer = _getReviewer();
    if (!reviewer) {
      _setActionStatus('Reviewer required.', true);
      return;
    }
    var reason = window.prompt('Reason for rejection (optional):', '');
    if (reason === null) {
      // User cancelled the prompt.
      _setActionStatus('Rejection cancelled.', false);
      return;
    }
    _setActionStatus('Submitting…', false);
    var body = JSON.stringify({
      reviewer: reviewer, reason: reason,
    });
    fetch('/admin/change-requests/' + encodeURIComponent(crId) +
          '/reject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body,
    }).then(function (r) {
      if (r.status === 404) {
        _markMock(crId, 'rejected');
        _setActionStatus(
          'Rejected (mock — backend not wired)', false,
        );
        setTimeout(function () {
          _closeDetail();
          refresh();
        }, 700);
        return;
      }
      if (!r.ok) {
        return r.text().then(function (t) {
          _setActionStatus('Reject failed: ' + (t || r.status), true);
        });
      }
      _markMock(crId, 'rejected');
      _setActionStatus('Rejected.', false);
      setTimeout(function () {
        _closeDetail();
        refresh();
      }, 500);
    }).catch(function (err) {
      _setActionStatus('Reject error: ' + err.message, true);
    });
  }

  function _openDetail(crId) {
    var cr = _findCr(crId);
    if (!cr) return;
    var modal = $('cr-detail-modal');
    if (!modal) return;
    _renderMeta(cr);
    var desc = $('cr-detail-description');
    if (desc) {
      desc.textContent = cr.title;
    }
    var diff = _syntheticDiff(cr);
    var before = $('cr-detail-diff-before');
    var after = $('cr-detail-diff-after');
    if (before) before.textContent = diff.before;
    if (after) after.textContent = diff.after;
    // CR.c — render arbiter slot.
    _renderArbiterSlot(cr);
    // CR.d — render actions slot (Approve / Reject + reviewer input).
    _renderActionsSlot(cr);
    // Reveal — a11y-modal.js auto-wires focus trap + Escape.
    modal.style.display = 'flex';
  }

  function _closeDetail() {
    var modal = $('cr-detail-modal');
    if (modal) modal.style.display = 'none';
  }

  function _wireDetailModal() {
    window.addEventListener(EVENT_VIEW, function (ev) {
      var crId = ev.detail && ev.detail.cr_id;
      if (crId) _openDetail(crId);
    });
    // Close button + CR.c arbiter toggle + CR.d approve/reject use
    // data-action; delegate via single document-level handler.
    document.addEventListener('click', function (ev) {
      var el = ev.target;
      while (el && el !== document) {
        var action = el.getAttribute && el.getAttribute('data-action');
        if (action === 'cr-detail-close') {
          _closeDetail();
          return;
        }
        if (action === 'cr-arbiter-toggle') {
          var target = el.getAttribute('data-target');
          if (target) _toggleArbiterExplanation(target);
          return;
        }
        if (action === 'cr-approve') {
          var crId = el.getAttribute('data-cr-id');
          if (crId) _approveCr(crId);
          return;
        }
        if (action === 'cr-reject') {
          var crId2 = el.getAttribute('data-cr-id');
          if (crId2) _rejectCr(crId2);
          return;
        }
        el = el.parentNode;
      }
    });
  }

  _wireDetailModal();

  // Expose for tests + downstream consumers.
  window.JAMES_ChangeRequests = {
    refresh: refresh,
    applyFilter: applyFilter,
    renderTable: renderTable,
    EVENT_VIEW: EVENT_VIEW,
    openDetail: _openDetail,
    closeDetail: _closeDetail,
    // v0.5 CR.d
    approveCr: _approveCr,
    rejectCr: _rejectCr,
    _setMockItems: function (items) {
      _MOCK_CRS = items;
      _lastFetch = null;
    }
  };
})();
