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
  var CHAT_PATH = '/chat';  // chat app (PR-intro-2 moved it off "/")

  function seen() {
    try {
      return localStorage.getItem(SEEN_KEY) === '1'
        // honour the legacy onboarding flag so users who finished the old
        // /onboarding flow are recognised without re-seeing the intro.
        || localStorage.getItem('james_onboarding_completed') === '1';
    } catch (_) { return false; }
  }
  function markSeen() {
    try { localStorage.setItem(SEEN_KEY, '1'); } catch (_) {}
  }

  // ── 2. front-door auto-skip (only when this IS the front door) ──
  // When served at "/", a returning visitor is bounced to /chat — UNLESS
  // they arrived with an explicit section hash (#tour / #glossary /
  // #intro), e.g. the /onboarding→/#tour and /glossary→/#glossary 301s,
  // or the admin "안내 / 용어집" links. Those must SHOW the section, not
  // skip. At the legacy /intro route (pathname !== "/") this is a no-op.
  var _h = (window.location.hash || '').replace('#', '');
  if (window.location.pathname === '/' && seen()
      && _h !== 'tour' && _h !== 'glossary' && _h !== 'intro') {
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

  // ── scroll-reveal (v0.6.1) ──
  // Fade-and-rise each content block as it scrolls into view. Pure
  // progressive enhancement: only adds the (initially-hidden) `.reveal`
  // class when IntersectionObserver exists, so a no-JS / old browser
  // never hides anything. Hidden tab sections (display:none) are still
  // observed — IO re-fires when a tab switch makes them visible.
  function setupReveal() {
    if (!('IntersectionObserver' in window)) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          e.target.classList.add('is-visible');
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });

    var sel = '.intro-card, .intro-moat, .glossary-section, .step';
    var cardN = 0;
    document.querySelectorAll(sel).forEach(function (el) {
      if (el.classList.contains('reveal')) return;
      el.classList.add('reveal');
      // gentle stagger across a row of cards
      if (el.classList.contains('intro-card')) {
        el.style.transitionDelay = ((cardN % 6) * 70) + 'ms';
        cardN++;
      }
      io.observe(el);
    });
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
    setupReveal();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
