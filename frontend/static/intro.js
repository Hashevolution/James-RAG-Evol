/* intro.js — SEKOS intro front door (v0.6.1).
 *
 * Responsibilities (kept narrow — step nav is onboarding.js, term search
 * is glossary.js):
 *   1. Tab switching between the 소개 / 사용안내 / 용어집 sections,
 *      synced to the URL hash (#intro / #tour / #glossary) so the old
 *      /onboarding → /#tour and /glossary → /#glossary redirects land on
 *      the right section.
 *   2. First-visit gate: when this page is served at "/" (the front door,
 *      from PR-intro-2 onward), a returning visitor who has already seen
 *      the intro is bounced straight to /chat — daily users get zero
 *      friction. At the temporary /intro route (PR-intro-1) the guard is
 *      dormant (pathname !== "/").
 *   3. Mark the intro as seen when the operator clicks a "챗 시작" CTA.
 *
 * localStorage flag: `james_intro_seen` ('1' once seen). Unifies the
 * legacy `james_onboarding_completed` flag (migrated in PR-intro-2).
 */
(function () {
  'use strict';

  var SEEN_KEY = 'james_intro_seen';
  // PR-intro-2 will serve chat here; until then chat is still at "/".
  var CHAT_PATH = '/chat';

  function seen() {
    try { return localStorage.getItem(SEEN_KEY) === '1'; } catch (_) { return false; }
  }
  function markSeen() {
    try { localStorage.setItem(SEEN_KEY, '1'); } catch (_) {}
  }

  // ── 2. front-door auto-skip (only when this IS the front door) ──
  // At "/intro" (isolated-review route) pathname !== "/", so this is a
  // no-op; it activates automatically once the page is served at "/".
  if (window.location.pathname === '/' && seen()) {
    window.location.replace(CHAT_PATH);
    return;
  }

  // ── 1. tab switching ──
  function showSection(name) {
    var tabs = document.querySelectorAll('[data-intro-tab]');
    var secs = document.querySelectorAll('[data-intro-section]');
    var matched = false;
    secs.forEach(function (s) {
      var on = s.getAttribute('data-intro-section') === name;
      if (on) { s.removeAttribute('hidden'); matched = true; }
      else { s.setAttribute('hidden', ''); }
      s.classList.toggle('intro-section-active', on);
    });
    tabs.forEach(function (t) {
      t.classList.toggle('intro-tab-active',
        t.getAttribute('data-intro-tab') === name);
    });
    return matched;
  }

  function syncFromHash() {
    var h = (window.location.hash || '').replace('#', '');
    if (h === 'tour' || h === 'glossary' || h === 'intro') {
      showSection(h);
    } else {
      showSection('intro');
    }
  }

  function bind() {
    document.querySelectorAll('[data-intro-tab]').forEach(function (t) {
      t.addEventListener('click', function () {
        var name = t.getAttribute('data-intro-tab');
        showSection(name);
        // update hash without a jump
        if (history.replaceState) history.replaceState(null, '', '#' + name);
        else window.location.hash = name;
      });
    });
    // CTA / skip → mark seen so next "/" visit skips straight to chat
    document.querySelectorAll('.intro-cta, [data-i18n="intro.skip_to_chat"]')
      .forEach(function (a) { a.addEventListener('click', markSeen); });

    window.addEventListener('hashchange', syncFromHash);
    syncFromHash();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
