/* PROJECT JAMES — modal accessibility helper.
 *
 * Wires every ``[role="dialog"]`` element on the page with three
 * behaviours that the WCAG 2.1 dialog pattern requires:
 *
 *   1. Focus moves INTO the modal when it becomes visible
 *      (first focusable child, or the dialog itself if none).
 *   2. Tab / Shift+Tab cycles WITHIN the modal — focus cannot
 *      escape to background page controls.
 *   3. Escape closes the topmost open modal (by clicking the
 *      .modal-btn.cancel button, which every JAMES modal has).
 *   4. Focus restores to whatever was focused before the modal
 *      opened, when the modal closes.
 *
 * No changes to existing open/close code are required — a
 * MutationObserver per modal watches the ``class`` / ``style``
 * attributes for visibility transitions. Modals just need the
 * right HTML attributes (role / aria-modal / aria-labelledby).
 *
 * Loaded from every full-page UI (index / admin / workspace /
 * graph). Self-contained; no globals other than the function
 * scope.
 */
(function () {
  'use strict';

  // Standard focusable selector list. ``offsetParent !== null`` is
  // a fast visibility check that also filters out display:none
  // descendants — important because JAMES modals show/hide whole
  // sub-forms (e.g. signup admin-username field only when admins
  // are auto-approved).
  var FOCUSABLE_SEL =
    'button:not([disabled]), [href], input:not([disabled]), ' +
    'select:not([disabled]), textarea:not([disabled]), ' +
    '[tabindex]:not([tabindex="-1"])';

  // modalEl → { prevFocus: HTMLElement | null }
  var tracked = new WeakMap();

  function focusables(modal) {
    var out = [];
    var list = modal.querySelectorAll(FOCUSABLE_SEL);
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (el.offsetParent !== null) out.push(el);
    }
    return out;
  }

  function isVisible(modal) {
    // Two visibility conventions exist in this codebase:
    //   (a) class="modal-overlay hidden"  — CSS rule sets display:none
    //   (b) inline style="display:none"   — admin's older modals
    // Falling back to getComputedStyle catches both without us
    // needing to know which one a given modal uses.
    if (modal.classList.contains('hidden')) return false;
    var s = getComputedStyle(modal);
    return s.display !== 'none' && s.visibility !== 'hidden';
  }

  function topmostVisibleModal() {
    var nodes = document.querySelectorAll('[role="dialog"]');
    var top = null;
    var topZ = -Infinity;
    for (var i = 0; i < nodes.length; i++) {
      var m = nodes[i];
      if (!isVisible(m)) continue;
      var z = parseInt(getComputedStyle(m).zIndex, 10);
      if (isNaN(z)) z = 0;
      if (z >= topZ) { topZ = z; top = m; }
    }
    return top;
  }

  function trapTab(modal, e) {
    if (e.key !== 'Tab') return;
    var list = focusables(modal);
    if (list.length === 0) {
      // No focusable children — keep focus on the dialog itself.
      e.preventDefault();
      if (modal.getAttribute('tabindex') === null) {
        modal.setAttribute('tabindex', '-1');
      }
      modal.focus();
      return;
    }
    var first = list[0];
    var last  = list[list.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  function onShow(modal) {
    tracked.set(modal, { prevFocus: document.activeElement });
    // The visible-modal observer may fire synchronously during
    // a click handler; defer focus move so the click handler's
    // own focus call (if any) doesn't get fought over.
    setTimeout(function () {
      if (!isVisible(modal)) return;
      var list = focusables(modal);
      if (list.length > 0) {
        try { list[0].focus(); } catch (e) { /* ignore */ }
      } else {
        if (modal.getAttribute('tabindex') === null) {
          modal.setAttribute('tabindex', '-1');
        }
        try { modal.focus(); } catch (e) { /* ignore */ }
      }
    }, 0);
  }

  function onHide(modal) {
    var info = tracked.get(modal);
    if (info && info.prevFocus && document.body.contains(info.prevFocus)) {
      try { info.prevFocus.focus(); } catch (e) { /* ignore */ }
    }
    tracked.delete(modal);
  }

  function observeModal(modal) {
    var wasVisible = isVisible(modal);
    var obs = new MutationObserver(function () {
      var now = isVisible(modal);
      if (now && !wasVisible)      onShow(modal);
      else if (!now && wasVisible) onHide(modal);
      wasVisible = now;
    });
    obs.observe(modal, {
      attributes: true,
      attributeFilter: ['class', 'style'],
    });
    if (wasVisible) onShow(modal);
  }

  function fireEscClose() {
    var m = topmostVisibleModal();
    if (!m) return false;
    // Every JAMES modal has a Cancel button with class
    // ``modal-btn cancel``. Fire its click — that path runs the
    // page's existing closeFoo() function and any state cleanup.
    var btn = m.querySelector('.modal-btn.cancel')
           || m.querySelector('[data-modal-close]')
           || m.querySelector('button[onclick*="close" i]');
    if (btn) { btn.click(); return true; }
    return false;
  }

  function onKeydown(e) {
    if (e.key === 'Escape') {
      if (fireEscClose()) e.preventDefault();
      return;
    }
    var top = topmostVisibleModal();
    if (top && top.contains(document.activeElement)) {
      trapTab(top, e);
    }
  }

  function init() {
    document.addEventListener('keydown', onKeydown, true);
    var modals = document.querySelectorAll('[role="dialog"]');
    for (var i = 0; i < modals.length; i++) observeModal(modals[i]);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
