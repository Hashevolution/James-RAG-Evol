/* graph-tabs.js — reasoning-graph hub tabs (v0.6.1).
 *
 * Folds /admin/reasoning-flow (#flow) and /admin/knowledge-rollback
 * (#rollback) into /admin/graph as tabs. The graph tab is default and
 * keeps its Time-Travel panel (which drives the live 3D view).
 *
 * Hash policy — the graph's Time-Travel deep-link uses `#t=<ISO>`, so we
 * must NOT clobber it: only `#flow` / `#rollback` select the other tabs;
 * ANY other hash (incl. `#t=...` or empty) resolves to the graph tab.
 *
 * 3D resize — a 3d-force-graph inside a `display:none` container renders
 * at 0×0. When the user returns to the graph tab we dispatch a window
 * resize so the force-graph re-fits its container.
 */
(function () {
  'use strict';

  var TABS = ['graph', 'flow', 'rollback'];

  function tabFromHash() {
    var h = window.location.hash || '';
    if (h.indexOf('#flow') === 0) return 'flow';
    if (h.indexOf('#rollback') === 0) return 'rollback';
    return 'graph';  // includes '', '#', and the time-travel '#t=...'
  }

  function show(name) {
    if (TABS.indexOf(name) === -1) name = 'graph';
    document.querySelectorAll('[data-graph-tab]').forEach(function (panel) {
      var on = panel.getAttribute('data-graph-tab') === name;
      if (on) panel.removeAttribute('hidden');
      else panel.setAttribute('hidden', '');
    });
    document.querySelectorAll('[data-graph-tab-btn]').forEach(function (btn) {
      btn.classList.toggle('graph-hub-tab-active',
        btn.getAttribute('data-graph-tab-btn') === name);
    });
    // Returning to the graph: the 3D canvas was display:none → re-fit it.
    if (name === 'graph') {
      try { window.dispatchEvent(new Event('resize')); } catch (_) {}
    }
  }

  function selectTab(name) {
    // Update the hash without disturbing the time-travel '#t=' deep-link:
    // graph tab clears only a tab-hash; flow/rollback set their own.
    var cur = window.location.hash || '';
    if (name === 'flow' || name === 'rollback') {
      if (history.replaceState) history.replaceState(null, '', '#' + name);
      else window.location.hash = name;
    } else if (cur.indexOf('#flow') === 0 || cur.indexOf('#rollback') === 0) {
      if (history.replaceState) history.replaceState(null, '', window.location.pathname + window.location.search);
      else window.location.hash = '';
    }
    show(name);
  }

  function bind() {
    document.querySelectorAll('[data-graph-tab-btn]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        selectTab(btn.getAttribute('data-graph-tab-btn'));
      });
    });
    window.addEventListener('hashchange', function () { show(tabFromHash()); });
    show(tabFromHash());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
