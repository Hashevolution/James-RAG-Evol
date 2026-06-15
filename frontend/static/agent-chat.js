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
    const payload = {
      api_key: _key(),
      message: msg,
      history: _history.slice(),
    };
    if (backend) payload.backend = backend;

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
    _appendNode(`
      <div style="align-self:flex-start;max-width:92%;background:var(--bg,#0f172a);border:1px solid var(--border,#334155);border-radius:8px;padding:8px 12px;font-family:var(--font-mono);font-size:11px;color:var(--text)">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <span><strong>${okIcon} ${_esc(call.name)}</strong>
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
})();
