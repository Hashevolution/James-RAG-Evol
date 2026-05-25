/* ── llm-install.js ──
   Shared first-run / model install controller.

   Backend: POST /llm/install/ kicks off `ollama pull`; GET
   /admin/llm/install-progress?model=… returns { percent, status,
   completed, total, done, error }. Two UIs share these endpoints —
   the chat-tab install button (chat.js) and the admin first-run
   wizard modal (admin.js). The HTTP + polling machinery lives here;
   each caller plugs in its own UI rendering via callbacks.

   Usage:
     const c = LlmInstall.start('gemma3:1b', {
       onStart: (model) => …,
       onProgress: (p) => …,           // p = { percent, status, completed, total }
       onDone: (model) => …,
       onError: (err) => …,
       onUnauthorized: () => …,        // 401 from progress poll
     });
     c.stop();                          // cancel polling (HTTP install keeps running server-side)
*/
(function (global) {
  const API = window.location.origin;
  const POLL_MS = 2500;

  function _authHeaders() {
    const t = localStorage.getItem('james_token') || '';
    const h = { 'Content-Type': 'application/json' };
    if (t) h['Authorization'] = `Bearer ${t}`;
    return h;
  }

  function _apiKey() {
    return localStorage.getItem('james_api_key') || '';
  }

  function start(model, cb) {
    cb = cb || {};
    let timer = null;
    const stop = () => {
      if (timer) { clearInterval(timer); timer = null; }
    };

    const tick = async () => {
      try {
        const r = await fetch(
          `${API}/admin/llm/install-progress?api_key=${encodeURIComponent(_apiKey())}&model=${encodeURIComponent(model)}`,
          { headers: _authHeaders() },
        );
        if (!r.ok) {
          if (r.status === 401) {
            stop();
            if (cb.onUnauthorized) cb.onUnauthorized();
          }
          return;
        }
        const p = await r.json();
        if (p.error) {
          stop();
          if (cb.onError) cb.onError(new Error(p.error));
          return;
        }
        if (p.done) {
          stop();
          if (cb.onDone) cb.onDone(model);
          return;
        }
        if (cb.onProgress) cb.onProgress(p);
      } catch (e) {
        console.warn('[llm-install poll]', e);
      }
    };

    (async () => {
      try {
        const r = await fetch(
          `${API}/llm/install/?api_key=${encodeURIComponent(_apiKey())}&model=${encodeURIComponent(model)}`,
          { method: 'POST', headers: _authHeaders() },
        );
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${r.status}`);
        }
        if (cb.onStart) cb.onStart(model);
        tick();
        timer = setInterval(tick, POLL_MS);
      } catch (e) {
        if (cb.onError) cb.onError(e);
      }
    })();

    return { stop };
  }

  global.LlmInstall = { start };
})(window);
