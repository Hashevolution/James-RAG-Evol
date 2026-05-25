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
 *   PUT    /admin/graph/relation                   (sources 배열 교체 —
 *                                                   per-source editor [#451],
 *                                                   Stage E.1, 2026-05-24)
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
  // [Stage E.1, 2026-05-24] per-source editor — cache last-fetched sources
  // so per-row ✕/✏️ can build a "modified sources[]" for the PUT endpoint
  // without re-fetching first. editingIdx is -1 when no row in edit mode.
  var currentSources    = [];             // last refreshSources() payload
  var editingIdx        = -1;             // index of row currently being edited

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
    currentEdge    = null;
    // [Stage E.1] reset per-row editor state so the next open is clean.
    currentSources = [];
    editingIdx     = -1;
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

  // [Stage E.1, 2026-05-24] per-source row — view mode (✏️ + ✕ actions)
  // or edit mode (weight input + note input + Save/Cancel). editingIdx
  // module-scope tracks which row is currently in edit mode.
  function renderSourceRow(s, idx) {
    if (idx === editingIdx) return renderSourceEditRow(s, idx);
    var doc = s.doc_id ? String(s.doc_id) : '<span style="color:var(--muted)">(none)</span>';
    var w   = (typeof s.weight === 'number') ? s.weight.toFixed(2) : '?';
    var ts  = s.ts ? String(s.ts).slice(0, 19) : '';
    var meta = '';
    if (s.author) meta += '<div style="color:var(--muted);font-size:10px">author: ' + escapeHtml(s.author) + '</div>';
    if (s.note)   meta += '<div style="color:var(--muted);font-size:10px;margin-top:2px">note: ' + escapeHtml(s.note) + '</div>';
    // Per-row actions: ✏️ (edit weight/note) and ✕ (delete this source only).
    var actions = '' +
      '<div style="display:flex;flex-direction:column;gap:4px;align-items:flex-end">' +
        '<button type="button" data-action="edit-src" data-idx="' + idx + '" ' +
                'title="Edit this source" ' +
                'style="background:transparent;border:1px solid var(--border);' +
                       'color:var(--text-soft);width:24px;height:22px;' +
                       'border-radius:4px;cursor:pointer;font-size:11px;line-height:1">' +
          '✏️' +
        '</button>' +
        '<button type="button" data-action="del-src" data-idx="' + idx + '" ' +
                'title="Delete this source" ' +
                'style="background:transparent;border:1px solid var(--danger);' +
                       'color:var(--danger);width:24px;height:22px;' +
                       'border-radius:4px;cursor:pointer;font-size:11px;line-height:1">' +
          '✕' +
        '</button>' +
      '</div>';
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
        actions +
      '</div>';
  }

  // [Stage E.1] inline edit row — weight + note inputs with Save/Cancel.
  // Pre-filled with current source values. Save triggers PUT (full sources
  // array replace); Cancel restores view mode without server call.
  function renderSourceEditRow(s, idx) {
    var w    = (typeof s.weight === 'number') ? s.weight.toFixed(2) : '0.50';
    var note = s.note ? String(s.note) : '';
    return '' +
      '<div data-src-idx="' + idx + '" data-edit="1" ' +
           'style="padding:6px 0;border-bottom:1px solid var(--border);' +
                  'background:rgba(99,102,241,.05)">' +
        '<div style="display:flex;gap:6px;align-items:center;font-family:var(--font-mono);' +
              'font-size:11px;margin-bottom:6px">' +
          roleBadge(s.role || '?') +
          '<span style="color:var(--muted);font-size:10px">editing #' + idx + '</span>' +
        '</div>' +
        '<div style="display:flex;gap:6px;align-items:center;margin-bottom:4px">' +
          '<label style="color:var(--muted);font-size:10px;font-family:var(--font-mono);width:50px">weight</label>' +
          '<input type="number" min="0" max="1" step="0.05" value="' + w + '" ' +
                 'data-edit-weight="' + idx + '" ' +
                 'style="flex:1;background:var(--bg);border:1px solid var(--border);' +
                        'color:var(--text);padding:3px 6px;border-radius:4px;' +
                        'font-family:var(--font-mono);font-size:11px">' +
        '</div>' +
        '<div style="display:flex;gap:6px;align-items:center;margin-bottom:6px">' +
          '<label style="color:var(--muted);font-size:10px;font-family:var(--font-mono);width:50px">note</label>' +
          '<input type="text" value="' + escapeHtml(note) + '" ' +
                 'data-edit-note="' + idx + '" placeholder="(optional)" ' +
                 'style="flex:1;background:var(--bg);border:1px solid var(--border);' +
                        'color:var(--text);padding:3px 6px;border-radius:4px;' +
                        'font-family:var(--font-mono);font-size:11px">' +
        '</div>' +
        '<div style="display:flex;gap:6px;justify-content:flex-end">' +
          '<button type="button" data-action="cancel-edit-src" data-idx="' + idx + '" ' +
                  'style="background:transparent;border:1px solid var(--border);' +
                         'color:var(--text-soft);padding:3px 10px;border-radius:4px;' +
                         'cursor:pointer;font-size:11px">Cancel</button>' +
          '<button type="button" data-action="save-edit-src" data-idx="' + idx + '" ' +
                  'style="background:var(--accent);border:1px solid var(--accent);' +
                         'color:#fff;padding:3px 10px;border-radius:4px;' +
                         'cursor:pointer;font-size:11px">Save</button>' +
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
      currentSources = srcs.slice();   // [Stage E.1] cache for per-row mutations
      if (!srcs.length) {
        box.innerHTML = '<div style="color:var(--muted);font-size:11px">No sources (legacy or unmigrated relation).</div>';
        editingIdx = -1;
        return;
      }
      // [Stage E.1] if editingIdx points past the new array (row was deleted)
      // reset to view mode to avoid rendering an orphaned editor.
      if (editingIdx >= srcs.length) editingIdx = -1;
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

  // [Stage E.1, 2026-05-24] PUT helper — replaces the relation's full
  // sources array. Returns true on success. Used by per-row delete and
  // per-row save-edit (both build a new array client-side then push it).
  async function putSources(sources) {
    if (!currentEdge) return false;
    setError('');
    var body = {
      api_key:       apiKey,
      src_entity_id: linkSrcId(currentEdge),
      tgt_entity_id: linkTgtId(currentEdge),
      relation_type: currentEdge.type || 'RELATED_TO',
      sources:       sources,
    };
    try {
      var r = await fetch(API + '/admin/graph/relation', {
        method: 'PUT', headers: authHeaders(), body: JSON.stringify(body),
      });
      if (!r.ok) {
        var j = await r.json().catch(function () { return {}; });
        setError(j.detail || ('error ' + r.status));
        return false;
      }
      await refreshSources();
      reloadSnapshot();
      return true;
    } catch (e) {
      setError(String(e));
      return false;
    }
  }

  // [Stage E.1] per-row delete. If this is the last remaining source the
  // backend PUT rejects an empty array (400 "use DELETE to drop") — so
  // we fall through to deleteRelation() for that case.
  async function deleteSourceAt(idx) {
    if (!currentEdge) return;
    if (!currentSources || idx < 0 || idx >= currentSources.length) return;
    if (currentSources.length === 1) {
      var okLast = window.confirm(
        'This is the only source for this relation — removing it deletes ' +
        'the entire relation. Proceed?'
      );
      if (!okLast) return;
      return deleteRelation(/*skipConfirm*/true);
    }
    var ok = window.confirm('Delete this source?');
    if (!ok) return;
    var newSrcs = currentSources.filter(function (_, i) { return i !== idx; });
    await putSources(newSrcs);
  }

  function startEditSource(idx) {
    if (idx < 0 || idx >= currentSources.length) return;
    editingIdx = idx;
    // Re-render in place without re-fetching from server.
    var box = $('edge-edit-sources');
    if (!box) return;
    box.innerHTML = currentSources.map(function (s, i) {
      return renderSourceRow(s, i);
    }).join('');
    // Focus the weight input for quick editing.
    var wInput = box.querySelector('[data-edit-weight="' + idx + '"]');
    if (wInput) { wInput.focus(); wInput.select(); }
  }

  function cancelEditSource() {
    editingIdx = -1;
    var box = $('edge-edit-sources');
    if (!box) return;
    box.innerHTML = currentSources.map(function (s, i) {
      return renderSourceRow(s, i);
    }).join('');
  }

  async function saveEditedSource(idx) {
    if (idx < 0 || idx >= currentSources.length) return;
    var box = $('edge-edit-sources');
    if (!box) return;
    var wInput = box.querySelector('[data-edit-weight="' + idx + '"]');
    var nInput = box.querySelector('[data-edit-note="' + idx + '"]');
    if (!wInput || !nInput) return;
    var w = parseFloat(wInput.value);
    if (!isFinite(w) || w < 0 || w > 1) {
      setError('weight must be a number in [0, 1]');
      return;
    }
    var copy = currentSources.slice();
    copy[idx] = Object.assign({}, copy[idx], {
      weight: w,
      note:   (nInput.value || '').trim(),
    });
    editingIdx = -1;             // exit edit mode before PUT
    var ok = await putSources(copy);
    if (!ok) {
      // PUT failed — re-enter edit mode so user can retry without re-typing
      editingIdx = idx;
      startEditSource(idx);
    }
  }

  async function deleteRelation(skipConfirm) {
    if (!currentEdge) return;
    if (!skipConfirm) {
      var ok = window.confirm(
        'Delete the entire ' + (currentEdge.type || 'RELATED_TO') +
        ' relation between ' + nodeName(linkSrcId(currentEdge)) +
        ' and ' + nodeName(linkTgtId(currentEdge)) + '?'
      );
      if (!ok) return;
    }
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
    /** PR-O6b — node editor 가 같은 토글 상태를 공유 (probe 재실행 회피). */
    isEditEnabled: function () { return editEnabled; },

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
    // [Stage E.1] wrap to avoid passing the click Event as skipConfirm.
    if (delBtn) delBtn.addEventListener('click', function () { deleteRelation(); });

    // [Stage E.1, 2026-05-24] per-source row actions (✏️ / ✕ / Save / Cancel)
    // — delegated handler on the sources box. data-action + data-idx on
    // each button drives the dispatch.
    var srcBox = $('edge-edit-sources');
    if (srcBox) {
      srcBox.addEventListener('click', function (e) {
        var t = e.target;
        if (!t || !t.getAttribute) return;
        var action = t.getAttribute('data-action');
        if (!action) return;
        var idx = parseInt(t.getAttribute('data-idx'), 10);
        if (!isFinite(idx)) return;
        e.preventDefault();
        if (action === 'del-src')          deleteSourceAt(idx);
        else if (action === 'edit-src')    startEditSource(idx);
        else if (action === 'save-edit-src') saveEditedSource(idx);
        else if (action === 'cancel-edit-src') cancelEditSource();
      });
    }

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
