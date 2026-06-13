/* PROJECT JAMES — operator onboarding flow (Phase 4 P4.1).
 *
 * Drives the 5-step `frontend/onboarding.html` page:
 *
 *   1. Welcome
 *   2. Search
 *   3. Audit log
 *   4. Change review
 *   5. Time-travel restore
 *
 * Step navigation: ← Prev / Next → buttons + clickable progress dots
 * (going back to any visited step). State persistence: localStorage
 * key `james_onboarding_completed` set to "1" when the user clicks
 * "관리자 페이지로 →" on step 5 AND the "don't show again" checkbox
 * is checked. The admin page (P4.4 follow-up) exposes a "restart
 * onboarding" link that clears this key.
 *
 * Plain ES5 — same convention as the rest of `frontend/static/`
 * (time-travel.js / index-init.js etc.). Maximises enterprise
 * IT-locked browser compat.
 *
 * Per CLAUDE.md rule #1 — no domain framing. The 5 steps name the
 * generic operator surfaces (search / audit / review / time-travel);
 * vertical content (legal contract review / medical record audit /
 * etc.) lands post-LOI in Track D.
 */
(function () {
  'use strict';

  var TOTAL_STEPS = 5;
  var STORAGE_KEY = 'james_onboarding_completed';

  var currentStep = 1;

  function $(id) { return document.getElementById(id); }
  function $$(selector) {
    return Array.prototype.slice.call(document.querySelectorAll(selector));
  }

  function persistCompleted() {
    try {
      var cb = $('dont-show-again');
      if (cb && cb.checked) {
        window.localStorage.setItem(STORAGE_KEY, '1');
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    } catch (_) { /* localStorage blocked → silently skip */ }
  }

  function setStep(target) {
    if (target < 1) target = 1;
    if (target > TOTAL_STEPS) target = TOTAL_STEPS;
    currentStep = target;

    // section visibility + step dot state
    var steps = $$('.step');
    for (var i = 0; i < steps.length; i++) {
      var n = parseInt(steps[i].getAttribute('data-step'), 10);
      var active = (n === currentStep);
      if (active) {
        steps[i].removeAttribute('hidden');
        steps[i].classList.add('step-active');
      } else {
        steps[i].setAttribute('hidden', 'hidden');
        steps[i].classList.remove('step-active');
      }
    }

    var dots = $$('.step-dot');
    for (var d = 0; d < dots.length; d++) {
      var n2 = parseInt(dots[d].getAttribute('data-step'), 10);
      dots[d].removeAttribute('aria-current');
      if (n2 < currentStep) {
        dots[d].setAttribute('data-state', 'done');
      } else if (n2 === currentStep) {
        dots[d].setAttribute('data-state', 'active');
        dots[d].setAttribute('aria-current', 'step');
      } else {
        dots[d].setAttribute('data-state', 'pending');
      }
    }

    // navigation buttons + "don't show again" checkbox visibility
    var prev = $('onboarding-prev');
    var next = $('onboarding-next');
    var finish = $('onboarding-finish');
    var checkbox = $('onboarding-checkbox');

    if (prev) {
      prev.disabled = (currentStep <= 1);
    }
    if (currentStep < TOTAL_STEPS) {
      if (next) next.removeAttribute('hidden');
      if (finish) finish.setAttribute('hidden', 'hidden');
      if (checkbox) checkbox.setAttribute('hidden', 'hidden');
    } else {
      // final step — hide Next, show Finish + checkbox
      if (next) next.setAttribute('hidden', 'hidden');
      if (finish) finish.removeAttribute('hidden');
      if (checkbox) checkbox.removeAttribute('hidden');
    }

    // move focus to the section heading for screen-reader narration
    var heading = document.getElementById('step-' + currentStep + '-title');
    if (heading) {
      heading.setAttribute('tabindex', '-1');
      try { heading.focus(); } catch (_) { /* ignore focus errors */ }
    }

    // sync URL hash for deep-link / back-button support
    var hash = '#step=' + currentStep;
    try {
      window.history.replaceState(null, '', hash);
    } catch (_) {
      window.location.hash = hash;
    }
  }

  function readHashStep() {
    var hash = window.location.hash || '';
    var match = hash.match(/step=(\d+)/);
    if (!match) return 1;
    var n = parseInt(match[1], 10);
    if (isNaN(n) || n < 1 || n > TOTAL_STEPS) return 1;
    return n;
  }

  function wire() {
    var prev = $('onboarding-prev');
    var next = $('onboarding-next');
    var finish = $('onboarding-finish');

    if (prev) {
      prev.addEventListener('click', function () { setStep(currentStep - 1); });
    }
    if (next) {
      next.addEventListener('click', function () { setStep(currentStep + 1); });
    }
    if (finish) {
      finish.addEventListener('click', persistCompleted);
    }

    // progress-dot click → jump to step (only when already visited;
    // ARIA `aria-current` flips on navigation)
    var dots = $$('.step-dot');
    for (var i = 0; i < dots.length; i++) {
      (function (dot) {
        dot.addEventListener('click', function () {
          var n = parseInt(dot.getAttribute('data-step'), 10);
          if (!isNaN(n)) setStep(n);
        });
        dot.style.cursor = 'pointer';
      })(dots[i]);
    }

    // keyboard: arrow keys advance / retreat steps (skip when an
    // input field has focus, so input typing isn't hijacked)
    document.addEventListener('keydown', function (ev) {
      var ae = document.activeElement;
      if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA'))
        return;
      if (ev.key === 'ArrowRight' || ev.key === 'PageDown') {
        setStep(currentStep + 1);
      } else if (ev.key === 'ArrowLeft' || ev.key === 'PageUp') {
        setStep(currentStep - 1);
      }
    });

    window.addEventListener('hashchange', function () {
      var n = readHashStep();
      if (n !== currentStep) setStep(n);
    });

    // initial render: respect URL hash for deep-link reopening
    setStep(readHashStep());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }

  // Expose for tests + downstream code (admin "restart onboarding"
  // link in P4.4).
  window.JAMES_Onboarding = {
    setStep: setStep,
    currentStep: function () { return currentStep; },
    isCompleted: function () {
      try {
        return window.localStorage.getItem(STORAGE_KEY) === '1';
      } catch (_) { return false; }
    },
    clearCompleted: function () {
      try { window.localStorage.removeItem(STORAGE_KEY); }
      catch (_) { /* ignore */ }
    },
    STORAGE_KEY: STORAGE_KEY,
    TOTAL_STEPS: TOTAL_STEPS
  };
})();
