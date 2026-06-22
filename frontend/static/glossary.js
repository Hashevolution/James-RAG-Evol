/* PROJECT JAMES — universal glossary tooltip + page search (P4.4).
 *
 * Two responsibilities:
 *
 *   1. On the `/glossary` page (when present) — provide a search box
 *      that hides non-matching entries on the fly.
 *
 *   2. On ANY page — scan the DOM for elements carrying a
 *      `data-glossary="<term-slug>"` attribute and attach a hover
 *      tooltip that surfaces the corresponding glossary entry.
 *      The tooltip floats above the page (single shared div); no
 *      per-element node creation.
 *
 * Plain ES5 — same convention as the rest of frontend/static/.
 */
(function () {
  'use strict';

  /* The canonical glossary content used by the floating tooltip on
   * every page. Same term-slugs as the dt entries in
   * `frontend/glossary.html` — the page itself is the SoT for the
   * formatted Korean copy; this map is the JS-side cache so the
   * tooltip works WITHOUT loading the /glossary page first.
   *
   * Entries are intentionally short (1-2 sentences). Operators who
   * want the full explanation click through to /glossary.
   *
   * Per CLAUDE.md rule #1 — domain-agnostic. Vertical-pack-specific
   * terms (e.g. legal "force majeure", medical "ICD-10") would land
   * in pack-side glossaries post-LOI, not here.
   */
  var GLOSSARY = {
    'rag': '질문에 답할 때 LLM 의 기억만 쓰지 않고 사내 문서를 먼저 검색한 뒤 그 결과를 근거로 답을 만드는 방식.',
    'graph-rag': '단순 문서 검색에 더해 온톨로지 그래프 (개념 간 관계망) 를 통해 답을 찾는 방식. 여러 문서의 정보를 연결.',
    'entity': '시스템이 알고 있는 한 개의 "것" — 사람 / 조직 / 개념 / 문서 등.',
    'relation': '엔티티들 사이의 연결. 예: "앤스로픽 ─CEO─ 다리오 아모데이".',
    'ontology': '엔티티 종류 + 관계 종류의 정의 체계.',
    'embedding': '텍스트를 숫자 벡터로 변환한 것. 의미 기반 검색에 사용.',
    'audit-log': '시스템의 모든 동작 기록. 누가 언제 무엇을 했는지 전부 저장 (위조 불가능).',
    'trace-id': '한 번의 질문/답변 흐름을 고유하게 식별하는 ID.',
    'replay': '과거 어떤 시점의 시스템 상태를 바이트 단위로 똑같이 재구성하는 기능.',
    'time-travel': '관리자 → 그래프 페이지에서 시점 선택 → 그 시점 상태를 보거나 되돌리는 기능.',
    'supersede': '예: "휴가 정책 v3 가 v2 를 supersede" = 새 버전이 이전을 대체. 이전 버전은 보존됨.',
    'cascade': '문서 삭제 시 그 문서를 근거로 한 다른 정보들을 자동으로 비활성화하는 동작.',
    'abstention': '시스템이 답을 모를 때 "정보가 없습니다" 라고 솔직하게 답하는 것.',
    'hallucination': 'LLM 이 사실이 아닌 내용을 그럴듯하게 만들어내는 현상.',
    'citation': '답변에 어떤 문서의 어느 부분을 사용했는지 출처를 함께 표시.',
    'path-coverage': '질문 답에 필요한 실제 근거 문서를 시스템이 얼마나 찾았는지 비율.',
    'rbac': '사용자 역할에 따라 무엇을 볼 수 있는지 결정 (역할 기반 접근 제어).',
    'abac': '역할 + 문서 속성 조합으로 접근 결정 (속성 기반 접근 제어).',
    'oidc': '회사 SSO 와 JAMES 를 연동하는 표준. JAMES 가 비밀번호를 직접 받지 않음.',
    'approval-evidence': '변경 승인 시 운영자 신원을 암호학적으로 기록한 정보. 사후 위조 불가능.',
    'csp': '브라우저가 어떤 스크립트/스타일을 실행할 수 있는지 제한하는 보안 정책.',
    'tenant': '한 JAMES 인스턴스에 여러 고객사가 있을 때 각 고객사.',
    'change-request': '직원이 정보 수정을 제안한 "Pending" 상태의 변경. 운영자 승인 전까지 미적용.',
    'rollback': '잘못된 변경을 되돌리는 동작. "최근 변경 되돌리기" + "특정 시점으로 복원" 두 가지.',
    'contradiction-arbiter': '새 정보가 기존과 충돌할 때 4 가지 규칙으로 결정론적 처리.',
    'reasoning-trace': '한 질문/답변에서 시스템이 거친 단계들의 기록. 추론 흐름 보기 페이지에서 시각화.'
  };

  function $(id) { return document.getElementById(id); }

  function escapeHtml(s) {
    if (s === null || typeof s === 'undefined') return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /* ── universal floating tooltip ──────────────────────────── */

  var tooltipEl = null;
  var hideTimer = null;
  var activeTrigger = null;

  function ensureTooltip() {
    if (tooltipEl) return tooltipEl;
    tooltipEl = document.createElement('div');
    tooltipEl.className = 'glossary-tooltip';
    tooltipEl.setAttribute('role', 'tooltip');
    tooltipEl.setAttribute('data-shown', 'false');
    document.body.appendChild(tooltipEl);
    return tooltipEl;
  }

  function showTooltip(trigger) {
    var term = trigger.getAttribute('data-glossary');
    if (!term) return;
    var def = GLOSSARY[term];
    if (!def) return;
    if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
    activeTrigger = trigger;
    var tip = ensureTooltip();
    tip.innerHTML =
      '<span class="tooltip-term">' + escapeHtml(term.replace(/-/g, ' ')) +
      '</span>' +
      '<span>' + escapeHtml(def) + '</span>' +
      '<a class="tooltip-link" href="/#glossary">전체 용어집 →</a>';
    // Position next to the trigger.
    var rect = trigger.getBoundingClientRect();
    var top = rect.bottom + window.scrollY + 6;
    var left = rect.left + window.scrollX;
    // Keep within viewport horizontally
    var max = window.innerWidth + window.scrollX - 340;
    if (left > max) left = max;
    if (left < 8) left = 8;
    tip.style.top = top + 'px';
    tip.style.left = left + 'px';
    tip.setAttribute('data-shown', 'true');
  }

  function scheduleHide() {
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(function () {
      if (tooltipEl) tooltipEl.setAttribute('data-shown', 'false');
      activeTrigger = null;
    }, 150);
  }

  function wireTooltips() {
    // Use event delegation so future-added [data-glossary] elements
    // (e.g. dynamically rendered) also get the tooltip without
    // re-wiring.
    document.addEventListener('mouseover', function (ev) {
      var el = ev.target;
      while (el && el !== document.body) {
        if (el.hasAttribute && el.hasAttribute('data-glossary')) {
          showTooltip(el);
          return;
        }
        el = el.parentNode;
      }
    }, true);
    document.addEventListener('mouseout', function (ev) {
      var el = ev.target;
      while (el && el !== document.body) {
        if (el.hasAttribute && el.hasAttribute('data-glossary')) {
          scheduleHide();
          return;
        }
        el = el.parentNode;
      }
    }, true);
    // Keyboard focus also shows the tooltip (a11y).
    document.addEventListener('focusin', function (ev) {
      var el = ev.target;
      if (el && el.hasAttribute && el.hasAttribute('data-glossary')) {
        showTooltip(el);
      }
    });
    document.addEventListener('focusout', function (ev) {
      var el = ev.target;
      if (el && el.hasAttribute && el.hasAttribute('data-glossary')) {
        scheduleHide();
      }
    });
    // Esc dismisses.
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && tooltipEl) {
        tooltipEl.setAttribute('data-shown', 'false');
      }
    });
  }

  /* ── /glossary page — live search ────────────────────────── */

  function wireSearch() {
    var input = $('glossary-search-input');
    var noResults = $('glossary-no-results');
    if (!input) return;  // not on the glossary page

    function filter(query) {
      var q = (query || '').trim().toLowerCase();
      var entries = document.querySelectorAll('.glossary-entry');
      var visible = 0;
      for (var i = 0; i < entries.length; i++) {
        var el = entries[i];
        var dt = el.querySelector('dt');
        var dd = el.querySelector('dd');
        var text = ((dt && dt.textContent) || '') + ' ' +
                   ((dd && dd.textContent) || '');
        var slug = el.getAttribute('data-term') || '';
        var match = !q ||
                    text.toLowerCase().indexOf(q) !== -1 ||
                    slug.toLowerCase().indexOf(q) !== -1;
        if (match) {
          el.style.display = '';
          visible++;
        } else {
          el.style.display = 'none';
        }
      }
      // Hide empty category sections + show "no results" hint.
      var sections = document.querySelectorAll('.glossary-section');
      for (var s = 0; s < sections.length; s++) {
        var anyVisible = sections[s].querySelector(
          '.glossary-entry:not([style*="display: none"])');
        sections[s].style.display = anyVisible ? '' : 'none';
      }
      if (noResults) {
        if (visible === 0 && q) {
          noResults.removeAttribute('hidden');
        } else {
          noResults.setAttribute('hidden', 'hidden');
        }
      }
    }

    input.addEventListener('input', function () {
      filter(input.value);
    });

    // Deep-link via URL hash to a specific term (#trace-id etc.).
    var hash = (window.location.hash || '').replace('#', '');
    if (hash) {
      input.value = hash.replace(/-/g, ' ');
      filter(input.value);
      var el = document.querySelector(
        '.glossary-entry[data-term="' + hash + '"]');
      if (el) {
        try { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
        catch (_) {}
        el.focus && el.focus();
      }
    }
  }

  function init() {
    wireTooltips();
    wireSearch();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose for tests + downstream code (admin pages that want to
  // dynamically annotate new content).
  window.JAMES_Glossary = {
    GLOSSARY: GLOSSARY,
    showTooltip: showTooltip,
    annotate: function (el, term) {
      if (el && term && GLOSSARY[term]) {
        el.setAttribute('data-glossary', term);
      }
    }
  };
})();
