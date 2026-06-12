/* PROJECT JAMES — Time-Travel timestamp picker (Track F.1 TT.a).
 *
 * Surfaces the G3 corpus_reconstruct_view_at primitive (PR #849)
 * as a date/time picker on /graph. State syncs with the URL hash
 * (`#t=<ISO>`) so a deep-link replays the same moment.
 *
 * Per `docs/handovers/v0.5-close-2026-06-12.md` §5.6 F.1 — UI shell
 * only. Backend call wired in TT.b (separate PR). For now this file:
 *
 *   1. On DOMContentLoaded: parse `#t=<ISO>` from window.location.hash;
 *      if present, populate the input + show "Viewing: <ts>" state.
 *   2. On Apply click: read the input value → write
 *      `#t=<ISO>` into window.location.hash → dispatch a
 *      `james:timetravel:set` CustomEvent on window with detail.iso.
 *   3. On Now click: clear the input + clear the hash → dispatch
 *      `james:timetravel:clear`.
 *   4. On hashchange (back/forward navigation): re-sync the input +
 *      state indicator from the hash.
 *
 * Downstream consumers (TT.b corpus-state renderer, TT.c reasoning-
 * trail replay) listen for the custom events:
 *
 *   window.addEventListener('james:timetravel:set',
 *     function (ev) {
 *       const iso = ev.detail.iso;
 *       // fetch /reconstruct-view-at?t=<iso> + repaint graph
 *     });
 *   window.addEventListener('james:timetravel:clear',
 *     function () { // restore current state });
 *
 * Plain ES5 — no template literals, arrow functions only at
 * top-level. Maximises enterprise IT-locked browser compat (same
 * convention as `index-init.js` from UI #4 PR #855).
 *
 * Mother-platform per CLAUDE.md rule #1 — no domain content. The
 * UI surface schema is "timestamp + apply + now". Customer-pilot
 * customisation lives in Track D post-LOI.
 */
(function () {
  'use strict';

  var HASH_KEY = 't';
  var EVENT_SET = 'james:timetravel:set';
  var EVENT_CLEAR = 'james:timetravel:clear';

  function $(id) { return document.getElementById(id); }

  function readHashIso() {
    var hash = window.location.hash || '';
    if (hash.charAt(0) === '#') hash = hash.substring(1);
    if (!hash) return '';
    var parts = hash.split('&');
    for (var i = 0; i < parts.length; i++) {
      var kv = parts[i].split('=');
      if (kv[0] === HASH_KEY && kv.length === 2) {
        try {
          return decodeURIComponent(kv[1]);
        } catch (_) {
          return '';
        }
      }
    }
    return '';
  }

  function writeHashIso(iso) {
    var existing = window.location.hash || '';
    if (existing.charAt(0) === '#') existing = existing.substring(1);
    var parts = existing ? existing.split('&') : [];
    // Drop any existing `t=` entry, then re-append.
    var kept = [];
    for (var i = 0; i < parts.length; i++) {
      var kv = parts[i].split('=');
      if (kv[0] !== HASH_KEY) kept.push(parts[i]);
    }
    if (iso) {
      kept.push(HASH_KEY + '=' + encodeURIComponent(iso));
    }
    var newHash = kept.join('&');
    // History.replaceState avoids spamming the back-button stack.
    var url = window.location.pathname + window.location.search +
              (newHash ? ('#' + newHash) : '');
    try {
      window.history.replaceState(null, '', url);
    } catch (_) {
      window.location.hash = newHash;
    }
  }

  function toInputValue(iso) {
    // <input type="datetime-local"> wants "YYYY-MM-DDTHH:MM" — strip
    // timezone + seconds. Returns '' on parse failure.
    if (!iso) return '';
    // Accept either "2026-06-12T14:30" or "2026-06-12T14:30:00+00:00".
    var match = iso.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})/);
    return match ? match[1] : '';
  }

  function fromInputValue(value) {
    // Convert input "YYYY-MM-DDTHH:MM" back to canonical ISO-8601.
    // The browser's datetime-local treats it as local time; we
    // append a "Z" to make it UTC for the audit-log semantics that
    // the G3 primitive expects. Operator can override by typing the
    // ISO string into the URL hash directly.
    if (!value) return '';
    // Accept already-ISO strings unchanged.
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2})?$/.test(value)) {
      // Append :00 + Z if not already specified.
      if (!/:\d{2}(Z|[+-]\d{2}:\d{2})?$/.test(value)) {
        return value + ':00Z';
      }
      if (!/(Z|[+-]\d{2}:\d{2})$/.test(value)) {
        return value + 'Z';
      }
      return value;
    }
    return '';
  }

  function t(key, fallback) {
    if (typeof window.t === 'function') {
      try { return window.t(key) || fallback; } catch (_) { return fallback; }
    }
    return fallback;
  }

  function updateState(iso) {
    var el = $('time-travel-state');
    if (!el) return;
    if (iso) {
      el.textContent = t('graph.timetravel.viewing_label', 'Viewing: ') + iso;
    } else {
      el.textContent = t('graph.timetravel.now_label', 'Viewing: NOW');
    }
  }

  function applyFromInput() {
    var input = $('time-travel-input');
    if (!input) return;
    var iso = fromInputValue(input.value);
    if (!iso) {
      // Soft fail — keep the now state.
      writeHashIso('');
      updateState('');
      window.dispatchEvent(new CustomEvent(EVENT_CLEAR));
      return;
    }
    writeHashIso(iso);
    updateState(iso);
    window.dispatchEvent(
      new CustomEvent(EVENT_SET, { detail: { iso: iso } })
    );
  }

  function clearTimeTravel() {
    var input = $('time-travel-input');
    if (input) input.value = '';
    writeHashIso('');
    updateState('');
    window.dispatchEvent(new CustomEvent(EVENT_CLEAR));
  }

  function syncFromHash() {
    var iso = readHashIso();
    var input = $('time-travel-input');
    if (input) input.value = toInputValue(iso);
    updateState(iso);
    if (iso) {
      window.dispatchEvent(
        new CustomEvent(EVENT_SET, { detail: { iso: iso } })
      );
    } else {
      window.dispatchEvent(new CustomEvent(EVENT_CLEAR));
    }
  }

  function wire() {
    var apply = $('time-travel-apply');
    var now = $('time-travel-now');
    if (apply) apply.addEventListener('click', applyFromInput);
    if (now) now.addEventListener('click', clearTimeTravel);
    window.addEventListener('hashchange', syncFromHash);
    // Initial sync from URL.
    syncFromHash();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }

  // Expose for tests and downstream code.
  window.JAMES_TimeTravel = {
    readHashIso: readHashIso,
    writeHashIso: writeHashIso,
    toInputValue: toInputValue,
    fromInputValue: fromInputValue,
    apply: applyFromInput,
    clear: clearTimeTravel,
    EVENT_SET: EVENT_SET,
    EVENT_CLEAR: EVENT_CLEAR
  };
})();
