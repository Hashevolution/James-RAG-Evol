/* PROJECT JAMES — Admin JS */

// Same-origin: works on PC (http://127.0.0.1:8000), phone via
// Tailscale Serve (https://james.xxx.ts.net), or any future reverse
// proxy. Avoids the mixed-content block when the page is loaded
// over https but the API was hardcoded to http.
const API  = window.location.origin;
// [#A8-4] SSO — token + role을 localStorage에서 읽어 챗 페이지와 공유.
// 이전 sessionStorage 값이 있으면 1회 마이그레이션 (사용자가 새로 로그인
// 하지 않아도 즉시 어드민 페이지 진입 가능).
(function _migrateAdminSessionToLocal() {
  for (const k of ['james_token', 'james_role']) {
    const sess = sessionStorage.getItem(k);
    if (sess && !localStorage.getItem(k)) localStorage.setItem(k, sess);
  }
})();
let token  = localStorage.getItem('james_token') || '';
let apiKey = localStorage.getItem('james_api_key') || '';

/* ── [STEP 5-A] 언어 토글 ── */
function toggleLang() {
  const cur = (typeof getLang === 'function') ? getLang() : 'ko';
  const next = cur === 'ko' ? 'en' : 'ko';
  if (typeof setLang === 'function') setLang(next);
  const indicator = document.getElementById('lang-current');
  if (indicator) indicator.textContent = next.toUpperCase();
}

/* 페이지 로드 시 언어 표시기 동기화 */
window.addEventListener('DOMContentLoaded', () => {
  const indicator = document.getElementById('lang-current');
  if (indicator && typeof getLang === 'function') {
    indicator.textContent = getLang().toUpperCase();
  }
});

/* ── 초기화 ── */
window.addEventListener('DOMContentLoaded', async () => {
  if (!apiKey) {
    apiKey = prompt('JAMES API Key:') || '';
    localStorage.setItem('james_api_key', apiKey);
  }
  // [#A8-4] localStorage에서 role 읽음 — chat에서 admin으로 로그인했다면
  // 자동으로 dashboard 진입. 비-admin role이거나 token 없으면 modal.
  const storedRole = localStorage.getItem('james_role') || '';
  if (!token || storedRole !== 'admin') {
    showAdminLoginModal();
  } else {
    loadDashboard();
  }
});

/* [#A8-4] cross-tab sync — 다른 탭(chat 페이지)에서 로그인/로그아웃 →
   이 어드민 탭의 token/role 즉시 동기화. admin role 잃으면 모달 자동
   띄움. localStorage storage 이벤트는 *다른* 탭의 변경만 받으므로 본
   탭이 자체 변경한 상태와 충돌 안 함. */
window.addEventListener('storage', (e) => {
  if (e.key !== 'james_token' && e.key !== 'james_role') return;
  token = localStorage.getItem('james_token') || '';
  const role = localStorage.getItem('james_role') || '';
  if (!token || role !== 'admin') {
    // admin 권한 잃음 → modal 띄워 재로그인 유도
    showAdminLoginModal();
  } else {
    // admin 권한 회복 → modal 닫고 dashboard
    const modal = document.getElementById('admin-login-modal');
    if (modal) modal.style.display = 'none';
    try { loadDashboard(); } catch (_) {}
    // [PR plan-3] cross-tab login 후에도 first-run wizard 체크
    setTimeout(() => { try { firstRunCheck(); } catch (_) {} }, 600);
  }
});

/* ── Admin 로그인 모달 ── */
function showAdminLoginModal() {
  const modal = document.getElementById('admin-login-modal');
  if (modal) {
    modal.style.display = 'flex';
    setTimeout(() => document.getElementById('admin-login-pw')?.focus(), 150);
  }
}

/* [#A8-3] admin password 보기/숨기기 토글. chat 페이지와 동일 패턴 —
   input.type 'password' ↔ 'text' swap + emoji 변경. */
function toggleAdminPwVisibility() {
  const input = document.getElementById('admin-login-pw');
  const btn   = document.getElementById('admin-login-pw-toggle');
  if (!input) return;
  if (input.type === 'password') {
    input.type = 'text';
    if (btn) btn.textContent = '🙈';
  } else {
    input.type = 'password';
    if (btn) btn.textContent = '👁️';
  }
}

async function doAdminLogin() {
  const username = document.getElementById('admin-login-id')?.value.trim() || 'admin';
  const password = document.getElementById('admin-login-pw')?.value || '';
  const errEl    = document.getElementById('admin-login-error');
  if (errEl) errEl.textContent = '';

  if (!password) { if(errEl) errEl.textContent = t('auth.password_required'); return; }

  try {
    const r = await fetch(`${API}/login/`, {
      method:  'POST',
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify({username, password, api_key: apiKey}),
    });
    const d = await r.json();

    if (!r.ok) {
      if(errEl) errEl.textContent = d.detail || `Login failed (${r.status})`;
      return;
    }

    // access_token 또는 token 필드 모두 처리
    const tok  = d.access_token || d.token || '';
    const role = d.role || 'external';

    if (!tok)            { if(errEl) errEl.textContent = t('auth.token_failed'); return; }
    if (role !== 'admin'){ if(errEl) errEl.textContent = `Admin role required (role: ${role})`; return; }

    token = tok;
    // [#A8-4] localStorage — chat 페이지와 공유. 다른 탭의 storage 이벤트로
    // chat 페이지 role-badge 자동 갱신.
    localStorage.setItem('james_token', token);
    localStorage.setItem('james_role',  role);

    const modal = document.getElementById('admin-login-modal');
    if (modal) modal.style.display = 'none';
    loadDashboard();
    // [PR plan-3] 로그인 후 LLM 모델 readiness 체크. 0개면 wizard 노출.
    setTimeout(() => { try { firstRunCheck(); } catch (_) {} }, 600);

  } catch (e) {
    if(errEl) errEl.textContent = `Server error: ${e.message}`;
  }
}

/* ── [PR plan-3, 2026-05-09] First-run wizard ───────────────────
   처음 admin 진입 시 (또는 ollama list가 비었을 때) 모달 띄움.
   하드웨어 측정 → 추천 모델 → 원클릭 설치 흐름.
   sessionStorage('james_firstrun_dismissed')에 dismiss 기록 — 재진입
   시 안 띄움. 그러나 firstRunCheck()는 항상 호출되며 dismiss 됐어도
   ↻ 새로고침 버튼이 강제 표시 가능. */

let _firstRunInstallPoll = null;

async function firstRunCheck() {
  // 이번 세션에서 이미 dismiss됐고 모델이 ≥1개면 wizard 안 띄움.
  // 강제 표시는 firstRunShow() 직접 호출.
  try {
    const data = await api('/admin/llm/resolution');
    const installed = data.installed || [];
    const dismissed = sessionStorage.getItem('james_firstrun_dismissed') === '1';
    if (installed.length === 0) {
      // 모델 0개면 dismiss 무시하고 강제 표시 (실제로 답변이 안 됨)
      firstRunShow(data);
    } else if (!dismissed) {
      // 모델 ≥1개여도 chat resolver가 fallback 상태면 알림 (정보 차원)
      const chatWarn = (data.chat || {}).warning || '';
      if (chatWarn && chatWarn.includes('not installed')) {
        // toast — modal까지는 띄우지 않음
        if (typeof toast === 'function') {
          toast(`ℹ️ ${chatWarn}`, 'info');
        }
      }
    }
    // hide wizard if it was shown but now we have models
    if (installed.length > 0) {
      const m = document.getElementById('firstrun-wizard-modal');
      if (m) m.style.display = 'none';
    }
  } catch (e) {
    console.warn('[firstrun] resolution check failed:', e.message);
  }
}

async function firstRunShow(resolutionData) {
  const modal = document.getElementById('firstrun-wizard-modal');
  if (!modal) return;
  modal.style.display = 'flex';

  // 1) 하드웨어 측정 + 추천
  const hwBox = document.getElementById('firstrun-hw-summary');
  const recBox = document.getElementById('firstrun-recommendations');
  if (hwBox) hwBox.innerHTML = '<div class="loading">측정 중...</div>';
  if (recBox) recBox.innerHTML = '<div class="loading" style="padding:20px;text-align:center">로딩...</div>';

  try {
    const recData = await api('/admin/llm/recommend');
    if (!recData.ok) throw new Error(recData.error || 'recommend failed');
    const summary = recData.specs_summary || {};
    if (hwBox) {
      hwBox.innerHTML = `
        <div><strong>🖥️ 이 PC 사양</strong></div>
        <div>GPU: ${_escHtml(summary.gpu || '?')}</div>
        <div>RAM: ${_escHtml(summary.ram || '?')}</div>
        <div>전체 등급: <strong style="color:var(--accent-fg)">Level ${summary.level || '?'}</strong></div>
      `;
    }
    // 우선 첫 번째 chat-feasible 모델을 강조, 나머지는 sub list.
    const recs = recData.recommendations || [];
    const chatFeasible = recs.filter(r => r.feasible &&
                                          (r.purpose || []).includes('chat'));
    const codingFeasible = recs.filter(r => r.feasible &&
                                            (r.purpose || []).includes('coding'));
    if (recBox) {
      let html = '';
      if (chatFeasible.length === 0) {
        html += `<div style="padding:14px;color:var(--warn);font-size:12px">
          ⚠️ 이 PC 사양에 적합한 chat 모델이 없습니다. 가장 가벼운 모델 (gemma3:1b)을 시도해보세요.
        </div>`;
        // Force-show gemma3:1b as fallback.
        html += _firstRunRow({tag:'gemma3:1b', desc:'초경량 (CPU-only OK)',
                              size_gb:1.0, purpose:['chat']}, true);
      } else {
        // Top chat candidate gets star + 강조
        html += '<div style="font-size:11px;color:var(--muted);padding:6px 10px;text-transform:uppercase;letter-spacing:.3px">💬 일상 대화</div>';
        chatFeasible.slice(0, 3).forEach((r, i) => {
          html += _firstRunRow(r, i === 0);
        });
        if (codingFeasible.length > 0) {
          html += '<div style="font-size:11px;color:var(--muted);padding:6px 10px;margin-top:8px;text-transform:uppercase;letter-spacing:.3px">💻 코딩</div>';
          codingFeasible.slice(0, 2).forEach(r => {
            html += _firstRunRow(r, false);
          });
        }
      }
      recBox.innerHTML = html;
    }
  } catch (e) {
    if (hwBox) hwBox.innerHTML = `<div style="color:#c00">측정 실패: ${_escHtml(e.message)}</div>`;
    if (recBox) recBox.innerHTML = `<div style="padding:20px;text-align:center;color:#c00">추천 로드 실패: ${_escHtml(e.message)}</div>`;
  }
}

function _firstRunRow(r, primary) {
  const sizeGB = (r.size_gb != null) ? `${r.size_gb}GB` : '';
  const desc = _escHtml(r.desc || r.description || '');
  const tag = _escHtml(r.tag || r.name || '');
  const stars = primary ? '⭐ ' : '   ';
  const bg = primary ? 'rgba(99,102,241,.10)' : 'transparent';
  const border = primary ? 'border:1px solid var(--accent);' : 'border:1px solid var(--border);';
  return `<div style="${border}background:${bg};border-radius:7px;padding:10px 12px;margin:4px 6px;
                       display:flex;align-items:center;gap:10px;font-size:13px">
    <div style="flex:1;min-width:0">
      <div style="${primary?'color:var(--accent-fg);font-weight:600':''}">${stars}${tag}</div>
      <div style="font-size:11px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
        ${desc}${sizeGB ? ' · ' + sizeGB : ''}
      </div>
    </div>
    <button onclick="firstRunInstall('${tag.replace(/'/g, "\\'")}')"
            style="padding:7px 14px;background:var(--accent);color:#fff;
                   border:0;border-radius:6px;cursor:pointer;font-size:12px;
                   font-weight:600;flex-shrink:0">
      📦 설치
    </button>
  </div>`;
}

async function firstRunInstall(model) {
  if (!model) return;
  const progressBox = document.getElementById('firstrun-progress');
  const progressText = document.getElementById('firstrun-progress-text');
  const progressBar = document.getElementById('firstrun-progress-bar');
  if (progressBox) progressBox.style.display = 'block';
  if (progressText) progressText.textContent = `${model} 설치 시작 중...`;

  try {
    const r = await fetch(
      `${API}/llm/install/?api_key=${encodeURIComponent(apiKey)}&model=${encodeURIComponent(model)}`,
      {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      },
    );
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${r.status}`);
    }
    // 진행률 폴링
    if (_firstRunInstallPoll) clearInterval(_firstRunInstallPoll);
    _firstRunInstallPoll = setInterval(() => _firstRunPollProgress(model), 2500);
    _firstRunPollProgress(model);   // 즉시 1회
  } catch (e) {
    if (progressText) progressText.textContent = `❌ 설치 실패: ${e.message}`;
  }
}

async function _firstRunPollProgress(model) {
  try {
    const r = await fetch(
      `${API}/admin/llm/install-progress?api_key=${encodeURIComponent(apiKey)}&model=${encodeURIComponent(model)}`,
      { headers: { 'Authorization': `Bearer ${token}` } },
    );
    if (!r.ok) {
      if (r.status === 401) {
        // 세션 만료 — 폴링 중단 + localStorage 정리 (chat tab role
        // badge도 같이 업데이트되도록 SSO 일관성 유지).
        clearInterval(_firstRunInstallPoll);
        _firstRunInstallPoll = null;
        try {
          localStorage.removeItem('james_token');
          localStorage.removeItem('james_role');
        } catch (_) {}
      }
      return;
    }
    const p = await r.json();
    const progressText = document.getElementById('firstrun-progress-text');
    const progressBar = document.getElementById('firstrun-progress-bar');
    if (p.error) {
      if (progressText) progressText.textContent = `❌ ${model} 실패: ${p.error}`;
      clearInterval(_firstRunInstallPoll);
      _firstRunInstallPoll = null;
      return;
    }
    if (p.done) {
      if (progressText) progressText.textContent = `✅ ${model} 설치 완료! 이제 답변할 수 있습니다.`;
      if (progressBar) progressBar.style.width = '100%';
      clearInterval(_firstRunInstallPoll);
      _firstRunInstallPoll = null;
      // 자동 닫기 (3초 후)
      setTimeout(() => {
        const modal = document.getElementById('firstrun-wizard-modal');
        if (modal) modal.style.display = 'none';
      }, 3000);
      return;
    }
    if (progressText) {
      const pctStr = (p.percent != null) ? `${p.percent}%` : (p.status || '진행 중');
      progressText.textContent = `⏳ ${model}: ${pctStr}`;
    }
    if (progressBar && p.percent != null) {
      progressBar.style.width = `${p.percent}%`;
    }
  } catch (e) {
    console.warn('[firstrun-poll]', e);
  }
}

function firstRunDismiss() {
  sessionStorage.setItem('james_firstrun_dismissed', '1');
  const modal = document.getElementById('firstrun-wizard-modal');
  if (modal) modal.style.display = 'none';
}


/* ── 사이드 nav 토글 (item #2) ──
   모바일: 햄버거 버튼 → 사이드 드로워 슬라이드 인/아웃
   섹션 fold: 각 nav-section 클릭 → 다음 .nav-group collapse 토글
*/
function toggleAdminNav() {
  const nav = document.getElementById('admin-nav');
  if (!nav) return;
  let backdrop = document.getElementById('admin-nav-backdrop');
  if (!backdrop) {
    backdrop = document.createElement('div');
    backdrop.id = 'admin-nav-backdrop';
    backdrop.onclick = () => toggleAdminNav();
    document.body.appendChild(backdrop);
  }
  const isOpen = nav.classList.toggle('admin-nav-open');
  backdrop.classList.toggle('show', isOpen);
}

function toggleNavSection(sectionEl) {
  // 섹션 다음 형제(.nav-group) 만 토글. 섹션 자체엔 nav-collapsed로
  // 회전 화살표 표시.
  if (!sectionEl) return;
  const group = sectionEl.nextElementSibling;
  sectionEl.classList.toggle('nav-collapsed');
  if (group && group.classList.contains('nav-group')) {
    group.classList.toggle('nav-group-collapsed');
  }
}

/* ── 페이지 전환 ── */
function showPage(id, el) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById(`page-${id}`).classList.add('active');
  el.classList.add('active');

  // 모바일에서 페이지 선택 후 자동으로 nav 닫기 (UX)
  const nav = document.getElementById('admin-nav');
  if (nav && nav.classList.contains('admin-nav-open')
      && window.matchMedia('(max-width: 768px)').matches) {
    toggleAdminNav();
  }

  const loaders = {
    dashboard:      loadDashboard,
    users:          loadUsers,
    entities:       loadEntities,
    memory:         loadMemory,
    patches:        loadPatches,
    audit:          loadAudit,
    uploads:        loadUploads,
    files:          loadFiles,
    settings:       loadSettings,
    proposals:      loadProposals,
    'evo-reports':  loadEvoReports,
    performance:    loadPerformance,
    learning:       loadLearning,
    character:      loadCharacter,
    knowledge:      loadKnowledge,
    hardware:       loadHardware,    // [P3-1]
  };
  loaders[id]?.();
}

/* ── API 요청 (Bearer 토큰 포함) ── */
async function api(path, method='GET', body=null) {
  const opts = {
    method,
    headers: {
      'Content-Type':  'application/json',
      'Authorization': `Bearer ${token}`,
    },
  };
  if (body) opts.body = JSON.stringify(body);
  const sep = path.includes('?') ? '&' : '?';
  const r   = await fetch(`${API}${path}${sep}api_key=${apiKey}`, opts);
  if (r.status === 401) {
    token = '';
    // [#A8-4] localStorage 전환 — 401 시 chat 페이지 role-badge도 자동 갱신.
    localStorage.removeItem('james_token');
    localStorage.removeItem('james_role');
    alert(t('auth.expired_refresh'));
    location.reload();
    return {};
  }
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

/* ── 대시보드 ── */
async function loadDashboard() {
  try {
    const data = await api('/admin/dashboard');
    const cards = document.getElementById('dash-cards');

    // ── 통계 카드 ──────────────────────────────────────────
    const avgColor  = (data.avg_elapsed > 20) ? 'var(--red,#f06292)' :
                      (data.avg_elapsed > 10) ? 'var(--warn,#ffb74d)' : 'var(--accent)';
    const blkColor  = data.blocked_count > 0 ? 'var(--warn,#ffb74d)' : 'var(--accent)';

    cards.innerHTML = `
      <div class="card">
        <div class="card-label">${t('dash.entity_count')}</div>
        <div class="card-value accent">${data.entity_count ?? '-'}</div>
        <div class="card-sub">${t('dash.subtext_vector',{count:data.vector_count??'-'})}</div>
      </div>
      <div class="card">
        <div class="card-label">${t('dash.today_queries')}</div>
        <div class="card-value accent">${data.today_queries ?? '-'}</div>
        <div class="card-sub">${t('dash.subtext_today')}</div>
      </div>
      <div class="card">
        <div class="card-label">${t('dash.avg_elapsed')}</div>
        <div class="card-value" style="color:${avgColor}">${data.avg_elapsed ?? '-'}s</div>
        <div class="card-sub">${t('dash.subtext_avg')}</div>
      </div>
      <div class="card">
        <div class="card-label">${t('dash.blocked_count')}</div>
        <div class="card-value" style="color:${blkColor}">${data.blocked_count ?? '-'}</div>
        <div class="card-sub">${t('dash.subtext_blocked')}</div>
      </div>
      <div class="card">
        <div class="card-label">${t('dash.user_count')}</div>
        <div class="card-value accent">${data.user_count ?? '-'}</div>
      </div>
      <div class="card">
        <div class="card-label">${t('dash.memory_count')}</div>
        <div class="card-value accent">${data.memory_count ?? '-'}</div>
        <div class="card-sub">${t('dash.subtext_memory')}</div>
      </div>
    `;

    // ── 웹검색 상태 카드 제거 — 실제 검색은 작동하지만
    //    표시만 불일치 발생 → 혼란 방지 위해 카드 미표시
    //    (검색 작동 여부는 서버 로그에서 확인: [WEB] Tavily 검색 성공 등)


    const chart = data.elapsed_chart || [];
    if (chart.length > 0) {
      const max_v = Math.max(...chart, 1);
      const bars  = chart.map(v => {
        const h   = Math.max(4, Math.round((v / max_v) * 60));
        const col = v > 20 ? '#f06292' : v > 10 ? '#ffb74d' : '#7c6af7';
        return `<div title="${v}s" style="width:${Math.floor(280/chart.length)-2}px;
          height:${h}px;background:${col};border-radius:2px 2px 0 0;
          flex-shrink:0"></div>`;
      }).join('');

      const chartEl = document.getElementById('dash-chart');
      if (chartEl) {
        chartEl.innerHTML = `
          <div class="section-title" style="margin-top:16px">
            ${t('dash.elapsed_chart',{count:chart.length})}
            <span style="font-size:10px;color:var(--muted);margin-left:8px">
              ${t('dash.chart_legend')}
            </span>
          </div>
          <div style="display:flex;align-items:flex-end;gap:2px;
                      height:70px;padding:8px 20px;background:var(--bg);
                      border-radius:6px;border:1px solid var(--border)">
            ${bars}
          </div>`;
      }
    }

    // ── 최근 감사 로그 ────────────────────────────────────
    const logBox = document.getElementById('dash-logs');
    const logs = data.recent_queries || data.recent_logs || [];
    if (!logs.length) {
      if (logBox) logBox.innerHTML = `<div style='color:var(--muted)'>${t('dash.no_logs')}</div>`;
    } else {
      if (logBox) {
        logBox.innerHTML = logs.map(l => {
          const blocked = l.blocked ? '🚫' : '✅';
          const elapsed = l.elapsed ? `${l.elapsed}s` : '';
          const q = (l.q || l.query || '').slice(0, 60);
          const ts = (l.ts || l.timestamp || '').slice(11, 19);
          return `<div style="padding:4px 0;border-bottom:1px solid var(--border);
                              font-size:12px;display:flex;gap:8px;align-items:center">
            <span style="color:var(--muted);font-family:var(--font-mono);min-width:60px">${ts}</span>
            <span>${blocked}</span>
            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${q || '-'}</span>
            <span style="color:var(--muted);font-family:var(--font-mono)">${elapsed}</span>
          </div>`;
        }).join('');
      }
    }
  } catch(e) {
    const cards = document.getElementById('dash-cards');
    if (cards) cards.innerHTML = `<div style='color:var(--muted)'>Load failed: ${e.message}</div>`;
  }
}

/* ── 사용자 ── */
async function loadUsers() {
  try {
    const data = await api('/admin/users');
    const tbody = document.getElementById('users-body');
    tbody.innerHTML = (data.users || []).map(u => `
      <tr>
        <td>${u.username}</td>
        <td><span class="badge-role role-${u.role}">${u.role}</span></td>
        <td class="mono">${u.created_at?.slice(0,10) || '-'}</td>
        <td class="mono">${u.last_login?.slice(0,16) || '-'}</td>
      </tr>
    `).join('') || `<tr><td colspan='4' class='empty'>${t('users.empty')}</td></tr>`;
  } catch (e) {
    document.getElementById('users-body').innerHTML = `<tr><td colspan="4" class="empty">${e.message}</td></tr>`;
  }
}

/* ── Entity (item #1: search + paging + detail modal) ── */
const ENTITIES_PAGE_SIZE = 50;
let entitiesOffset = 0;
let entitiesSearchTimer = null;

function onEntitiesSearchInput() {
  // debounce 250ms — substring 검색이라 keystroke마다 fetch 안 띄움
  if (entitiesSearchTimer) clearTimeout(entitiesSearchTimer);
  entitiesSearchTimer = setTimeout(() => {
    entitiesOffset = 0;
    loadEntities();
  }, 250);
}

function entitiesPage(delta) {
  entitiesOffset = Math.max(0, entitiesOffset + delta * ENTITIES_PAGE_SIZE);
  loadEntities();
}

async function loadEntities() {
  try {
    const q     = document.getElementById('entities-search')?.value.trim() || '';
    const etype = document.getElementById('entities-etype-filter')?.value || '';
    const qs    = `q=${encodeURIComponent(q)}&etype=${encodeURIComponent(etype)}`
                + `&limit=${ENTITIES_PAGE_SIZE}&offset=${entitiesOffset}`;
    const data  = await api(`/admin/entities?${qs}`);

    // 카드 - corpus 전체 카운트
    const cards = document.getElementById('entity-cards');
    const counts = data.type_counts || {};
    cards.innerHTML = Object.entries(counts).map(([type, cnt]) => `
      <div class="card">
        <div class="card-label">${type.toUpperCase()}</div>
        <div class="card-value accent">${cnt}</div>
      </div>
    `).join('') || '';

    // 타입 필터 셀렉트 — 첫 로드 시 옵션 채움 (모든 타입)
    const sel = document.getElementById('entities-etype-filter');
    if (sel && sel.options.length <= 1) {
      Object.keys(counts).sort().forEach(type => {
        const opt = document.createElement('option');
        opt.value = type;
        opt.textContent = type;
        sel.appendChild(opt);
      });
    }

    // 카운터: filtered / total_all
    const counter = document.getElementById('entities-counter');
    if (counter) {
      counter.textContent = q || etype
        ? `${data.total} / ${data.total_all} (필터됨)`
        : `${data.total_all} 전체`;
    }

    // 테이블 — 행 클릭 → 상세
    const tbody = document.getElementById('entities-body');
    tbody.innerHTML = (data.entities || []).map(e => `
      <tr style="cursor:pointer" onclick="openEntityDetail('${e.entity_id}')">
        <td>${escapeHtml(e.name) || `<em style="color:var(--muted)">${e.entity_id}</em>`}</td>
        <td class="mono">${e.entity_type}</td>
        <td><span class="badge-status">${e.sensitivity || '-'}</span></td>
        <td class="mono">${e.relation_count ?? 0}</td>
      </tr>
    `).join('') || `<tr><td colspan='4' class='empty'>${t('entity.no_entity')}</td></tr>`;

    // 페이지 라벨
    const pageNo = Math.floor(entitiesOffset / ENTITIES_PAGE_SIZE) + 1;
    const pageLabel = document.getElementById('entities-page-label');
    if (pageLabel) pageLabel.textContent = `page ${pageNo} (${entitiesOffset + 1}-${Math.min(entitiesOffset + ENTITIES_PAGE_SIZE, data.total)})`;

    const prevBtn = document.getElementById('entities-prev');
    const nextBtn = document.getElementById('entities-next');
    if (prevBtn) prevBtn.disabled = entitiesOffset === 0;
    if (nextBtn) nextBtn.disabled = entitiesOffset + ENTITIES_PAGE_SIZE >= data.total;
  } catch (e) {
    document.getElementById('entities-body').innerHTML = `<tr><td colspan="4" class="empty">${e.message}</td></tr>`;
  }
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}

async function openEntityDetail(entityId) {
  const modal = document.getElementById('entity-detail-modal');
  const titleEl = document.getElementById('entity-detail-title');
  const metaEl  = document.getElementById('entity-detail-meta');
  const relEl   = document.getElementById('entity-detail-relations');
  const bodyEl  = document.getElementById('entity-detail-body');

  if (titleEl) titleEl.textContent = '로딩 중...';
  if (metaEl)  metaEl.textContent  = '';
  if (relEl)   relEl.innerHTML     = '';
  if (bodyEl)  bodyEl.textContent  = '';
  modal.style.display = 'flex';

  try {
    const data = await api(`/admin/entities/${encodeURIComponent(entityId)}`);
    if (titleEl) titleEl.textContent = data.name || data.entity_id;
    if (metaEl) {
      metaEl.textContent =
        `id=${data.entity_id} · type=${data.entity_type} · ` +
        `sensitivity=${data.sensitivity} · relations=${(data.relations||[]).length}`;
    }
    if (relEl) {
      const rels = data.relations || [];
      if (rels.length === 0) {
        relEl.innerHTML = `<div style="font-size:11px;color:var(--muted)">관계 정보 없음</div>`;
      } else {
        relEl.innerHTML = `
          <div class="section-title">▸ 관계 (${rels.length})</div>
          <div style="font-size:12px;font-family:var(--font-mono);
                      max-height:120px;overflow-y:auto;background:var(--bg);
                      padding:8px;border-radius:4px">
            ${rels.slice(0, 30).map(r =>
              `${escapeHtml(r.predicate || r.type || '?')} → ${escapeHtml(r.target || r.target_name || '?')}`
            ).join('<br>')}
            ${rels.length > 30 ? `<br><em>... +${rels.length - 30}개 더</em>` : ''}
          </div>
        `;
      }
    }
    if (bodyEl) bodyEl.textContent = data.body || '(본문 없음)';
  } catch (e) {
    if (titleEl) titleEl.textContent = '로드 실패';
    if (bodyEl)  bodyEl.textContent  = e.message;
  }
}

function closeEntityDetail(e) {
  if (e && e.target.id !== 'entity-detail-modal') return;
  document.getElementById('entity-detail-modal').style.display = 'none';
}

/* ── Memory ── */
async function loadMemory() {
  try {
    const data = await api('/admin/memory');
    const stats = data.stats || {};
    const cards = document.getElementById('memory-cards');
    cards.innerHTML = `
      <div class="card"><div class="card-label">PREFERENCES</div><div class="card-value accent">${stats.preferences ?? 0}</div></div>
      <div class="card"><div class="card-label">PATTERNS</div><div class="card-value accent">${stats.patterns ?? 0}</div></div>
      <div class="card"><div class="card-label">GOALS</div><div class="card-value accent">${stats.goals ?? 0}</div></div>
      <div class="card"><div class="card-label">${t('mem.card_turns')}</div><div class="card-value success">${stats.conversations ?? 0}</div></div>
      <div class="card"><div class="card-label">${t('mem.card_session_summary')}</div><div class="card-value success">${stats.session_summaries ?? 0}</div></div>
    `;
    // 선호도
    const tbody = document.getElementById('memory-prefs');
    tbody.innerHTML = (data.preferences || []).map(p => `
      <tr>
        <td class="mono">${p.key}</td>
        <td>${p.value}</td>
        <td class="mono">${p.updated_at?.slice(0,10) || '-'}</td>
      </tr>
    `).join('') || `<tr><td colspan='3' class='empty'>${t('mem.no_prefs')}</td></tr>`;

    // 장기 기억
    await loadLongTerm();
    // 세션 목록
    await loadSessions();

  } catch (e) {
    document.getElementById('memory-cards').innerHTML =
      `<div class="empty">${e.message}</div>`;
  }
}

async function loadLongTerm() {
  try {
    const data = await api('/history/long-term/?limit=10');
    const tbody = document.getElementById('long-term-body');
    tbody.innerHTML = (data.summaries || []).map(s => {
      // item #3-b: row click → original turns modal. session_id is
      // present in the API response (memory/store.py:492).
      const sid = s.session_id || '';
      const onclick = sid
        ? `onclick="openSessionTurns('${escapeHtml(sid)}', '${escapeHtml((s.topic || '').slice(0, 40))}')"`
        : '';
      const cursor = sid ? 'cursor:pointer' : '';
      const hint   = sid ? '' : ' <em style="color:var(--muted);font-size:10px">(no session_id)</em>';
      return `
        <tr style="${cursor}" ${onclick}>
          <td class="mono">${s.saved_at?.slice(0,10) || '-'}</td>
          <td>${escapeHtml(s.topic || '-')}${hint}</td>
          <td style="max-width:400px;font-size:12px">${escapeHtml((s.summary || '').slice(0,120) || '-')}</td>
          <td>${sid ? '🔍 펼침' : '-'}</td>
        </tr>
      `;
    }).join('') || `<tr><td colspan='4' class='empty'>${t('mem.no_longterm')}</td></tr>`;
  } catch (e) {
    document.getElementById('long-term-body').innerHTML =
      `<tr><td colspan="4" class="empty">${e.message}</td></tr>`;
  }
}

async function loadSessions() {
  try {
    const data = await api('/history/sessions/');
    const tbody = document.getElementById('sessions-body');
    tbody.innerHTML = (data.sessions || []).map(s => {
      const sid = s.session_id || '';
      // item #3-b: session_id 셀 + turn_count 셀 클릭 → 원본 펼침
      // (액션 버튼은 그대로 두고 행 일부만 클릭 가능하게 — 실수로
      // summarize&delete 버튼 누르는 사고 방지)
      const expandable = sid
        ? `onclick="openSessionTurns('${escapeHtml(sid)}', '${escapeHtml(sid.slice(0,20))}')" style="cursor:pointer"`
        : '';
      return `
        <tr>
          <td class="mono" style="font-size:10px" ${expandable}>${escapeHtml(sid.slice(0,20)) || '-'}</td>
          <td class="mono" ${expandable}>${s.turn_count ?? 0} turns</td>
          <td class="mono">${s.started?.slice(0,16) || '-'}</td>
          <td class="mono">${s.last?.slice(0,16) || '-'}</td>
          <td>
            <button class="btn btn-approve" style="font-size:10px"
              onclick="summarizeAndDelete('${escapeHtml(sid)}')" data-i18n='mem.summarize_delete'>Summarize & Delete</button>
          </td>
        </tr>
      `;
    }).join('') || `<tr><td colspan='5' class='empty'>${t('mem.no_sessions')}</td></tr>`;
  } catch (e) {
    document.getElementById('sessions-body').innerHTML =
      `<tr><td colspan="5" class="empty">${e.message}</td></tr>`;
  }
}

/* ── item #3-b: 세션 원본 대화 펼침 modal ── */
async function openSessionTurns(sessionId, label) {
  const modal = document.getElementById('session-turns-modal');
  const titleEl = document.getElementById('session-turns-title');
  const metaEl  = document.getElementById('session-turns-meta');
  const bodyEl  = document.getElementById('session-turns-body');

  if (titleEl) titleEl.textContent = `세션 원본 대화 — ${label || sessionId}`;
  if (metaEl)  metaEl.textContent  = `로딩 중... (session_id=${sessionId})`;
  if (bodyEl)  bodyEl.innerHTML    = '';
  modal.style.display = 'flex';

  try {
    const data = await api(`/history/?session_id=${encodeURIComponent(sessionId)}&limit=200`);
    const turns = data.turns || [];
    if (metaEl) metaEl.textContent = `session_id=${sessionId} · ${turns.length} 턴`;
    if (turns.length === 0) {
      bodyEl.innerHTML = `<div style="color:var(--muted);text-align:center;padding:20px">이 세션에 저장된 턴이 없습니다.</div>`;
      return;
    }
    bodyEl.innerHTML = turns.map(turn => {
      const isUser = (turn.role || turn.speaker || '').toLowerCase().includes('user');
      const text   = turn.content || turn.text || turn.answer || '';
      const ts     = turn.created_at || turn.time || turn.timestamp || '';
      const tsShort = (ts || '').slice(0, 19).replace('T', ' ');
      return `
        <div style="display:flex;flex-direction:column;gap:4px;
                    background:${isUser ? 'rgba(124,106,247,.10)' : 'var(--bg)'};
                    border-left:3px solid ${isUser ? '#7c6af7' : '#3da78a'};
                    padding:10px 12px;border-radius:4px">
          <div style="font-size:10px;color:var(--muted);font-family:var(--font-mono);
                      display:flex;justify-content:space-between">
            <span>${isUser ? '🗨️ user' : '🤖 james'}${turn.mode ? ' · mode=' + escapeHtml(turn.mode) : ''}</span>
            <span>${escapeHtml(tsShort)}</span>
          </div>
          <div style="white-space:pre-wrap;font-size:13px">${escapeHtml(text)}</div>
        </div>
      `;
    }).join('');
  } catch (e) {
    if (metaEl) metaEl.textContent = '';
    bodyEl.innerHTML = `<div style="color:var(--red,#f06292);text-align:center;padding:20px">로드 실패: ${escapeHtml(e.message)}</div>`;
  }
}

function closeSessionTurns(e) {
  if (e && e.target.id !== 'session-turns-modal') return;
  document.getElementById('session-turns-modal').style.display = 'none';
}

async function summarizeAndDelete(sessionId) {
  try {
    // 1. 요약 저장
    const r = await api(`/history/summarize/?session_id=${sessionId}`, 'POST');
    if (r.success) {
      toast(`✅ ${r.topic || sessionId.slice(0,12)} saved`, 'success');
    }
    // 2. 세션 삭제
    await api(`/history/?session_id=${sessionId}`, 'DELETE');
    // 3. 목록 갱신
    await loadSessions();
    await loadLongTerm();
  } catch (e) {
    alert(`Failed: ${e.message}`);
  }
}

function toast(msg, type = 'success') {
  const t = document.createElement('div');
  t.style.cssText = `position:fixed;bottom:24px;right:24px;padding:10px 16px;
    border-radius:8px;font-size:13px;z-index:100;
    background:rgba(76,175,125,.15);border:1px solid var(--success);
    color:var(--success);animation:fadeIn .25s ease`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

/* ── Patches ── */
async function loadPatches() {
  try {
    const data = await api('/admin/patches');
    const tbody = document.getElementById('patches-body');
    tbody.innerHTML = (data.patches || []).map(p => `
      <tr>
        <td class="mono">${p.patch_id}</td>
        <td class="mono">${p.target?.split('/').pop() || '-'}</td>
        <td><span class="badge-status status-${p.status?.toLowerCase()}">${p.status}</span></td>
        <td class="mono">${p.confidence != null ? (p.confidence*100).toFixed(0)+'%' : '-'}</td>
        <td class="mono">${p.created_at?.slice(0,16) || '-'}</td>
        <td>${p.status === 'PENDING_APPROVAL' ? `
          <button class="btn btn-approve" onclick="patchAction('${p.patch_id}','approve')" data-i18n='prop.approve'>Approve</button>
          <button class="btn btn-reject"  onclick="patchAction('${p.patch_id}','reject')" data-i18n='prop.reject'>Reject</button>
        ` : '-'}</td>
      </tr>
    `).join('') || `<tr><td colspan='6' class='empty'>${t('patch.no_patches')}</td></tr>`;
  } catch (e) {
    document.getElementById('patches-body').innerHTML = `<tr><td colspan="6" class="empty">${e.message}</td></tr>`;
  }
}

async function patchAction(patchId, action) {
  try {
    await api(`/admin/patch/${action}`, 'POST', { patch_id: patchId, api_key: apiKey });
    alert(`${action==='approve'?t('prop.approve'):t('prop.reject')} done`);
    loadPatches();
  } catch (e) {
    alert(`Failed: ${e.message}`);
  }
}

/* ── 감사 로그 ── */
async function loadAudit() {
  try {
    const data = await api('/admin/audit');
    const logs = data.logs || [];
    const el   = document.getElementById('audit-log');
    el.innerHTML = logs.length
      ? logs.map(l => renderLogEntry(l)).join('')
      : `<div class='empty'>${t('dash.no_logs')}</div>`;
  } catch (e) {
    document.getElementById('audit-log').innerHTML = `<div class="empty">${e.message}</div>`;
  }
}

function renderLogEntry(l) {
  const blocked  = l.blocked || l.event?.includes('BLOCK') || l.event?.includes('REJECT');
  const override = l.admin_override;
  const cls = override ? 'log-override' : (blocked ? 'log-blocked' : 'log-allowed');
  return `<div class="log-entry ${cls}">
    <span class="log-time">${(l.time||l.timestamp||'').slice(11,19)}</span>
    <span>[${l.event||l.action||'EVENT'}] ${l.detail||l.query||''}</span>
  </div>`;
}

/* ── 업로드 파일 이력 [#7-C] ── */
let _uploadsOffset = 0;
const _uploadsLimit = 50;

function _escHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function loadUploads(resetOffset = true) {
  if (resetOffset) _uploadsOffset = 0;
  const qInput = document.getElementById('uploads-search');
  const q = qInput ? qInput.value.trim() : '';
  const tbody = document.getElementById('uploads-tbody');
  const meta  = document.getElementById('uploads-meta');
  const pager = document.getElementById('uploads-pager');
  if (!tbody) return;
  tbody.innerHTML = `<div class="loading">${t('common.loading') || '로딩 중...'}</div>`;
  if (meta)  meta.textContent = '';
  if (pager) pager.innerHTML  = '';

  try {
    const path = `/admin/uploads/history/?limit=${_uploadsLimit}` +
                 `&offset=${_uploadsOffset}` +
                 (q ? `&q=${encodeURIComponent(q)}` : '');
    const data = await api(path);
    const items = data.items || [];
    const total = data.total || 0;

    if (items.length === 0) {
      tbody.innerHTML = `<div class="empty" style="padding:30px;text-align:center;color:var(--muted)">
        ${q ? `'${_escHtml(q)}' 검색 결과 없음` : '업로드 이력 없음'}
      </div>`;
    } else {
      tbody.innerHTML = `
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="background:var(--surface-2);text-align:left">
              <th style="padding:10px 14px;color:var(--muted);font-weight:600">시간</th>
              <th style="padding:10px 14px;color:var(--muted);font-weight:600">파일명</th>
              <th style="padding:10px 14px;color:var(--muted);font-weight:600">역할</th>
              <th style="padding:10px 14px;color:var(--muted);font-weight:600">IP</th>
              <th style="padding:10px 14px;color:var(--muted);font-weight:600">상태</th>
            </tr>
          </thead>
          <tbody>
            ${items.map(it => {
              const ts = (it.timestamp || '').slice(0, 19).replace('T', ' ');
              const blocked = it.blocked;
              const statusBadge = blocked
                ? `<span style="background:#fee;color:#c00;padding:2px 8px;
                    border-radius:4px;font-size:11px;font-weight:600">차단</span>`
                : `<span style="background:#efe;color:#080;padding:2px 8px;
                    border-radius:4px;font-size:11px;font-weight:600">성공</span>`;
              const sevTitle = it.security_event
                ? ` title="${_escHtml(it.security_event)}"` : '';
              return `<tr style="border-top:1px solid var(--border)"${sevTitle}>
                <td style="padding:10px 14px;font-family:var(--font-mono);
                           font-size:11px;color:var(--muted)">${_escHtml(ts)}</td>
                <td style="padding:10px 14px">${_escHtml(it.filename)}</td>
                <td style="padding:10px 14px;font-size:12px">${_escHtml(it.user_role)}</td>
                <td style="padding:10px 14px;font-family:var(--font-mono);
                           font-size:11px;color:var(--muted)">${_escHtml(it.ip_address)}</td>
                <td style="padding:10px 14px">${statusBadge}</td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>`;
    }

    if (meta) {
      const showStart = total === 0 ? 0 : (_uploadsOffset + 1);
      const showEnd   = Math.min(_uploadsOffset + items.length, total);
      meta.textContent = `${showStart}–${showEnd} / 전체 ${total}건${q ? ` ('${q}' 필터)` : ''}`;
    }

    if (pager) {
      const hasPrev = _uploadsOffset > 0;
      const hasNext = (_uploadsOffset + items.length) < total;
      pager.innerHTML = `
        <button onclick="_uploadsPrev()" ${hasPrev ? '' : 'disabled'}
                style="padding:6px 14px;background:var(--surface-2);
                       border:1px solid var(--border);border-radius:6px;
                       color:var(--text);cursor:${hasPrev ? 'pointer' : 'not-allowed'};
                       opacity:${hasPrev ? '1' : '0.4'};font-size:12px">
          ‹ 이전
        </button>
        <button onclick="_uploadsNext()" ${hasNext ? '' : 'disabled'}
                style="padding:6px 14px;background:var(--surface-2);
                       border:1px solid var(--border);border-radius:6px;
                       color:var(--text);cursor:${hasNext ? 'pointer' : 'not-allowed'};
                       opacity:${hasNext ? '1' : '0.4'};font-size:12px">
          다음 ›
        </button>`;
    }
  } catch (e) {
    tbody.innerHTML = `<div class="empty" style="padding:30px;text-align:center;color:#c00">
      로딩 실패: ${_escHtml(e.message)}
    </div>`;
  }
}

function _uploadsPrev() {
  _uploadsOffset = Math.max(0, _uploadsOffset - _uploadsLimit);
  loadUploads(false);
}

function _uploadsNext() {
  _uploadsOffset = _uploadsOffset + _uploadsLimit;
  loadUploads(false);
}

/* ── [item #2 / 2026-05-09] 파일 관리 통합 탭 ──
   사용자 피드백: 업로드 + 이력 + 트리 + 검색을 하나의 세션으로.
   업로드/이력은 기존 endpoint 재사용; 이 탭의 신규 책임은 트리/검색/
   다운로드. 트리 root는 wiki/uploads/media 중 선택 (서버 allowlist).
   ⚠ 모든 endpoint는 admin-gated + 경로 traversal 방어. */
let _filesCurrentRoot = 'wiki';

function _humanSize(bytes) {
  if (bytes == null) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' GB';
}

function _humanMtime(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts * 1000);
    return d.toISOString().slice(0, 16).replace('T', ' ');
  } catch (_) { return ''; }
}

function onFilesRootChange() {
  const sel = document.getElementById('files-root');
  if (sel) {
    _filesCurrentRoot = sel.value || 'wiki';
    loadFiles();
  }
}

async function loadFiles() {
  const root = _filesCurrentRoot;
  const container = document.getElementById('files-content');
  const info = document.getElementById('files-info');
  if (!container) return;
  container.innerHTML = `<div class="loading">${t('common.loading') || '로딩 중...'}</div>`;
  if (info) info.textContent = '';
  // Reset search input on tree reload.
  const sb = document.getElementById('files-search');
  if (sb) sb.value = '';

  try {
    const data = await api(`/admin/files/tree?root=${encodeURIComponent(root)}&max_depth=3`);
    if (!data.exists) {
      container.innerHTML = `<div class="empty" style="padding:30px;text-align:center;color:var(--muted)">
        '${_escHtml(root)}' 디렉토리 없음 (아직 생성 안 됨)
      </div>`;
      return;
    }
    const children = data.children || [];
    if (children.length === 0) {
      container.innerHTML = `<div class="empty" style="padding:30px;text-align:center;color:var(--muted)">
        비어 있음
      </div>`;
      if (info) info.textContent = `root=${root} · 0 entries`;
      return;
    }
    container.innerHTML = _renderTree(children, '', root);
    if (info) info.textContent = `root=${root} · ${children.length} top-level entries`;
  } catch (e) {
    container.innerHTML = `<div class="empty" style="padding:30px;text-align:center;color:#c00">
      트리 로드 실패: ${_escHtml(e.message)}
    </div>`;
  }
}

/* Recursive tree renderer. Folders render as collapsible <details>
   so the user can expand/collapse selectively without the whole tree
   collapsing on a re-render. Files have a download link (only for
   allowlisted extensions — server enforces, but we don't render the
   link for ones we know will 403). */
const _DOWNLOAD_OK_EXTS = new Set([
  'md','txt','pdf','docx','doc','xlsx','xls','pptx','ppt','csv','html','htm',
  'json','yaml','yml','png','jpg','jpeg','gif','webp','bmp','tiff','mp4','avi',
  'mov','mkv','webm','mp3','wav','m4a','aac','flac','hwpx','hwp',
]);

function _renderTree(nodes, parentPath, root) {
  if (!nodes || !nodes.length) return '';
  let html = '<ul style="list-style:none;padding-left:0;margin:0">';
  for (const n of nodes) {
    const fullRel = parentPath ? `${parentPath}/${n.name}` : n.name;
    if (n.type === 'dir') {
      const childHtml = (n.children && n.children.length)
        ? _renderTree(n.children, fullRel, root)
        : '<div style="padding:4px 0 4px 18px;color:var(--muted);font-size:11px">(empty)</div>';
      html += `<li style="margin:2px 0">
        <details style="padding-left:12px;border-left:1px dashed var(--border-2)">
          <summary style="cursor:pointer;color:var(--accent-fg);
                          padding:3px 6px;border-radius:4px">
            📂 ${_escHtml(n.name)}/
          </summary>
          <div style="padding-left:14px;margin-top:2px">${childHtml}</div>
        </details>
      </li>`;
    } else {
      const ext = (n.name.split('.').pop() || '').toLowerCase();
      const canDownload = _DOWNLOAD_OK_EXTS.has(ext);
      const dlLink = canDownload
        ? `<a href="${API}/admin/files/download?root=${encodeURIComponent(root)}&path=${encodeURIComponent(fullRel)}&api_key=${encodeURIComponent(apiKey)}"
              target="_blank" rel="noopener"
              style="color:var(--accent-fg);text-decoration:none;font-size:11px;
                     margin-left:8px"
              title="다운로드">⬇</a>`
        : '';
      html += `<li style="margin:2px 0;padding:3px 6px 3px 18px;
                          border-left:1px dashed var(--border-2);
                          display:flex;align-items:center;gap:6px">
        <span>📄 ${_escHtml(n.name)}</span>
        <span style="color:var(--muted);font-size:11px;flex:1">
          ${_humanSize(n.size)} · ${_humanMtime(n.mtime)}
        </span>${dlLink}
      </li>`;
    }
  }
  html += '</ul>';
  return html;
}

async function searchFiles() {
  const sb = document.getElementById('files-search');
  const q = sb ? sb.value.trim() : '';
  if (!q) { loadFiles(); return; }
  const root = _filesCurrentRoot;
  const container = document.getElementById('files-content');
  const info = document.getElementById('files-info');
  if (!container) return;
  container.innerHTML = `<div class="loading">${t('common.loading') || '로딩 중...'}</div>`;
  if (info) info.textContent = '';

  try {
    const data = await api(`/admin/files/search?root=${encodeURIComponent(root)}&q=${encodeURIComponent(q)}&limit=200`);
    const matches = data.matches || [];
    if (matches.length === 0) {
      container.innerHTML = `<div class="empty" style="padding:30px;text-align:center;color:var(--muted)">
        '${_escHtml(q)}' 일치 없음 (root=${_escHtml(root)})
      </div>`;
      if (info) info.textContent = `'${q}' · 0 matches`;
      return;
    }
    let html = '<ul style="list-style:none;padding-left:0;margin:0">';
    for (const m of matches) {
      const ext = (m.name.split('.').pop() || '').toLowerCase();
      const canDownload = _DOWNLOAD_OK_EXTS.has(ext);
      const dlLink = canDownload
        ? `<a href="${API}/admin/files/download?root=${encodeURIComponent(root)}&path=${encodeURIComponent(m.path)}&api_key=${encodeURIComponent(apiKey)}"
              target="_blank" rel="noopener"
              style="color:var(--accent-fg);text-decoration:none;font-size:11px;
                     margin-left:8px"
              title="다운로드">⬇</a>`
        : '';
      html += `<li style="margin:3px 0;padding:6px 8px;
                          border-bottom:1px dotted var(--border-2);
                          display:flex;align-items:center;gap:8px">
        <span style="color:var(--muted);font-size:11px;
                     font-family:var(--font-mono);flex-shrink:0">${_escHtml(m.path)}</span>
        <span style="color:var(--muted);font-size:11px;flex:1;text-align:right">
          ${_humanSize(m.size)} · ${_humanMtime(m.mtime)}
        </span>${dlLink}
      </li>`;
    }
    html += '</ul>';
    container.innerHTML = html;
    const truncMsg = data.truncated ? ` (limit ${matches.length}; refine query)` : '';
    if (info) info.textContent = `'${q}' · ${matches.length} matches${truncMsg}`;
  } catch (e) {
    container.innerHTML = `<div class="empty" style="padding:30px;text-align:center;color:#c00">
      검색 실패: ${_escHtml(e.message)}
    </div>`;
  }
}

/* ── 언어 전환 — i18n.js의 t() 사용으로 대체됨 ── */
function onLanguageChange(lang) {
  // 구 I18N 딕셔너리 제거 — applyTranslations()로 자동 처리
}

/* ── 설정 — 드롭다운 연동 ── */
// 보호 파일 목록 (고정 + 동적)
const PROTECTED_CANDIDATES = [
  { file: 'core/security_layer.py',  label: '🔐 Security Layer',  default: true  },
  { file: 'core/auth.py',            label: '🔑 Auth Module',      default: true  },
  { file: 'config.py',               label: '⚙️  Config File',     default: true  },
  { file: 'server_llmwiki.py',       label: '🌐 FastAPI Server',   default: false },
  { file: 'core/graph_engine.py',    label: '🕸️  Graph Engine',    default: false },
  { file: 'core/reasoning_engine.py',label: '🧠 Reasoning Engine', default: false },
  { file: 'core/vector_store.py',    label: '🗄️  Vector Store',    default: false },
];


function buildProtectedCheckboxes(currentProtected = []) {
  const container = document.getElementById('protected-checkboxes');
  if (!container) return;
  const checked = new Set(
    typeof currentProtected === 'string'
      ? currentProtected.split(',').map(s => s.trim()).filter(Boolean)
      : (Array.isArray(currentProtected) ? currentProtected : [])
  );
  container.innerHTML = PROTECTED_CANDIDATES.map(c => `
    <label style="display:flex;align-items:center;gap:8px;
                  cursor:pointer;font-size:13px;padding:3px 0">
      <input type="checkbox" class="protected-chk" value="${c.file}"
             ${checked.has(c.file) || (checked.size === 0 && c.default) ? 'checked' : ''}
             style="accent-color:var(--accent);width:14px;height:14px">
      <span>${c.label}</span>
      <span style="font-size:10px;color:var(--muted);font-family:var(--font-mono)">${c.file}</span>
    </label>
  `).join('');
}

function getProtectedFiles() {
  return Array.from(
    document.querySelectorAll('.protected-chk:checked')
  ).map(cb => cb.value).join(',');
}

async function loadSettings() {
  try {
    const data = await api('/admin/settings');

    // LLM 드롭다운
    const modelSel = document.getElementById('set-model');
    if (modelSel && data.model) {
      const opt = Array.from(modelSel.options).find(o => o.value === data.model);
      if (opt) modelSel.value = data.model;
      else {
        // 현재 모델이 목록에 없으면 동적 추가
        const newOpt = document.createElement('option');
        newOpt.value = data.model;
        newOpt.textContent = `🔧 ${data.model} (${t('set.current')})`;
        modelSel.prepend(newOpt);
        modelSel.value = data.model;
      }
    }
    // 현재 모델 배지 표시
    const badge = document.getElementById('model-current-badge');
    if (badge && data.model) {
      badge.textContent = `${t('set.model_checking').replace('checking...','').trim()} ${data.model}`;
    }

    // Max Loop 슬라이더
    const loopEl  = document.getElementById('set-loop');
    const loopVal = document.getElementById('set-loop-val');
    if (loopEl && data.max_loop) {
      loopEl.value = data.max_loop;
      if (loopVal) loopVal.textContent = data.max_loop;
    }

    // 보호 파일 체크박스
    buildProtectedCheckboxes(data.protected || '');

    // persona 로드
    const p = data.persona || {};
    if (p.name)   document.getElementById('set-name').value   = p.name;
    if (p.style)  document.getElementById('set-style').value  = p.style;
    if (p.custom) document.getElementById('set-custom').value = p.custom;

    const lang    = p.language || 'Korean';
    const langSel = document.getElementById('set-language');
    if (langSel) {
      const opt = Array.from(langSel.options).find(o => o.value === lang);
      if (opt) langSel.value = lang;
    }
    updatePersonaPreview(p);
  } catch (e) {
    console.error('loadSettings:', e);
    // 체크박스는 기본값으로 초기화
    buildProtectedCheckboxes('');
  }
  // [#A6-1] settings 진입 시 웹 검색 설정도 함께 로드
  try { loadWebSearchConfig(); } catch (e) { console.warn(e); }
}

function updatePersonaPreview(p) {
  const el = document.getElementById('persona-preview');
  if (!el) return;
  const name = p.name || t('app.name');
  const style = p.style || '';
  const lang = p.language || 'Korean';
  el.textContent = `→ LLM: "Your name is ${name}. ${style ? `You are ${style}. ` : ''}Always answer in ${lang}요."`;
}

async function savePersona() {
  const name     = document.getElementById('set-name').value.trim();
  const style    = document.getElementById('set-style').value.trim();
  const language = document.getElementById('set-language').value.trim();
  const custom   = document.getElementById('set-custom').value.trim();

  if (!name && !style && !language) {
    alert(t('set.persona_required'));
    return;
  }

  const body = { api_key: apiKey, name, style, language, custom };

  try {
    const r = await fetch(`${API}/admin/persona`, {
      method:  'POST',
      headers: {
        'Content-Type':  'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(body),
    });

    const data = await r.json();

    if (!r.ok) {
      alert(`❌ Save failed (${r.status})\n${data.detail || JSON.stringify(data)}`);
      return;
    }

    if (data.success) {
      alert(`${t('set.persona_saved')}\n${JSON.stringify(data.saved||{})}`);
      updatePersonaPreview(data.persona || body);
    } else {
      alert(`Save failed: ${JSON.stringify(data)}`);
    }
  } catch (e) {
    alert(`❌ Network error: ${e.message}\nCheck that the server is running.`);
  }
}

async function saveSettings() {
  const body = {
    api_key:         apiKey,
    model:           document.getElementById('set-model').value,
    max_loop:        parseInt(document.getElementById('set-loop').value) || 2,
    protected_files: getProtectedFiles(),
  };
  try {
    await api('/admin/settings', 'POST', body);
    // 현재 모델 배지 갱신
    const badge = document.getElementById('model-current-badge');
    if (badge) badge.textContent = `${t('set.model_checking').replace('checking...','').trim()} ${body.model}`;
    alert(t('set.server_saved'));
  } catch (e) {
    alert(`Failed: ${e.message}`);
  }
}

/* ── [#A6-1] Web Search 설정 — role 권한 + threshold 조정 + 엔진 상태 ──
   admin 페이지 settings 섹션에서 사용. loadSettings에서 같이 호출되어
   체크박스/슬라이더 채움. saveWebSearchConfig는 별도 버튼 (다른 설정과
   충돌 없이 독립 저장 — TAVILY 키 변경/엔진 전환 시 별도 reload 가능). */
async function loadWebSearchConfig() {
  try {
    const data = await api('/admin/web-search-config/');
    // 엔진 상태 표시 (engine_status: tavily/duckduckgo/none)
    const statusEl = document.getElementById('web-search-status-display');
    if (statusEl) {
      const s = data.engine_status || {};
      const active = s.active_engine || 'none';
      const lines = [];
      if (active === 'tavily') {
        lines.push(`✅ Tavily 활성화 (key set, advanced 모드)`);
      } else if (active === 'duckduckgo') {
        lines.push(`🦆 DuckDuckGo fallback`);
        if (!s.tavily_key) lines.push(`⚠️ TAVILY_API_KEY 미설정`);
        if (s.tavily_exhausted) lines.push(`⚠️ Tavily 할당량 소진`);
      } else {
        lines.push(`❌ 검색 엔진 없음`);
        if (!s.tavily_installed) lines.push(`pip install tavily-python`);
        if (!s.ddg_installed) lines.push(`pip install duckduckgo-search`);
      }
      statusEl.innerHTML = lines.map(l => `<div>${l}</div>`).join('');

      // [#A6-1 (b)] TAVILY_API_KEY 미설정 + DDG가 active이면 토스트 경고.
      // 운영자는 .env에 키 추가하면 advanced 검색 + raw_content 본문까지
      // 무료 1000회/월 사용 가능. 어드민 페이지 진입 1회만 alert.
      if (!s.tavily_key && active === 'duckduckgo' && !window._toastedTavily) {
        window._toastedTavily = true;
        if (typeof toast === 'function') {
          toast('⚠️ TAVILY_API_KEY 미설정 — DDG fallback 동작 중. .env에 추가 추천 (free 1000/월).', 'warn');
        }
      }
    }
    // 체크박스 채움
    const allowed = new Set(data.allowed_roles || ['admin']);
    document.querySelectorAll('.ws-role-cb').forEach(cb => {
      cb.checked = allowed.has(cb.value);
    });
    // threshold slider
    const slider = document.getElementById('ws-threshold');
    const val    = document.getElementById('ws-threshold-val');
    if (slider && data.threshold != null) {
      slider.value = data.threshold;
      if (val) val.textContent = Number(data.threshold).toFixed(2);
      applyWsThresholdLabel(data.threshold);
    }
  } catch (e) {
    console.warn('[admin] /admin/web-search-config/ load 실패:', e);
  }
}

/* [#A8-2] threshold 슬라이더 값 → 직관적 라벨 매핑.
   pipeline.py 의 `unified_score < threshold` 트리거 조건상,
   threshold 가 *높을수록* 더 많은 쿼리가 웹 검색으로 넘어간다.
     0.05~0.20  안함    — 거의 모든 쿼리가 internal-only
     0.20~0.35  소극    — 자료 빈약할 때만 웹
     0.35~0.50  보통    — default (0.30) 근처, 균형
     0.50~0.65  적극    — 자료 풍부해도 자주 웹으로 보강
     0.65~0.80  강력    — 거의 모든 쿼리에 웹 검색 (Tavily 할당량 빠르게 소진)
   라벨별 색상도 다르게 — 시각적 강약 표현. */
function applyWsThresholdLabel(value) {
  const v = parseFloat(value);
  const valEl   = document.getElementById('ws-threshold-val');
  const labelEl = document.getElementById('ws-threshold-label');
  if (valEl)   valEl.textContent = v.toFixed(2);
  if (!labelEl) return;
  let label, bg, fg;
  if (v < 0.20)      { label = '안함';  bg = 'rgba(138,141,153,.18)'; fg = '#8a8d99'; }
  else if (v < 0.35) { label = '소극';  bg = 'rgba(79,195,247,.18)';  fg = '#4fc3f7'; }
  else if (v < 0.50) { label = '보통';  bg = 'rgba(99,102,241,.18)';  fg = '#a5b4fc'; }
  else if (v < 0.65) { label = '적극';  bg = 'rgba(255,183,77,.20)';  fg = '#ffb74d'; }
  else               { label = '강력';  bg = 'rgba(240,98,146,.22)';  fg = '#f06292'; }
  labelEl.textContent       = label;
  labelEl.style.background  = bg;
  labelEl.style.color       = fg;
}

async function saveWebSearchConfig() {
  const roles = Array.from(document.querySelectorAll('.ws-role-cb'))
                     .filter(cb => cb.checked)
                     .map(cb => cb.value);
  if (roles.length === 0) {
    alert('Allowed Roles는 최소 1개 필요. (전부 비활성화하려면 .env에서 TAVILY_API_KEY 제거)');
    return;
  }
  const threshold = parseFloat(document.getElementById('ws-threshold').value);
  try {
    await api('/admin/web-search-config/', 'POST', {
      api_key:       apiKey,
      allowed_roles: roles,
      threshold,
    });
    if (typeof toast === 'function') {
      toast(`✅ 웹 검색 설정 저장됨 (roles=${roles.join(',')}, threshold=${threshold})`, 'success');
    } else {
      alert('Web search settings saved.');
    }
  } catch (e) {
    alert(`Failed: ${e.message}`);
  }
}

/* ── 자기진화 제안 ── */

let _currentProposalId = null;

async function loadProposals() {
  try {
    const data = await api('/admin/proposals/?status=pending');
    const tbody = document.getElementById('proposals-body');
    const proposals = data.proposals || [];

    if (!proposals.length) {
      tbody.innerHTML = `<tr><td colspan='5' class='empty'>${t('prop.no_pending')}</td></tr>`;
      return;
    }

    const riskColor = { low:'var(--success)', medium:'var(--warn)', high:'var(--danger)' };
    tbody.innerHTML = proposals.map(p => {
      const isWebLearn = p.type === 'knowledge_update' &&
                         p.metadata?.auto_action === 'web_learn';
      const topic = p.metadata?.topic || '';
      const actionBtns = isWebLearn
        ? `<button class="btn btn-approve" style="font-size:10px;background:#4fc3f7"
             onclick="executeWebLearnProposal('${p.proposal_id}','${topic}',this)">
             ${t('prop.web_search')}
           </button>
           <button class="btn btn-reject" style="font-size:10px"
             onclick="rejectProposalById('${p.proposal_id}')">❌ Reject</button>`
        : `<button class="btn btn-approve" style="font-size:10px"
             onclick="approveProposal('${p.proposal_id}')">✅ Approve</button>
           <button class="btn btn-reject" style="font-size:10px"
             onclick="rejectProposalById('${p.proposal_id}')">❌ Reject</button>`;

      return `<tr>
        <td><span class="mono" style="font-size:10px">${p.type}</span></td>
        <td><span style="color:${riskColor[p.risk]||'var(--muted)'}">
          ${p.risk?.toUpperCase() || '-'}</span></td>
        <td style="max-width:320px;font-size:12px">${p.title}</td>
        <td class="mono">${p.created_at?.slice(0,16) || '-'}</td>
        <td style="display:flex;gap:4px;flex-wrap:wrap">
          <button class="btn" style="font-size:10px;background:var(--surface);
            border:1px solid var(--border);color:var(--text)"
            onclick="showProposalDetail('${p.proposal_id}',\`${escAdm(p.title)}\`,\`${escAdm(p.description)}\n\n${escAdm(p.content?.slice(0,600))}\`)">
            ${t('prop.detail')}
          </button>
          ${actionBtns}
        </td>
      </tr>`;
    }).join('');

  } catch (e) {
    document.getElementById('proposals-body').innerHTML =
      `<tr><td colspan="5" class="empty">${e.message}</td></tr>`;
  }
}

function escAdm(s) {
  return (s || '').replace(/`/g, "'").replace(/\n/g, '\\n').slice(0, 300);
}

function showProposalDetail(id, title, content) {
  _currentProposalId = id;
  const detail = document.getElementById('proposal-detail');
  const dc     = document.getElementById('proposal-detail-content');
  detail.style.display = 'block';
  dc.textContent = `[${id}]\n${title}\n\n${content.replace(/\\n/g, '\n')}`;

  document.getElementById('detail-approve-btn').onclick = () => approveProposal(id);
  document.getElementById('detail-reject-btn').onclick  = () => rejectProposalById(id);
  detail.scrollIntoView({ behavior: 'smooth' });
}

async function approveProposal(proposalId) {
  if (!confirm(t('prop.approve_confirm'))) return;
  try {
    const r = await api(`/admin/proposals/${proposalId}/approve`, 'POST',
                        {api_key: apiKey});
    const status = r.success ? '✅ Success' : t('hw.llm_failed');
    alert(`${t('prop.execute_done')}\n\n${status}: ${r.message||''}\n${t('prop.elapsed')}: ${r.elapsed_sec}s`);
    await loadProposals();
    await loadEvoReports();
    document.getElementById('proposal-detail').style.display = 'none';
  } catch (e) {
    alert(`Approve failed: ${e.message}`);
  }
}

async function rejectProposalById(proposalId) {
  const reason = prompt(t('prop.reject_prompt')) || '';
  try {
    await api(
      `/admin/proposals/${proposalId}/reject?reason=${encodeURIComponent(reason)}`,
      'POST'
    );
    // [4-C] Reject 사유 → memory_store 장기기억 저장
    if (reason.trim()) {
      try {
        await api('/admin/memory/save-rejection', 'POST', {
          proposal_id: proposalId,
          reason:      reason.trim(),
        });
        toast(t('prop.rejected_saved'), 'success');
      } catch { toast(t('prop.rejected'), 'success'); }
    } else {
      toast(t('prop.rejected'), 'success');
    }
    await loadProposals();
    document.getElementById('proposal-detail').style.display = 'none';
  } catch (e) {
    alert(`Reject failed: ${e.message}`);
  }
}

/* ── [4-C] 웹 검색 제안 실행 ── */
async function executeWebLearnProposal(proposalId, topic, btn) {
  if (!confirm(
    t('prop.web_confirm',{topic}) +
    `${t('learn.web_duration')}`
  )) return;
  btn.disabled   = true;
  btn.textContent = t('prop.searching');
  try {
    // 웹 검색 학습 실행
    const r = await api(
      `/admin/learn/topic/?topic=${encodeURIComponent(topic)}&use_web=true`, 'POST'
    );
    if (r.success) {
      // proposal Approve 처리
      await api(`/admin/proposals/${proposalId}/approve`, 'POST');
      toast(t('learn.web_done')+` [${r.domain}]`, 'success');
      btn.textContent = t('prop.completed');
      btn.style.background = '#4caf7d';
      await loadProposals();
      // 지식 레벨 UI 갱신
      setTimeout(() => loadKnowledge(), 1000);
    } else {
      throw new Error(r.message || 'Learning failed');
    }
  } catch(e) {
    btn.textContent = '❌ Failed';
    btn.disabled = false;
    alert(`Execution failed: ${e.message}`);
  }
}

async function generateProposals() {
  const btn = event.target;
  btn.textContent = t('prop.analyzing');
  btn.disabled = true;
  try {
    const r = await api('/admin/proposals/generate/', 'POST');
    if (r.generated > 0) {
      toast(t('prop.generated',{count:r.generated}), 'success');
      await loadProposals();
    } else {
      toast(t('prop.no_signals'), 'success');
    }
  } catch (e) {
    alert(`Generation failed: ${e.message}`);
  } finally {
    btn.textContent = t('prop.generate');
    btn.disabled = false;
  }
}

/* ── 진화 보고서 ── */

async function loadEvoReports() {
  try {
    const data = await api('/admin/evo-reports/');
    const tbody = document.getElementById('evo-reports-body');
    const reports = data.reports || [];

    tbody.innerHTML = reports.length
      ? reports.map(r => `
          <tr>
            <td class="mono">${r.executed_at?.slice(0,16) || '-'}</td>
            <td class="mono">${r.type || '-'}</td>
            <td style="font-size:12px">${r.title || '-'}</td>
            <td style="color:${r.success ? 'var(--success)' : 'var(--danger)'}">
              ${r.success ? '✅ Success' : '❌ Failed'}: ${(r.message||'').slice(0,40)}</td>
            <td class="mono">${r.elapsed_sec ?? '-'}s</td>
          </tr>`)
        .join('')
      : `<tr><td colspan='5' class='empty'>${t('evo.no_reports')}</td></tr>`;
  } catch (e) {
    document.getElementById('evo-reports-body').innerHTML =
      `<tr><td colspan="5" class="empty">${e.message}</td></tr>`;
  }
}

/* ── 성능 평가 ── */

async function loadPerformance() {
  try {
    const data = await api('/admin/performance/metrics/');
    const perf = data.performance || {};
    const imp  = data.importance  || {};

    const gradeColor = { A:'var(--success)', B:'var(--accent2)',
                         C:'var(--warn)', D:'var(--danger)', 'N/A':'var(--muted)' };
    const last = await api('/admin/performance/history/?limit=1');
    const lastGrade = last.history?.[0]?.grade || 'N/A';

    document.getElementById('perf-cards').innerHTML = `
      <div class="card"><div class="card-label">${t('perf.grade')}</div>
        <div class="card-value" style="color:${gradeColor[lastGrade]}">${lastGrade}</div></div>
      <div class="card"><div class="card-label">${t('perf.avg_retrieval')}</div>
        <div class="card-value accent">${((perf.avg_retrieval_score||0)*100).toFixed(0)}%</div></div>
      <div class="card"><div class="card-label">${t('perf.avg_speed')}</div>
        <div class="card-value ${(perf.avg_response_sec||0)>15?'danger':'success'}">
          ${(perf.avg_response_sec||0).toFixed(1)}s</div></div>
      <div class="card"><div class="card-label">${t('perf.high_importance')}</div>
        <div class="card-value warn">${imp.high_importance||0}</div></div>
      <div class="card"><div class="card-label">${t('perf.repeat_errors')}</div>
        <div class="card-value warn">${imp.repeated_errors||0}</div></div>
      <div class="card"><div class="card-label">${t('perf.eval_count')}</div>
        <div class="card-value accent">${perf.eval_count||0}</div></div>
    `;
    await loadPerfHistory();
  } catch (e) {
    document.getElementById('perf-cards').innerHTML =
      `<div class="empty">${e.message}</div>`;
  }
}

async function loadPerfHistory() {
  try {
    const data  = await api('/admin/performance/history/?limit=10');
    const tbody = document.getElementById('perf-history-body');
    const gradeColor = { A:'var(--success)', B:'var(--accent2)',
                         C:'var(--warn)', D:'var(--danger)' };
    tbody.innerHTML = (data.history || []).map(h => `
      <tr>
        <td class="mono">${h.evaluated_at?.slice(0,16)||'-'}</td>
        <td style="color:${gradeColor[h.grade]||'var(--muted)'}">
          <strong>${h.grade}</strong></td>
        <td class="mono">${h.total_score?.toFixed(1)||'-'}/100</td>
        <td class="mono">${((h.metrics?.avg_retrieval_score||0)*100).toFixed(0)}%</td>
        <td class="mono">${h.metrics?.avg_response_sec?.toFixed(1)||'-'}s</td>
        <td style="font-size:11px;color:var(--warn)">
          ${(h.issues||[]).slice(0,2).join(' / ')||'-'}</td>
      </tr>`).join('')
      || `<tr><td colspan='6' class='empty'>${t('perf.no_history')}</td></tr>`;
  } catch (e) {
    document.getElementById('perf-history-body').innerHTML =
      `<tr><td colspan="6" class="empty">${e.message}</td></tr>`;
  }
}

async function runEvaluation() {
  const btn = event.target;
  btn.textContent = t('perf.running'); btn.disabled = true;
  try {
    const r = await api('/admin/performance/evaluate/', 'POST');
    const gc = { A:'✅', B:'🟡', C:'🟠', D:'❌' };
    alert(`${t('perf.eval_done',{grade:r.grade,score:r.total_score,issues:(r.issues||[]).join(', ')||t('perf.no_issue')} )}`);
    await loadPerformance();
  } catch (e) {
    alert(`${t('perf.eval_failed',{msg:e.message})}`);
  } finally {
    btn.textContent = t('perf.run_now'); btn.disabled = false;
  }
}

/* ── 자기학습 ── */

async function loadLearning() {
  try {
    const data  = await api('/admin/learn/error-queries/?min_count=2');
    const tbody = document.getElementById('error-queries-body');
    tbody.innerHTML = (data.error_queries || []).map(q => `
      <tr>
        <td style="font-size:12px">${q.query?.slice(0,50)||'-'}</td>
        <td class="mono">${q.count} times</td>
        <td class="mono">${(q.avg_score*100).toFixed(0)}%</td>
        <td class="mono">${q.last?.slice(0,10)||'-'}</td>
        <td>
          <button class="btn btn-approve" style="font-size:10px"
            onclick="learnSingleTopic('${(q.query||'').replace(/'/g,"\\'")}')">
            Learn</button>
        </td>
      </tr>`).join('')
      || `<tr><td colspan='5' class='empty'>${t('learn.no_errors')}</td></tr>`;
  } catch (e) {
    document.getElementById('error-queries-body').innerHTML =
      `<tr><td colspan="5" class="empty">${e.message}</td></tr>`;
  }
}

async function learnTopic() {
  const topic  = document.getElementById('learn-topic-input')?.value.trim();
  const result = document.getElementById('learn-result');
  if (!topic) { alert(t('learn.enter_topic')); return; }
  if (result) result.textContent = `${t('learn.in_progress',{topic})}`;
  await learnSingleTopic(topic);
}

/* ── [U-1] 웹 검색 장기 학습 (통합 파이프라인) ── */
async function webLearnTopic() {
  const input  = document.getElementById('web-learn-input');
  const result = document.getElementById('web-learn-result');
  const topic  = input?.value.trim();
  if (!topic) { alert(t('learn.enter_search_topic')); return; }

  if (result) {
    result.style.display = 'block';
    result.innerHTML = `
      <div style="color:var(--muted)">
        ${t('learn.web_step1')}<br>
        ${t('learn.web_step2')}<br>
        ${t('learn.web_step3')}<br>
        ${t('learn.web_step4')}
      </div>
      <div style="color:var(--muted);font-size:11px;margin-top:6px">
        (20-40s)
      </div>`;
  }

  try {
    const r = await api(
      `/admin/learn/topic/?topic=${encodeURIComponent(topic)}&use_web=true`, 'POST'
    );

    if (r.success) {
      const sourceLinks = (r.sources||[])
        .map(u => `<a href="${u}" target="_blank"
          style="color:var(--accent);font-size:10px;word-break:break-all">${u.slice(0,60)}</a>`)
        .join('<br>');

      const domainBadge = r.domain
        ? `<span style="background:var(--accent);color:#fff;border-radius:4px;
                        padding:2px 8px;font-size:10px">${r.domain}</span>`
        : '';

      const fetchedNote = r.fetched_urls > 0
        ? `<span style="color:#4caf7d;font-size:10px">
             ✅ ${r.fetched_urls} URL(s) fetched</span>`
        : `<span style="color:var(--muted);font-size:10px">
             ${t('learn.web_no_url')}</span>`;

      result.innerHTML = `
        <div style="color:#4caf7d;font-weight:700;margin-bottom:8px;
                    display:flex;align-items:center;gap:8px">
          ${t('learn.web_done')}  ${domainBadge}
        </div>
        <div style="background:var(--bg);border-radius:6px;padding:10px;
                    margin-bottom:8px;font-size:12px;line-height:1.7;
                    white-space:pre-wrap">${r.knowledge || ''}</div>
        <div style="font-size:11px;color:var(--muted)">
          📄 wiki: ${r.wiki_path ? r.wiki_path.split(/[\\/]/).pop() : '-'}<br>
          ${fetchedNote}<br>
          📚 Sources (${(r.sources||[]).length}):<br>
          ${sourceLinks}
        </div>`;

      toast(`✅ Long-term knowledge saved: '${r.topic}' [${r.domain}]`, 'success');
      setTimeout(() => loadKnowledge(), 1000);
      if (input) input.value = '';
    } else {
      result.innerHTML = `<span style="color:var(--warn)">⚠️ ${r.message}</span>`;
    }
  } catch(e) {
    if (result) result.innerHTML =
      `<span style="color:var(--red)">❌ Failed: ${e.message}</span>`;
  }
}

async function learnSingleTopic(topic) {
  const result = document.getElementById('learn-result');
  try {
    const r = await api(`/admin/learn/topic/?topic=${encodeURIComponent(topic)}`, 'POST');
    const msg = r.success
      ? `✅ '${r.topic}' learned (quality: ${(r.quality*100).toFixed(0)}%) — Proposal: ${r.proposal_id}`
      : `⚠️ '${topic}' ${r.message}`;
    if (result) result.textContent = msg;
    if (r.success) {
      toast(msg, 'success');
      await loadProposals();
    }
  } catch (e) {
    if (result) result.textContent = `❌ Failed: ${e.message}`;
  }
}

async function learnFromErrors() {
  const result = document.getElementById('learn-result');
  if (result) result.textContent = t('learn.auto_learning');
  try {
    const r = await api('/admin/learn/from-errors/', 'POST');
    const msg = r.learned > 0
      ? `${t('learn.auto_done',{count:r.learned,topics:(r.topics||[]).map(x=>x.topic).join(', ')})}`
      : t('learn.no_detected');
    if (result) result.textContent = msg;
    if (r.learned > 0) { await loadProposals(); await loadLearning(); }
  } catch (e) {
    if (result) result.textContent = `❌ Failed: ${e.message}`;
  }
}

/* ════════════════════════════════
   [P2 unified UX 2026-05-10]
   성향 캐릭터 UI — Interactive radar with correlation ripple
   - SVG radar (드래그로 vertex 직접 이동)
   - 점선 edges = 상관관계 (녹/적색 = 양/음 weight)
   - vertex 이동 시 backend ripple 모방 → 영향받는 vertex 펄스
   - 하단 슬라이더는 보조 정밀 입력 (양방향 동기화)
════════════════════════════════ */

let _traits = [];                  // [{id, label, label_ko, group, value, default, icon}]
let _correlations = [];            // [{from, to, weight}]
let _ripple_damping = 0.3;
let _selected_trait_id = null;     // 마지막으로 클릭/드래그한 vertex
let _drag_state = null;            // {tid, pointerId, cx, cy, R, angle}

// Group A~D 짝(opposing) — 백엔드 _OPPONENTS와 정확히 일치해야 함.
const _OPPONENTS = {
  curiosity:'focus',     focus:'curiosity',
  caution:'boldness',    boldness:'caution',
  analytical:'intuitive', intuitive:'analytical',
  independent:'collaborative', collaborative:'independent',
};

async function loadCharacter() {
  try {
    // 두 API 병렬 호출 — traits + correlations.
    const [data, corrData] = await Promise.all([
      api('/admin/character/'),
      api('/admin/character/correlations').catch(() => ({correlations: [], damping: 0.3})),
    ]);
    _traits          = data.traits || [];
    _correlations    = corrData.correlations || [];
    _ripple_damping  = corrData.damping ?? 0.3;
    renderInteractiveRadar();
    renderTraitSliders(_traits);
    renderConnectionsPanel(null);
  } catch (e) {
    console.error('[CHARACTER]', e.message);
  }
}

// ─── 인터랙티브 SVG 레이더 ───────────────────────────────────────
function renderInteractiveRadar() {
  const svg = document.getElementById('char-radar');
  if (!svg) return;

  const W = 600, H = 600;
  const cx = W/2, cy = H/2;
  const R  = Math.min(W, H)/2 - 80;          // 라벨 공간 확보

  const n = _traits.length;
  if (!n) { svg.innerHTML = ''; return; }

  // 각 trait의 angle (위쪽 12시 방향이 첫 trait, 시계방향).
  const angles = _traits.map((_, i) => (i / n) * Math.PI * 2 - Math.PI/2);
  const angleMap = {};
  _traits.forEach((tr, i) => { angleMap[tr.id] = angles[i]; });

  // 좌표 변환 — value(0..1) → (x, y).
  function pt(idx, v) {
    return {
      x: cx + Math.cos(angles[idx]) * R * v,
      y: cy + Math.sin(angles[idx]) * R * v,
    };
  }

  let inner = '';

  // ─── 1) 격자 (4 단계) ────────────────────────────────────────
  [0.25, 0.5, 0.75, 1.0].forEach(r => {
    const pts = angles.map((a) =>
      `${(cx + Math.cos(a)*R*r).toFixed(1)},${(cy + Math.sin(a)*R*r).toFixed(1)}`
    ).join(' ');
    inner += `<polygon class="radar-grid" points="${pts}"/>`;
  });

  // ─── 2) 축 + 라벨 ────────────────────────────────────────────
  angles.forEach((a, i) => {
    const x2 = cx + Math.cos(a) * R;
    const y2 = cy + Math.sin(a) * R;
    inner += `<line class="radar-axis" x1="${cx}" y1="${cy}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}"/>`;
    // 라벨 (icon + 한글명) — 외곽
    const lx = cx + Math.cos(a) * (R + 30);
    const ly = cy + Math.sin(a) * (R + 30);
    const tr = _traits[i];
    const labelText = (tr.label_ko || tr.label);
    inner += `
      <text class="radar-icon" x="${lx.toFixed(1)}" y="${(ly-8).toFixed(1)}"
            text-anchor="middle">${escapeHtml(tr.icon)}</text>
      <text class="radar-label" x="${lx.toFixed(1)}" y="${(ly+8).toFixed(1)}"
            text-anchor="middle">${escapeHtml(labelText)}</text>`;
  });

  // ─── 3) 짝(opposing) 연결선 — 매우 흐리게 ────────────────────
  // 시각적으로 "두 trait이 1.0 sum 짝" 임을 알려줌.
  const drawnPairs = new Set();
  _traits.forEach((tr, i) => {
    const opp = _OPPONENTS[tr.id];
    if (!opp) return;
    const key = [tr.id, opp].sort().join('|');
    if (drawnPairs.has(key)) return;
    drawnPairs.add(key);
    const j = _traits.findIndex(x => x.id === opp);
    if (j < 0) return;
    const p1 = pt(i, _traits[i].value);
    const p2 = pt(j, _traits[j].value);
    inner += `<line class="pair-edge" x1="${p1.x.toFixed(1)}" y1="${p1.y.toFixed(1)}"
                    x2="${p2.x.toFixed(1)}" y2="${p2.y.toFixed(1)}"/>`;
  });

  // ─── 4) 상관관계 edges (선택된 trait 강조) ───────────────────
  _correlations.forEach((corr) => {
    const i = _traits.findIndex(x => x.id === corr.from);
    const j = _traits.findIndex(x => x.id === corr.to);
    if (i < 0 || j < 0) return;
    const p1 = pt(i, _traits[i].value);
    const p2 = pt(j, _traits[j].value);
    const sign = corr.weight >= 0 ? 'pos' : 'neg';
    const isActive = _selected_trait_id &&
                     (corr.from === _selected_trait_id || corr.to === _selected_trait_id);
    const cls = `corr-edge ${sign}` + (isActive ? ' active' : '');
    // 약한 곡선 (Q control point는 중심 쪽으로)
    const mx = (p1.x + p2.x)/2;
    const my = (p1.y + p2.y)/2;
    const tx = cx + (mx - cx) * 0.6;
    const ty = cy + (my - cy) * 0.6;
    const sw = (1 + Math.abs(corr.weight) * 1.5).toFixed(2);
    inner += `<path class="${cls}" d="M${p1.x.toFixed(1)},${p1.y.toFixed(1)}
                                       Q${tx.toFixed(1)},${ty.toFixed(1)}
                                       ${p2.x.toFixed(1)},${p2.y.toFixed(1)}"
                    style="stroke-width:${sw}"/>`;
  });

  // ─── 5) 데이터 폴리곤 (값 영역) ──────────────────────────────
  const polyPts = _traits.map((tr, i) => {
    const p = pt(i, tr.value);
    return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
  }).join(' ');
  inner += `<polygon class="radar-fill" points="${polyPts}"/>`;

  // ─── 6) Vertex (드래그 가능) ─────────────────────────────────
  _traits.forEach((tr, i) => {
    const p = pt(i, tr.value);
    const sel = (tr.id === _selected_trait_id) ? ' selected' : '';
    inner += `<circle class="radar-vertex${sel}"
                      cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="6"
                      data-trait-id="${escapeHtml(tr.id)}"
                      data-axis-index="${i}">
                <title>${escapeHtml(tr.label_ko || tr.label)}: ${Math.round(tr.value*100)}%</title>
              </circle>`;
  });

  svg.innerHTML = inner;

  // ─── 7) Pointer events on vertices ───────────────────────────
  // [PR #157 패턴 준수] inline onclick 없이 addEventListener 로만.
  svg.querySelectorAll('.radar-vertex').forEach(circle => {
    circle.addEventListener('pointerdown', onVertexPointerDown);
  });
}

function onVertexPointerDown(ev) {
  ev.preventDefault();
  const circle = ev.currentTarget;
  const tid = circle.getAttribute('data-trait-id');
  const idx = parseInt(circle.getAttribute('data-axis-index'), 10);
  if (!tid || isNaN(idx)) return;

  _selected_trait_id = tid;
  circle.classList.add('dragging');
  circle.setPointerCapture(ev.pointerId);

  // SVG 내부 좌표 시스템 — viewBox 600x600 기준이지만 화면 픽셀 크기는
  // 다를 수 있음. CTM(currentTransformationMatrix)을 사용해서 변환.
  const svg = document.getElementById('char-radar');
  const n = _traits.length;
  const angle = (idx / n) * Math.PI * 2 - Math.PI/2;
  const cx = 300, cy = 300, R = 220;       // viewBox 600x600 기준

  _drag_state = { tid, idx, pointerId: ev.pointerId, cx, cy, R, angle, svg };

  svg.addEventListener('pointermove', onVertexPointerMove);
  svg.addEventListener('pointerup',   onVertexPointerUp);
  svg.addEventListener('pointercancel', onVertexPointerUp);

  // 첫 드래그 직전 상태 — selected 강조 + 영향력 패널 갱신.
  renderConnectionsPanel(tid);
}

function _svgPointToViewBox(svg, ev) {
  const pt = svg.createSVGPoint();
  pt.x = ev.clientX; pt.y = ev.clientY;
  const ctm = svg.getScreenCTM();
  if (!ctm) return null;
  return pt.matrixTransform(ctm.inverse());
}

function onVertexPointerMove(ev) {
  if (!_drag_state) return;
  const { tid, idx, cx, cy, R, angle, svg } = _drag_state;
  const p = _svgPointToViewBox(svg, ev);
  if (!p) return;
  // 드래그한 좌표를 해당 axis 위 길이로 사영(projection).
  const dx = p.x - cx, dy = p.y - cy;
  const proj = dx * Math.cos(angle) + dy * Math.sin(angle);   // axis 위 스칼라
  let v = proj / R;
  v = Math.max(0, Math.min(1, v));
  v = Math.round(v * 100) / 100;                              // 1% 단위로 snap
  applyTraitChangeLocally(tid, v, /*animate*/ false);
}

function onVertexPointerUp(ev) {
  if (!_drag_state) return;
  const { tid, svg } = _drag_state;
  svg.removeEventListener('pointermove', onVertexPointerMove);
  svg.removeEventListener('pointerup',   onVertexPointerUp);
  svg.removeEventListener('pointercancel', onVertexPointerUp);
  // 드래그 종료 시점 기준으로 ripple animation 시각화.
  const tr = _traits.find(x => x.id === tid);
  if (tr) animateRippleFor(tid, tr.value);
  _drag_state = null;
  // dragging 클래스 제거 (재렌더링이 처리하지만 명시).
  svg.querySelectorAll('.radar-vertex.dragging').forEach(c => c.classList.remove('dragging'));
  renderInteractiveRadar();
  renderConnectionsPanel(tid);
}

// vertex 드래그 / 슬라이더 둘 다 호출 — 백엔드 ripple 로직 미러링.
function applyTraitChangeLocally(traitId, newValue, animate=true) {
  const idx = _traits.findIndex(x => x.id === traitId);
  if (idx < 0) return;
  const old = _traits[idx].value;
  const delta = newValue - old;
  _traits[idx].value = newValue;

  // 짝 즉시 flip.
  const opp = _OPPONENTS[traitId];
  const skip = new Set([traitId]);
  if (opp) {
    const oi = _traits.findIndex(x => x.id === opp);
    if (oi >= 0) {
      _traits[oi].value = Math.round((1 - newValue) * 1000) / 1000;
      skip.add(opp);
    }
  }

  // 상관 trait ripple — backend와 동일 식.
  _correlations.forEach(corr => {
    if (corr.from !== traitId) return;
    if (skip.has(corr.to)) return;
    const ti = _traits.findIndex(x => x.id === corr.to);
    if (ti < 0) return;
    const oldVal = _traits[ti].value;
    const nudge = delta * corr.weight * _ripple_damping;
    let nv = Math.max(0, Math.min(1, oldVal + nudge));
    nv = Math.round(nv * 1000) / 1000;
    _traits[ti].value = nv;
  });

  // SVG + 슬라이더 UI 동기화.
  renderInteractiveRadar();
  syncSlidersToTraits();
  if (animate) {
    // (드래그 중에는 매 프레임 호출되므로 끄고, 종료 시 한번만 발화)
    animateRippleFor(traitId);
  }
}

function animateRippleFor(sourceTid /*, _droppedValue */) {
  // 드래그 종료 후 한 번만: ripple 클래스를 영향받은 vertex에 부여.
  const svg = document.getElementById('char-radar');
  if (!svg) return;
  _correlations.forEach(corr => {
    if (corr.from !== sourceTid) return;
    const targetCircle = svg.querySelector(`.radar-vertex[data-trait-id="${corr.to}"]`);
    if (!targetCircle) return;
    const cls = corr.weight >= 0 ? 'ripple-pos' : 'ripple-neg';
    targetCircle.classList.remove('ripple-pos', 'ripple-neg');
    // force reflow → re-trigger animation
    void targetCircle.getBoundingClientRect();
    targetCircle.classList.add(cls);
    // 슬라이더에도 동일 강조
    const row = document.querySelector(`.trait-row[data-trait-id="${corr.to}"]`);
    if (row) {
      row.classList.remove('ripple-pos', 'ripple-neg');
      void row.getBoundingClientRect();
      row.classList.add(cls);
      setTimeout(() => row.classList.remove(cls), 800);
    }
  });
}

// ─── 우측 패널: 선택한 trait의 영향력 ────────────────────────────
function renderConnectionsPanel(tid) {
  const el = document.getElementById('char-connections');
  if (!el) return;
  if (!tid) {
    el.innerHTML = `<div class="char-connections-empty">${
      escapeHtml(t('char.connections_empty') || '레이더의 점을 클릭하면 그 성향과 연결된 다른 성향들이 표시됩니다.')
    }</div>`;
    return;
  }
  const tr = _traits.find(x => x.id === tid);
  if (!tr) { el.innerHTML = ''; return; }

  // 짝 + 상관 trait 모두 모음.
  const rows = [];
  const opp = _OPPONENTS[tid];
  if (opp) {
    const o = _traits.find(x => x.id === opp);
    if (o) rows.push({label: (o.label_ko || o.label), icon: o.icon, weight: -1.0, kind: 'pair'});
  }
  _correlations.forEach(c => {
    if (c.from === tid) {
      const o = _traits.find(x => x.id === c.to);
      if (o) rows.push({label: (o.label_ko || o.label), icon: o.icon, weight: c.weight, kind: 'corr'});
    }
  });

  let html = `<div style="font-size:12px;color:var(--accent);margin-bottom:6px">
                ${escapeHtml(tr.icon)} ${escapeHtml(tr.label_ko || tr.label)}
                <span style="color:var(--muted);font-size:11px">→ ${rows.length}</span>
              </div>`;
  if (rows.length === 0) {
    html += `<div class="char-connections-empty">독립 성향 (다른 성향에 영향 없음)</div>`;
  } else {
    rows.forEach(r => {
      const sign = r.weight >= 0 ? 'pos' : 'neg';
      const arrow = r.weight >= 0 ? '↑' : '↓';
      let weightLabel;
      if (r.kind === 'pair') {
        weightLabel = '짝(1.0 합)';
      } else {
        const eff = (r.weight * _ripple_damping).toFixed(2);
        weightLabel = `${arrow} ${(eff > 0 ? '+' : '')}${eff}`;
      }
      html += `<div class="char-conn-row">
                 <span class="char-conn-label">${escapeHtml(r.icon)} ${escapeHtml(r.label)}</span>
                 <span class="char-conn-weight ${sign}">${escapeHtml(weightLabel)}</span>
               </div>`;
    });
  }
  el.innerHTML = html;
}

// ─── 보조 입력: 그룹별 슬라이더 (정밀 조정) ──────────────────────
function renderTraitSliders(traits) {
  const container = document.getElementById('trait-sliders');
  if (!container) return;
  // Group 라벨 — i18n 미정의 시 기본값 fallback.
  const groups = {
    A: t('char.group_a') || 'A · 인지 (탐구 ↔ 집중)',
    B: t('char.group_b') || 'B · 신중성 (신중 ↔ 과감)',
    C: t('char.group_c') || 'C · 사고 (분석 ↔ 직관)',
    D: t('char.group_d') || 'D · 사회성 (독립 ↔ 협력)',
    E: t('char.group_e') || 'E · 핵심 가치 (독립)',
    F: t('char.group_f') || 'F · 표현 스타일 (독립)',
  };
  // 그룹별 묶음 — Object.groupBy 사용 가능 환경이면 더 깔끔하지만 폴리필.
  const byGroup = {};
  traits.forEach(tr => {
    if (!byGroup[tr.group]) byGroup[tr.group] = [];
    byGroup[tr.group].push(tr);
  });

  let html = '';
  Object.keys(byGroup).sort().forEach(g => {
    html += `<div class="trait-group">
      <div style="font-size:9px;color:var(--muted);font-family:var(--font-mono);
                  letter-spacing:1px;margin:6px 0">
        GROUP ${g} — ${escapeHtml(groups[g])}
      </div>`;
    byGroup[g].forEach(tr => {
      const pct = Math.round(tr.value * 100);
      html += `
        <div class="trait-row" data-trait-id="${escapeHtml(tr.id)}"
             style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
          <span style="width:22px;text-align:center">${escapeHtml(tr.icon)}</span>
          <span style="width:90px;font-size:12px;color:var(--text)">${escapeHtml(tr.label_ko || tr.label)}</span>
          <input type="range" min="0" max="100" value="${pct}"
                 data-slider-id="${escapeHtml(tr.id)}"
                 style="flex:1;accent-color:var(--accent)">
          <span class="trait-pct" data-pct-id="${escapeHtml(tr.id)}"
                style="width:36px;font-size:11px;font-family:var(--font-mono);
                       color:var(--accent);text-align:right">${pct}%</span>
        </div>`;
    });
    html += `</div>`;
  });
  container.innerHTML = html;

  // [PR #157 패턴] data-attr + addEventListener — inline oninput X.
  container.querySelectorAll('input[type="range"][data-slider-id]').forEach(input => {
    input.addEventListener('input', onSliderInput);
    input.addEventListener('change', onSliderChangeCommit);
  });
}

function onSliderInput(ev) {
  const tid = ev.currentTarget.getAttribute('data-slider-id');
  const v = parseInt(ev.currentTarget.value, 10) / 100;
  _selected_trait_id = tid;
  applyTraitChangeLocally(tid, v, /*animate*/ false);
  renderConnectionsPanel(tid);
}

function onSliderChangeCommit(ev) {
  const tid = ev.currentTarget.getAttribute('data-slider-id');
  animateRippleFor(tid);
}

function syncSlidersToTraits() {
  _traits.forEach(tr => {
    const slider = document.querySelector(`input[data-slider-id="${tr.id}"]`);
    const pct = document.querySelector(`[data-pct-id="${tr.id}"]`);
    const newPct = Math.round(tr.value * 100);
    if (slider && parseInt(slider.value, 10) !== newPct) slider.value = newPct;
    if (pct) pct.textContent = newPct + '%';
  });
}

// ─── Save / Reset ────────────────────────────────────────────────
async function saveCharacter() {
  let ok = true;
  // 백엔드 set_trait는 짝/ripple를 자동 적용하므로 — 중복 적용 방지를
  // 위해 "변경된 trait의 source 만" 보내도 되지만, 안전하게는 전부
  // POST. 서버가 멱등(idempotent)이라 같은 값 다시 보내도 문제 없음.
  for (const tr of _traits) {
    try {
      await api('/admin/character/', 'POST',
        { api_key: apiKey, trait_id: tr.id, value: tr.value });
    } catch { ok = false; }
  }
  toast(
    ok ? (t('char.save_ok') || '성향 저장 완료')
       : (t('char.save_warn') || '일부 성향 저장 실패'),
    ok ? 'success' : 'warn'
  );
}

function resetCharacter() {
  // 백엔드 TRAITS의 default 값과 매치 — 16 traits.
  const defaults = {
    curiosity:.5, focus:.5, caution:.7, boldness:.3,
    analytical:.6, intuitive:.4, independent:.5, collaborative:.5,
    security:.9, creativity:.5, empathy:.5,
    conciseness:.5, directness:.5, optimism:.5,
    risk_tolerance:.4, patience:.6,
  };
  _traits.forEach(tr => { tr.value = defaults[tr.id] ?? tr.default ?? 0.5; });
  _selected_trait_id = null;
  renderInteractiveRadar();
  renderTraitSliders(_traits);
  renderConnectionsPanel(null);
}

// 글로벌 export — 인라인 onclick (HTML의 saveCharacter / resetCharacter).
window.saveCharacter  = saveCharacter;
window.resetCharacter = resetCharacter;

/* ════════════════════════════════
   P7-EVO-E: 능력 성장 UI
════════════════════════════════ */

async function loadKnowledge() {
  try {
    const data = await api('/admin/knowledge/');
    renderCapabilities(data.capabilities || []);
    renderDomains(data.domains || []);
    const gains = data.recent_gains || [];
    const el = document.getElementById('recent-gains');
    if (el && gains.length)
      el.textContent = t('growth.recent_gains') + gains.join(' | ');
  } catch (e) {
    console.error('[KNOWLEDGE]', e.message);
  }
}

function renderCapabilities(caps) {
  const el = document.getElementById('capability-bars');
  if (!el) return;
  el.innerHTML = caps.map(c => `
    <div style="margin-bottom:14px">
      <div style="display:flex;justify-content:space-between;margin-bottom:4px">
        <span style="font-size:13px">${c.icon} <strong>${c.label}</strong></span>
        <span style="font-size:12px;font-family:var(--font-mono);color:var(--accent)">${c.pct}%</span>
      </div>
      <div style="background:var(--border);border-radius:4px;height:8px;overflow:hidden">
        <div style="width:${c.pct}%;height:100%;background:var(--accent);
          border-radius:4px;transition:width .5s ease"></div>
      </div>
      <div style="font-size:10px;color:var(--muted);margin-top:3px">${c.desc}</div>
    </div>`).join('');
}

/* [#2-C] 도메인별 도넛 차트.
   linear bar 대신 SVG ring으로 표시 — 진행도(tier_pct)가 호의 길이로
   한눈에 보이고, level cap 제거(#2-B)로 두 자리 레벨도 자연스럽게
   중앙에 표기. ring의 stroke-dasharray로 진행도를 그려 transition 적용.
   각 도메인 색을 stage-color로 전달해 도넛 stroke + glow에 inject. */
function _domainDonut(d) {
  const r = 32;                // 반지름
  const cx = 40, cy = 40;
  const circ = 2 * Math.PI * r;
  const tierPct = (d.tier_pct != null ? d.tier_pct : (d.pct ?? 0));
  const filled = circ * (tierPct / 100);
  return `
    <svg viewBox="0 0 80 80" width="80" height="80" aria-label="domain progress">
      <!-- 배경 트랙 -->
      <circle cx="${cx}" cy="${cy}" r="${r}"
              fill="none" stroke="var(--border, #2a2d33)" stroke-width="6"/>
      <!-- 진행 호 -->
      <circle cx="${cx}" cy="${cy}" r="${r}"
              fill="none" stroke="${d.color}" stroke-width="6"
              stroke-linecap="round"
              transform="rotate(-90 ${cx} ${cy})"
              stroke-dasharray="${filled} ${circ}"
              style="filter:drop-shadow(0 0 4px ${d.color}88);
                     transition:stroke-dasharray .6s ease"/>
      <!-- 중앙 레벨 숫자 -->
      <text x="${cx}" y="${cy + 1}" text-anchor="middle"
            dominant-baseline="middle"
            style="font-size:20px;font-weight:900;fill:${d.color};
                   font-family:var(--font-mono, ui-monospace, monospace);
                   letter-spacing:-1px">${d.level}</text>
      <!-- "Lv" 레이블 -->
      <text x="${cx}" y="${cy - 13}" text-anchor="middle"
            style="font-size:8px;fill:var(--muted, #888);
                   font-family:var(--font-mono, ui-monospace, monospace);
                   letter-spacing:1px">LV</text>
    </svg>
  `;
}

function renderDomains(domains) {
  const el = document.getElementById('domain-levels');
  if (!el) return;
  // [#2-C] 도넛 차트 그리드. 카드별 좌측 도넛 + 우측 메타데이터.
  // [#2-B] level cap 제거 — "/10" 표기 삭제. 큰 숫자는 도넛 중앙에서
  // 자동 fit (font-size 20px가 두 자리도 안전).
  el.innerHTML = `<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:12px">` +
    domains.map(d => `
      <div style="background:var(--surface);border:1px solid var(--border);
        border-radius:8px;padding:14px;display:flex;align-items:center;gap:14px">
        <!-- 좌: 도넛 -->
        <div style="flex-shrink:0">${_domainDonut(d)}</div>
        <!-- 우: 메타 -->
        <div style="flex:1;min-width:0">
          <div style="font-size:13px;margin-bottom:6px">
            ${d.icon} <strong>${d.label}</strong>
          </div>
          <div style="font-size:10px;color:var(--muted);
                      font-family:var(--font-mono);line-height:1.6">
            <div>다음까지 <strong style="color:${d.color}">${d.tier_pct ?? d.pct}%</strong></div>
            <div>📄 ${d.wiki_count ?? 0} wiki · score ${d.score ?? 0}</div>
          </div>
        </div>
      </div>`).join('') + '</div>';
}

/* ── [P3-1] 하드웨어 장비 현황 ── */
async function loadHardware() {
  try {
    const data = await api('/hardware/');
    const specs = data.specs || {};

    const rankEl  = document.getElementById('hw-rank-badge');
    const labelEl = document.getElementById('hw-rank-label');
    if (rankEl) {
      const lv   = specs.overall_level || 1;
      const stars = '★'.repeat(Math.min(lv, 10));
      rankEl.textContent = `Lv.${lv}  ${stars}`;
      rankEl.style.color = lv >= 8 ? '#f06292' : lv >= 6 ? '#7c6af7' : '#4fc3f7';
    }
    if (labelEl) labelEl.textContent = specs.james_rank || '';

    const cardsEl = document.getElementById('hw-cards');
    if (cardsEl) {
      const comps = [
        { key:'cpu',  spec: specs.cpu  || {} },
        { key:'ram',  spec: specs.ram  || {} },
        { key:'gpu',  spec: specs.gpu  || {} },
        { key:'disk', spec: specs.disk || {} },
      ];
      const lvColor = lv => lv >= 9 ? '#f06292' : lv >= 7 ? '#7c6af7'
                           : lv >= 5 ? '#4fc3f7' : lv >= 3 ? '#4caf7d' : '#aaa';

      cardsEl.innerHTML = comps.map(({ key, spec }) => {
        const w   = spec.weapon || {};
        const lv  = spec.level  || 0;
        const col = lvColor(lv);
        let detail = '';
        if (key==='cpu')  detail=`${spec.cores||'?'} cores · ${spec.freq_mhz||'?'}MHz ${spec.usage_pct!=null?`· ${spec.usage_pct}%`:''}`;
        if (key==='ram')  detail=`${spec.total_gb||'?'}GB total · ${spec.available_gb||'?'}GB free`;
        if (key==='gpu')  detail=spec.found ? `${spec.name} (${spec.vram_gb||'?'}GB)` : t('hw.cpu_only');
        if (key==='disk') detail=`${spec.total_gb||'?'}GB · free ${spec.free_gb||'?'}GB`;
        return `
          <div style="background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
              <div style="font-size:28px">${w.icon||'🔧'}</div>
              <div><div style="font-weight:700;font-size:15px">${w.name||'?'}</div>
                   <div style="font-size:10px;color:var(--muted)">${w.role||key}</div></div>
              <div style="margin-left:auto;font-size:26px;font-weight:900;color:${col};font-family:var(--font-mono)">
                ${lv}<span style="font-size:11px;font-weight:400;color:var(--muted)">/10</span></div>
            </div>
            <div style="background:var(--bg);border-radius:4px;height:6px;overflow:hidden;margin-bottom:8px">
              <div style="width:${Math.min(100,lv*10)}%;height:100%;background:${col};border-radius:4px;transition:width .8s;box-shadow:0 0 8px ${col}66"></div>
            </div>
            <div style="font-size:11px;color:var(--muted);font-family:var(--font-mono);margin-bottom:4px">${detail}</div>
            <div style="font-size:11px;color:var(--text)">${w.desc||''}</div>
          </div>`;
      }).join('');
    }

    const sysEl = document.getElementById('hw-sysinfo');
    if (sysEl) sysEl.innerHTML = [
      `🖥️  플랫폼:  ${specs.platform||'?'}`,
      `⚔️  CPU:    ${specs.cpu?.name||'?'} (${specs.cpu?.cores||'?'}cores)`,
      `🛡️  RAM:    ${specs.ram?.total_gb||'?'} GB`,
      `🪄  GPU:    ${specs.gpu?.found ? specs.gpu?.name : t('hw.cpu_only')} ${specs.gpu?.vram_gb?`(${specs.gpu.vram_gb}GB)`:''}`,
      `🎒  Disk:   ${specs.disk?.total_gb||'?'}GB (free ${specs.disk?.free_gb||'?'}GB)`,
    ].map(l=>`<div>${l}</div>`).join('');

    // [4-B] LLM 추천 로드
    await loadLLMRecommend();

  } catch(e) {
    const el = document.getElementById('hw-cards');
    if (el) el.innerHTML = `<div style="color:var(--muted)">측정 실패: ${e.message}</div>`;
  }
}

/* ── [4-B] LLM 추천 + 설치 ── */
async function loadLLMRecommend() {
  const el = document.getElementById('llm-recommend-list');
  if (!el) return;
  try {
    const [recData, instData] = await Promise.all([
      api('/admin/llm/recommend'),
      api('/admin/llm/installed').catch(() => ({ models: [] })),
    ]);
    const installed = new Set((instData.models||[]).map(m => m.name));
    const recs      = recData.recommendations || [];
    const feasible  = recs.filter(m => m.feasible);
    const infeasible= recs.filter(m => !m.feasible);

    const renderCard = (m) => {
      const isInstalled = installed.has(m.name);
      const purposes    = (m.purpose||[]).map(p => ({
        chat:'💬',retrieval:'🔍',coding:'💻',multimodal:'🖼️'
      }[p]||p)).join(' ');
      const btnStyle = isInstalled
        ? `background:#4caf7d;cursor:default`
        : `background:var(--accent);cursor:pointer`;
      const btnLabel = isInstalled ? t('hw.llm_installed') : `${t('hw.llm_install_btn',{size:m.size_gb})}`;
      const cardBg   = isInstalled ? 'rgba(76,175,125,.08)' : 'var(--surface)';

      return `<div style="display:flex;align-items:center;gap:12px;padding:10px;
                           margin-bottom:8px;border-radius:8px;
                           background:${cardBg};border:1px solid var(--border)">
        <div style="flex:1">
          <div style="font-weight:700;font-size:13px">${m.name}</div>
          <div style="font-size:11px;color:var(--muted);margin-top:2px">
            ${purposes} ${m.desc}
          </div>
        </div>
        <div style="font-size:11px;color:var(--muted);text-align:right;min-width:60px">
          ${m.size_gb}GB
        </div>
        <button onclick="installLLM('${m.name}', this)"
                style="border:none;border-radius:6px;padding:5px 12px;
                       font-size:11px;font-weight:600;color:#fff;
                       ${btnStyle}" ${isInstalled?'disabled':''}>
          ${btnLabel}
        </button>
      </div>`;
    };

    el.innerHTML = `
      <div style="font-size:12px;color:var(--muted);margin-bottom:10px">
        📊 GPU ${recData.specs_summary?.gpu || '?'} · RAM ${recData.specs_summary?.ram || '?'}
        · ${t('hw.llm_feasible',{count:feasible.length})}
      </div>
      ${feasible.map(renderCard).join('')}
      ${infeasible.length > 0 ? `
        <details style="margin-top:8px">
          <summary style="font-size:11px;color:var(--muted);cursor:pointer">
            ${t('hw.llm_low_specs',{count:infeasible.length})}
          </summary>
          <div style="margin-top:8px;opacity:.6">
            ${infeasible.map(m => `
              <div style="display:flex;justify-content:space-between;
                          padding:6px 0;border-bottom:1px solid var(--border);
                          font-size:11px">
                <span>${m.name}</span>
                <span style="color:var(--muted)">${m.reason_fail||''}</span>
              </div>`).join('')}
          </div>
        </details>` : ''}`;
  } catch(e) {
    el.innerHTML = `<div style="color:var(--muted);font-size:12px">
      LLM 추천 실패: ${e.message}<br>
      <span style="font-size:10px">Ollama가 실행 중인지 확인하세요</span>
    </div>`;
  }
}

async function installLLM(modelName, btn) {
  if (!confirm(`'${modelName}' 다운로드하시겠습니까?\n(모델 크기에 따라 수분~수십분 소요)`)) return;
  btn.disabled = true;
  btn.textContent = t('hw.llm_installing');
  btn.style.background = '#ffb74d';
  try {
    const r = await api(`/admin/llm/pull?model=${encodeURIComponent(modelName)}`, 'POST');
    if (r.ok) {
      btn.textContent = '✅ Installed';
      btn.style.background = '#4caf7d';
      toast(t('hw.llm_install_done',{model:modelName}), 'success');
      // 어드민 설정 드롭다운 갱신
      const sel = document.getElementById('set-model');
      if (sel && !Array.from(sel.options).find(o => o.value === modelName)) {
        const opt = document.createElement('option');
        opt.value = opt.textContent = modelName;
        sel.add(opt);
      }
    } else {
      throw new Error(r.error || t('hw.install_failed'));
    }
  } catch(e) {
    btn.textContent = '❌ Failed';
    btn.style.background = '#f06292';
    btn.disabled = false;
    alert(`Install failed: ${e.message}`);
  }
}

