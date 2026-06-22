/* PROJECT JAMES — reasoning flow visualization (Phase 4 P4.3).
 *
 * Drives the reasoning-flow tab embedded in /admin/graph (#flow). Three responsibilities:
 *
 *   1. List recent traces (GET /admin/audit/recent-traces)
 *   2. Load a specific trace (GET /admin/trace/{trace_id})
 *   3. Render the 3-swimlane visualization (RETRIEVE / EXPAND / VERIFY)
 *      with clickable stage cards + detail panel on click
 *
 * The STAGE_META map mirrors chat.js exactly (same icons, labels,
 * phases) so the auditor's view + the live chat view tell the same
 * story. Domain-agnostic per CLAUDE.md rule #1.
 */
(function () {
  'use strict';

  /* Stage taxonomy — same shape as chat.js STAGE_META + TT.c, with
   * one extra "description" field per stage explaining what it does
   * in plain Korean. Surface the description in the detail panel. */
  var STAGE_META = {
    auth:        { icon: '', label: '권한 확인',     phase: 'retrieve',
                   desc: '요청자가 이 질문을 할 권한이 있는지 확인합니다.' },
    risky_coding_blocked: { icon: '', label: '위험 명령 차단', phase: 'retrieve',
                            desc: '위험한 명령이 감지되어 차단되었습니다.' },
    retrieve:    { icon: '', label: '자료 검색',     phase: 'retrieve',
                   desc: '사내 문서에서 질문과 관련된 자료를 찾습니다.' },
    rerank:      { icon: '', label: '재정렬',        phase: 'retrieve',
                   desc: '찾은 자료를 질문과의 관련성 순으로 다시 정렬합니다.' },
    graph:       { icon: '', label: '관계 그래프',   phase: 'expand',
                   desc: '온톨로지 그래프에서 관련된 엔티티들의 관계를 탐색합니다.' },
    tool:        { icon: '', label: '도구 호출',     phase: 'expand',
                   desc: '필요한 외부 도구 (계산기, 검색, 코드 실행 등) 를 호출합니다.' },
    coding_route: { icon: '', label: '코딩 라우팅',  phase: 'expand',
                    desc: '코딩 질문을 적절한 LLM 으로 라우팅합니다.' },
    coding_llm_pick: { icon: '', label: '모델 선택', phase: 'expand',
                       desc: '쿼리 복잡도에 맞는 LLM 을 선택합니다.' },
    coding_user_pick: { icon: '', label: '사용자 모델 선택', phase: 'expand',
                        desc: '사용자가 지정한 LLM 으로 라우팅합니다.' },
    coding_done: { icon: '',  label: '코딩 완료',     phase: 'verify',
                   desc: '코딩 응답 생성이 완료되었습니다.' },
    coding_llm_error: { icon: '', label: '코더 오류', phase: 'verify',
                        desc: 'LLM 호출 중 오류가 발생했습니다.' },
    coding_fallback_done: { icon: '',  label: 'Fallback 완료', phase: 'verify',
                            desc: '주 모델 실패 후 대체 모델로 응답을 생성했습니다.' },
    coding_fallback_error: { icon: '', label: 'Fallback 오류', phase: 'verify',
                             desc: '대체 모델도 실패했습니다.' },
    coding_user_pick_done: { icon: '', label: '사용자 모델 완료', phase: 'verify',
                             desc: '사용자가 선택한 LLM 으로 응답 생성 완료.' },
    coding_user_pick_error: { icon: '', label: '사용자 모델 오류', phase: 'verify',
                              desc: '사용자가 선택한 LLM 호출 실패.' },
    answer:      { icon: '', label: '답변 생성',     phase: 'verify',
                   desc: '찾은 자료를 바탕으로 LLM 이 답변을 생성합니다.' },
    complete:    { icon: '', label: '완료',          phase: 'verify',
                   desc: '추론 과정이 모두 완료되었습니다.' }
  };

  /* User-friendly field labels (Korean) for the detail panel.
   * Anything not in this map shows the raw field name. */
  var FIELD_LABELS = {
    ts_ns:           '시각',
    duration_ms:     '소요 시간',
    sources_count:   '찾은 자료 수',
    sources:         '자료 목록',
    rerank_top_k:    '재정렬 후 N',
    graph_paths_count: '그래프 경로 수',
    blocked:         '차단 여부',
    tokens_in:       '입력 토큰',
    tokens_out:      '출력 토큰',
    model:           '사용 모델',
    elapsed_sec:     '경과 시간 (초)',
    answer_len:      '답변 길이',
    error:           '오류',
    user_role:       '사용자 역할',
    abstained:       '회피 여부'
  };

  var currentTraceStages = [];

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

  function getCreds() {
    var apiKey = (window.localStorage &&
                  window.localStorage.getItem('james_api_key')) || '';
    var token = (window.localStorage &&
                 window.localStorage.getItem('james_token')) || '';
    return { apiKey: apiKey, token: token };
  }

  function request(method, url, onOk, onError) {
    var creds = getCreds();
    if (!creds.apiKey) {
      onError(401, { detail: t('flow.err.admin_required',
                                'admin login required') });
      return;
    }
    var sep = url.indexOf('?') === -1 ? '?' : '&';
    var fullUrl = url + sep + 'api_key=' + encodeURIComponent(creds.apiKey);

    var xhr = new XMLHttpRequest();
    xhr.open(method, fullUrl, true);
    xhr.setRequestHeader('Accept', 'application/json');
    if (creds.token) {
      xhr.setRequestHeader('Authorization', 'Bearer ' + creds.token);
    }
    xhr.onload = function () {
      var parsed = null;
      try { parsed = JSON.parse(xhr.responseText); } catch (_) {}
      if (xhr.status >= 200 && xhr.status < 300) {
        onOk(parsed || {});
      } else {
        onError(xhr.status, parsed);
      }
    };
    xhr.onerror = function () {
      onError(0, { detail: t('flow.err.network', 'network error') });
    };
    xhr.send();
  }

  /* ── trace list ──────────────────────────────────────────── */

  function loadRecentTraces() {
    var list = $('flow-recent-list');
    if (!list) return;
    list.innerHTML = '<div class="loading">' +
      escapeHtml(t('flow.loading', '불러오는 중…')) + '</div>';

    request('GET', '/admin/audit/recent-traces?limit=20',
      function (body) {
        var rows = body.traces || [];
        if (rows.length === 0) {
          list.innerHTML = '<div class="empty-state">' +
            escapeHtml(t('flow.selector.empty',
              '최근 질문이 없습니다. trace_id 를 직접 입력해 보세요.')) +
            '</div>';
          return;
        }
        var html = '';
        for (var i = 0; i < rows.length; i++) {
          var r = rows[i];
          var when = r.first_ts_ns ?
            formatHmsFromNs(r.first_ts_ns) : '-';
          var q = r.question ? r.question :
                  ('(trace_id: ' + r.trace_id.substring(0, 12) + '…)');
          var meta = r.user ? ('by ' + r.user) : '';
          html += '<div class="recent-row" data-trace-id="' +
                  escapeHtml(r.trace_id) + '">' +
                  '<span class="row-time">' + escapeHtml(when) + '</span>' +
                  '<span class="row-q">' + escapeHtml(q) + '</span>' +
                  '<span class="row-meta">' + escapeHtml(meta) + '</span>' +
                  '<span class="row-stages">' +
                    escapeHtml(String(r.stage_count)) + ' 단계' +
                  '</span>' +
                  '</div>';
        }
        list.innerHTML = html;
        var rowsEls = list.querySelectorAll('.recent-row');
        for (var j = 0; j < rowsEls.length; j++) {
          (function (el) {
            el.addEventListener('click', function () {
              var tid = el.getAttribute('data-trace-id');
              if (tid) loadTrace(tid);
            });
          })(rowsEls[j]);
        }
      },
      function (status, parsed) {
        renderError(list, status, parsed);
      });
  }

  function formatHmsFromNs(ns) {
    var dt = new Date(ns / 1e6);
    var hh = ('0' + dt.getHours()).slice(-2);
    var mm = ('0' + dt.getMinutes()).slice(-2);
    var ss = ('0' + dt.getSeconds()).slice(-2);
    return hh + ':' + mm + ':' + ss;
  }

  /* ── trace load + visualization ─────────────────────────── */

  function loadTrace(traceId) {
    if (!traceId) return;
    var input = $('flow-trace-input');
    if (input) input.value = traceId;

    var error = $('flow-error');
    if (error) { error.setAttribute('hidden', 'hidden'); error.innerHTML = ''; }

    request('GET', '/admin/trace/' + encodeURIComponent(traceId),
      function (body) {
        var stages = body.stages || [];
        currentTraceStages = stages;
        renderViz(body, stages);
      },
      function (status, parsed) {
        var error = $('flow-error');
        if (error) {
          error.removeAttribute('hidden');
          var msg = (parsed && parsed.detail) || '';
          if (status === 404) msg = t('flow.err.not_found',
            '해당 trace_id 를 찾을 수 없습니다.');
          if (!msg) msg = t('flow.err.unknown',
            '알 수 없는 오류') + ' (HTTP ' + status + ')';
          error.innerHTML = escapeHtml(msg);
        }
      });
  }

  function renderViz(body, stages) {
    var section = $('flow-viz-section');
    if (!section) return;
    section.removeAttribute('hidden');

    var summary = $('flow-summary');
    if (summary) {
      var first = (stages[0] && stages[0].ts_ns) || 0;
      var last = (stages[stages.length - 1] &&
                  stages[stages.length - 1].ts_ns) || 0;
      var totalMs = first && last ?
        Math.round((last - first) / 1e6) : 0;
      summary.innerHTML =
        '<dl>' +
        '<dt>' + escapeHtml(t('flow.summary.trace_id', 'Trace ID')) +
        '</dt><dd style="font-family:var(--font-mono);font-size:11px;' +
        'word-break:break-all">' + escapeHtml(body.trace_id || '?') +
        '</dd>' +
        '<dt>' + escapeHtml(t('flow.summary.day', '날짜')) +
        '</dt><dd>' + escapeHtml(body.day || '?') + '</dd>' +
        '<dt>' + escapeHtml(t('flow.summary.stages', '단계 수')) +
        '</dt><dd>' + escapeHtml(String(stages.length)) + '</dd>' +
        '<dt>' + escapeHtml(t('flow.summary.total_time', '전체 소요')) +
        '</dt><dd>' + escapeHtml(totalMs > 0 ?
          (totalMs + ' ms') : '-') + '</dd>' +
        '</dl>';
    }

    var phases = { retrieve: [], expand: [], verify: [] };
    for (var i = 0; i < stages.length; i++) {
      var s = stages[i];
      var meta = STAGE_META[s.stage] || {
        icon: '', label: s.stage || 'unknown', phase: 'verify',
        desc: '',
      };
      phases[meta.phase].push({ idx: i, stage: s, meta: meta });
    }

    renderSwimlane('phase-retrieve', phases.retrieve, stages);
    renderSwimlane('phase-expand',   phases.expand,   stages);
    renderSwimlane('phase-verify',   phases.verify,   stages);

    // Hide previous detail until operator clicks again.
    var detail = $('flow-detail-panel');
    if (detail) detail.setAttribute('hidden', 'hidden');

    // Scroll viz into view smoothly.
    try {
      section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (_) { /* old browsers — ignore */ }
  }

  function renderSwimlane(containerId, items, allStages) {
    var c = $(containerId);
    if (!c) return;
    if (items.length === 0) {
      c.innerHTML = '<div class="swimlane-empty">' +
        escapeHtml(t('flow.swimlane.empty',
          '이 phase 에서 발생한 단계가 없습니다.')) + '</div>';
      return;
    }
    var html = '';
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var sCard = renderStageCard(item, allStages);
      html += sCard;
    }
    c.innerHTML = html;
    var cards = c.querySelectorAll('.stage-card');
    for (var j = 0; j < cards.length; j++) {
      (function (el) {
        el.addEventListener('click', function () {
          var idx = parseInt(el.getAttribute('data-stage-idx'), 10);
          if (!isNaN(idx)) showStageDetail(idx);
        });
      })(cards[j]);
    }
  }

  function renderStageCard(item, allStages) {
    var s = item.stage;
    var when = s.ts_ns ? formatHmsFromNs(s.ts_ns) : '';
    var dur = '';
    if (item.idx + 1 < allStages.length) {
      var nextTs = allStages[item.idx + 1].ts_ns;
      if (nextTs && s.ts_ns) {
        var ms = Math.round((nextTs - s.ts_ns) / 1e6);
        if (ms > 0) dur = ms + ' ms';
      }
    }
    return '<div class="stage-card" data-stage-idx="' +
           item.idx + '" tabindex="0" role="button"' +
           ' aria-label="' + escapeHtml(item.meta.label) +
           ' — ' + escapeHtml(when) + '">' +
           '<span class="stage-icon">' + escapeHtml(item.meta.icon) +
           '</span>' +
           '<span class="stage-label">' +
           escapeHtml(item.meta.label) + '</span>' +
           '<div class="stage-meta">' +
           '<span class="meta-time">' + escapeHtml(when) + '</span>' +
           (dur ? '<span class="meta-dur">' + escapeHtml(dur) +
                  '</span>' : '') +
           '</div></div>';
  }

  function showStageDetail(idx) {
    var stage = currentTraceStages[idx];
    if (!stage) return;
    var meta = STAGE_META[stage.stage] || {
      icon: '', label: stage.stage || '?', desc: '', phase: 'verify',
    };

    // Mark the selected card.
    var allCards = document.querySelectorAll('.stage-card');
    for (var i = 0; i < allCards.length; i++) {
      allCards[i].setAttribute('data-selected', 'false');
    }
    var selCard = document.querySelector(
      '.stage-card[data-stage-idx="' + idx + '"]');
    if (selCard) selCard.setAttribute('data-selected', 'true');

    var content = $('flow-detail-content');
    if (!content) return;

    var fields = '';
    var skip = { trace_id: 1, stage: 1, phase: 1 };
    for (var k in stage) {
      if (!Object.prototype.hasOwnProperty.call(stage, k)) continue;
      if (skip[k]) continue;
      var label = FIELD_LABELS[k] || k;
      var val = stage[k];
      var display = val;
      if (k === 'ts_ns' && typeof val === 'number') {
        display = formatHmsFromNs(val) + ' (' + val + ')';
      } else if (typeof val === 'object' && val !== null) {
        display = JSON.stringify(val, null, 2);
      }
      fields += '<dl class="detail-field">' +
                '<dt>' + escapeHtml(label) + '</dt>' +
                '<dd>' + escapeHtml(String(display)) + '</dd>' +
                '</dl>';
    }

    content.innerHTML =
      '<div class="detail-stage-header">' +
      '<div class="label">' + escapeHtml(meta.icon) + ' ' +
      escapeHtml(meta.label) + '</div>' +
      (meta.desc ? '<div class="description">' +
        escapeHtml(meta.desc) + '</div>' : '') +
      '</div>' +
      '<div class="detail-fields">' + fields + '</div>';

    var panel = $('flow-detail-panel');
    if (panel) {
      panel.removeAttribute('hidden');
      try { panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
      catch (_) {}
    }
  }

  function renderError(target, status, parsed) {
    var msg = (parsed && parsed.detail) || '';
    if (status === 401 || status === 403) {
      msg = t('flow.err.admin_required', '관리자 로그인이 필요합니다');
    } else if (!msg) {
      msg = t('flow.err.unknown', '알 수 없는 오류') +
            ' (HTTP ' + status + ')';
    }
    target.innerHTML = '<div class="flow-error">' +
      escapeHtml(msg) + '</div>';
  }

  /* ── wire ────────────────────────────────────────────────── */

  function wire() {
    var input = $('flow-trace-input');
    var loadBtn = $('flow-load-btn');
    var refreshBtn = $('flow-refresh-btn');

    if (loadBtn) {
      loadBtn.addEventListener('click', function () {
        var v = input && input.value && input.value.trim();
        if (v) loadTrace(v);
      });
    }
    if (input) {
      input.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter') {
          var v = input.value && input.value.trim();
          if (v) loadTrace(v);
        }
      });
    }
    if (refreshBtn) {
      refreshBtn.addEventListener('click', loadRecentTraces);
    }
    loadRecentTraces();
    // v0.6.1 — deep-link from a chat answer: /admin/graph?trace=<id>#flow
    // (graph-tabs lands on #flow; we auto-load the trace here).
    try {
      var deepTrace = new URLSearchParams(window.location.search).get('trace');
      if (deepTrace && deepTrace.trim()) loadTrace(deepTrace.trim());
    } catch (e) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }

  // Expose for tests + downstream.
  window.JAMES_ReasoningFlow = {
    loadRecentTraces: loadRecentTraces,
    loadTrace:        loadTrace,
    showStageDetail:  showStageDetail,
    STAGE_META:       STAGE_META,
    FIELD_LABELS:     FIELD_LABELS
  };
})();
