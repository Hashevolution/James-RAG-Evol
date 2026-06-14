/* ── auth.js ──
   Shared auth HTTP wrappers for all pages (chat, admin, graph,
   workspace).

   Login modals stay per-page — markup, DOM ids, and post-login UX
   diverge by design (chat shows chat UI, admin loads dashboard,
   graph runs bootstrap, workspace reloads data). What used to be
   duplicated was the POST + token parse + role check + localStorage
   write. That now lives here.

   The password-reset-confirm endpoint is anonymous (no Bearer,
   no api_key query) and was duplicated near-verbatim between
   chat.js and admin.js — same fetch shape, same response handling,
   only the surrounding UX (toast vs alert) differed.

   Usage:
     const res = await Auth.login({
       username, password, apiKey,
       requireRole: 'admin',   // or null to accept any role
     });
     if (!res.ok) { showError(res.error); return; }
     // res.token, res.role available; localStorage already written.

     const res = await Auth.resetPasswordConfirm({
       username, token, newPassword,
     });
     if (!res.ok) { showError(res.error); return; }
*/
(function (global) {
  const API = window.location.origin;

  async function login(opts) {
    opts = opts || {};
    const username = (opts.username || '').trim();
    const password = opts.password || '';
    const apiKey = opts.apiKey || '';
    const requireRole = opts.requireRole || null;

    if (!username || !password) {
      return { ok: false, error: '아이디와 비밀번호를 입력하세요.' };
    }
    if (!apiKey) {
      return { ok: false, error: 'API Key를 입력하세요.' };
    }

    try {
      const r = await fetch(`${API}/login/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, api_key: apiKey }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        return { ok: false, error: d.detail || `로그인 실패 (${r.status})` };
      }
      const token = d.access_token || d.token || '';
      const role = d.role || 'external';
      if (!token) {
        return { ok: false, error: '토큰 발급 실패' };
      }
      if (requireRole && role !== requireRole) {
        return { ok: false, error: `${requireRole} 권한 필요 (현재: ${role})` };
      }
      // SSO: chat / admin / graph / workspace 탭이 storage 이벤트로
      // 자동 동기화되도록 동일 키 사용.
      localStorage.setItem('james_token', token);
      localStorage.setItem('james_role', role);
      // v0.6.1 — refresh the workspace badge after a successful login
      // so the operator sees the correct workspace immediately rather
      // than after a full page reload.
      try {
        if (window.JAMES_WORKSPACE_BADGE &&
            typeof window.JAMES_WORKSPACE_BADGE.refresh === 'function') {
          window.JAMES_WORKSPACE_BADGE.refresh();
        }
      } catch (_) { /* badge wiring is optional */ }
      return { ok: true, token, role };
    } catch (e) {
      return { ok: false, error: `서버 오류: ${e.message || e}` };
    }
  }

  async function resetPasswordConfirm(opts) {
    opts = opts || {};
    const username = (opts.username || '').trim();
    const token = (opts.token || '').trim();
    const newPassword = opts.newPassword || '';

    if (!username || !token || !newPassword) {
      return { ok: false, error: '아이디, 토큰, 새 비밀번호를 모두 입력하세요.' };
    }

    try {
      // Bare fetch — no Bearer header (anonymous flow), no api_key
      // query (the endpoint is public). Token-error responses
      // collapse to 401 by design (enumeration defense).
      const r = await fetch(`${API}/password/reset/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, token, new_password: newPassword }),
      });
      if (r.ok) return { ok: true };
      let detail = `${r.status}`;
      try { detail = (await r.json()).detail || detail; } catch (_e) {}
      return { ok: false, error: detail };
    } catch (e) {
      return { ok: false, error: `서버 오류: ${e.message || e}` };
    }
  }

  global.Auth = { login, resetPasswordConfirm };
})(window);
