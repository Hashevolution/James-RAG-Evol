/* PROJECT JAMES — Time-Travel reasoning-trail replay (Track F.1 TT.c).
 *
 * Given a trace_id, fetches /admin/graph/trace-replay (filtered to the
 * current time-travel cutoff) and renders the stages in the same
 * 3-phase format the live chat panel uses (chat.js STAGE_META):
 *
 *   RETRIEVE  → auth · risky_coding_blocked · retrieve · rerank
 *   EXPAND    → graph · tool · coding_route / coding_llm_pick / ...
 *   VERIFY    → coding_done · answer · complete · *_error · ...
 *
 * Unknown stages bucket to VERIFY (defensive default mirrors chat.js).
 *
 * Per `docs/handovers/v0.5-close-2026-06-12.md` §5.6 F.1 TT.c. The
 * UI is mother-platform — no domain framing. The panel renders the
 * existing audit primitive (one trace's per-stage JSONL trail) at
 * a point-in-time cutoff that the TT.a picker controls.
 *
 * Plain ES5 — same convention as TT.a (time-travel.js) and TT.b
 * (time-travel-renderer.js).
 *
 * Loading order: AFTER `graph.js`, `time-travel.js` (TT.a) and
 * `time-travel-renderer.js` (TT.b). TT.b's overlay sits in the
 * top-right; the trail panel sits below it.
 */
(function () {
  'use strict';

  var EVENT_SET = 'james:timetravel:set';
  var EVENT_CLEAR = 'james:timetravel:clear';
  var PANEL_ID = 'time-travel-trail-panel';
  var ENDPOINT = '/admin/graph/trace-replay';

  // Mirrors chat.js STAGE_META in the minimum needed to bucket a
  // stage into a phase + render an icon. Kept inline because the
  // chat panel only loads on /, not /graph; reusing the symbol
  // would require a shared module the project doesn't have yet.
  var STAGE_META = {
    auth:                  { icon: '', label: 'Auth check',         phase: 'retrieve' },
    risky_coding_blocked:  { icon: '', label: 'Risky cmd blocked',  phase: 'retrieve' },
    retrieve:              { icon: '', label: 'Retrieve',           phase: 'retrieve' },
    rerank:                { icon: '', label: 'Rerank',             phase: 'retrieve' },
    graph:                 { icon: '', label: 'Graph expand',       phase: 'expand'   },
    tool:                  { icon: '', label: 'Tool call',          phase: 'expand'   },
    coding_route:          { icon: '', label: 'Coding route',       phase: 'expand'   },
    coding_llm_pick:       { icon: '', label: 'Model pick',         phase: 'expand'   },
    coding_user_pick:      { icon: '', label: 'User model pick',    phase: 'expand'   },
    coding_done:           { icon: '',  label: 'Coding done',        phase: 'verify'   },
    coding_llm_error:      { icon: '', label: 'Coder LLM error',    phase: 'verify'   },
    coding_fallback_done:  { icon: '',  label: 'Fallback done',      phase: 'verify'   },
    coding_fallback_error: { icon: '', label: 'Fallback error',     phase: 'verify'   },
    coding_user_pick_done: { icon: '',  label: 'User pick done',     phase: 'verify'   },
    coding_user_pick_error:{ icon: '', label: 'User pick error',    phase: 'verify'   },
    answer:                { icon: '', label: 'Answer',             phase: 'verify'   },
    complete:              { icon: '', label: 'Complete',           phase: 'verify'   }
  };

  var PHASE_ORDER = ['retrieve', 'expand', 'verify'];

  // Currently active cutoff (set by TT.a `:set` event, null on clear).
  var currentCutoffIso = '';

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

  function ensurePanel() {
    var existing = $(PANEL_ID);
    if (existing) return existing;
    var stage = document.querySelector('.stage');
    if (!stage) return null;
    var div = document.createElement('div');
    div.id = PANEL_ID;
    div.className = 'overlay tt-trail';
    div.setAttribute('role', 'region');
    div.setAttribute('aria-label', 'Reasoning trail replay');
    // Positioned below the TT.b replay summary (top:62px + ~180px
    // estimate); on phones this stacks below it within the same
    // right gutter. Capped at max-height 50vh so a long trail
    // becomes scrollable rather than pushing everything off-screen.
    div.style.cssText =
      'position:absolute;right:8px;top:260px;width:300px;max-width:80vw;' +
      'max-height:50vh;overflow:auto;' +
      'background:var(--surface-2);border:1px solid var(--border);' +
      'border-radius:7px;padding:10px 12px;color:var(--text-soft);' +
      'font-family:var(--font-mono);font-size:11px;line-height:1.55;' +
      'letter-spacing:.2px;z-index:20;display:none;' +
      'box-shadow:0 2px 10px rgba(0,0,0,.4)';
    stage.appendChild(div);
    return div;
  }

  function hidePanel() {
    var panel = $(PANEL_ID);
    if (panel) panel.style.display = 'none';
    if (window.JAMES_Graph && window.JAMES_Graph.clearTraceHighlight) {
      window.JAMES_Graph.clearTraceHighlight();
    }
  }

  // Make the panel noticeable when it (re)appears — scroll it into the
  // viewport and briefly flash its border. Without this the small
  // top-right overlay is easy to miss, esp. on phones (the "그래프에서
  // 이 추론 보기" button felt like it did nothing).
  function revealPanel(panel) {
    if (!panel) return;
    try { panel.scrollIntoView({ block: 'nearest' }); } catch (_) {}
    var base = '0 2px 10px rgba(0,0,0,.4)';
    panel.style.boxShadow = '0 0 0 2px var(--accent-fg,#6cf), ' + base;
    setTimeout(function () { panel.style.boxShadow = base; }, 1200);
  }

  function renderHeader(stateText) {
    return '<div class="fw-600 c-accent-fg mb-6 u-bedf52b8">' +
           escapeHtml(t('graph.timetravel.trace.title',
                        'Reasoning trail')) +
           '</div>' +
           '<div class="c-muted mb-6">' +
           stateText + '</div>';
  }

  function renderLoading(traceId) {
    var panel = ensurePanel();
    if (!panel) return;
    panel.style.display = 'block';
    panel.innerHTML = renderHeader(
      escapeHtml(t('graph.timetravel.trace.loading', 'Loading trail…')) +
      ' (' + escapeHtml(traceId) + ')'
    );
    revealPanel(panel);
  }

  function renderError(detail, traceId) {
    var panel = ensurePanel();
    if (!panel) return;
    panel.style.display = 'block';
    var safeDetail = detail ? ' — ' + escapeHtml(detail) : '';
    var traceFrag = traceId ? ' (' + escapeHtml(traceId) + ')' : '';
    panel.innerHTML = renderHeader(
      '<span class="u-6812cd91">' +
      escapeHtml(t('graph.timetravel.trace.error', 'Trail unavailable')) +
      safeDetail + traceFrag + '</span>'
    );
    revealPanel(panel);
  }

  function renderEmpty() {
    var panel = ensurePanel();
    if (!panel) return;
    panel.style.display = 'block';
    panel.innerHTML = renderHeader(
      escapeHtml(t('graph.timetravel.trace.empty',
                   'Paste a trace_id to replay its reasoning trail.'))
    );
  }

  function bucketStages(stages) {
    var buckets = { retrieve: [], expand: [], verify: [] };
    for (var i = 0; i < stages.length; i++) {
      var s = stages[i] || {};
      var name = s.stage || '';
      var meta = STAGE_META[name] || { icon: '', label: name || 'unknown',
                                       phase: 'verify' };
      buckets[meta.phase].push({ stage: name, meta: meta, raw: s });
    }
    return buckets;
  }

  function renderStageRow(entry) {
    var raw = entry.raw || {};
    var tsLabel = '';
    if (typeof raw.ts_ns === 'number') {
      // ts_ns → human time. ts_ns is naive UNIX ns (per
      // core/observability.log_stage). Convert to ms + render
      // the wall-clock HH:MM:SS so the operator can tie this to
      // the time-travel cutoff visually.
      var dt = new Date(raw.ts_ns / 1e6);
      var hh = ('0' + dt.getHours()).slice(-2);
      var mm = ('0' + dt.getMinutes()).slice(-2);
      var ss = ('0' + dt.getSeconds()).slice(-2);
      tsLabel = hh + ':' + mm + ':' + ss;
    }
    var icon = entry.meta.icon || '·';
    var label = entry.meta.label || entry.stage || '';
    return '<div class="d-flex gap-6 u-5c9e3ed5">' +
           '<span class="u-fe407230">' + escapeHtml(icon) + '</span>' +
           '<span class="flex-1 c-text">' +
           escapeHtml(label) + '</span>' +
           '<span class="c-muted fs-10">' +
           escapeHtml(tsLabel) + '</span></div>';
  }

  function renderPhase(phaseKey, entries) {
    if (entries.length === 0) return '';
    var labelKey = 'graph.timetravel.trace.phase_' + phaseKey;
    var label = t(labelKey, phaseKey.toUpperCase());
    var rows = '';
    for (var i = 0; i < entries.length; i++) {
      rows += renderStageRow(entries[i]);
    }
    return '<div class="mt-8">' +
           '<div class="fw-600 c-accent-fg fs-10 ls-1 u-bf903b75">' +
           escapeHtml(label) +
           ' <span class="c-muted fw-400 ls-0">(' + entries.length + ')</span></div>' +
           rows + '</div>';
  }

  function renderTrail(body) {
    var panel = ensurePanel();
    if (!panel) return;
    panel.style.display = 'block';
    var stages = (body && body.stages) || [];
    var traceId = (body && body.trace_id) || '';
    var replayed = (body && body.replayed_count) || 0;
    var total = (body && body.total_count) || 0;

    var replayedLabel = t('graph.timetravel.trace.replayed', 'Replayed: ');
    var ofLabel = t('graph.timetravel.trace.of', ' of ');

    var header =
      '<div class="fw-600 c-accent-fg mb-6 u-bedf52b8">' +
      escapeHtml(t('graph.timetravel.trace.title', 'Reasoning trail')) +
      '</div>' +
      '<div class="c-muted fs-10 mb-6 wb-all">' +
      escapeHtml(traceId) + '</div>' +
      '<div class="u-85503ffb">' +
      escapeHtml(replayedLabel) +
      '<span class="c-text fw-600">' +
      escapeHtml(String(replayed)) + '</span>' +
      escapeHtml(ofLabel) +
      '<span class="c-text">' +
      escapeHtml(String(total)) + '</span></div>';

    // v0.6.1 (gap ③) — jump to the swimlane flow view of this same trace.
    var toFlowBtn = traceId ?
      ('<button class="fs-10 mb-8 cursor-pointer bg-surface-2 bd-1 br-6 c-text-soft u-98aca85a" id="trace-to-flow-btn" type="button" ' +
       '>' +
       escapeHtml(t('graph.timetravel.trace.to_flow', '추론 흐름으로 보기 →')) +
       '</button>') : '';

    var buckets = bucketStages(stages);
    var phaseHtml = '';
    for (var i = 0; i < PHASE_ORDER.length; i++) {
      phaseHtml += renderPhase(PHASE_ORDER[i], buckets[PHASE_ORDER[i]]);
    }

    panel.innerHTML = header + toFlowBtn + phaseHtml;

    // v0.6.1 — highlight the nodes this trace traversed on the 3D graph.
    // The graph stage logs `matched_entity_ids` (the validated entity ids
    // it expanded); collect them and hand them to graph.js.
    var traceNodeIds = [];
    for (var si = 0; si < stages.length; si++) {
      var st = stages[si] || {};
      if (st.stage === 'graph' && st.matched_entity_ids &&
          st.matched_entity_ids.length) {
        for (var mi = 0; mi < st.matched_entity_ids.length; mi++) {
          var id = st.matched_entity_ids[mi];
          if (traceNodeIds.indexOf(id) < 0) traceNodeIds.push(id);
        }
      }
    }
    var lit = 0;
    if (window.JAMES_Graph && window.JAMES_Graph.highlightTraceNodes) {
      lit = window.JAMES_Graph.highlightTraceNodes(traceNodeIds) || 0;
    }
    var hlNote;
    if (!traceNodeIds.length) {
      hlNote = t('graph.timetravel.trace.no_nodes',
                 '이 추론에는 그래프 노드 기록이 없습니다 (옛 추론).');
    } else if (!lit) {
      hlNote = t('graph.timetravel.trace.nodes_off',
                 '관련 노드가 현재 그래프 화면에 없습니다.');
    } else {
      hlNote = t('graph.timetravel.trace.nodes_lit',
                 '그래프에 %n개 노드 강조됨').replace('%n', String(lit));
    }
    panel.insertAdjacentHTML('afterbegin',
      '<div class="fs-10 mb-4 u-e8895f24">● ' + escapeHtml(hlNote) + '</div>');

    revealPanel(panel);

    var toFlow = document.getElementById('trace-to-flow-btn');
    if (toFlow) {
      toFlow.addEventListener('click', function () {
        if (window.JAMES_GraphTabs) window.JAMES_GraphTabs.select('flow');
        if (window.JAMES_ReasoningFlow && window.JAMES_ReasoningFlow.loadTrace) {
          window.JAMES_ReasoningFlow.loadTrace(traceId);
        }
      });
    }
  }

  // ─── HTTP fetch ────────────────────────────────────────────────

  function getCreds() {
    var apiKey = (window.localStorage &&
                  window.localStorage.getItem('james_api_key')) || '';
    var token = (window.localStorage &&
                 window.localStorage.getItem('james_token')) || '';
    return { apiKey: apiKey, token: token };
  }

  function fetchTrail(traceId, isoOrEmpty) {
    var creds = getCreds();
    if (!creds.apiKey) {
      renderError('admin login required', traceId);
      return;
    }
    var url = ENDPOINT +
              '?api_key=' + encodeURIComponent(creds.apiKey) +
              '&trace_id=' + encodeURIComponent(traceId);
    if (isoOrEmpty) {
      url += '&t=' + encodeURIComponent(isoOrEmpty);
    }
    renderLoading(traceId);

    var xhr = new XMLHttpRequest();
    xhr.open('GET', url, true);
    xhr.setRequestHeader('Accept', 'application/json');
    if (creds.token) {
      xhr.setRequestHeader('Authorization', 'Bearer ' + creds.token);
    }
    xhr.onload = function () {
      if (xhr.status >= 200 && xhr.status < 300) {
        var parsed;
        try { parsed = JSON.parse(xhr.responseText); }
        catch (e) { renderError('parse error', traceId); return; }
        if (!parsed || parsed.ok !== true) {
          renderError((parsed && parsed.detail) || 'malformed response',
                      traceId);
          return;
        }
        renderTrail(parsed);
      } else if (xhr.status === 404) {
        renderError(t('graph.timetravel.trace.notfound', 'Trace not found'),
                    traceId);
      } else if (xhr.status === 401 || xhr.status === 403) {
        renderError('admin login required', traceId);
      } else if (xhr.status === 400) {
        renderError('invalid timestamp', traceId);
      } else {
        renderError('HTTP ' + xhr.status, traceId);
      }
    };
    xhr.onerror = function () { renderError('network error', traceId); };
    xhr.send();
  }

  // ─── event wiring ──────────────────────────────────────────────

  function readTraceInput() {
    var input = $('time-travel-trace-input');
    if (!input) return '';
    return (input.value || '').trim();
  }

  function onShowTrail() {
    var traceId = readTraceInput();
    if (!traceId) { renderEmpty(); return; }
    fetchTrail(traceId, currentCutoffIso);
  }

  // Direct API for cross-module callers (the flow→graph button). Takes the
  // trace_id explicitly so it doesn't depend on the input element being
  // present/populated at call time (avoids a tab-switch race), and still
  // syncs the visible input for display.
  function showTrace(traceId) {
    traceId = (traceId || '').trim();
    if (!traceId) return;
    var input = $('time-travel-trace-input');
    if (input) input.value = traceId;
    fetchTrail(traceId, currentCutoffIso);
  }

  function onCutoffSet(ev) {
    var iso = (ev && ev.detail && ev.detail.iso) || '';
    currentCutoffIso = iso;
    // If a trace_id is currently in the input, auto-refresh so the
    // panel stays in sync with the picker.
    var traceId = readTraceInput();
    if (traceId && $(PANEL_ID) && $(PANEL_ID).style.display !== 'none') {
      fetchTrail(traceId, currentCutoffIso);
    }
  }

  function onCutoffClear() {
    currentCutoffIso = '';
    // On clear we DON'T auto-hide the trail panel — the trail is
    // useful at "now" too. The operator can hit "Show trail" again
    // to refresh against the live moment, or clear the input.
    var traceId = readTraceInput();
    if (traceId && $(PANEL_ID) && $(PANEL_ID).style.display !== 'none') {
      fetchTrail(traceId, '');
    }
  }

  function wire() {
    var btn = $('time-travel-trace-apply');
    if (btn) btn.addEventListener('click', onShowTrail);
    var input = $('time-travel-trace-input');
    if (input) {
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          onShowTrail();
        }
      });
    }
    window.addEventListener(EVENT_SET, onCutoffSet);
    window.addEventListener(EVENT_CLEAR, onCutoffClear);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }

  // Expose for tests + downstream code.
  window.JAMES_TimeTravelTrace = {
    show: onShowTrail,
    showTrace: showTrace,
    hide: hidePanel,
    fetchTrail: fetchTrail,
    renderTrail: renderTrail,
    renderError: renderError,
    bucketStages: bucketStages,
    STAGE_META: STAGE_META,
    PHASE_ORDER: PHASE_ORDER,
    PANEL_ID: PANEL_ID,
    ENDPOINT: ENDPOINT
  };
})();
