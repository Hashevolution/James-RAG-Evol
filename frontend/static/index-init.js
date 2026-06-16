/* PROJECT JAMES — chat page (/) inline-script extraction.
 *
 * Moved out of frontend/index.html as part of the v0.5 UI #4
 * CSP-hardening pass (`docs/reviews/v0.5-ui-1-accessibility-pass.md`
 * §3.2 follow-up; handover doc task #5/#8 hybrid).
 *
 * Removing the page's only `<script>` inline block means the chat
 * page's CSP can drop `script-src 'unsafe-inline'` — the production
 * CSP header can use `script-src 'self'` without breaking the
 * sidebar / history-restore wiring.
 *
 * No behaviour change. Functions are exposed on `window` so existing
 * call sites in `chat.js` / `upload.js` (which already reference
 * `toggleSidebar` and `switchSidebarMode` by name) keep working.
 *
 * Load order in index.html:
 *   i18n.js → auth.js → chat.js → upload.js → a11y-modal.js (defer)
 *   → index-init.js (this file, regular — must run AFTER the others
 *                    define `restoreHistory`, `loadMineSidebar`,
 *                    `loadSessionList`).
 */

(function () {
  'use strict';

  /* v0.6.1 mobile fix (2026-06-15): on phone-sized viewports the
   * sidebar is `position:fixed; width:88vw` overlay (mobile.css §
   * "사이드바"). Default-open used to make the chat surface
   * inaccessible on first load; the operator caught it on Galaxy
   * Tailscale tunnel. Default-collapsed on phones, respect operator
   * choice if they explicitly toggled in a previous session. */
  function _isPhoneViewport() {
    try {
      return window.matchMedia &&
             window.matchMedia('(max-width: 768px)').matches;
    } catch (_) { return false; }
  }

  window.addEventListener('DOMContentLoaded', function () {
    if (typeof restoreHistory === 'function') {
      restoreHistory();
    }
    // W5: restore last-selected sidebar mode. v0.6.1 (2026-06-15) —
    // the Claude-style reorg flips the default from "upload" to
    // "sessions" so an operator opening a fresh session lands on chat
    // history (the Claude analogue), not the upload drop zone.
    try {
      var saved = localStorage.getItem('james_sidebar_mode');
      if (saved && saved !== 'sessions') {
        switchSidebarMode(saved);
      } else if (!saved) {
        // Apply the new default explicitly so the rail-tab highlight is
        // in sync with the panel-mode .active class set in HTML.
        switchSidebarMode('sessions');
      }
    } catch (_) {}

    // v0.6.1 — phone-viewport default-collapsed.
    var sb = document.getElementById('sidebar');
    var openBtn = document.getElementById('sidebar-open-btn');
    if (sb && _isPhoneViewport()) {
      var pref = '';
      try { pref = localStorage.getItem('james_sidebar_open_mobile') || ''; }
      catch (_) {}
      // Operator hasn't expressed a preference → collapse so the chat
      // surface is reachable on first paint.
      if (pref !== 'open') {
        sb.classList.add('collapsed');
        if (openBtn) openBtn.classList.add('visible');
      }
    }
  });

  function toggleSidebar() {
    var sb = document.getElementById('sidebar');
    var btn = document.getElementById('sidebar-open-btn');
    if (!sb || !btn) return;
    var collapsed = sb.classList.toggle('collapsed');
    btn.classList.toggle('visible', collapsed);
    // v0.6.1 v4 (2026-06-16) — toggle text override (▶/◀) was removed;
    // the toggle now hosts an inline ☰ SVG. Replacing textContent
    // would wipe the SVG. The button's icon stays constant; only the
    // sidebar's transform state changes.

    // v0.6.1 mobile fix — sync the backdrop overlay and persist the
    // operator's choice so we don't fight them on the next reload.
    var bd = document.getElementById('sidebar-backdrop');
    if (bd) bd.classList.toggle('show', !collapsed && _isPhoneViewport());
    try {
      if (_isPhoneViewport()) {
        localStorage.setItem('james_sidebar_open_mobile',
                              collapsed ? 'closed' : 'open');
      }
    } catch (_) {}
  }

  /* v0.6.1 v4 (2026-06-16) — phone swipe gesture for the sidebar.
   *
   * Operator request: a left/right swipe should toggle the sidebar
   * the way Claude / Gmail / most modern mobile apps do it. This
   * captures touchstart / touchend at document scope and only acts
   * on the phone viewport (≤ 768px).
   *
   *   closed → open  : swipe-right that STARTED in the left edge
   *                    zone (≤ EDGE_PX). The narrow zone keeps the
   *                    gesture from competing with horizontal
   *                    scrolling inside chat content.
   *   open  → close  : swipe-left that started inside the open
   *                    sidebar OR on the backdrop overlay. Anywhere
   *                    is fair game because the backdrop covers the
   *                    full viewport.
   *
   * Vertical-dominant gestures (|dy| > VERT_GUARD) are ignored so
   * normal up/down scrolling never triggers a toggle. A maximum
   * duration (DURATION_MAX) drops very slow gestures the user
   * probably abandoned mid-scroll.
   */
  function _setupSwipeToggle() {
    var EDGE_PX = 28;          // closed-state left-edge activation zone
    var DELTA_X_MIN = 55;      // minimum horizontal travel to fire
    var VERT_GUARD = 60;       // |dy| above this = vertical scroll
    var DURATION_MAX = 700;    // ms — drop very slow drags

    var sx = 0, sy = 0, st = 0;
    var startedFromEdge = false;
    var startedInSidebar = false;
    var active = false;

    function onStart(e) {
      if (!_isPhoneViewport()) return;
      var tp = e.touches && e.touches[0];
      if (!tp) return;
      sx = tp.clientX;
      sy = tp.clientY;
      st = Date.now();
      var sb = document.getElementById('sidebar');
      var isOpen = sb && !sb.classList.contains('collapsed');

      // Don't hijack swipes that started on form controls or scroll
      // containers where the touch is genuinely a scroll/select.
      var tgt = e.target;
      if (tgt && tgt.closest) {
        if (tgt.closest('input, textarea, select, [contenteditable]')) {
          active = false;
          return;
        }
      }

      startedFromEdge = !isOpen && sx <= EDGE_PX;
      startedInSidebar = isOpen && tgt && tgt.closest
        && (tgt.closest('#sidebar') || tgt.closest('#sidebar-backdrop'));
      active = startedFromEdge || !!startedInSidebar;
    }

    function onEnd(e) {
      if (!active) return;
      active = false;
      var tp = (e.changedTouches && e.changedTouches[0])
            || (e.touches && e.touches[0]);
      if (!tp) return;
      var dx = tp.clientX - sx;
      var dy = tp.clientY - sy;
      var dt = Date.now() - st;
      if (dt > DURATION_MAX) return;
      if (Math.abs(dy) > VERT_GUARD) return;
      if (Math.abs(dx) < DELTA_X_MIN) return;
      var sb = document.getElementById('sidebar');
      if (!sb) return;
      var isOpen = !sb.classList.contains('collapsed');

      if (!isOpen && startedFromEdge && dx > 0) {
        // swipe-right from left edge → open
        toggleSidebar();
      } else if (isOpen && startedInSidebar && dx < 0) {
        // swipe-left inside the open sidebar / backdrop → close
        toggleSidebar();
      }
    }

    // Passive listeners — we only TOGGLE on end, never preventDefault,
    // so we never block native scroll. The browser scroll behaviour
    // stays intact.
    document.addEventListener('touchstart', onStart, { passive: true });
    document.addEventListener('touchend', onEnd, { passive: true });
    // touchcancel mirrors touchend semantics for our case (e.g. when
    // the gesture is interrupted by a phone notification overlay).
    document.addEventListener('touchcancel', onEnd, { passive: true });
  }

  // Wire the swipe handler once on DOMContentLoaded (above) — the
  // listeners are document-scoped so they survive sidebar mutation.
  window.addEventListener('DOMContentLoaded', _setupSwipeToggle);

  /* W5: sidebar rail mode switcher.
     Public entry point — W6 will call this on drag-enter to flip the
     panel to "upload" so the user sees the drop zone even if they
     were browsing the recent / search modes.
     Selection persists across reloads via localStorage. */
  function switchSidebarMode(modeId) {
    if (!modeId) return;
    // v0.6.1 — both the legacy .sidebar-rail-item AND the new
    // .sidebar-tab carry data-mode. Toggle .active on either so the
    // Claude-style reorg layout AND any leftover rail element stay in
    // sync without a separate code path.
    var modeEls = document.querySelectorAll(
      '.sidebar-rail-item[data-mode], .sidebar-tab[data-mode]'
    );
    var panels = document.querySelectorAll('.sidebar-panel-mode');
    var matched = false;
    modeEls.forEach(function (el) {
      var on = el.dataset.mode === modeId;
      el.classList.toggle('active', on);
      if (on) matched = true;
    });
    if (!matched) return;  // unknown mode → ignore
    panels.forEach(function (el) {
      el.classList.toggle('active', el.dataset.mode === modeId);
    });
    // W8-B: lazy-load the "내 자료" list when switching into recent.
    if (modeId === 'recent' && typeof loadMineSidebar === 'function') {
      loadMineSidebar();
    }
    // P3-4 → sidebar: lazy-load the "대화 이력" list when switching
    // into sessions (was: floating panel toggle).
    if (modeId === 'sessions' && typeof loadSessionList === 'function') {
      loadSessionList();
    }
    // v0.6.1 v5 (2026-06-16) — search mode: focus the search input
    // + ensure session cache is fresh (so the client-side filter has
    // something to filter). primeSidebarSearch is exposed by chat.js.
    if (modeId === 'search' && typeof primeSidebarSearch === 'function') {
      primeSidebarSearch();
    }
    // Update the panel header title from the matching rail tip so
    // i18n stays in one place.
    var titleEl = document.getElementById('sidebar-title');
    var ral = document.querySelector(
      '.sidebar-rail-item[data-mode="' + modeId + '"] .sidebar-rail-tip'
    );
    if (titleEl && ral) {
      titleEl.innerHTML = '▸ <span>' + ral.textContent.trim() + '</span>';
    }
    // If collapsed, opening the rail also expands the sidebar so the
    // user sees the new mode's content — otherwise the click feels
    // dead.
    var sb = document.getElementById('sidebar');
    if (sb && sb.classList.contains('collapsed')) {
      toggleSidebar();
    }
    try { localStorage.setItem('james_sidebar_mode', modeId); } catch (_) {}
  }

  // Expose for existing call sites (chat.js / upload.js / data-action
  // delegation) that reference these globals by name.
  window.toggleSidebar = toggleSidebar;
  window.switchSidebarMode = switchSidebarMode;
})();
