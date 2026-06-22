/**
 * PROJECT JAMES — Cycle 12 PR-O6b (frontend follow-up to PR-O6).
 *
 * Backend (PR #294) added ``PUT /admin/graph/node`` for renaming an
 * entity, fixing entity_type, adding aliases, editing summary, or
 * toggling sensitivity. PR-O6b is the matching admin UI: a "노드 편집"
 * button injected into the existing entity summary panel (.np-summary),
 * which opens a modal form mirroring the edge-edit modal's UX.
 *
 * Activation:
 *   1) admin 으로 로그인
 *   2) 사이드바의 "Edit mode" 토글 ON  (graph_editor.js 가 probe + 토글)
 *   3) graph 노드 클릭 → neighbor-panel 의 요약 블록 하단에 "노드 편집"
 *      버튼이 나타남
 *
 * Toggle 상태는 graph_editor.js (window.GraphEditor.isEditEnabled())
 * 에 위임 — probe / JAMES_GRAPH_EDIT flag 는 한 곳에서만 확인.
 *
 * Backend dependencies:
 *   GET /admin/entities/<id>     (full frontmatter 로드)
 *   PUT /admin/graph/node        (allowlisted patch)
 *
 * No bundler — graph_editor.js 와 동일한 vanilla IIFE 패턴.
 */
(function () {
  'use strict';

  var API     = '';
  var apiKey  = '';
  var token   = '';
  var snapshotData = null;

  var currentNode  = null;        // {entity_id, frontmatter} 로드된 노드
  var currentNodeId = null;        // summary panel 의 현재 노드 id

  function $(id) { return document.getElementById(id); }
  function authHeaders() {
    return { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' };
  }
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  // i18n.js 의 t() 가 있으면 사용, 없으면 fallback string.
  function _t(key, fallback) {
    if (typeof t === 'function') {
      var v = t(key);
      if (v && v !== key) return v;
    }
    return fallback;
  }

  // ──────────────────────────────────────────────────────────────
  // np-summary-actions 에 "노드 편집" 버튼 주입.
  // graph.js 가 entity summary 를 그릴 때마다 호출.
  // 조건: admin token + GraphEditor.isEditEnabled() == true.
  // ──────────────────────────────────────────────────────────────
  function onEntitySummaryRendered(data) {
    if (!data || !data.entity_id) return;
    currentNodeId = data.entity_id;

    var host = $('np-summary-actions');
    if (!host) return;
    host.innerHTML = '';

    // admin 토큰 없음 → 버튼 숨김 (그래도 panel 자체는 anonymous 도 볼 수 있게).
    if (!token) return;

    // 토글 OFF → 버튼 숨김. graph_editor.js 의 토글 상태 재사용.
    var enabled = false;
    if (window.GraphEditor &&
        typeof window.GraphEditor.isEditEnabled === 'function') {
      try { enabled = !!window.GraphEditor.isEditEnabled(); }
      catch (_e) { enabled = false; }
    }
    if (!enabled) return;

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'np-summary-edit-btn';
    btn.textContent = _t('graph.node.edit.button', '노드 편집');
    btn.setAttribute('style',
      'margin-top:10px;width:100%;padding:8px 10px;' +
      'background:var(--surface-2);border:1px solid var(--border);' +
      'border-radius:6px;color:var(--text-soft);font-size:12px;' +
      'font-family:var(--font-mono);letter-spacing:.4px;cursor:pointer'
    );
    btn.addEventListener('click', function () { openModal(data.entity_id); });
    host.appendChild(btn);
  }

  // ──────────────────────────────────────────────────────────────
  // Modal lifecycle
  // ──────────────────────────────────────────────────────────────
  async function openModal(entityId) {
    setError('');
    var modal = $('node-edit-modal');
    if (!modal) return;
    // 폼 초기화 후 로딩 표시.
    fillForm(null);
    setStatus(_t('graph.node.edit.loading', '엔티티 정보 불러오는 중…'));
    modal.classList.add('show');

    try {
      var url = API + '/admin/entities/' + encodeURIComponent(entityId) +
                '?api_key=' + encodeURIComponent(apiKey);
      var r = await fetch(url, { headers: authHeaders() });
      if (!r.ok) {
        var j = await r.json().catch(function () { return {}; });
        setError(j.detail || ('HTTP ' + r.status));
        return;
      }
      var data = await r.json();
      currentNode = data;
      fillForm(data);
      setStatus('');
    } catch (e) {
      setError(String(e));
    }
  }

  function closeModal() {
    var modal = $('node-edit-modal');
    if (modal) modal.classList.remove('show');
    currentNode = null;
  }

  function setError(msg) {
    var el = $('node-edit-error');
    if (el) el.textContent = msg || '';
  }
  function setStatus(msg) {
    var el = $('node-edit-status');
    if (el) el.textContent = msg || '';
  }

  function fillForm(data) {
    var fm = (data && data.frontmatter) || {};
    $('node-edit-id').textContent = (data && data.entity_id) || '—';
    $('node-edit-name').value       = (data && data.name) || '';
    $('node-edit-etype').value      =
      (data && data.entity_type) || 'concept';
    var aliases = fm.aliases;
    $('node-edit-aliases').value = (Array.isArray(aliases) ? aliases : []).join('\n');
    $('node-edit-summary').value    = fm.summary || '';
    $('node-edit-sens').value       =
      (data && data.sensitivity === 'sensitive') ? 'sensitive' : 'normal';
  }

  // ──────────────────────────────────────────────────────────────
  // Patch build — diff against currentNode 로 변경 필드만 보낸다.
  // 백엔드 update_node_attributes 도 no-op 변경에 graceful 하지만,
  // unchanged 필드를 안 보내면 audit log + diff 가 깔끔.
  // ──────────────────────────────────────────────────────────────
  function buildPatch() {
    var fm = (currentNode && currentNode.frontmatter) || {};

    var name = $('node-edit-name').value.trim();
    var etype = $('node-edit-etype').value;
    var sens  = $('node-edit-sens').value;
    var summary = $('node-edit-summary').value;
    var aliasesRaw = $('node-edit-aliases').value;
    var aliases = aliasesRaw.split('\n')
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length > 0; });

    var patch = {};
    if (name && name !== (currentNode && currentNode.name)) patch.name = name;
    if (etype && etype !== (currentNode && currentNode.entity_type)) patch.entity_type = etype;
    var origSens = (currentNode && currentNode.sensitivity === 'sensitive') ? 'sensitive' : 'normal';
    if (sens !== origSens) patch.sensitivity = sens;

    // aliases 비교는 순서 + 내용 둘 다.
    var origAliases = Array.isArray(fm.aliases) ? fm.aliases : [];
    if (aliases.length !== origAliases.length ||
        aliases.some(function (a, i) { return a !== origAliases[i]; })) {
      patch.aliases = aliases;
    }

    var origSummary = (fm.summary == null) ? '' : String(fm.summary);
    if (summary !== origSummary) patch.summary = summary;

    return patch;
  }

  async function save() {
    if (!currentNode || !currentNode.entity_id) {
      setError(_t('graph.node.edit.noEntity', '엔티티가 로드되지 않았습니다.'));
      return;
    }
    setError('');
    var patch = buildPatch();
    if (!Object.keys(patch).length) {
      setStatus(_t('graph.node.edit.noChange', '변경된 내용이 없습니다.'));
      return;
    }

    // 클라이언트 사전 검증 (백엔드 cap 과 일치).
    if (patch.name !== undefined && patch.name.length === 0) {
      setError(_t('graph.node.edit.nameRequired', '이름은 비울 수 없습니다.'));
      return;
    }
    if (patch.aliases && patch.aliases.length > 20) {
      setError(_t('graph.node.edit.aliasLimit', '별칭은 20개까지 가능합니다.'));
      return;
    }
    if (patch.summary !== undefined && patch.summary.length > 4000) {
      setError(_t('graph.node.edit.summaryCap', '요약은 4000자까지 가능합니다.'));
      return;
    }

    setStatus(_t('graph.node.edit.saving', '저장 중…'));
    var saveBtn = $('node-edit-save');
    if (saveBtn) saveBtn.disabled = true;

    try {
      var r = await fetch(API + '/admin/graph/node', {
        method:  'PUT',
        headers: authHeaders(),
        body:    JSON.stringify({
          api_key:   apiKey,
          entity_id: currentNode.entity_id,
          patch:     patch,
        }),
      });
      if (!r.ok) {
        var j = await r.json().catch(function () { return {}; });
        setStatus('');
        setError(j.detail || ('HTTP ' + r.status));
        return;
      }
      var resp = await r.json();
      var changed = (resp && resp.result && resp.result.changed_fields) || [];
      setStatus(_t('graph.node.edit.saved', '저장 완료') +
                ' — ' + changed.length + _t('graph.node.edit.fieldsChanged', '개 필드 변경'));

      // 그래프 리로드 — 이름 / type / sensitivity 변경 시각 반영.
      reloadSnapshot();
      // 짧은 지연 후 모달 닫기 — 토스트성 피드백 시인성.
      setTimeout(function () { closeModal(); }, 700);
    } catch (e) {
      setStatus('');
      setError(String(e));
    } finally {
      if (saveBtn) saveBtn.disabled = false;
    }
  }

  function reloadSnapshot() {
    if (typeof window.reloadGraphSnapshot === 'function') {
      try { window.reloadGraphSnapshot(); return; }
      catch (_e) { /* fall through */ }
    }
    var sel = $('src-select');
    if (sel) sel.dispatchEvent(new Event('change'));
  }

  // ──────────────────────────────────────────────────────────────
  // Public hooks
  // ──────────────────────────────────────────────────────────────
  window.GraphNodeEditor = {
    onSnapshotLoaded: function (g, d, auth) {
      snapshotData = d;
      apiKey = (auth && auth.apiKey) || apiKey;
      token  = (auth && auth.token)  || token;
      if (auth && typeof auth.api === 'string') API = auth.api;
    },
    onEntitySummaryRendered: onEntitySummaryRendered,
  };

  // ──────────────────────────────────────────────────────────────
  // wiring (DOMContentLoaded 후 1 회)
  // ──────────────────────────────────────────────────────────────
  function wire() {
    var closeBtn = $('node-edit-close');
    if (closeBtn) closeBtn.addEventListener('click', closeModal);

    var saveBtn = $('node-edit-save');
    if (saveBtn) saveBtn.addEventListener('click', save);

    var overlay = $('node-edit-modal');
    if (overlay) {
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeModal();
      });
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
})();
