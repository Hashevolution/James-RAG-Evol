/* W7-B — workspace page client.

   Shares localStorage keys with chat.js / admin.js so login state
   propagates across all three pages:
     james_token   — JWT
     james_role    — last resolved role (admin/manager/employee/external)
     james_api_key — system api_key (set on chat page; reused here)

   The page is mode-agnostic: it always tries the admin endpoint first
   when the cached role is "admin", otherwise the /artifacts/mine/*
   endpoint. The data-scope-badge in the UI reflects which path was used.
*/
'use strict';

const API = '';
const PAGE_SIZE = 50;

let _token   = '';
let _role    = '';
let _apiKey  = '';
let _dataOffset = 0;
let _dataTotal  = 0;
let _searchTimer = null;
let _currentTab = 'data';

function _loadStored() {
  _token  = localStorage.getItem('james_token')   || '';
  _role   = localStorage.getItem('james_role')    || '';
  _apiKey = localStorage.getItem('james_api_key') || '';
}

function _saveStored(token, role, apiKey) {
  if (token  !== undefined) { _token  = token;  localStorage.setItem('james_token', token); }
  if (role   !== undefined) { _role   = role;   localStorage.setItem('james_role',  role);  }
  if (apiKey !== undefined) {
    _apiKey = apiKey;
    if (apiKey) localStorage.setItem('james_api_key', apiKey);
  }
}

function _clearStored() {
  _token = ''; _role = '';
  localStorage.removeItem('james_token');
  localStorage.removeItem('james_role');
}

/* ── i18n helper alias (mirrors chat.js's `t()`) ── */
function t(key) {
  try {
    if (typeof window.t === 'function') return window.t(key);
    if (typeof translations !== 'undefined') {
      const lang = localStorage.getItem('james_lang') || 'ko';
      return (translations[lang] && translations[lang][key]) || key;
    }
  } catch (_) {}
  return key;
}

/* ── toast ── */
let _toastTimer = null;
function toast(msg, kind = '') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = `toast show ${kind}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), 2200);
}

/* ── auth ── */
function showLogin() {
  document.getElementById('login-modal').classList.remove('hidden');
  document.getElementById('login-error').textContent = '';
  // Pre-fill api_key from localStorage so users don't re-type.
  const ak = document.getElementById('login-apikey');
  if (ak && _apiKey) ak.value = _apiKey;
  document.getElementById('login-id').focus();
}

function closeLogin() {
  document.getElementById('login-modal').classList.add('hidden');
}

async function doLogin() {
  const username = document.getElementById('login-id').value.trim();
  const password = document.getElementById('login-pw').value;
  const apiKey   = document.getElementById('login-apikey').value.trim() || _apiKey;
  const errEl    = document.getElementById('login-error');
  errEl.textContent = '';
  if (!username || !password) {
    errEl.textContent = '아이디와 비밀번호를 입력하세요.';
    return;
  }
  if (!apiKey) {
    errEl.textContent = 'API Key 를 입력하세요.';
    return;
  }
  try {
    const r = await fetch(`${API}/login/`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ username, password, api_key: apiKey }),
    });
    const data = await r.json();
    if (!r.ok) {
      errEl.textContent = data.detail || '로그인 실패';
      return;
    }
    _saveStored(data.access_token || data.token, data.role || 'employee', apiKey);
    closeLogin();
    document.getElementById('login-pw').value = '';
    updateRoleBadge();
    toast(`✅ ${username} (${_role}) 로그인`, 'success');
    reloadData();
  } catch (e) {
    errEl.textContent = `서버 오류: ${e.message}`;
  }
}

function doLogout() {
  _clearStored();
  updateRoleBadge();
  toast('로그아웃 완료', 'success');
  // Repaint the data tab with the empty state.
  document.getElementById('data-body').innerHTML =
    `<tr><td colspan="5" class="empty">${t('workspace.login_to_view')}</td></tr>`;
}

function updateRoleBadge() {
  const badge = document.getElementById('role-badge');
  const who   = document.getElementById('role-who');
  const name  = document.getElementById('role-name');
  const loginBtn  = document.getElementById('login-btn');
  const logoutBtn = document.getElementById('logout-btn');
  if (_token && _role) {
    who.textContent  = _usernameFromToken();
    name.textContent = `· ${_role}`;
    badge.style.display = 'inline-block';
    loginBtn.style.display  = 'none';
    logoutBtn.style.display = 'inline-block';
  } else {
    badge.style.display = 'none';
    loginBtn.style.display  = 'inline-block';
    logoutBtn.style.display = 'none';
  }
}

function _usernameFromToken() {
  if (!_token) return '';
  try {
    const parts = _token.split('.');
    if (parts.length !== 3) return '';
    let b = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    b += '='.repeat((4 - b.length % 4) % 4);
    return JSON.parse(atob(b)).sub || '';
  } catch (_) { return ''; }
}

/* Forgot-password — reuse the chat page flow rather than duplicating
   the modal here. Sends the user back to /chat once they're done. */
function openForgot() {
  closeLogin();
  // Simple punt: navigate to the chat page where the existing
  // forgot-password modal lives. Returning here is the user's choice.
  window.location.href = '/';
}

/* ── data tab — main feature ── */
function _isAdmin() { return _role === 'admin'; }

async function _apiFetch(path) {
  // Build URL: api_key in query for compatibility with existing
  // server pattern. JWT in Authorization header so the server can
  // resolve role from the same Bearer it expects elsewhere.
  const sep = path.includes('?') ? '&' : '?';
  const url = `${API}${path}${sep}api_key=${encodeURIComponent(_apiKey || '')}`;
  const r = await fetch(url, {
    headers: _token ? { Authorization: `Bearer ${_token}` } : {},
  });
  if (r.status === 401) {
    // Token invalid / expired → clear state, force a re-login.
    _clearStored();
    updateRoleBadge();
    showLogin();
    throw new Error('인증이 만료되었습니다. 다시 로그인하세요.');
  }
  if (!r.ok) {
    let detail = `${r.status}`;
    try { detail = (await r.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return r.json();
}

function selectTab(tab) {
  _currentTab = tab;
  document.querySelectorAll('nav .nav-item').forEach(el =>
    el.classList.toggle('active', el.dataset.tab === tab));
  for (const id of ['tab-data', 'tab-jobs', 'tab-search']) {
    const el = document.getElementById(id);
    if (el) el.style.display = id === `tab-${tab}` ? '' : 'none';
  }
  if (tab === 'data') reloadData();
  if (tab === 'jobs') reloadJobs();
}

function onDataSearchInput() {
  if (_searchTimer) clearTimeout(_searchTimer);
  _searchTimer = setTimeout(() => {
    _dataOffset = 0;
    reloadData();
  }, 250);
}

function dataPage(delta) {
  const next = _dataOffset + delta * PAGE_SIZE;
  if (next < 0) return;
  if (next >= _dataTotal && delta > 0) return;
  _dataOffset = next;
  reloadData();
}

function _fmtBytes(n) {
  if (n == null) return '-';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n/1024).toFixed(1)} KB`;
  return `${(n/(1024*1024)).toFixed(1)} MB`;
}

function _fmtTs(sec) {
  if (!sec) return '-';
  try {
    const d = new Date(sec * 1000);
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch (_) { return '-'; }
}

function _esc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                  .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function reloadData() {
  const body = document.getElementById('data-body');
  if (!_token) {
    body.innerHTML = `<tr><td colspan="5" class="empty">${t('workspace.login_to_view')}</td></tr>`;
    return;
  }
  body.innerHTML = `<tr><td colspan="5" class="empty">${t('common.loading')}</td></tr>`;

  const q       = document.getElementById('data-q').value.trim();
  const status  = document.getElementById('data-status').value;
  const adminPath = _isAdmin();
  const root = adminPath ? '/admin/artifacts/list' : '/artifacts/mine/list';

  const scopeBadge = document.getElementById('data-scope-badge');
  scopeBadge.style.display = adminPath ? 'inline-block' : 'none';
  scopeBadge.textContent   = adminPath ? 'ADMIN (전체 사용자)' : '';

  // Hide uploader column on /mine/ — every row has the same uploader.
  document.getElementById('th-uploader').style.display = adminPath ? '' : 'none';

  const params = new URLSearchParams({
    limit:  String(PAGE_SIZE),
    offset: String(_dataOffset),
  });
  if (q)      params.set('q', q);
  if (status) params.set('status', status);

  try {
    const data = await _apiFetch(`${root}?${params.toString()}`);
    _dataTotal = data.total || 0;

    const counter = document.getElementById('data-counter');
    const from = _dataTotal ? _dataOffset + 1 : 0;
    const to   = Math.min(_dataOffset + PAGE_SIZE, _dataTotal);
    counter.textContent = `${from}–${to} / ${_dataTotal}`;

    const pageinfo = document.getElementById('data-pageinfo');
    pageinfo.textContent = `page ${Math.floor(_dataOffset / PAGE_SIZE) + 1}`;
    document.getElementById('data-prev').disabled = _dataOffset === 0;
    document.getElementById('data-next').disabled = _dataOffset + PAGE_SIZE >= _dataTotal;

    if (!(data.items || []).length) {
      body.innerHTML = `<tr><td colspan="5" class="empty">${t('workspace.empty')}</td></tr>`;
      return;
    }

    body.innerHTML = data.items.map(it => {
      const status = it.status || 'unknown';
      const uploaderCell = adminPath
        ? `<td class="mono">${_esc(it.uploaded_by || '-')}</td>`
        : '';
      return `<tr data-action="open-detail" data-artifact-id="${_esc(it.artifact_id)}" style="cursor:pointer">
        <td>${_esc(it.origin_name || '')}
            <span style="color:var(--muted);font-size:10px;display:block;font-family:var(--font-mono)">${_fmtBytes(it.origin_size)}</span>
        </td>
        ${uploaderCell}
        <td class="mono">${_fmtTs(it.uploaded_at)}</td>
        <td><span class="status-badge status-${status}">${status}</span></td>
        <td class="mono" style="text-align:center">${it.entity_count || 0}</td>
      </tr>`;
    }).join('');
  } catch (e) {
    body.innerHTML = `<tr><td colspan="5" class="empty">${_esc(e.message)}</td></tr>`;
  }
}

async function openDetail(artifactId) {
  const root = _isAdmin() ? '/admin/artifacts' : '/artifacts/mine';
  try {
    const it = await _apiFetch(`${root}/${encodeURIComponent(artifactId)}`);
    document.getElementById('detail-title').textContent = it.origin_name || '-';
    document.getElementById('d-id').textContent       = it.artifact_id;
    document.getElementById('d-path').textContent     = it.origin_path;
    document.getElementById('d-size').textContent     = _fmtBytes(it.origin_size);
    document.getElementById('d-uploader').textContent = it.uploaded_by || '-';
    document.getElementById('d-time').textContent     = _fmtTs(it.uploaded_at);
    document.getElementById('d-status').textContent   = it.status || '-';
    const ents = document.getElementById('d-entities');
    if (!it.entities || !it.entities.length) {
      ents.innerHTML = `<span style="color:var(--muted);font-size:11px">${t('workspace.no_entities')}</span>`;
    } else {
      ents.innerHTML = it.entities.map(e =>
        `<span class="chip">${_esc(e)}</span>`).join('');
    }
    document.getElementById('detail-panel').classList.add('open');
  } catch (e) {
    toast(`❌ ${e.message}`, 'error');
  }
}

function closeDetail() {
  document.getElementById('detail-panel').classList.remove('open');
}

/* ── W8-B: jobs tab ── */

function onJobTypeChange() {
  const t = document.getElementById('job-type').value;
  const hintEl = document.getElementById('job-input-hint');
  const labelEl = document.getElementById('job-input-label');
  const refsEl  = document.getElementById('job-input-refs');
  if (t === 'entity_export') {
    labelEl.textContent = 'CATEGORIES';
    if (hintEl) hintEl.textContent = (window.t && window.t('workspace.refs_hint_export'))
      || '예: concept, document · 빈 칸이면 모든 카테고리를 내보냅니다.';
    refsEl.placeholder = '예: concept, document  (비워두면 전체)';
  } else if (t === 'doc_combine') {
    labelEl.textContent = 'ENTITY IDS';
    if (hintEl) hintEl.textContent = (window.t && window.t('workspace.refs_hint_doc'))
      || '예: ent_001, ent_042 · 각 entity 의 markdown 본문이 연결됩니다.';
    refsEl.placeholder = '예: ent_001, ent_042';
  } else {
    labelEl.textContent = 'ENTITY IDS';
    if (hintEl) hintEl.textContent = (window.t && window.t('workspace.refs_hint_excel'))
      || '예: ent_001, ent_042 · 빈 항목은 자동으로 생략됩니다.';
    refsEl.placeholder = '예: ent_001, ent_042';
  }
}

async function runJob() {
  const btn = document.getElementById('run-job-btn');
  const job_type = document.getElementById('job-type').value;
  const rawRefs  = document.getElementById('job-input-refs').value || '';
  const input_refs = rawRefs.split(',').map(s => s.trim()).filter(Boolean);

  btn.disabled = true;
  const origText = btn.textContent;
  btn.textContent = '⏳';
  try {
    const r = await fetch(`${API}/jobs/run?api_key=${encodeURIComponent(_apiKey || '')}`, {
      method:  'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(_token ? { Authorization: `Bearer ${_token}` } : {}),
      },
      body: JSON.stringify({ job_type, input_refs }),
    });
    if (r.status === 401) {
      _clearStored(); updateRoleBadge(); showLogin();
      throw new Error('인증 만료 — 재로그인 필요');
    }
    if (!r.ok) {
      let detail = `${r.status}`;
      try { detail = (await r.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    const row = await r.json();
    if (row.status === 'done') {
      toast(`✅ ${job_type} 완료`, 'success');
    } else {
      toast(`❌ ${job_type}: ${row.status}`, 'error');
    }
    document.getElementById('job-input-refs').value = '';
    reloadJobs();
  } catch (e) {
    toast(`❌ ${e.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = origText;
  }
}

async function reloadJobs() {
  const body = document.getElementById('jobs-body');
  if (!_token) {
    body.innerHTML = `<tr><td colspan="6" class="empty">${t('workspace.login_to_view')}</td></tr>`;
    return;
  }
  body.innerHTML = `<tr><td colspan="6" class="empty">${t('common.loading')}</td></tr>`;
  const adminPath = _isAdmin();
  const root = adminPath ? '/admin/jobs/list' : '/jobs/list';

  const scopeBadge = document.getElementById('jobs-scope-badge');
  scopeBadge.style.display = adminPath ? 'inline-block' : 'none';
  scopeBadge.textContent   = adminPath ? 'ADMIN (전체 사용자)' : '';

  // Owner column visible only in admin view.
  const ownerTh = document.getElementById('th-job-owner');
  if (ownerTh) ownerTh.style.display = adminPath ? '' : 'none';

  try {
    const data = await _apiFetch(`${root}?limit=50`);
    const counter = document.getElementById('jobs-counter');
    counter.textContent = `${(data.items || []).length} / ${data.total || 0}`;
    if (!(data.items || []).length) {
      body.innerHTML = `<tr><td colspan="6" class="empty">${t('workspace.no_jobs')}</td></tr>`;
      return;
    }
    body.innerHTML = data.items.map(j => {
      const status = j.status || 'pending';
      const ownerCell = adminPath
        ? `<td class="mono">${_esc(j.owner || '-')}</td>` : '';
      const resultCell = j.output_path
        ? `<span class="mono" style="font-size:10px;color:var(--muted)">${_esc(j.output_path.split('/').pop())}</span>`
        : '<span style="color:var(--muted)">—</span>';
      const dlBtn = (j.status === 'done' && j.output_path)
        ? `<button data-action="download-job" data-job-id="${_esc(j.job_id)}" data-admin="${adminPath ? 'true' : 'false'}"
                   style="padding:4px 10px;background:#1e7a3e;color:#fff;border:0;border-radius:4px;cursor:pointer;font-size:11px">다운로드</button>`
        : (j.status === 'failed'
            ? `<button data-action="show-job-error" data-job-id="${_esc(j.job_id)}" data-admin="${adminPath ? 'true' : 'false'}"
                       style="padding:4px 10px;background:transparent;border:1px solid var(--border);color:var(--muted);border-radius:4px;cursor:pointer;font-size:11px">에러 보기</button>`
            : '<span style="color:var(--muted)">—</span>');
      return `<tr>
        <td class="mono">${_esc(j.job_type)}</td>
        <td class="mono">${_fmtTs(j.created_at)}</td>
        <td><span class="status-badge status-${status}">${status}</span></td>
        ${ownerCell}
        <td>${resultCell}</td>
        <td>${dlBtn}</td>
      </tr>`;
    }).join('');
  } catch (e) {
    body.innerHTML = `<tr><td colspan="6" class="empty">${_esc(e.message)}</td></tr>`;
  }
}

async function downloadJob(jobId, isAdminView) {
  // Admin's view can't reuse the user's /jobs/{id}/download — that
  // endpoint requires owner match. For admin diagnosis we just hit
  // the /admin/jobs/{id} detail and rely on the row's output_path,
  // served back by /jobs/{id}/download when the admin owns it, OR
  // by navigating to /workspace/results/... if we expose a static
  // mount. For now: admin uses the same /jobs/{id}/download path —
  // they get 404 if not owner (matrix override grants explicit
  // cross-owner read). Operators can still inspect via /admin/jobs/{id}.
  const path = `/jobs/${encodeURIComponent(jobId)}/download` +
               `?api_key=${encodeURIComponent(_apiKey || '')}`;
  try {
    const r = await fetch(path, {
      headers: _token ? { Authorization: `Bearer ${_token}` } : {},
    });
    if (!r.ok) {
      let detail = `${r.status}`;
      try { detail = (await r.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    const blob = await r.blob();
    const cd = r.headers.get('Content-Disposition') || '';
    const m  = /filename="?([^"]+)"?/.exec(cd);
    const name = m ? m[1] : `job-${jobId}.bin`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    toast(`❌ ${e.message}`, 'error');
  }
}

async function showJobError(jobId, isAdminView) {
  const root = isAdminView ? '/admin/jobs' : '/jobs';
  try {
    const row = await _apiFetch(`${root}/${encodeURIComponent(jobId)}`);
    alert(`Job ${jobId}\n\nstatus: ${row.status}\n\n${row.error || '(no detail)'}`);
  } catch (e) {
    toast(`❌ ${e.message}`, 'error');
  }
}

/* ── lang toggle (chat.js pattern) ── */
function toggleLang() {
  const cur = localStorage.getItem('james_lang') || 'ko';
  const next = cur === 'ko' ? 'en' : 'ko';
  localStorage.setItem('james_lang', next);
  location.reload();
}

/* ── Inline-handler migration (CSP-friendly delegation) ──
 * workspace.html no longer uses ``onclick=`` / ``onchange=`` /
 * ``oninput=`` / ``onkeydown=`` / ``href="javascript:…"`` inline
 * attributes. Static elements carry ``data-action`` and the
 * document-level click delegate routes by name. Stable inputs
 * (search, status select, job type select, login modal fields)
 * are wired directly by id since they live for the lifetime of
 * the page and don't appear in any innerHTML template. */
function _bindFrontendEvents() {
  document.addEventListener('click', (e) => {
    const t = e.target.closest && e.target.closest('[data-action]');
    if (!t) return;
    const action = t.getAttribute('data-action');
    switch (action) {
      case 'toggle-lang':      toggleLang(); break;
      case 'show-login':       showLogin(); break;
      case 'do-logout':        doLogout(); break;
      case 'select-tab':       selectTab(t.getAttribute('data-tab')); break;
      case 'data-page-prev':   dataPage(-1); break;
      case 'data-page-next':   dataPage(1); break;
      case 'run-job':          runJob(); break;
      case 'reload-jobs':      reloadJobs(); break;
      case 'close-detail':     closeDetail(); break;
      case 'close-login':      closeLogin(); break;
      case 'do-login':         doLogin(); break;
      case 'open-forgot':      e.preventDefault(); openForgot(); break;
      case 'open-detail':      openDetail(t.getAttribute('data-artifact-id')); break;
      case 'download-job':
        downloadJob(
          t.getAttribute('data-job-id'),
          t.getAttribute('data-admin') === 'true',
        );
        break;
      case 'show-job-error':
        showJobError(
          t.getAttribute('data-job-id'),
          t.getAttribute('data-admin') === 'true',
        );
        break;
    }
  });
}

function _bindStableInputs() {
  const dq = document.getElementById('data-q');
  if (dq) dq.addEventListener('input', () => onDataSearchInput());
  const dstat = document.getElementById('data-status');
  if (dstat) dstat.addEventListener('change', () => reloadData());
  const jt = document.getElementById('job-type');
  if (jt) jt.addEventListener('change', () => onJobTypeChange());
  const lpw = document.getElementById('login-pw');
  if (lpw) lpw.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') doLogin();
  });
  const lkey = document.getElementById('login-apikey');
  if (lkey) lkey.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') doLogin();
  });
}

/* ── boot ── */
window.addEventListener('DOMContentLoaded', () => {
  _bindFrontendEvents();
  _bindStableInputs();
  _loadStored();
  updateRoleBadge();
  if (!_token) {
    document.getElementById('data-body').innerHTML =
      `<tr><td colspan="5" class="empty">${t('workspace.login_to_view')}</td></tr>`;
    showLogin();
  } else {
    reloadData();
  }
});

// Cross-tab sync — log out / in elsewhere reflects here.
window.addEventListener('storage', (e) => {
  if (e.key === 'james_token' || e.key === 'james_role') {
    _loadStored();
    updateRoleBadge();
    if (_token) reloadData();
  }
});
