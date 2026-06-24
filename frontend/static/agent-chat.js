/* PROJECT JAMES — Agent chat panel (v0.6.1 Phase D-2)
 *
 * Lives inside admin.html as a separate page. Calls
 * POST /agent/chat/ — synchronous per turn (the server runs the LLM
 * tool-use loop, max 5 iterations, internally). The panel renders:
 *
 *   * assistant text bubble
 *   * one card per tool call (name, args, ok/error, elapsed_ms)
 *   * a status line + cancel button while a turn is in flight
 *
 * Per-call interactive confirm (Allow / Deny / Always-allow) requires
 * either SSE / WebSocket streaming or a multi-step API where the server
 * pauses for client approval before each dispatch. Both are larger
 * surface than this PR is scoped to ship; the "🔓 세션 동안 도구 자동
 * 허용" checkbox is the operator-side gate for now. If the box is
 * unchecked and the LLM emits a tool_use call, the client refuses the
 * turn before sending and asks the operator to check the box.
 *
 * Cancel is best-effort via AbortController — the server can't be
 * stopped mid-turn but the client returns control to the operator
 * immediately and the in-flight POST is abandoned.
 */
(function () {
  'use strict';

  let _history = [];      // conversation history we send back to the server
  let _abort = null;      // current AbortController, if a turn is in flight
  let _booted = false;    // loadAgentChat is invoked every time the page
                          // is shown; only attach listeners once.

  function _tok() {
    try { return localStorage.getItem('james_token') || ''; } catch (_) { return ''; }
  }
  function _key() {
    try { return localStorage.getItem('james_api_key') || ''; } catch (_) { return ''; }
  }
  function _t(k, fb) {
    return (typeof t === 'function' ? t(k) : '') || fb || k;
  }
  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }
  function _log() { return document.getElementById('agent-chat-log'); }
  function _status() { return document.getElementById('agent-chat-status'); }
  function _setStatus(msg) {
    const el = _status(); if (el) el.textContent = msg || '';
  }
  function _autoAllow() {
    const cb = document.getElementById('agent-chat-auto-allow');
    return !!(cb && cb.checked);
  }

  /* ── v0.6.1 UX overhaul state: sessions / model / folder browser ── */
  let _sessions = [];          // session summaries from the server
  let _activeSession = null;   // {id, title} of the open conversation
  let _wsBooted = false;       // bootAgentWorkspace listeners attached once
  let _browseCur = '';         // current path shown in the browser modal
  let _browsePickable = false; // is _browseCur registerable

  function _authHeaders(extra) {
    const h = Object.assign({}, extra || {});
    const tk = _tok();
    if (tk) h.Authorization = 'Bearer ' + tk;
    return h;
  }
  /* Append api_key to a URL (admin GET/DELETE endpoints take it as a
     query param; POST/PUT take it in the JSON body). */
  function _q(url) {
    return url + (url.includes('?') ? '&' : '?')
      + 'api_key=' + encodeURIComponent(_key());
  }
  async function _api(method, url, body) {
    const opt = {
      method,
      headers: _authHeaders(body ? { 'Content-Type': 'application/json' } : {}),
    };
    if (body) opt.body = JSON.stringify(body);
    const r = await fetch(url, opt);
    if (!r.ok) {
      let d = '' + r.status;
      try { d = (await r.json()).detail || d; } catch (_) {}
      throw new Error(d);
    }
    return r.status === 204 ? null : r.json();
  }
  function _setLlmMsg(msg) {
    const el = document.getElementById('agent-llm-msg');
    if (el) el.textContent = msg || '';
  }

  /* Public: called from admin.js showPage() loader map. */
  window.loadAgentChat = function loadAgentChat() {
    if (_booted) return;
    _booted = true;
    const inp = document.getElementById('agent-chat-input');
    if (inp) {
      inp.addEventListener('keydown', (e) => {
        // Ctrl/Cmd+Enter sends; bare Enter inserts a newline (textarea
        // default), matching the workspace template-engine UX.
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          sendAgentChat();
        }
      });
    }
  };

  /* Public: send button + Ctrl+Enter handler. */
  window.sendAgentChat = async function sendAgentChat() {
    const inp = document.getElementById('agent-chat-input');
    const msg = (inp && inp.value || '').trim();
    if (!msg) return;
    if (_abort) {
      _setStatus(_t('agentchat.busy', '진행 중인 호출이 있습니다. 잠시 후 다시 시도하세요.'));
      return;
    }
    _renderUserBubble(msg);
    if (inp) inp.value = '';
    _toggleSending(true);

    const backendSel = document.getElementById('agent-chat-backend');
    const backend = (backendSel && backendSel.value) || null;
    const modelSel = document.getElementById('agent-chat-model');
    const model = (modelSel && modelSel.value) || null;
    const payload = {
      api_key: _key(),
      message: msg,
      history: _history.slice(),
    };
    if (backend) payload.backend = backend;
    if (model) payload.model = model;

    _abort = new AbortController();
    try {
      const r = await fetch('/agent/chat/', {
        method: 'POST',
        headers: Object.assign(
          { 'Content-Type': 'application/json' },
          _tok() ? { Authorization: 'Bearer ' + _tok() } : {},
        ),
        body: JSON.stringify(payload),
        signal: _abort.signal,
      });
      if (!r.ok) {
        let detail = '' + r.status;
        try { detail = (await r.json()).detail || detail; } catch (_) {}
        throw new Error(detail);
      }
      const data = await r.json();
      _handleResponse(msg, data);
      _persistActive();          // save this turn into the active session
    } catch (e) {
      if (e.name === 'AbortError') {
        _setStatus(_t('agentchat.aborted', '중단됨'));
      } else {
        _renderErrorBubble(e.message || String(e));
      }
    } finally {
      _abort = null;
      _toggleSending(false);
    }
  };

  window.cancelAgentChat = function cancelAgentChat() {
    if (_abort) {
      try { _abort.abort(); } catch (_) {}
    }
  };

  window.clearAgentChat = function clearAgentChat() {
    _history = [];
    const box = _log();
    if (box) {
      box.innerHTML =
        `<div style="color:var(--muted);font-size:12px">${
          _esc(_t('agentchat.empty', '(아직 대화 없음 — 아래에 메시지를 입력하세요)'))
        }</div>`;
    }
    _setStatus('');
    // Persist the now-empty history to the active session (keeps the
    // session but clears its turns).
    if (_activeSession) _persistActive();
  };

  function _toggleSending(busy) {
    const sendBtn = document.getElementById('agent-chat-send-btn');
    const cancelBtn = document.getElementById('agent-chat-cancel-btn');
    if (sendBtn) sendBtn.disabled = !!busy;
    if (cancelBtn) cancelBtn.style.display = busy ? '' : 'none';
    _setStatus(busy ? _t('agentchat.thinking', '⏳ 처리 중…') : '');
  }

  function _appendNode(html) {
    const box = _log();
    if (!box) return;
    // Drop the empty-placeholder block on first append.
    const empty = box.querySelector('[data-i18n="agentchat.empty"]');
    if (empty && empty.parentElement === box) empty.remove();
    const wrap = document.createElement('div');
    wrap.innerHTML = html;
    while (wrap.firstChild) box.appendChild(wrap.firstChild);
    box.scrollTop = box.scrollHeight;
  }

  function _renderUserBubble(text) {
    _appendNode(`
      <div style="align-self:flex-end;max-width:80%;background:var(--accent,#3b82f6);color:var(--on-accent,#fff);padding:8px 12px;border-radius:12px 12px 4px 12px;font-size:13px;white-space:pre-wrap;word-break:break-word">
        ${_esc(text)}
      </div>
    `);
  }

  function _renderAssistantBubble(text) {
    if (!text) return;
    _appendNode(`
      <div style="align-self:flex-start;max-width:80%;background:var(--surface-2,#1e293b);color:var(--text);padding:8px 12px;border-radius:12px 12px 12px 4px;font-size:13px;white-space:pre-wrap;word-break:break-word">
        ${_esc(text)}
      </div>
    `);
  }

  function _renderErrorBubble(msg) {
    _appendNode(`
      <div style="align-self:flex-start;max-width:90%;background:#5b1e1e;color:#fcc;padding:8px 12px;border-radius:8px;font-size:12px;font-family:var(--font-mono)">
        ❌ ${_esc(msg)}
      </div>
    `);
  }

  function _renderToolCard(call) {
    const okIcon = call.ok ? '✅' : '❌';
    const argsJson = JSON.stringify(call.input || {}, null, 0);
    const detail = call.ok
      ? (_t('agentchat.tool_ok', '완료'))
      : _esc(call.error || 'error');
    // run_shell is the highest-risk tool — flag it with a warning border
    // + a ⚠ marker so the operator can spot a shell call at a glance.
    const isShell = call.name === 'run_shell';
    const border = isShell ? '#a16207' : 'var(--border,#334155)';
    const shellTag = isShell
      ? ` <span style="color:#fc8" title="${_esc(_t('agentchat.shell_tag_title', '셸 명령 실행 — 운영자 허용 폴더 안에서만'))}">⚠ shell</span>`
      : '';
    _appendNode(`
      <div style="align-self:flex-start;max-width:92%;background:var(--bg,#0f172a);border:1px solid ${border};border-radius:8px;padding:8px 12px;font-family:var(--font-mono);font-size:11px;color:var(--text)">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <span><strong>${okIcon} ${_esc(call.name)}</strong>${shellTag}
                <span style="color:var(--muted);margin-left:6px">iter ${call.iter || ''}</span></span>
          <span style="color:var(--muted)">${call.elapsed_ms != null ? call.elapsed_ms + ' ms' : ''}</span>
        </div>
        <div style="color:var(--muted);word-break:break-all;margin-bottom:2px">args: ${_esc(argsJson)}</div>
        <div style="color:${call.ok ? 'var(--muted)' : '#fcc'};word-break:break-all">${detail}</div>
      </div>
    `);
  }

  function _handleResponse(userMsg, data) {
    // Push the user turn + the synthetic assistant turn into our
    // history so the next call sends the right context. For Ollama the
    // server doesn't need the assistant block to be tool_use-shaped;
    // for Anthropic it does, but the server already accumulated that
    // shape internally — what we send back is the simpler shape the
    // factory accepts as initial history.
    _history.push({ role: 'user', content: userMsg });
    if (data.text) _history.push({ role: 'assistant', content: data.text });

    // Render tool cards in order, then the assistant text last.
    const trace = data.tool_trace || [];
    if (trace.length && !_autoAllow()) {
      // Tools fired but the operator never checked the auto-allow box.
      // Surface the tool cards but warn — next turn won't be allowed
      // to fire tools either until the box is checked.
      _renderErrorBubble(_t('agentchat.auto_allow_warn',
        '에이전트가 도구를 호출했습니다. 다음 호출을 허용하려면 상단의 "세션 동안 도구 자동 허용" 을 체크하세요.'));
    }
    trace.forEach(_renderToolCard);
    _renderAssistantBubble(data.text);
    _setStatus(`${_t('agentchat.status_done', '완료')} · ${
      _t('agentchat.iters', 'iter')} ${data.iterations || 0} · ${
      _t('agentchat.calls', 'calls')} ${trace.length} · ${_esc(data.backend || '')}`);
  }

  /* ── v0.6.1 UX overhaul: render a loaded session's history ── */
  function _renderHistory() {
    const box = _log();
    if (!box) return;
    box.innerHTML = '';
    if (!_history.length) {
      box.innerHTML =
        `<div style="color:var(--muted);font-size:12px">${
          _esc(_t('agentchat.empty', '(아직 대화 없음 — 아래에 메시지를 입력하세요)'))
        }</div>`;
      return;
    }
    _history.forEach(m => {
      if (m.role === 'user') _renderUserBubble(m.content);
      else _renderAssistantBubble(m.content);
    });
  }

  /* ── Sessions ── */
  function _renderSessions() {
    const box = document.getElementById('agent-session-list');
    if (!box) return;
    if (!_sessions.length) {
      box.innerHTML = `<div style="color:var(--muted);font-size:11px">${
        _esc(_t('agentsess.empty', '세션 없음 — + 새 대화'))}</div>`;
      return;
    }
    box.innerHTML = _sessions.map(s => {
      const active = _activeSession && _activeSession.id === s.id;
      return `<div data-action="agent-session-open" data-sid="${_esc(s.id)}"
        style="display:flex;justify-content:space-between;align-items:center;gap:4px;
        padding:6px 8px;border-radius:6px;cursor:pointer;font-size:12px;
        background:${active ? 'var(--accent,#3b82f6)' : 'var(--bg)'};
        color:${active ? '#fff' : 'var(--text)'};border:1px solid var(--border)">
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${_esc(s.title)}</span>
        <button data-action="agent-session-del" data-sid="${_esc(s.id)}"
          title="${_esc(_t('agentsess.del', '삭제'))}"
          style="border:0;background:transparent;color:${active ? '#fff' : 'var(--muted)'};
          cursor:pointer;font-size:12px;padding:0 2px">✕</button>
      </div>`;
    }).join('');
  }

  async function _loadSessions() {
    try {
      const d = await fetch(_q('/admin/agent/sessions'),
        { headers: _authHeaders() }).then(r => r.json());
      _sessions = d.sessions || [];
    } catch (_) { _sessions = []; }
    if (_activeSession && !_sessions.find(s => s.id === _activeSession.id)) {
      _activeSession = null;
    }
    if (!_activeSession && _sessions.length) {
      await _selectSession(_sessions[0].id);
    } else {
      _renderSessions();
    }
  }

  async function _selectSession(id) {
    if (!id) return;
    try {
      const d = await fetch(_q('/admin/agent/sessions/' + encodeURIComponent(id)),
        { headers: _authHeaders() }).then(r => r.json());
      _activeSession = { id: d.session.id, title: d.session.title };
      _history = (d.session.messages || []).map(m => ({ role: m.role, content: m.content }));
      _renderHistory();
    } catch (e) {
      _setStatus(_t('agentsess.load_fail', '세션 로드 실패') + ': ' + (e.message || e));
    }
    _renderSessions();
  }

  async function _newSession() {
    try {
      const d = await _api('POST', '/admin/agent/sessions',
        { api_key: _key(), title: _t('agentsess.new_title', '새 대화') });
      _sessions.unshift(d.session);
      _activeSession = { id: d.session.id, title: d.session.title };
      _history = [];
      _renderHistory();
      _renderSessions();
      _setStatus('');
    } catch (e) {
      _setStatus(_t('agentsess.new_fail', '세션 생성 실패') + ': ' + (e.message || e));
    }
  }

  async function _deleteSession(id, ev) {
    if (ev) ev.stopPropagation();
    if (!id) return;
    if (!confirm(_t('agentsess.del_confirm', '이 대화 세션을 삭제할까요?'))) return;
    try {
      await fetch(_q('/admin/agent/sessions/' + encodeURIComponent(id)),
        { method: 'DELETE', headers: _authHeaders() });
    } catch (_) {}
    if (_activeSession && _activeSession.id === id) {
      _activeSession = null;
      _history = [];
      _renderHistory();
    }
    await _loadSessions();
  }

  async function _persistActive() {
    try {
      if (!_activeSession) {
        const first = (_history.find(m => m.role === 'user') || {}).content || '새 대화';
        const d = await _api('POST', '/admin/agent/sessions',
          { api_key: _key(), title: String(first).slice(0, 40) });
        _activeSession = { id: d.session.id, title: d.session.title };
      }
      await _api('PUT', '/admin/agent/sessions/' + encodeURIComponent(_activeSession.id),
        { api_key: _key(), messages: _history });
      _loadSessions();      // refresh sidebar title / ordering
    } catch (_) {}
  }

  /* ── Model / backend settings ── */
  let _llmData = null;

  async function _loadAgentModels(refresh) {
    const sel = document.getElementById('agent-chat-model');
    if (!sel) return;
    try {
      _llmData = await fetch(_q('/admin/agent/llm-settings'),
        { headers: _authHeaders() }).then(r => r.json());
      const bsel = document.getElementById('agent-chat-backend');
      if (bsel && !bsel.value && _llmData.backend) bsel.value = _llmData.backend;
      _populateModels();
      const shc = document.getElementById('agent-enable-shell');
      if (shc) shc.checked = !!_llmData.shell_enabled;
      const clc = document.getElementById('agent-allow-cloud');
      if (clc) clc.checked = !!_llmData.allow_cloud;
      if (refresh) _setLlmMsg(_t('agentchat.models_refreshed', '모델 목록 갱신 완료'));
    } catch (e) {
      _setLlmMsg(_t('agentchat.models_fail', 'ollama 모델 조회 실패 (ollama 미실행?)'));
    }
  }

  /* Fill the MODEL dropdown for the selected backend: installed Ollama
     models, or the Claude family for the cloud backend. */
  function _populateModels() {
    const sel = document.getElementById('agent-chat-model');
    const bsel = document.getElementById('agent-chat-backend');
    if (!sel || !_llmData) return;
    const backend = (bsel && bsel.value) || _llmData.backend || 'ollama';
    const prev = sel.value;
    let list, cur;
    if (backend === 'anthropic' || backend === 'claude_cli') {
      list = _llmData.claude_models || [];
      cur = _llmData.anthropic_model;
      _setCloudStatus();
    } else {
      list = _llmData.installed_ollama_models || [];
      cur = _llmData.ollama_model;
      _setLlmMsg('');
    }
    const opts = [`<option value="">${_esc((_t('agentchat.model_default', '(기본) ')) + (cur || ''))}</option>`]
      .concat((list || []).map(m => `<option value="${_esc(m)}">${_esc(m)}</option>`));
    sel.innerHTML = opts.join('');
    if (prev && (list || []).indexOf(prev) >= 0) sel.value = prev;
  }

  /* Tell the operator exactly what to set before the cloud backend works.
     claude_cli (Max-plan CLI) needs the `claude` CLI but NO API key;
     anthropic (HTTP) needs ANTHROPIC_API_KEY. Both need ALLOW_CLOUD. */
  function _setCloudStatus() {
    if (!_llmData) return;
    const bsel = document.getElementById('agent-chat-backend');
    const backend = (bsel && bsel.value) || _llmData.backend || 'anthropic';
    const need = [];
    if (!_llmData.allow_cloud) need.push('JAMES_AGENT_ALLOW_CLOUD=1');
    if (backend === 'claude_cli') {
      if (!_llmData.claude_cli_present) need.push(_t('agentchat.cloud_need_cli', 'claude CLI (Max 플랜 로그인)'));
    } else {
      if (!_llmData.anthropic_key_present) need.push('ANTHROPIC_API_KEY');
    }
    if (!need.length) {
      _setLlmMsg(_t('agentchat.cloud_ready', '☁ 클라우드(Claude) 사용 준비됨'));
    } else {
      _setLlmMsg(_t('agentchat.cloud_need', '☁ 클라우드 사용하려면 서버에 설정 필요: ') + need.join(' + '));
    }
  }

  async function _saveAgentModel() {
    const bsel = document.getElementById('agent-chat-backend');
    const sel = document.getElementById('agent-chat-model');
    const backend = (bsel && bsel.value) || null;
    const model = (sel && sel.value) || '';
    const body = { api_key: _key() };
    if (backend) body.backend = backend;
    if (model) {
      if (backend === 'anthropic' || backend === 'claude_cli') body.anthropic_model = model;
      else body.ollama_model = model;
    }
    try {
      await _api('POST', '/admin/agent/llm-settings', body);
      _setLlmMsg(_t('agentchat.model_saved', '기본값으로 저장됨'));
    } catch (e) {
      _setLlmMsg(_t('agentchat.model_save_fail', '저장 실패') + ': ' + (e.message || e));
    }
  }

  /* ── Shell tool toggle (run_shell) ── */
  async function _toggleShell() {
    const cb = document.getElementById('agent-enable-shell');
    const msgEl = document.getElementById('agent-shell-msg');
    const on = !!(cb && cb.checked);
    try {
      await _api('POST', '/admin/agent/llm-settings',
        { api_key: _key(), enable_shell: on });
      if (msgEl) msgEl.textContent = on
        ? _t('agentchat.shell_on', '셸 실행 켜짐')
        : _t('agentchat.shell_off', '셸 실행 꺼짐');
    } catch (e) {
      if (cb) cb.checked = !on;     // revert on failure
      if (msgEl) msgEl.textContent = (e.message || e);
    }
  }

  /* ── Cloud-egress toggle (JAMES_AGENT_ALLOW_CLOUD) ── */
  async function _toggleAllowCloud() {
    const cb = document.getElementById('agent-allow-cloud');
    const on = !!(cb && cb.checked);
    try {
      await _api('POST', '/admin/agent/llm-settings',
        { api_key: _key(), allow_cloud: on });
      if (_llmData) _llmData.allow_cloud = on;
      _setCloudStatus();
    } catch (e) {
      if (cb) cb.checked = !on;     // revert on failure
      _setLlmMsg((e.message || e));
    }
  }

  /* ── Folder browser modal ── */
  function _browseModal() { return document.getElementById('agent-browse-modal'); }
  async function _openBrowse() {
    const m = _browseModal();
    if (!m) return;
    m.style.display = 'flex';
    await _navBrowse('');
  }
  function _closeBrowse() {
    const m = _browseModal();
    if (m) m.style.display = 'none';
  }
  async function _navBrowse(path) {
    try {
      const url = '/admin/agent/browse' + (path ? ('?path=' + encodeURIComponent(path)) : '');
      const d = await fetch(_q(url), { headers: _authHeaders() }).then(r => {
        if (!r.ok) throw new Error('' + r.status);
        return r.json();
      });
      _browseCur = d.current || '';
      _browsePickable = !!d.registerable;
      _renderBrowse(d);
    } catch (e) {
      const l = document.getElementById('agent-browse-list');
      if (l) l.innerHTML = `<div style="color:#f88;font-size:12px;padding:6px">${_esc(e.message || e)}</div>`;
    }
  }
  function _renderBrowse(d) {
    const cur = document.getElementById('agent-browse-current');
    if (cur) cur.textContent = d.current || _t('agent.browse_roots', '(드라이브 / 홈)');
    const pick = document.getElementById('agent-browse-pick-btn');
    if (pick) { pick.disabled = !d.registerable; pick.style.opacity = d.registerable ? '1' : '.5'; }
    const list = document.getElementById('agent-browse-list');
    if (!list) return;
    let html = '';
    if (d.parent !== null && d.current) {
      html += `<div data-action="agent-browse-nav" data-path="${_esc(d.parent)}"
        style="padding:6px 8px;border-radius:6px;cursor:pointer;font-size:12px;
        font-family:var(--font-mono);background:var(--bg);border:1px solid var(--border)">⬑ ${
        _esc(_t('agent.browse_up', '상위 폴더'))}</div>`;
    }
    const entries = d.entries || [];
    if (!entries.length && d.current) {
      html += `<div style="color:var(--muted);font-size:12px;padding:6px">${
        _esc(_t('agent.browse_empty', '(하위 폴더 없음)'))}</div>`;
    }
    html += entries.map(en => `<div data-action="agent-browse-nav" data-path="${_esc(en.path)}"
      style="display:flex;justify-content:space-between;align-items:center;padding:6px 8px;
      border-radius:6px;cursor:pointer;font-size:12px;font-family:var(--font-mono);
      background:var(--bg);border:1px solid var(--border)">
      <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">📁 ${_esc(en.name)}</span>
      ${en.registerable ? '' : `<span style="color:#f88;font-size:10px" title="${_esc(_t('agent.browse_blocked', '등록 불가'))}">⛔</span>`}
    </div>`).join('');
    list.innerHTML = html;
  }
  function _pickBrowse() {
    if (!_browseCur || !_browsePickable) return;
    const inp = document.getElementById('agent-path-input');
    if (inp) inp.value = _browseCur;
    _closeBrowse();
    if (window.registerAgentPath) window.registerAgentPath();
  }

  /* ── Delegated click handler for the new actions ── */
  function _wsClick(e) {
    const el = e.target.closest && e.target.closest('[data-action]');
    if (!el) return;
    switch (el.getAttribute('data-action')) {
      case 'agent-session-new':    _newSession(); break;
      case 'agent-session-open':   _selectSession(el.getAttribute('data-sid')); break;
      case 'agent-session-del':    _deleteSession(el.getAttribute('data-sid'), e); break;
      case 'agent-model-refresh':  _loadAgentModels(true); break;
      case 'agent-model-save':     _saveAgentModel(); break;
      case 'agent-shell-toggle':   _toggleShell(); break;
      case 'agent-cloud-toggle':   _toggleAllowCloud(); break;
      case 'agent-browse-open':    _openBrowse(); break;
      case 'agent-browse-close':   _closeBrowse(); break;
      case 'agent-browse-nav':     _navBrowse(el.getAttribute('data-path')); break;
      case 'agent-browse-pick':    _pickBrowse(); break;
      default: return;
    }
  }

  /* Public: booted by admin.js loadAgentPage() when the page is shown. */
  window.bootAgentWorkspace = function bootAgentWorkspace() {
    if (!_wsBooted) {
      _wsBooted = true;
      document.addEventListener('click', _wsClick);
      // Switching backend (ollama ⇄ anthropic) re-fills the model
      // dropdown (Ollama models vs the Claude family) + cloud status.
      document.addEventListener('change', function (e) {
        if (e.target && e.target.id === 'agent-chat-backend') _populateModels();
      });
    }
    _loadSessions();
    _loadAgentModels(false);
  };
})();
