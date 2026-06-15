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
    // W5: restore last-selected sidebar mode (default = upload).
    try {
      var saved = localStorage.getItem('james_sidebar_mode');
      if (saved && saved !== 'upload') {
        switchSidebarMode(saved);
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
    var tog = sb.querySelector('.sidebar-toggle');
    var collapsed = sb.classList.toggle('collapsed');
    btn.classList.toggle('visible', collapsed);
    if (tog) tog.textContent = collapsed ? '▶' : '◀';

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

  /* W5: sidebar rail mode switcher.
     Public entry point — W6 will call this on drag-enter to flip the
     panel to "upload" so the user sees the drop zone even if they
     were browsing the recent / search modes.
     Selection persists across reloads via localStorage. */
  function switchSidebarMode(modeId) {
    if (!modeId) return;
    var rail = document.querySelectorAll('.sidebar-rail-item');
    var panels = document.querySelectorAll('.sidebar-panel-mode');
    var matched = false;
    rail.forEach(function (el) {
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
