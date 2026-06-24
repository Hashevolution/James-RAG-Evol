/* PROJECT JAMES — Workspace badge v0.6.1
 *
 * Fetches /workspace/info on load and populates the header badge
 * (`#workspace-badge` + `#workspace-name`) so the operator can tell
 * at a glance which workspace this JAMES instance is serving —
 * default vs dogfood-<date> vs research-cycle-γ etc.
 *
 * Auth: the endpoint requires a logged-in JWT subject. We piggyback
 * on the same `james_token` / `james_api_key` localStorage values the
 * chat / workspace / admin pages already use. If neither is present,
 * the badge stays hidden (no point showing "—" to a logged-out user).
 */
(function () {
  'use strict';

  function _tok() {
    try { return localStorage.getItem('james_token') || ''; } catch (_) { return ''; }
  }
  function _key() {
    try { return localStorage.getItem('james_api_key') || ''; } catch (_) { return ''; }
  }

  async function _fetchInfo() {
    var path = '/workspace/info';
    if (_key()) path += '?api_key=' + encodeURIComponent(_key());
    var headers = _tok() ? { Authorization: 'Bearer ' + _tok() } : {};
    var r = await fetch(path, { headers: headers });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }

  function _decorate(info) {
    var box = document.getElementById('workspace-badge');
    if (!box) return;
    var nameEl = document.getElementById('workspace-name');
    if (!nameEl) return;
    nameEl.textContent = info.workspace_name || 'default';
    // v0.6.1 v6 (2026-06-16) — operator catch: the badge said
    // "default" but the operator (Korean) couldn't tell what the
    // word meant. Tooltip now self-documents: name on top, then
    // "기본 workspace" / "사용자 workspace" + path + entities +
    // tenant flag. Hover-only — visual chrome stays compact.
    var name = info.workspace_name || 'default';
    var nameRow = 'Workspace: ' + name
      + (info.is_default ? ' (기본 / default)' : ' (사용자 선택)');
    var tooltipBits = [nameRow];
    if (info.workspace_path) tooltipBits.push('경로: ' + info.workspace_path);
    if (typeof info.entity_count === 'number') {
      tooltipBits.push('엔티티: ' + info.entity_count);
    }
    if (info.per_tenant_enabled) tooltipBits.push('per-tenant 격리 활성');
    if (info.is_default) {
      tooltipBits.push(
        '— 별도 workspace 를 만들지 않은 상태입니다. /workspace 페이지에서 분리 가능.'
      );
    }
    box.title = tooltipBits.join('\n');
    // Visually distinguish dogfood / non-default so the operator
    // immediately notices they're NOT on the main workspace.
    if (!info.is_default) {
      box.classList.add('workspace-badge-custom');
    } else {
      box.classList.remove('workspace-badge-custom');
    }
    box.style.display = '';
    box.classList.remove('d-none');  // markup hide is now .d-none (CSP migration)
  }

  async function _boot() {
    var box = document.getElementById('workspace-badge');
    if (!box) return;
    // Stay hidden until the fetch resolves so a logged-out page
    // doesn't flash a stale "—".
    box.style.display = 'none';
    if (!_tok() && !_key()) return;
    try {
      var info = await _fetchInfo();
      _decorate(info);
    } catch (_) {
      // 401 / network — quietly stay hidden. Operator sees the
      // login control instead.
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _boot);
  } else {
    _boot();
  }

  // Expose a small refresh hook so post-login flows can re-decorate.
  window.JAMES_WORKSPACE_BADGE = { refresh: _boot };
})();
