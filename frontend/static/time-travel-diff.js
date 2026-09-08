/* PROJECT JAMES — Time-Travel now-vs-T diff view (Track F.1 TT.d).
 *
 * Renders a side-by-side modal comparing the audit-replay graph
 * snapshot at the picker's T against the snapshot at "now":
 *
 *   ┌─── AT T ─────────┬─── AT NOW ─────────┐
 *   │ events     12    │ events       15    │
 *   │ active     8     │ active       10    │
 *   │ chains     3     │ chains       3     │
 *   ├──────────────────┴────────────────────┤
 *   │ Added since T     (2) edge_x, edge_y  │
 *   │ Invalidated since (1) edge_z          │
 *   │ Chains extended   (1) head_a          │
 *   └───────────────────────────────────────┘
 *
 * Each diff row has a "View audit evidence" link that deep-links
 * into the admin audit log filter so the operator can see the
 * lifecycle rows that justify the change.
 *
 * Per `docs/handovers/v0.5-close-2026-06-12.md` §5.6 F.1 TT.d. The
 * diff is computed server-side at `/admin/graph/diff-vs-now` (see
 * routes/admin.py); the renderer only paints. UI is domain-agnostic
 * per CLAUDE.md rule #1.
 *
 * Plain ES5 — same convention as the earlier F.1 shells.
 *
 * Loading order: AFTER `graph.js`, `time-travel.js` (TT.a),
 * `time-travel-renderer.js` (TT.b), `time-travel-trace.js` (TT.c).
 */
(function () {
  'use strict';

  var EVENT_SET = 'james:timetravel:set';
  var EVENT_CLEAR = 'james:timetravel:clear';
  var MODAL_ID = 'time-travel-diff-modal';
  var ENDPOINT = '/admin/graph/diff-vs-now';
  var DEFAULT_LIMIT = 500;

  var currentCutoffIso = '';

  function $(id) { return document.getElementById(id); }

  function t(key, fallback) {
    if (typeof window.t === 'function') {
      try { return window.t(key) || fallback; } catch (_) { return fallback; }
    }
    return fallback;
  }

  function escapeHtml(s) {
    if (s === null || typeof s === 'undefined') return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function ensureModal() {
    var existing = $(MODAL_ID);
    if (existing) return existing;
    var div = document.createElement('div');
    div.id = MODAL_ID;
    div.className = 'modal-overlay';
    div.setAttribute('role', 'dialog');
    div.setAttribute('aria-modal', 'true');
    div.setAttribute('aria-labelledby', MODAL_ID + '-title');
    // Hidden by default; .show flips display: flex per modal-overlay
    // convention (see frontend/static/graph.css). Inline fallback in
    // case the stylesheet hasn't reached us yet.
    div.style.cssText =
      'display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);' +
      'z-index:40;align-items:center;justify-content:center;padding:24px';
    div.innerHTML =
      '<div id="' + MODAL_ID + '-card" class="modal-card bg-surface bd-1 ovy-auto c-text font-mono fs-12 u-1b4f1f9d" ' +
      '>' +
      '<div id="' + MODAL_ID + '-body"></div>' +
      '</div>';
    document.body.appendChild(div);
    // Click outside the card closes.
    div.addEventListener('click', function (ev) {
      if (ev.target === div) closeModal();
    });
    // ESC closes (same convention as a11y-modal.js).
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && div.style.display !== 'none') {
        closeModal();
      }
    });
    return div;
  }

  function showModal() {
    var modal = ensureModal();
    if (!modal) return;
    modal.style.display = 'flex';
    modal.classList.add('show');
  }

  function closeModal() {
    var modal = $(MODAL_ID);
    if (!modal) return;
    modal.style.display = 'none';
    modal.classList.remove('show');
  }

  function setBody(html) {
    var body = $(MODAL_ID + '-body');
    if (body) body.innerHTML = html;
  }

  function renderLoading() {
    showModal();
    setBody(
      '<div class="fw-700 c-accent-fg mb-8 u-bedf52b8" id="' + MODAL_ID + '-title">' +
      escapeHtml(t('graph.timetravel.diff.title',
                   'State diff: T → NOW')) +
      '</div>' +
      '<div class="c-muted">' +
      escapeHtml(t('graph.timetravel.diff.loading',
                   'Computing diff…')) +
      '</div>'
    );
  }

  function renderError(detail) {
    showModal();
    var safeDetail = detail ? ' — ' + escapeHtml(detail) : '';
    setBody(
      '<div class="fw-700 c-accent-fg mb-8 u-bedf52b8" id="' + MODAL_ID + '-title">' +
      escapeHtml(t('graph.timetravel.diff.title',
                   'State diff: T → NOW')) +
      '</div>' +
      '<div class="u-6812cd91">' +
      escapeHtml(t('graph.timetravel.diff.error', 'Diff unavailable')) +
      safeDetail + '</div>' + closeButtonHtml()
    );
  }

  function closeButtonHtml() {
    return '<div class="u-4552a90f">' +
           '<button class="bg-surface-2 bd-1 br-6 c-text-soft cursor-pointer fs-11 fw-600 font-mono u-8d4f1f00" type="button" data-action="diff-close" ' +
           'aria-label="Close diff modal" ' +
           '>' +
           escapeHtml(t('graph.timetravel.diff.close', 'Close')) +
           '</button></div>';
  }

  function evidenceLinkHtml(edgeId) {
    var safe = escapeHtml(edgeId);
    // Deep-link to the admin audit log filtered by the edge_id. The
    // admin page handles unrecognised query string keys gracefully
    // (falls back to the empty filter), so this link is safe even
    // if the operator's admin.html hasn't yet learned the new hash.
    var href = '/admin?q=' + encodeURIComponent(edgeId) + '#audit';
    return '<a class="c-accent-fg no-underline fs-10 ml-6 u-62f51076" href="' + href + '" target="_blank" rel="noopener" ' +
           ' ' +
           'aria-label="Open audit log for edge ' + safe + '">' +
           '[' + escapeHtml(t('graph.timetravel.diff.evidence',
                              'View audit evidence')) + ']</a>';
  }

  function listSection(label, ids, opts) {
    if (!ids || ids.length === 0) return '';
    opts = opts || {};
    var rows = '';
    for (var i = 0; i < ids.length; i++) {
      var id = ids[i];
      rows += '<li class="d-flex items-center u-5c9e3ed5">' +
              '<span class="flex-1 wb-all">' +
              escapeHtml(id) + '</span>' +
              (opts.evidence === false ? '' : evidenceLinkHtml(id)) +
              '</li>';
    }
    return '<div class="mt-10">' +
           '<div class="fw-600 c-accent-fg fs-10 ls-1 mb-4">' +
           escapeHtml(label) +
           ' <span class="c-muted fw-400 ls-0">(' + ids.length + ')</span></div>' +
           '<ul class="u-82ef8585">' +
           rows + '</ul></div>';
  }

  function chainsSection(label, chainsObj) {
    var keys = [];
    for (var k in chainsObj) {
      if (Object.prototype.hasOwnProperty.call(chainsObj, k)) keys.push(k);
    }
    if (keys.length === 0) return '';
    var rows = '';
    for (var i = 0; i < keys.length; i++) {
      var head = keys[i];
      var c = chainsObj[head];
      var at_t = (c.at_t || []).join(' → ') || '∅';
      var at_now = (c.at_now || []).join(' → ') || '∅';
      rows += '<li class="u-c2bfc000">' +
              '<div class="d-flex items-center">' +
              '<span class="flex-1 fw-600 c-text wb-all">' + escapeHtml(head) + '</span>' +
              evidenceLinkHtml(head) + '</div>' +
              '<div class="u-1a5d6bb4">' +
              'T: ' + escapeHtml(at_t) + '</div>' +
              '<div class="c-muted fs-10">' +
              'NOW: ' + escapeHtml(at_now) + '</div></li>';
    }
    return '<div class="mt-10">' +
           '<div class="fw-600 c-accent-fg fs-10 ls-1 mb-4">' +
           escapeHtml(label) +
           ' <span class="c-muted fw-400 ls-0">(' + keys.length + ')</span></div>' +
           '<ul class="u-82ef8585">' +
           rows + '</ul></div>';
  }

  function summaryRow(leftLabel, leftVal, rightVal) {
    return '<div class="d-flex u-1507212a">' +
           '<span class="flex-1 c-muted">' +
           escapeHtml(leftLabel) + '</span>' +
           '<span class="c-text fw-600 u-56876cf6">' + escapeHtml(String(leftVal)) + '</span>' +
           '<span class="c-text fw-600 u-56876cf6">' + escapeHtml(String(rightVal)) + '</span>' +
           '</div>';
  }

  function renderDiff(body) {
    showModal();
    var title = t('graph.timetravel.diff.title', 'State diff: T → NOW');
    var thenLabel = t('graph.timetravel.diff.then', 'AT T');
    var nowLabel = t('graph.timetravel.diff.now', 'AT NOW');
    var eventsT = t('graph.timetravel.diff.events_at_t', 'Events at T');
    var eventsNow = t('graph.timetravel.diff.events_at_now', 'Events at NOW');
    var addedLabel = t('graph.timetravel.diff.added', 'Added since T');
    var removedLabel = t('graph.timetravel.diff.removed', 'Removed since T');
    var invalidLabel = t('graph.timetravel.diff.invalidated',
                         'Invalidated since T');
    var chainsLabel = t('graph.timetravel.diff.chains', 'Chains extended');
    var packsAddedLabel = t('graph.timetravel.diff.packs_added',
                            'Packs mounted');
    var packsRemovedLabel = t('graph.timetravel.diff.packs_removed',
                              'Packs unmounted');
    var emptyLabel = t('graph.timetravel.diff.empty',
                       'No changes between T and NOW.');

    var header =
      '<div class="fw-700 c-accent-fg mb-4 u-bedf52b8" id="' + MODAL_ID + '-title">' +
      escapeHtml(title) + '</div>' +
      '<div class="c-muted fs-10 mb-10">' +
      'T: ' + escapeHtml(body.t) + ' • NOW: ' + escapeHtml(body.now) +
      '</div>';

    // Header row of the summary table (T | NOW).
    var summary =
      '<div class="d-flex u-9d1b88d9">' +
      '<span class="flex-1"></span>' +
      '<span class="fw-600 c-accent-fg fs-10 ls-1 u-56876cf6">' +
      escapeHtml(thenLabel) + '</span>' +
      '<span class="fw-600 c-accent-fg fs-10 ls-1 u-56876cf6">' +
      escapeHtml(nowLabel) + '</span></div>' +
      summaryRow(eventsT, body.event_count_at_t, body.event_count_at_now);

    var added = body.added_edges || [];
    var removed = body.removed_edges || [];
    var invalidated = body.invalidated_since || [];
    var chains = body.chain_extended || {};
    var packsAdded = body.mounted_packs_added || [];
    var packsRemoved = body.mounted_packs_removed || [];

    var anyDiff = (added.length + removed.length + invalidated.length +
                   packsAdded.length + packsRemoved.length) > 0;
    for (var k in chains) {
      if (Object.prototype.hasOwnProperty.call(chains, k)) {
        anyDiff = true; break;
      }
    }

    var sections =
      listSection(addedLabel, added) +
      listSection(removedLabel, removed) +
      listSection(invalidLabel, invalidated) +
      chainsSection(chainsLabel, chains) +
      listSection(packsAddedLabel, packsAdded, { evidence: false }) +
      listSection(packsRemovedLabel, packsRemoved, { evidence: false });

    if (!anyDiff) {
      sections = '<div class="c-muted u-3c4d5870">' + escapeHtml(emptyLabel) +
                 '</div>';
    }

    if (body.truncated) {
      sections += '<div class="mt-8 c-muted fs-10">(' +
                  escapeHtml('capped at limit — partial view') + ')</div>';
    }

    setBody(header + summary + sections + closeButtonHtml());

    // Wire the close button (the body innerHTML overrode any prior
    // listeners, so re-attach every render).
    var modal = $(MODAL_ID);
    if (modal) {
      var closeBtn = modal.querySelector('[data-action="diff-close"]');
      if (closeBtn) closeBtn.addEventListener('click', closeModal);
    }
  }

  // ─── HTTP fetch ────────────────────────────────────────────────

  function getCreds() {
    var apiKey = (window.localStorage &&
                  window.localStorage.getItem('james_api_key')) || '';
    var token = (window.localStorage &&
                 window.localStorage.getItem('james_token')) || '';
    return { apiKey: apiKey, token: token };
  }

  function fetchDiff(iso) {
    if (!iso) { renderError(t('graph.timetravel.diff.no_cutoff',
                              'Pick a moment first')); return; }
    var creds = getCreds();
    if (!creds.apiKey) {
      renderError('admin login required'); return;
    }
    var url = ENDPOINT +
              '?api_key=' + encodeURIComponent(creds.apiKey) +
              '&t=' + encodeURIComponent(iso) +
              '&limit=' + DEFAULT_LIMIT;

    renderLoading();

    var xhr = new XMLHttpRequest();
    xhr.open('GET', url, true);
    xhr.setRequestHeader('Accept', 'application/json');
    if (creds.token) {
      xhr.setRequestHeader('Authorization', 'Bearer ' + creds.token);
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
        renderDiff(parsed);
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

  // ─── event wiring ──────────────────────────────────────────────

  function setButtonEnabled(enabled) {
    var btn = $('time-travel-diff');
    if (!btn) return;
    btn.disabled = !enabled;
    btn.style.cursor = enabled ? 'pointer' : 'not-allowed';
    btn.style.opacity = enabled ? '1' : '.5';
  }

  function onCutoffSet(ev) {
    currentCutoffIso = (ev && ev.detail && ev.detail.iso) || '';
    setButtonEnabled(!!currentCutoffIso);
  }

  function onCutoffClear() {
    currentCutoffIso = '';
    setButtonEnabled(false);
    closeModal();
  }

  function onDiffClick() {
    if (!currentCutoffIso) return;
    fetchDiff(currentCutoffIso);
  }

  function wire() {
    var btn = $('time-travel-diff');
    if (btn) btn.addEventListener('click', onDiffClick);
    window.addEventListener(EVENT_SET, onCutoffSet);
    window.addEventListener(EVENT_CLEAR, onCutoffClear);
    // Reflect the initial picker state (TT.a's syncFromHash fires
    // EVENT_SET/CLEAR at DOMContentLoaded; if we missed it because
    // of load order, the disabled button stays disabled — safe).
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }

  // Expose for tests + downstream code.
  window.JAMES_TimeTravelDiff = {
    fetchDiff: fetchDiff,
    renderDiff: renderDiff,
    renderError: renderError,
    closeModal: closeModal,
    setButtonEnabled: setButtonEnabled,
    MODAL_ID: MODAL_ID,
    ENDPOINT: ENDPOINT
  };
})();
