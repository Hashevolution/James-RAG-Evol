/**
 * PROJECT JAMES — Knowledge Cascade Phase E (frontend UI).
 *
 * docs/design/v0.3-knowledge-cascade.md §7. Backend (PR #271) 가 깐
 * 3 mutation endpoint + 1 read endpoint 위에서 동작하는 admin 전용
 * edge 편집 UI.
 *
 * Activation:
 *   1) admin 으로 로그인 (login-modal 의 정상 flow)
 *   2) 사이드바의 "Edit mode" 토글 클릭 → 서버의 JAMES_GRAPH_EDIT=1
 *      여부 확인. flag off 면 alert + 토글 OFF 유지.
 *   3) flag on 인 경우 ForceGraph3D 의 link 클릭이 본 모듈의 modal 을
 *      열도록 wired.
 *
 * Backend dependencies:
 *   GET    /admin/graph/relation                   (read sources)
 *   POST   /admin/graph/relation/source            (append manual source)
 *   DELETE /admin/graph/relation                   (drop relation 전체)
 *   PUT    /admin/graph/relation                   (지금은 미사용 — per-source
 *                                                   editor 는 follow-up)
 *
 * No bundler — same vanilla pattern as graph.js (IIFE, window 노출).
 */
(function () {
  'use strict';

  var API = '';
  var graphInstance = null;
  var snapshotData  = null;
  var apiKey        = '';
  var token         = '';

  var editEnabled       = false;          // 토글 상태 (client side)
  var editFlagChecked   = false;          // 서버 flag 확인 했는지
  var currentEdge       = null;           // 모달에 표시 중인 edge

  // ──────────────────────────────────────────────────────────────
  // DOM refs (graph.html 에 정의)
  // ──────────────────────────────────────────────────────────────
  function $(id) { return document.getElementById(id); }

  function authHeaders() {
    return { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' };
  }
  function withKey(url) {
    return url + (url.indexOf('?') < 0 ? '?' : '&') + 'api_key=' + encodeURIComponent(apiKey);
  }

  // ──────────────────────────────────────────────────────────────
  // 서버 flag probe — JAMES_GRAPH_EDIT 가 켜져 있는지 확인.
  // GET /admin/graph/relation 에 일부러 매칭 안 되는 dummy 를 보내 본다:
  //   - 403 graph_edit_disabled → flag off
  //   - 404 relation not found  → flag on, gate 통과
  //   - 401  → 토큰 무효 (로그인 다시)
  // ──────────────────────────────────────────────────────────────
  async function probeEditFlag() {
    try {
      var url = withKey(API + '/admin/graph/relation') +
                '&src_entity_id=__probe__&tgt_entity_id=__probe__' +
                '&relation_type=RELATED_TO';
      var r = await fetch(url, { headers: authHeaders() });
      if (r.status === 403) {
        var j = await r.json().catch(function () { return {}; });
        if (String(j.detail || '').indexOf('graph_edit_disabled') >= 0) {
          return { ok: false, reason: 'disabled' };
        }
        return { ok: false, reason: 'forbidden' };
      }
      if (r.status === 401) return { ok: false, reason: 'auth' };
      // 200 또는 404 모두 flag on → gate 통과
      return { ok: true };
    } catch (e) {
      return { ok: false, reason: 'network' };
    }
  }

  // ──────────────────────────────────────────────────────────────
  // edge → src/tgt/type 정규화. graph.js 가 만들어둔 link dict 는
  // {source: node_ref|id, target: node_ref|id, type, weight, conf} 형식.
  // ──────────────────────────────────────────────────────────────
  function linkSrcId(l) {
    return typeof l.source === 'object' ? l.source.id : l.source;
  }
  function linkTgtId(l) {
    return typeof l.target === 'object' ? l.target.id : l.target;
  }
  function nodeName(id) {
    if (!snapshotData) return id;
    for (var i = 0; i < snapshotData.nodes.length; i++) {
      if (snapshotData.nodes[i].id === id) return snapshotData.nodes[i].name;
    }
    return id;
  }

  // ──────────────────────────────────────────────────────────────
  // Modal lifecycle
  // ──────────────────────────────────────────────────────────────
  function openModal(edge) {
    currentEdge = edge;
    var modal = $('edge-edit-modal');
    if (!modal) return;
    $('edge-edit-src').textContent  = nodeName(linkSrcId(edge));
    $('edge-edit-tgt').textContent  = nodeName(linkTgtId(edge));
    $('edge-edit-type').textContent = edge.type || 'RELATED_TO';
    $('edge-edit-conf').textContent = (edge.conf != null) ? String(edge.conf) : '—';
    $('edge-edit-error').textContent = '';
    $('edge-edit-sources').innerHTML =
      '<div style="color:var(--muted);font-family:var(--font-mono);font-size:11px">Loading sources...</div>';
    modal.classList.add('show');
    refreshSources();
  }

  function closeModal() {
    var modal = $('edge-edit-modal');
    if (modal) modal.classList.remove('show');
    currentEdge = null;
  }

  function setError(msg) {
    var el = $('edge-edit-error');
    if (el) el.textContent = msg || '';
  }

  function roleBadge(role) {
    var color = 'var(--muted)';
    if (role === 'manual')  color = 'var(--accent)';
    if (role === 'extract') color = '#a5b4fc';
    if (role === 'inverse') color = '#94a3b8';
    if (role === 'legacy')  color = '#f59e0b';
    return '<span style="display:inline-block;padding:1px 6px;border-radius:4px;' +
           'background:rgba(255,255,255,.05);border:1px solid ' + color + ';' +
           'color:' + color + ';font-size:10px;font-family:var(--font-mono);' +
           'letter-spacing:.5px">' + role + '</span>';
  }

  function renderSourceRow(s, idx) {
    var doc = s.doc_id ? String(s.doc_id) : '<span style="color:var(--muted)">(none)</span>';
    var w   = (typeof s.weight === 'number') ? s.weight.toFixed(2) : '?';
    var ts  = s.ts ? String(s.ts).slice(0, 19) : '';
    var meta = '';
    if (s.author) meta += '<div style="color:var(--muted);font-size:10px">author: ' + escapeHtml(s.author) + '</div>';
    if (s.note)   meta += '<div style="color:var(--muted);font-size:10px;margin-top:2px">note: ' + escapeHtml(s.note) + '</div>';
    return '' +
      '<div data-src-idx="' + idx + '" style="display:flex;align-items:flex-start;' +
         'gap:8px;padding:6px 0;border-bottom:1px solid var(--border)">' +
        '<div style="flex:1;min-width:0">' +
          '<div style="display:flex;gap:6px;align-items:center;font-family:var(--font-mono);font-size:11px">' +
            roleBadge(s.role || '?') +
            '<span style="color:var(--text-soft)">w=' + w + '</span>' +
            (ts ? '<span style="color:var(--muted);font-size:10px">' + ts + '</span>' : '') +
          '</div>' +
          '<div style="margin-top:2px;color:var(--text-soft);font-family:var(--font-mono);' +
                'font-size:10px;word-break:break-all">' + doc + '</div>' +
          meta +
        '</div>' +
      '</div>';
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  async function refreshSources() {
    if (!currentEdge) return;
    var box = $('edge-edit-sources');
    try {
      var url = withKey(API + '/admin/graph/relation') +
                '&src_entity_id=' + encodeURIComponent(linkSrcId(currentEdge)) +
                '&tgt_entity_id=' + encodeURIComponent(linkTgtId(currentEdge)) +
                '&relation_type=' + encodeURIComponent(currentEdge.type || 'RELATED_TO');
      var r = await fetch(url, { headers: authHeaders() });
      if (!r.ok) {
        var j = await r.json().catch(function () { return {}; });
        box.innerHTML = '<div style="color:var(--danger);font-size:11px">' +
                        escapeHtml(j.detail || ('error ' + r.status)) + '</div>';
        return;
      }
      var data = await r.json();
      var rel  = (data && data.relation) || {};
      var srcs = rel.sources || [];
      if (!srcs.length) {
        box.innerHTML = '<div style="color:var(--muted);font-size:11px">No sources (legacy or unmigrated relation).</div>';
        return;
      }
      box.innerHTML = srcs.map(function (s, i) { return renderSourceRow(s, i); }).join('');
      if (rel.confidence != null) {
        $('edge-edit-conf').textContent = String(rel.confidence);
      }
    } catch (e) {
      box.innerHTML = '<div style="color:var(--danger);font-size:11px">' +
                      escapeHtml(String(e)) + '</div>';
    }
  }

  // ──────────────────────────────────────────────────────────────
  // Mutation handlers
  // ──────────────────────────────────────────────────────────────
  async function appendManualSource() {
    if (!currentEdge) return;
    setError('');
    var wEl = $('edge-edit-weight');
    var nEl = $('edge-edit-note');
    var w   = parseFloat(wEl.value);
    if (!isFinite(w) || w < 0 || w > 1) {
      setError('weight must be a number in [0, 1]'); return;
    }
    var body = {
      api_key:       apiKey,
      src_entity_id: linkSrcId(currentEdge),
      tgt_entity_id: linkTgtId(currentEdge),
      relation_type: currentEdge.type || 'RELATED_TO',
      source: {
        doc_id: null,
        weight: w,
        role:   'manual',
        author: 'admin',
        note:   (nEl.value || '').trim(),
      },
    };
    try {
      var r = await fetch(API + '/admin/graph/relation/source', {
        method: 'POST', headers: authHeaders(), body: JSON.stringify(body),
      });
      if (!r.ok) {
        var j = await r.json().catch(function () { return {}; });
        setError(j.detail || ('error ' + r.status)); return;
      }
      nEl.value = '';
      await refreshSources();
      reloadSnapshot();
    } catch (e) {
      setError(String(e));
    }
  }

  async function deleteRelation() {
    if (!currentEdge) return;
    var ok = window.confirm(
      'Delete the entire ' + (currentEdge.type || 'RELATED_TO') +
      ' relation between ' + nodeName(linkSrcId(currentEdge)) +
      ' and ' + nodeName(linkTgtId(currentEdge)) + '?'
    );
    if (!ok) return;
    setError('');
    var body = {
      api_key:       apiKey,
      src_entity_id: linkSrcId(currentEdge),
      tgt_entity_id: linkTgtId(currentEdge),
      relation_type: currentEdge.type || 'RELATED_TO',
    };
    try {
      var r = await fetch(API + '/admin/graph/relation', {
        method: 'DELETE', headers: authHeaders(), body: JSON.stringify(body),
      });
      if (!r.ok) {
        var j = await r.json().catch(function () { return {}; });
        setError(j.detail || ('error ' + r.status)); return;
      }
      closeModal();
      reloadSnapshot();
    } catch (e) {
      setError(String(e));
    }
  }

  function reloadSnapshot() {
    // graph.js 가 노출한 reload 가 있으면 호출, 아니면 src-select change
    // 이벤트를 강제로 fire — 동일 source 면 재페치 한다.
    if (typeof window.reloadGraphSnapshot === 'function') {
      try { window.reloadGraphSnapshot(); return; }
      catch (_e) { /* fall through */ }
    }
    var sel = document.getElementById('src-select');
    if (sel) sel.dispatchEvent(new Event('change'));
  }

  // ──────────────────────────────────────────────────────────────
  // Toggle behavior
  // ──────────────────────────────────────────────────────────────
  async function onToggleClick() {
    var btn = $('graph-edit-toggle');
    var hint = $('graph-edit-hint');
    if (!btn) return;

    if (editEnabled) {
      editEnabled = false;
      btn.textContent = '🔒 Edit mode: OFF';
      if (hint) hint.style.display = 'none';
      return;
    }

    if (!editFlagChecked) {
      btn.disabled = true;
      var probe = await probeEditFlag();
      btn.disabled = false;
      editFlagChecked = true;
      if (!probe.ok) {
        var msg = 'Edit mode unavailable';
        if (probe.reason === 'disabled') {
          msg = 'Server has JAMES_GRAPH_EDIT off. Set JAMES_GRAPH_EDIT=1 + restart.';
        } else if (probe.reason === 'auth') {
          msg = 'Auth expired — please re-login.';
        }
        window.alert(msg);
        return;
      }
    }
    editEnabled = true;
    btn.textContent = '🔓 Edit mode: ON';
    if (hint) hint.style.display = 'block';
  }

  // ──────────────────────────────────────────────────────────────
  // Public hooks
  // ──────────────────────────────────────────────────────────────
  window.GraphEditor = {
    /** graph.js 가 snapshot load 직후 호출. */
    onSnapshotLoaded: function (g, d, auth) {
      graphInstance = g;
      snapshotData  = d;
      apiKey        = (auth && auth.apiKey) || apiKey;
      token         = (auth && auth.token)  || token;

      // 토글 wrapper 노출 (admin 토큰이 있으면). server flag 는 토글
      // 누를 때 lazy probe — 페이지 로드마다 probe 보내지 않음.
      if (token) {
        var wrap = $('graph-edit-wrap');
        if (wrap) wrap.style.display = '';
      }

      // ForceGraph3D 의 link click → modal. 본 핸들러는 항상 등록되어
      // 있고, edit 모드가 OFF 면 no-op.
      if (g && typeof g.onLinkClick === 'function') {
        g.onLinkClick(function (link) {
          if (!editEnabled || !link) return;
          openModal(link);
        });
      }
    },
  };

  // ──────────────────────────────────────────────────────────────
  // wiring (DOMContentLoaded 후 1 회)
  // ──────────────────────────────────────────────────────────────
  function wire() {
    var btn = $('graph-edit-toggle');
    if (btn) btn.addEventListener('click', onToggleClick);

    var closeBtn = $('edge-edit-close');
    if (closeBtn) closeBtn.addEventListener('click', closeModal);

    var appendBtn = $('edge-edit-append');
    if (appendBtn) appendBtn.addEventListener('click', appendManualSource);

    var delBtn = $('edge-edit-delete-relation');
    if (delBtn) delBtn.addEventListener('click', deleteRelation);

    // overlay 클릭 닫기
    var overlay = $('edge-edit-modal');
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
