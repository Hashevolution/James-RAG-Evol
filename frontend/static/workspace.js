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
let _srcTimer = null;  // v0.6.1 — 원본 자료 탭 검색 debounce
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
  // v0.6.1 — also drop the persisted api_key (auth.js writes it on
  // successful login).
  try { localStorage.removeItem('james_api_key'); } catch (_) {}
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

  const res = await Auth.login({ username, password, apiKey });
  if (!res.ok) { errEl.textContent = res.error; return; }
  // Auth.login already wrote token+role to localStorage; sync locals
  // and save apiKey separately (Auth doesn't manage api key).
  _saveStored(res.token, res.role, apiKey);
  closeLogin();
  document.getElementById('login-pw').value = '';
  updateRoleBadge();
  toast(`✅ ${username} (${_role}) 로그인`, 'success');
  reloadData();
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
  window.location.href = '/chat';
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
  // [v0.2.x CR-C] cr tab joins the rotation; keeping the id list
  // explicit so an unknown tab doesn't silently leave another panel
  // visible.
  for (const id of ['tab-data', 'tab-jobs', 'tab-search', 'tab-cr',
                    'tab-templates']) {
    const el = document.getElementById(id);
    if (el) el.style.display = id === `tab-${tab}` ? '' : 'none';
  }
  if (tab === 'data')      reloadData();
  if (tab === 'jobs')      reloadJobs();
  if (tab === 'cr')        reloadCrs();
  if (tab === 'templates') reloadTemplates();
  if (tab === 'search')    srcSearch();  // renders the hint / current results
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

/* ── 원본 자료 (source documents) tab — find → view → edit.
   Wires /admin/files/{search,view,download} + the wiki-edit modal.
   Design: docs/design/v0.6.1-workspace-source-documents-tab.md ── */
function _srcRoot() {
  const s = document.getElementById('src-root');
  return (s && s.value) || 'wiki';
}
function _srcStem(path) {
  const base = String(path || '').split('/').pop();
  return base.replace(/\.[^.]+$/, '');
}
function srcSearchDebounced() {
  if (_srcTimer) clearTimeout(_srcTimer);
  _srcTimer = setTimeout(() => srcSearch(), 250);
}
async function srcSearch() {
  const list = document.getElementById('src-results');
  if (!list) return;
  const qel = document.getElementById('src-q');
  const q = (qel && qel.value) || '';
  if (!q.trim()) {
    list.innerHTML = `<div style="padding:14px;font-size:12px;color:var(--muted)">${t('workspace.src_hint')}</div>`;
    return;
  }
  list.innerHTML = `<div style="padding:14px;font-size:12px;color:var(--muted)">…</div>`;
  try {
    const root = _srcRoot();
    const data = await _apiFetch(
      `/admin/files/search?q=${encodeURIComponent(q.trim())}&root=${encodeURIComponent(root)}`);
    const rows = data.matches || [];
    if (!rows.length) {
      list.innerHTML = `<div style="padding:14px;font-size:12px;color:var(--muted)">${t('workspace.src_no_match')}</div>`;
      return;
    }
    list.innerHTML = rows.map(r =>
      `<div data-action="src-open" data-path="${_esc(r.path)}" style="padding:8px 10px;border-bottom:1px solid var(--border);cursor:pointer">
         <div style="font-size:12px;color:var(--text);word-break:break-all">${_esc(r.name)}</div>
         <div style="font-size:10px;color:var(--muted)">${_esc(r.path)} · ${_fmtBytes(r.size)}</div>
       </div>`).join('')
      + (data.truncated ? `<div style="padding:8px;font-size:10px;color:var(--muted)">${t('workspace.src_truncated')}</div>` : '');
  } catch (e) {
    list.innerHTML = `<div style="padding:14px;font-size:12px;color:#e66">${_esc(e.message)}</div>`;
  }
}
async function srcOpen(path) {
  const view = document.getElementById('src-view');
  if (!view) return;
  const root = _srcRoot();
  const editable = (root === 'wiki' && /\.md$/i.test(path));
  const dlUrl = `${API}/admin/files/download?root=${encodeURIComponent(root)}&path=${encodeURIComponent(path)}&api_key=${encodeURIComponent(_apiKey || '')}`;
  const head =
    `<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap">
       <div style="font-weight:600;font-size:13px;flex:1;min-width:0;word-break:break-all">${_esc(path)}</div>
       ${editable ? `<button class="modal-btn primary" data-action="src-edit" data-path="${_esc(path)}">${t('workspace.src_edit')}</button>` : ''}
       <a class="modal-btn" href="${dlUrl}" target="_blank" rel="noopener">${t('workspace.src_download')}</a>
     </div>`;
  view.innerHTML = `<div style="padding:14px;font-size:12px;color:var(--muted)">…</div>`;
  try {
    const data = await _apiFetch(
      `/admin/files/view?root=${encodeURIComponent(root)}&path=${encodeURIComponent(path)}`);
    view.innerHTML = head +
      `<pre style="white-space:pre-wrap;word-break:break-word;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:12px;font-size:12px;max-height:60vh;overflow:auto">${_esc(data.content)}</pre>`;
  } catch (e) {
    // 415 (binary) / 413 (too big) → view unavailable, download still works.
    view.innerHTML = head +
      `<div style="padding:14px;font-size:12px;color:var(--muted)">${_esc(e.message)}<br>${t('workspace.src_download_only')}</div>`;
  }
}
function srcEdit(path) {
  // Hand off to the existing 추론편집(wiki-edit) modal, pre-loaded by the
  // filename stem (find_entity_file resolves entities by stem).
  if (typeof openWikiEdit !== 'function') return;
  openWikiEdit();
  const nm = document.getElementById('we-name');
  if (nm) nm.value = _srcStem(path);
  if (typeof wikiEditLoad === 'function') wikiEditLoad();
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

/* ── [v0.2.x CR-C] Change Request panel ──
 *
 * Backend contract:
 *   GET    /admin/cr/                  list      (auth user)
 *   GET    /admin/cr/{cr_id}           detail    (auth user)
 *   POST   /admin/cr/                  propose   (auth user)
 *   POST   /admin/cr/{cr_id}/approve   merge     (admin only)
 *   POST   /admin/cr/{cr_id}/reject    reject    (admin only)
 *   POST   /admin/cr/{cr_id}/review    comment   (auth user)
 *
 * The endpoints take api_key in the query / body and the JWT in
 * the Authorization header — same shape as the existing data /
 * jobs endpoints (_apiFetch handles the GET pattern; POST goes
 * through a hand-built fetch so the body can carry api_key + the
 * payload together, matching the FastAPI route signatures).
 */
let _currentCrId = null;

async function reloadCrs() {
  const body = document.getElementById('cr-body');
  if (!_token) {
    body.innerHTML =
      `<tr><td colspan="5" class="empty">${t('workspace.login_to_view')}</td></tr>`;
    return;
  }
  body.innerHTML =
    `<tr><td colspan="5" class="empty">${t('common.loading')}</td></tr>`;
  const status      = document.getElementById('cr-filter-status').value;
  const targetType  = document.getElementById('cr-filter-target').value;
  const scopeBadge  = document.getElementById('cr-scope-badge');
  scopeBadge.style.display = _isAdmin() ? 'inline-block' : 'none';

  const qs = new URLSearchParams();
  if (status)     qs.set('status', status);
  if (targetType) qs.set('target_type', targetType);
  qs.set('limit', '50');

  try {
    const data = await _apiFetch(`/admin/cr/?${qs.toString()}`);
    const items = data.items || [];
    document.getElementById('cr-counter').textContent = `${items.length}`;
    if (!items.length) {
      body.innerHTML =
        `<tr><td colspan="5" class="empty">${t('workspace.cr_empty')}</td></tr>`;
      return;
    }
    body.innerHTML = items.map(cr => {
      const statusBadge =
        `<span class="status-badge status-${cr.status}">${cr.status}</span>`;
      return `<tr style="cursor:pointer" data-action="cr-open" data-cr-id="${_esc(cr.cr_id)}">
        <td>${statusBadge}</td>
        <td class="mono" style="font-size:11px">${_esc(cr.target_type)}<br>
            <span style="color:var(--muted);font-size:10px">${_esc(cr.target_id)}</span></td>
        <td>${_esc(cr.title)}</td>
        <td class="mono">${_esc(cr.proposer)}</td>
        <td class="mono">${_fmtTs(cr.created_at)}</td>
      </tr>`;
    }).join('');
  } catch (e) {
    body.innerHTML =
      `<tr><td colspan="5" class="empty">${_esc(e.message)}</td></tr>`;
  }
}

async function openCr(crId) {
  _currentCrId = crId;
  const panel = document.getElementById('cr-detail-panel');
  const msg   = document.getElementById('cr-detail-msg');
  panel.style.display = 'block';
  msg.textContent = '';
  try {
    const data = await _apiFetch(`/admin/cr/${encodeURIComponent(crId)}`);
    _renderCrDetail(data.cr, data.reviews || []);
  } catch (e) {
    msg.textContent = `❌ ${e.message}`;
  }
}

function _renderCrDetail(cr, reviews) {
  document.getElementById('cr-detail-status-badge').textContent = cr.status;
  document.getElementById('cr-detail-status-badge').className =
    `status-badge status-${cr.status}`;
  document.getElementById('cr-detail-title').textContent  = cr.title || '—';
  document.getElementById('cr-detail-id').textContent     = cr.cr_id;
  document.getElementById('cr-detail-target').textContent =
    `${cr.target_type} · ${cr.target_id}`;
  document.getElementById('cr-detail-proposer').textContent = cr.proposer;
  document.getElementById('cr-detail-created').textContent  =
    _fmtTs(cr.created_at);

  // Merged / reject rows are conditional — only visible when relevant.
  const mergedRow = document.getElementById('cr-detail-merged-row');
  if (cr.status === 'merged' && cr.merged_at) {
    mergedRow.style.display = '';
    document.getElementById('cr-detail-merged').textContent =
      `${cr.merged_by || '?'} · ${_fmtTs(cr.merged_at)}`;
  } else {
    mergedRow.style.display = 'none';
  }
  const rejRow = document.getElementById('cr-detail-reject-row');
  if (cr.reject_reason) {
    rejRow.style.display = '';
    document.getElementById('cr-detail-reject').textContent = cr.reject_reason;
  } else {
    rejRow.style.display = 'none';
  }

  document.getElementById('cr-detail-description').textContent =
    cr.description || '(no description)';

  // proposed_diff arrives as a JSON string from the backend; pretty-
  // print when possible so reviewers don't have to read minified JSON.
  let diffText = cr.proposed_diff || '';
  try {
    diffText = JSON.stringify(JSON.parse(diffText), null, 2);
  } catch (_) { /* leave raw */ }
  document.getElementById('cr-detail-diff').textContent = diffText;

  const reviewsEl = document.getElementById('cr-detail-reviews');
  if (!reviews.length) {
    reviewsEl.innerHTML =
      `<div class="empty" style="font-size:11px">${t('workspace.cr_no_reviews')}</div>`;
  } else {
    reviewsEl.innerHTML = reviews.map(rv => `
      <div style="background:var(--bg);border:1px solid var(--border-2);
                  border-radius:6px;padding:8px 10px">
        <div style="font-size:11px;color:var(--muted);font-family:var(--font-mono);
                    display:flex;justify-content:space-between">
          <span>${_esc(rv.reviewer)} · ${_esc(rv.decision)}</span>
          <span>${_fmtTs(rv.created_at)}</span>
        </div>
        <div style="font-size:12px;margin-top:3px">${_esc(rv.body) || ''}</div>
      </div>
    `).join('');
  }

  // Action visibility — admin gets approve/reject on an open CR;
  // every auth user can comment. Closed CRs hide the action row.
  const approveBtn = document.getElementById('cr-approve-btn');
  const rejectBtn  = document.getElementById('cr-reject-btn');
  const isOpen     = cr.status === 'open';
  const isAdmin    = _isAdmin();
  approveBtn.style.display = (isOpen && isAdmin) ? 'inline-block' : 'none';
  rejectBtn .style.display = (isOpen && isAdmin) ? 'inline-block' : 'none';
}

function closeCrDetail() {
  _currentCrId = null;
  document.getElementById('cr-detail-panel').style.display = 'none';
}

function toggleCrPropose() {
  const f = document.getElementById('cr-propose-form');
  f.style.display = (f.style.display === 'none' || !f.style.display)
                    ? '' : 'none';
  document.getElementById('cr-propose-msg').textContent = '';
}

function cancelCrPropose() {
  document.getElementById('cr-propose-form').style.display = 'none';
}

async function submitCrPropose() {
  const msg = document.getElementById('cr-propose-msg');
  msg.textContent = '';
  const targetType = document.getElementById('cr-form-target-type').value;
  const targetId   = document.getElementById('cr-form-target-id').value.trim();
  const title      = document.getElementById('cr-form-title').value.trim();
  const description = document.getElementById('cr-form-description').value;
  const baseHash   = document.getElementById('cr-form-base-hash').value.trim();
  const bodyTxt    = document.getElementById('cr-form-body').value;
  if (!targetId || !title || !baseHash) {
    msg.textContent = '❌ target_id / title / base_hash 모두 필수';
    return;
  }
  // v0.2.x only supports {"op": "replace", "body": "..."} for
  // wiki_entity. run_jobs target lands in PR-CR-D — kept here so
  // the UI doesn't have to fork once that PR ships.
  const proposedDiff = (targetType === 'wiki_entity')
    ? { op: 'replace', body: bodyTxt }
    : { op: 'replace', body: bodyTxt };

  try {
    const r = await _crPost('/admin/cr/', {
      target_type:   targetType,
      target_id:     targetId,
      title,
      description,
      proposed_diff: proposedDiff,
      base_hash:     baseHash,
      labels:        [],
    });
    msg.textContent = `✅ 제안 생성 — ${r.cr.cr_id}`;
    cancelCrPropose();
    reloadCrs();
  } catch (e) {
    msg.textContent = `❌ ${e.message}`;
  }
}

async function submitCrApprove() {
  if (!_currentCrId) return;
  const msg = document.getElementById('cr-detail-msg');
  msg.textContent = '';
  if (!confirm(`승인 후 target 에 즉시 적용됩니다.\n${_currentCrId}\n계속할까요?`)) return;
  try {
    const r = await _crPost(
      `/admin/cr/${encodeURIComponent(_currentCrId)}/approve`, {},
    );
    msg.textContent = `✅ ${r.cr.status} — by ${r.cr.merged_by || ''}`;
    await openCr(_currentCrId);
    reloadCrs();
  } catch (e) {
    msg.textContent = `❌ ${e.message}`;
  }
}

async function submitCrReject() {
  if (!_currentCrId) return;
  const reason = prompt('거절 사유 (선택)') || '';
  const msg = document.getElementById('cr-detail-msg');
  msg.textContent = '';
  try {
    const r = await _crPost(
      `/admin/cr/${encodeURIComponent(_currentCrId)}/reject`,
      { reason },
    );
    msg.textContent = `✅ ${r.cr.status}`;
    await openCr(_currentCrId);
    reloadCrs();
  } catch (e) {
    msg.textContent = `❌ ${e.message}`;
  }
}

async function submitCrComment() {
  if (!_currentCrId) return;
  const bodyEl = document.getElementById('cr-comment-body');
  const body   = bodyEl.value.trim();
  const msg    = document.getElementById('cr-detail-msg');
  msg.textContent = '';
  if (!body) {
    msg.textContent = '❌ 코멘트 본문이 비었습니다';
    return;
  }
  try {
    await _crPost(
      `/admin/cr/${encodeURIComponent(_currentCrId)}/review`,
      { decision: 'comment', body },
    );
    bodyEl.value = '';
    msg.textContent = '✅ 코멘트 등록';
    await openCr(_currentCrId);
  } catch (e) {
    msg.textContent = `❌ ${e.message}`;
  }
}

async function _crPost(path, body) {
  // POST helper — folds api_key + payload together so the endpoint
  // signatures (which expect api_key in the body) get exactly what
  // they need. Mirrors how _apiFetch handles the GET case.
  const url = path;
  const r = await fetch(url, {
    method:  'POST',
    headers: {
      'Content-Type':  'application/json',
      ...(_token ? { Authorization: `Bearer ${_token}` } : {}),
    },
    body: JSON.stringify({ api_key: _apiKey || '', ...body }),
  });
  if (r.status === 401) {
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

/* ── v18.7 추론 편집 모달 ──────────────────────────────────────
   문서 불러오기 → 본문 드래그 선택 → 자연어 지시 → LLM 초안 →
   검토/수정 → 적용. base_hash 자동(운영자 SHA 손계산 불필요), 적용
   시 충돌 검사(409)로 동시편집 방지. 챗 wiki_edit 와 동일
   read_entity/update_entity 재사용 (백업+감사+벡터 동기화). */
let _weBaseHash = '';

function openWikiEdit() {
  if (!_isAdmin()) { toast('admin 전용 기능입니다.', 'error'); return; }
  _weBaseHash = '';
  const msg = document.getElementById('we-msg'); if (msg) msg.textContent = '';
  const nm = document.getElementById('we-name'); if (nm) nm.value = '';
  const body = document.getElementById('we-body'); if (body) body.textContent = '';
  const ins = document.getElementById('we-instruction'); if (ins) ins.value = '';
  const draft = document.getElementById('we-draft'); if (draft) draft.value = '';
  document.getElementById('we-body-wrap').style.display = 'none';
  document.getElementById('we-instruction-wrap').style.display = 'none';
  document.getElementById('we-draft-wrap').style.display = 'none';
  document.getElementById('we-apply-btn').style.display = 'none';
  const m = document.getElementById('wiki-edit-modal');
  if (m) m.classList.remove('hidden');
}

function closeWikiEdit() {
  const m = document.getElementById('wiki-edit-modal');
  if (m) m.classList.add('hidden');
}

async function wikiEditLoad() {
  const name = document.getElementById('we-name').value.trim();
  const msg = document.getElementById('we-msg');
  msg.textContent = '';
  if (!name) { msg.textContent = '❌ ENTITY 이름을 입력하세요.'; return; }
  try {
    const data = await _apiFetch(
      `/admin/wiki/edit/source?name=${encodeURIComponent(name)}`);
    if (!data.found) {
      msg.textContent = `❌ ${data.message || '문서를 찾을 수 없습니다.'}`;
      return;
    }
    document.getElementById('we-body').textContent = data.body || '';
    _weBaseHash = data.base_hash || '';
    document.getElementById('we-body-wrap').style.display = '';
    document.getElementById('we-instruction-wrap').style.display = '';
    document.getElementById('we-draft-wrap').style.display = 'none';
    document.getElementById('we-apply-btn').style.display = 'none';
    msg.textContent = `✅ 불러옴 (${(data.body || '').length}자)`;
  } catch (e) { msg.textContent = `❌ ${e.message}`; }
}

function _weCaptureSelection() {
  // 본문(#we-body) 안에서 드래그된 텍스트만 선택으로 인정.
  try {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return '';
    const body = document.getElementById('we-body');
    if (body && sel.anchorNode && body.contains(sel.anchorNode)) {
      return sel.toString();
    }
  } catch (_) {}
  return '';
}

async function wikiEditDraft() {
  const name = document.getElementById('we-name').value.trim();
  const instruction = document.getElementById('we-instruction').value.trim();
  const msg = document.getElementById('we-msg');
  msg.textContent = '';
  if (!name) { msg.textContent = '❌ 먼저 문서를 불러오세요.'; return; }
  if (!instruction) { msg.textContent = '❌ 편집 지시를 입력하세요.'; return; }
  const selected = _weCaptureSelection();
  const btn = document.getElementById('we-draft-btn');
  if (btn) { btn.disabled = true; btn.textContent = '초안 생성 중…'; }
  try {
    const data = await _crPost('/admin/wiki/edit/draft', {
      name, instruction, selected_text: selected,
    });
    document.getElementById('we-draft').value = data.draft_body || '';
    document.getElementById('we-model').textContent = `model: ${data.model || ''}`;
    _weBaseHash = data.base_hash || _weBaseHash;
    document.getElementById('we-draft-wrap').style.display = '';
    document.getElementById('we-apply-btn').style.display = '';
    msg.textContent = selected
      ? `✅ 초안 생성 (선택 ${selected.length}자 중심)`
      : '✅ 초안 생성 (문서 전체 대상)';
  } catch (e) {
    msg.textContent = `❌ ${e.message}`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '초안 생성'; }
  }
}

async function wikiEditApply() {
  const name = document.getElementById('we-name').value.trim();
  const newBody = document.getElementById('we-draft').value;
  const msg = document.getElementById('we-msg');
  msg.textContent = '';
  if (!newBody.trim()) { msg.textContent = '❌ 적용할 본문이 비었습니다.'; return; }
  if (!confirm(`'${name}' 문서에 편집을 적용합니다. 계속할까요?\n(변경 전 자동 백업됩니다)`)) return;
  const btn = document.getElementById('we-apply-btn');
  if (btn) { btn.disabled = true; btn.textContent = '적용 중…'; }
  try {
    const res = await _crPost('/admin/wiki/edit/apply', {
      name, new_body: newBody, base_hash: _weBaseHash,
    });
    // v0.6.1 — surface the cascade result (관계 무효화/추가/역방향/파생)
    // returned by update_entity so the operator sees what the edit did.
    toast((res && res.message) ? res.message : `✅ 적용 완료: ${name}`, 'success');
    closeWikiEdit();
    if (_currentTab === 'data') reloadData();
  } catch (e) {
    // 409 = 불러온 뒤 누군가 수정 → 충돌. 메시지로 재로드 유도.
    msg.textContent = `❌ ${e.message}`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '적용'; }
  }
}

/* ── [v0.6 template-formatting engine] Templates tab ──
 *
 * Backend contract (routes/templating.py):
 *   POST   /templates/                        register
 *   GET    /templates/mine/list               list (owner-scoped)
 *   GET    /templates/{id}                     detail + parsed spec
 *   DELETE /templates/{id}                     delete
 *   POST   /templates/{id}/apply               reshape raw → output
 *   GET    /templates/{id}/output/{out_id}     download
 *
 * All endpoints take api_key in the query and the JWT in the
 * Authorization header (same shape as the data / jobs / cr tabs).
 * GETs go through _apiFetch; the register/apply POSTs are hand-built
 * so the JSON body matches the FastAPI request models, and the
 * download goes through a blob fetch like downloadJob.
 */
let _currentTplId = null;
let _lastTplOutId = null;
/* How the TEMPLATE box was last filled — recorded so create posts the
   right `mode` (text / file / image). Reset to 'text' on manual edit. */
let _tplMode = 'text';

async function reloadTemplates() {
  const body = document.getElementById('tpl-body');
  if (!_token) {
    body.innerHTML =
      `<tr><td colspan="4" class="empty">${t('workspace.login_to_view')}</td></tr>`;
    return;
  }
  body.innerHTML = `<tr><td colspan="4" class="empty">${t('common.loading')}</td></tr>`;
  try {
    const data = await _apiFetch('/templates/mine/list');
    const items = data.items || [];
    document.getElementById('tpl-counter').textContent = `${items.length}`;
    if (!items.length) {
      body.innerHTML =
        `<tr><td colspan="4" class="empty">${t('workspace.tpl_empty')}</td></tr>`;
      return;
    }
    body.innerHTML = items.map(it => `
      <tr style="cursor:pointer" data-action="tpl-open"
          data-tpl-id="${_esc(it.id)}" data-tpl-name="${_esc(it.name)}">
        <td>${_esc(it.name)}</td>
        <td class="mono" style="font-size:11px">${_esc(it.mode || 'text')}</td>
        <td class="mono">${_fmtTs(_tsToSec(it.created_at))}</td>
        <td>
          <button data-action="tpl-delete" data-tpl-id="${_esc(it.id)}"
                  style="padding:4px 10px;background:transparent;border:1px solid var(--border);color:var(--muted);border-radius:4px;cursor:pointer;font-size:11px"
                  >${t('common.delete')}</button>
        </td>
      </tr>`).join('');
  } catch (e) {
    body.innerHTML = `<tr><td colspan="4" class="empty">${_esc(e.message)}</td></tr>`;
  }
}

/* created_at is an ISO-ish "%Y-%m-%dT%H:%M:%S" string from the store;
   _fmtTs wants epoch seconds, so convert (fall back gracefully). */
function _tsToSec(iso) {
  if (!iso) return 0;
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? 0 : Math.floor(ms / 1000);
}

function onTplFileChange() {
  const inp = document.getElementById('tpl-form-file');
  const f = inp && inp.files && inp.files[0];
  if (!f) return;
  const reader = new FileReader();
  reader.onload = () => {
    document.getElementById('tpl-form-raw').value = String(reader.result || '');
    _tplMode = 'file';
    if (!document.getElementById('tpl-form-name').value.trim()) {
      document.getElementById('tpl-form-name').value =
        f.name.replace(/\.[^.]+$/, '');
    }
  };
  reader.readAsText(f);
}

/* Image mode — POST the picked image to /templates/ingest-image; the
   server OCRs it (Tesseract, on-box) and returns the extracted text,
   which fills the TEMPLATE box for the operator to review + register.
   v0.6 — 두 input (사진첩 picker / 모바일 카메라 capture) 공유. */
async function onTplImageChange(srcId) {
  const id = srcId || 'tpl-form-image';
  const inp = document.getElementById(id);
  const f = inp && inp.files && inp.files[0];
  if (!f) return;
  const msg = document.getElementById('tpl-form-msg');
  msg.textContent = `⏳ OCR…`;
  try {
    const fd = new FormData();
    fd.append('file', f);
    const r = await fetch(
      `/templates/ingest-image?api_key=${encodeURIComponent(_apiKey || '')}`,
      {
        method: 'POST',
        headers: _token ? { Authorization: `Bearer ${_token}` } : {},
        body: fd,
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
    const data = await r.json();
    document.getElementById('tpl-form-raw').value = data.raw_text || '';
    _tplMode = data.mode || 'image';
    if (!document.getElementById('tpl-form-name').value.trim()) {
      document.getElementById('tpl-form-name').value =
        f.name.replace(/\.[^.]+$/, '');
    }
    msg.textContent = `✅ ${t('workspace.tpl_ocr_done')}`;
  } catch (e) {
    msg.textContent = `❌ ${e.message}`;
  } finally {
    inp.value = '';
  }
}

/* v0.6.1 — Document mode: POST `.docx` / `.pdf` / `.pptx` / `.xlsx` /
   `.hwp` to /templates/ingest-document; server (markitdown) extracts
   text. `.hwp` may fail on builds without a parser — the server surfaces
   an explicit "한글에서 .docx 로 저장 후 업로드" error rather than empty. */
async function onTplDocChange() {
  const inp = document.getElementById('tpl-form-doc');
  const f = inp && inp.files && inp.files[0];
  if (!f) return;
  const msg = document.getElementById('tpl-form-msg');
  msg.textContent = `⏳ ${t('workspace.tpl_doc_ingesting')}`;
  try {
    const fd = new FormData();
    fd.append('file', f);
    const r = await fetch(
      `/templates/ingest-document?api_key=${encodeURIComponent(_apiKey || '')}`,
      {
        method: 'POST',
        headers: _token ? { Authorization: `Bearer ${_token}` } : {},
        body: fd,
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
    const data = await r.json();
    document.getElementById('tpl-form-raw').value = data.raw_text || '';
    _tplMode = data.mode || 'document';
    if (!document.getElementById('tpl-form-name').value.trim()) {
      document.getElementById('tpl-form-name').value =
        f.name.replace(/\.[^.]+$/, '');
    }
    msg.textContent = `✅ ${t('workspace.tpl_doc_done')}`;
  } catch (e) {
    msg.textContent = `❌ ${e.message}`;
  } finally {
    inp.value = '';
  }
}

async function createTemplate() {
  const msg = document.getElementById('tpl-form-msg');
  msg.textContent = '';
  const name = document.getElementById('tpl-form-name').value.trim();
  const raw  = document.getElementById('tpl-form-raw').value;
  if (!name || !raw.trim()) {
    msg.textContent = `❌ ${t('workspace.tpl_need_name_raw')}`;
    return;
  }
  try {
    const meta = await _crPost('/templates/', {
      name, raw_text: raw, mode: _tplMode,
    });
    msg.textContent = `✅ ${meta.id}`;
    document.getElementById('tpl-form-name').value = '';
    document.getElementById('tpl-form-raw').value = '';
    const fileInp = document.getElementById('tpl-form-file');
    if (fileInp) fileInp.value = '';
    _tplMode = 'text';
    reloadTemplates();
  } catch (e) {
    msg.textContent = `❌ ${e.message}`;
  }
}

async function openTemplate(tplId, tplName) {
  _currentTplId = tplId;
  _lastTplOutId = null;
  const panel = document.getElementById('tpl-apply-panel');
  panel.style.display = 'block';
  document.getElementById('tpl-apply-name').textContent = tplName || tplId;
  document.getElementById('tpl-apply-id').textContent = tplId;
  document.getElementById('tpl-apply-msg').textContent = '';
  document.getElementById('tpl-result').style.display = 'none';
  document.getElementById('tpl-apply-content').value = '';
  const ph = document.getElementById('tpl-apply-placeholders');
  ph.innerHTML = `<span style="color:var(--muted);font-size:11px">${t('common.loading')}</span>`;
  try {
    const data = await _apiFetch(`/templates/${encodeURIComponent(tplId)}`);
    const placeholders = (data.spec && data.spec.placeholders) || [];
    ph.innerHTML = placeholders.length
      ? placeholders.map(p => `<span class="chip">${_esc(p)}</span>`).join('')
      : `<span style="color:var(--muted);font-size:11px">${t('workspace.tpl_no_placeholders')}</span>`;
    _renderTplOutputs(data.outputs || []);
  } catch (e) {
    ph.innerHTML = `<span style="color:var(--muted);font-size:11px">${_esc(e.message)}</span>`;
  }
}

function _renderTplOutputs(outputs) {
  const el = document.getElementById('tpl-apply-outputs');
  if (!outputs.length) {
    el.innerHTML = `<span style="color:var(--muted);font-size:11px">${t('workspace.tpl_no_outputs')}</span>`;
    return;
  }
  el.innerHTML = outputs.map(o => `
    <div style="display:flex;justify-content:space-between;align-items:center;
                background:var(--bg);border:1px solid var(--border-2);
                border-radius:6px;padding:6px 10px">
      <span class="mono" style="font-size:11px">${_esc(o.filename)}
        <span style="color:var(--muted)">· ${_fmtBytes(o.size)}</span></span>
      <button data-action="tpl-download-out" data-out-id="${_esc(o.out_id)}"
              style="padding:4px 10px;background:#1e7a3e;color:#fff;border:0;border-radius:4px;cursor:pointer;font-size:11px"
              >${t('workspace.tpl_download')}</button>
    </div>`).join('');
}

function closeTplApply() {
  _currentTplId = null;
  _lastTplOutId = null;
  document.getElementById('tpl-apply-panel').style.display = 'none';
}

async function applyTemplate() {
  if (!_currentTplId) return;
  const btn = document.getElementById('tpl-apply-btn');
  const msg = document.getElementById('tpl-apply-msg');
  msg.textContent = '';
  const raw_content = document.getElementById('tpl-apply-content').value;
  const fmt = document.getElementById('tpl-apply-fmt').value;
  const instructionEl = document.getElementById('tpl-apply-instruction');
  const instruction = (instructionEl && instructionEl.value || '').trim();
  if (!raw_content.trim()) {
    msg.textContent = `❌ ${t('workspace.tpl_need_content')}`;
    return;
  }
  btn.disabled = true;
  const orig = btn.textContent;
  btn.textContent = '⏳';
  try {
    const payload = { raw_content, fmt };
    if (instruction) payload.instruction = instruction;
    const r = await _crPost(
      `/templates/${encodeURIComponent(_currentTplId)}/apply`,
      payload,
    );
    _lastTplOutId = r.out_id;
    document.getElementById('tpl-result-preview').textContent = r.preview || '';
    document.getElementById('tpl-result').style.display = 'block';
    msg.textContent = `✅ ${r.filename}`;
    // Refresh outputs list so the new file shows up.
    const data = await _apiFetch(`/templates/${encodeURIComponent(_currentTplId)}`);
    _renderTplOutputs(data.outputs || []);
  } catch (e) {
    msg.textContent = `❌ ${e.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
}

async function downloadTemplateOutput(outId) {
  const id = outId || _lastTplOutId;
  if (!_currentTplId || !id) return;
  const path = `/templates/${encodeURIComponent(_currentTplId)}/output/${encodeURIComponent(id)}` +
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
    const name = m ? m[1] : `${id}.bin`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    toast(`❌ ${e.message}`, 'error');
  }
}

async function deleteTemplate(tplId) {
  if (!tplId) return;
  if (!confirm(t('workspace.tpl_confirm_delete'))) return;
  try {
    const r = await fetch(
      `/templates/${encodeURIComponent(tplId)}?api_key=${encodeURIComponent(_apiKey || '')}`,
      {
        method: 'DELETE',
        headers: _token ? { Authorization: `Bearer ${_token}` } : {},
      });
    if (!r.ok) {
      let detail = `${r.status}`;
      try { detail = (await r.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    toast('✅ 삭제 완료', 'success');
    if (_currentTplId === tplId) closeTplApply();
    reloadTemplates();
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
      /* ── 원본 자료 (source documents) tab ── */
      case 'src-open':         srcOpen(t.getAttribute('data-path')); break;
      case 'src-edit':         e.stopPropagation(); srcEdit(t.getAttribute('data-path')); break;
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
      /* ── [v0.2.x CR-C] Change Request panel actions ── */
      case 'cr-open':            openCr(t.getAttribute('data-cr-id')); break;
      case 'cr-close-detail':    closeCrDetail(); break;
      case 'cr-toggle-propose':  toggleCrPropose(); break;
      case 'cr-cancel-propose':  cancelCrPropose(); break;
      case 'cr-submit-propose':  submitCrPropose(); break;
      case 'cr-reload':          reloadCrs(); break;
      case 'cr-submit-approve':  submitCrApprove(); break;
      case 'cr-submit-reject':   submitCrReject(); break;
      case 'cr-submit-comment':  submitCrComment(); break;
      // v18.7 — 추론 편집 모달
      case 'wiki-edit-open':     openWikiEdit(); break;
      case 'wiki-edit-close':    closeWikiEdit(); break;
      case 'wiki-edit-load':     wikiEditLoad(); break;
      case 'wiki-edit-draft':    wikiEditDraft(); break;
      case 'wiki-edit-apply':    wikiEditApply(); break;
      /* ── [v0.6 template-formatting engine] actions ── */
      case 'tpl-reload':         reloadTemplates(); break;
      case 'tpl-create':         createTemplate(); break;
      case 'tpl-open':
        openTemplate(t.getAttribute('data-tpl-id'),
                     t.getAttribute('data-tpl-name'));
        break;
      case 'tpl-delete':
        e.stopPropagation();
        deleteTemplate(t.getAttribute('data-tpl-id'));
        break;
      case 'tpl-close-apply':    closeTplApply(); break;
      case 'tpl-apply':          applyTemplate(); break;
      case 'tpl-copy':           copyTemplatePreview(); break;
      case 'tpl-download':       downloadTemplateOutput(null); break;
      case 'tpl-download-out':
        downloadTemplateOutput(t.getAttribute('data-out-id'));
        break;
    }
  });
}

function _bindStableInputs() {
  const dq = document.getElementById('data-q');
  if (dq) dq.addEventListener('input', () => onDataSearchInput());
  /* v0.6.1 — 원본 자료 탭 검색(파일명) + root 전환. */
  const srcq = document.getElementById('src-q');
  if (srcq) srcq.addEventListener('input', () => srcSearchDebounced());
  const srcroot = document.getElementById('src-root');
  if (srcroot) srcroot.addEventListener('change', () => srcSearch());
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
  /* [v0.2.x CR-C] CR filter selects — reload on change. */
  const crStatus = document.getElementById('cr-filter-status');
  if (crStatus) crStatus.addEventListener('change', () => reloadCrs());
  const crTarget = document.getElementById('cr-filter-target');
  if (crTarget) crTarget.addEventListener('change', () => reloadCrs());
  /* [v0.6 template engine] file / image pickers fill the TEMPLATE
     textarea; a manual edit reverts the recorded source to 'text'. */
  const tplFile = document.getElementById('tpl-form-file');
  if (tplFile) tplFile.addEventListener('change', () => onTplFileChange());
  const tplImage = document.getElementById('tpl-form-image');
  if (tplImage) tplImage.addEventListener('change', () => onTplImageChange('tpl-form-image'));
  // v0.6 — 모바일 카메라 직접 진입 input; 같은 OCR 파이프라인 공유.
  const tplImageCam = document.getElementById('tpl-form-image-camera');
  if (tplImageCam) tplImageCam.addEventListener('change', () => onTplImageChange('tpl-form-image-camera'));
  // v0.6.1 — 문서 양식 등록 (.docx / .pdf / .pptx / .xlsx / .hwp).
  const tplDoc = document.getElementById('tpl-form-doc');
  if (tplDoc) tplDoc.addEventListener('change', () => onTplDocChange());
  const tplRaw = document.getElementById('tpl-form-raw');
  if (tplRaw) tplRaw.addEventListener('input', () => { _tplMode = 'text'; });
}

/* v0.6.1 — copy the formatted preview text to clipboard. Falls back to
   a hidden textarea + execCommand on contexts without clipboard API
   (http:// without secure context). */
async function copyTemplatePreview() {
  const pre = document.getElementById('tpl-result-preview');
  const msg = document.getElementById('tpl-apply-msg');
  const text = pre && pre.textContent || '';
  if (!text) return;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    if (msg) msg.textContent = `📋 ${t('workspace.tpl_copy_done')}`;
  } catch (e) {
    if (msg) msg.textContent = `❌ ${e.message}`;
  }
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
