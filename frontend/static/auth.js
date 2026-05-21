/* ── auth.js ──
   Shared /login/ HTTP wrapper for all pages (chat, admin, graph,
   workspace).

   Login modals stay per-page — markup, DOM ids, and post-login UX
   diverge by design (chat shows chat UI, admin loads dashboard,
   graph runs bootstrap, workspace reloads data). What used to be
   duplicated was the POST + token parse + role check + localStorage
   write. That now lives here.

   Usage:
     const res = await Auth.login({
       username, password, apiKey,
       requireRole: 'admin',   // or null to accept any role
     });
     if (!res.ok) { showError(res.error); return; }
     // res.token, res.role available; localStorage already written.
     // Caller does its own post-login UI (close modal, reload, etc.)
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
      return { ok: true, token, role };
    } catch (e) {
      return { ok: false, error: `서버 오류: ${e.message || e}` };
    }
  }

  global.Auth = { login };
})(window);
