/* PROJECT JAMES — Chat JS */

// Same-origin: works on PC (http://127.0.0.1:8000), phone via
// Tailscale Serve (https://james.xxx.ts.net), or any future reverse
// proxy. Avoids the mixed-content block when the page is loaded
// over https but the API was hardcoded to http.
const API = window.location.origin;
let SOURCE_TYPE = 'prod';
let token    = sessionStorage.getItem('james_token') || '';
let userRole = sessionStorage.getItem('james_role')  || '';

/* ── [STEP 5-A / 5-C] 언어 토글 ── */
function toggleLang() {
  const cur  = (typeof getLang === 'function') ? getLang() : 'ko';
  const next = cur === 'ko' ? 'en' : 'ko';
  if (typeof setLang === 'function') setLang(next);

  // [5-C] UI 언어 전환 시 LLM 응답 언어도 동기화
  const llmLang = next === 'en' ? 'English' : 'Korean';
  sessionStorage.setItem('james_session_lang', llmLang);
  console.log(`[LANG] UI=${next} → LLM session_language=${llmLang}`);
}

/* 페이지 로드 시 언어 표시기 동기화 */
window.addEventListener('DOMContentLoaded', () => {
  const indicator = document.getElementById('lang-current');
  if (indicator && typeof getLang === 'function') {
    indicator.textContent = getLang().toUpperCase();
  }
  // [5-C] 초기 LLM 언어 = UI 기본 언어 (영어)
  if (!sessionStorage.getItem('james_session_lang')) {
    sessionStorage.setItem('james_session_lang', 'English');
  }
});

/* ── 토큰 유틸 ── */
function getToken()  { return sessionStorage.getItem('james_token') || token || ''; }
function saveToken(t, role) {
  token = t; userRole = role;
  sessionStorage.setItem('james_token', t);
  sessionStorage.setItem('james_role',  role);
}

// JWT 만료까지 남은 초 (파싱 실패 시 0)
function tokenSecondsLeft() {
  const t = getToken();
  if (!t) return 0;
  try {
    const payload = JSON.parse(atob(t.split('.')[1].replace(/-/g,'+').replace(/_/g,'/')));
    return Math.max(0, payload.exp - Math.floor(Date.now() / 1000));
  } catch { return 0; }
}

// 토큰 만료 임박 감지 (30분 이하 → 경고 배지)
function checkTokenExpiry() {
  const left = tokenSecondsLeft();
  if (!getToken()) return;
  if (left === 0) {
    // 이미 만료 — 자동 재로그인 유도
    token = '';
    sessionStorage.removeItem('james_token');
    updateRoleBadge();
    const warn = document.createElement('div');
    warn.style.cssText = 'position:fixed;top:60px;left:50%;transform:translateX(-50%);' +
      'background:#f06292;color:#fff;padding:10px 20px;border-radius:8px;' +
      'z-index:9999;font-size:13px;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,.3)';
    warn.innerHTML = '⚠️ 로그인 세션이 만료됐습니다. 클릭하면 재로그인합니다.';
    warn.onclick = () => { warn.remove(); showLogin(); };
    document.body.appendChild(warn);
    setTimeout(() => warn.remove?.(), 10000);
  } else if (left < 1800) {
    // 30분 이하 — 경고
    const badge = document.getElementById('role-badge');
    if (badge) badge.title = `세션 ${Math.floor(left/60)}분 후 만료`;
  }
}

// 5분마다 만료 확인
setInterval(checkTokenExpiry, 5 * 60 * 1000);

/* ── 초기화 ── */
window.addEventListener('DOMContentLoaded', () => {
  if (!localStorage.getItem('james_api_key')) {
    const key = prompt('JAMES API Key를 입력하세요:') || '';
    if (key) localStorage.setItem('james_api_key', key);
  }
  updateRoleBadge();
});


/* ════════════════════════════════
   대화 세션 관리
════════════════════════════════ */

// 세션 ID — 탭 단위 유지 (새 탭은 새 세션)
function getSessionId() {
  let sid = sessionStorage.getItem('james_session');
  if (!sid) {
    sid = 'sess_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
    sessionStorage.setItem('james_session', sid);
  }
  return sid;
}

const SESSION_ID = getSessionId();
const HISTORY_KEY = `james_history_${SESSION_ID}`;
const MAX_STORED  = 50;  // localStorage 최대 저장 턴 수

/* ── 대화 localStorage 저장 ── */
function saveToLocal(role, text, meta = {}) {
  try {
    const history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    history.push({ role, text, meta, time: Date.now() });
    if (history.length > MAX_STORED) history.splice(0, history.length - MAX_STORED);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  } catch {}
}

/* ── 이전 대화 복원 ── */
function restoreHistory() {
  try {
    const history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    if (!history.length) return;

    hideWelcome();
    history.forEach(({ role, text, meta }) => {
      if (role === 'user') {
        appendMsg('user', text);
      } else {
        appendJamesMsg({ answer: text, mode: meta.mode || '', graph_paths: meta.paths || [] });
      }
    });

    // 복원 안내 배지
    const badge = document.createElement('div');
    badge.style.cssText = 'text-align:center;font-size:11px;color:var(--muted);padding:8px;font-family:var(--font-mono)';
    badge.textContent = `↑ 이전 대화 ${history.length}개 복원됨`;
    document.getElementById('messages').prepend(badge);
  } catch {}
}

/* ── 대화 초기화 (요약 저장 후 삭제) ── */
async function clearHistory() {
  if (!confirm('현재 대화를 초기화할까요?\n대화 내용이 장기 기억으로 요약 저장됩니다.')) return;

  // 요약 먼저 저장 (장기 기억)
  await summarizeSession();

  // 단기 기억 삭제
  localStorage.removeItem(HISTORY_KEY);
  fetch(`${API}/history/?api_key=${getApiKey()}&session_id=${SESSION_ID}`, {
    method:  'DELETE',
    headers: getAuthHeaders(),
  }).catch(() => {});
  location.reload();
}

/* ── 세션 요약 저장 (장기 기억) ── */
async function summarizeSession() {
  const history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
  if (history.length < 2) return;  // 대화 없으면 스킵

  try {
    await fetch(`${API}/history/summarize/?api_key=${getApiKey()}&session_id=${SESSION_ID}`, {
      method:  'POST',
      headers: getAuthHeaders(),
    });
    console.log('[JAMES] 세션 요약 저장 완료');
  } catch (e) {
    console.warn('[JAMES] 세션 요약 실패:', e.message);
  }
}

/* ── 페이지 종료 시 자동 요약 ── */
window.addEventListener('beforeunload', () => {
  const history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
  if (history.length < 4) return;  // 최소 2턴 이상일 때만

  // sendBeacon으로 비동기 전송 (페이지 언로드 중에도 동작)
  const url = `${API}/history/summarize/?api_key=${getApiKey()}&session_id=${SESSION_ID}`;
  navigator.sendBeacon(url);
});

/* ── API Key ── */
function getApiKey() {
  return localStorage.getItem('james_api_key') || '';
}

/* ── 소스 타입 전환 ── */
function setSource(type, btn) {
  SOURCE_TYPE = type;
  document.querySelectorAll('.source-toggle button')
    .forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

/* ════════════════════════════════
   로그인 / 로그아웃
════════════════════════════════ */

function showLogin() {
  if (token) return;   // 이미 로그인됨 → 무시
  document.getElementById('login-modal').classList.remove('hidden');
  document.getElementById('login-id').focus();
  document.getElementById('login-error').textContent = '';
}

function closeLogin() {
  document.getElementById('login-modal').classList.add('hidden');
}

function closeLoginOutside(e) {
  if (e.target === document.getElementById('login-modal')) closeLogin();
}

async function doLogin() {
  const username = document.getElementById('login-id').value.trim();
  const password = document.getElementById('login-pw').value;
  const errEl    = document.getElementById('login-error');
  errEl.textContent = '';

  if (!username || !password) {
    errEl.textContent = '아이디와 비밀번호를 입력하세요.';
    return;
  }

  try {
    const r = await fetch(`${API}/login/`, {
      method:  'POST',
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify({
        username, password,
        api_key: getApiKey(),
      }),
    });

    const data = await r.json();

    if (!r.ok) {
      errEl.textContent = data.detail || '로그인 실패';
      return;
    }

    // 토큰 저장
    token    = data.access_token;
    userRole = data.role || 'employee';
    sessionStorage.setItem('james_token', token);
    localStorage.setItem('james_role',  userRole);

    closeLogin();
    updateRoleBadge();
    document.getElementById('login-pw').value = '';

    toast(`✅ ${username} (${userRole}) 로그인 완료`, 'success');

  } catch (e) {
    errEl.textContent = `서버 오류: ${e.message}`;
  }
}

function logout() {
  token    = '';
  userRole = '';
  sessionStorage.removeItem('james_token');
  sessionStorage.removeItem('james_role');
  updateRoleBadge();
  toast('로그아웃 완료', 'success');
}

function updateRoleBadge() {
  const badge    = document.getElementById('role-badge');
  const roleText = document.getElementById('role-name');

  if (token && userRole) {
    badge.classList.add('logged-in');
    badge.onclick = null;
    badge.style.cursor = 'default';

    const roleColor = {
      admin:    'var(--danger)',
      manager:  'var(--warn)',
      employee: 'var(--accent)',
      external: 'var(--muted)',
    }[userRole] || 'var(--muted)';

    roleText.innerHTML = `
      <span style="color:${roleColor};font-weight:600">${userRole.toUpperCase()}</span>
      <button class="logout-btn" onclick="logout()" title="로그아웃">✕</button>
    `;
  } else {
    badge.classList.remove('logged-in');
    badge.onclick = showLogin;
    badge.style.cursor = 'pointer';
    roleText.innerHTML = '로그인';
  }
}

/* ════════════════════════════════
   인증 헬퍼
════════════════════════════════ */

function getAuthHeaders() {
  const h = {'Content-Type': 'application/json'};
  if (token) h['Authorization'] = `Bearer ${token}`;
  return h;
}

/* ── textarea 자동 높이 ── */
function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

/* ── 키 핸들러 ── */
function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

/* ── 칩 클릭 ── */
function useChip(el) {
  const input = document.getElementById('chat-input');
  input.value = el.textContent;
  autoResize(input);
  input.focus();
}

/* ════════════════════════════════
   메시지 전송
════════════════════════════════ */

async function sendMessage() {
  const input = document.getElementById('chat-input');
  const text  = input.value.trim();
  if (!text) return;

  hideWelcome();
  appendMsg('user', text);
  saveToLocal('user', text);
  input.value = '';
  input.style.height = 'auto';

  // [STEP2-A FIX] 언어 변경 명령 감지 → 요청 전에 세션 언어 즉시 변경
  const langPatterns = [
    { pattern: /영어|english/i,  lang: 'english'  },
    { pattern: /한국어|korean/i, lang: 'korean'   },
    { pattern: /일본어|japanese/i,lang: 'japanese' },
  ];
  const resetPattern = /다시\s*(한국어|원래|기본)|한국어로\s*(돌아|바꿔|복원)/;

  if (resetPattern.test(text)) {
    sessionStorage.removeItem('james_session_lang');
  } else if (/영어|한국어|일본어|english|korean|japanese/i.test(text) &&
             /로|으로|말해|답해|해줘|전환|바꿔/i.test(text)) {
    const matched = langPatterns.find(p => p.pattern.test(text));
    if (matched) {
      sessionStorage.setItem('james_session_lang', matched.lang);
      toast(`언어 설정: ${matched.lang}`, 'success');
    }
  }

  const typing = appendTyping();
  document.getElementById('send-btn').disabled = true;

  try {
    const r = await fetch(`${API}/query/`, {
      method:  'POST',
      headers: getAuthHeaders(),
      body:    JSON.stringify({
        question:         text,
        api_key:          getApiKey(),
        source_type:      SOURCE_TYPE,
        session_id:       SESSION_ID,
        session_language: sessionStorage.getItem('james_session_lang') || '',
      }),
    });

    typing.remove();

    if (r.status === 401) {
      token = '';
      sessionStorage.removeItem('james_token');
      updateRoleBadge();
      appendMsg('james', '⚠️ 인증이 만료됐습니다. 다시 로그인해주세요.');
      showLogin();
      return;
    }

    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      appendMsg('james', `오류: ${err.detail || r.statusText}`);
      return;
    }

    const data = await r.json();
    appendJamesMsg(data);

    // ── [4-A] 특이사항 알림 ────────────────────────────────
    // 웹 검색으로 보완된 경우
    if (data.mode === 'web_augmented' || data.web_searched) {
      jamesNotify(t('toast.web_augmented'), 'web');
    }
    // 장기 기억 저장된 경우
    if (data.longterm_saved) {
      jamesNotify(t('toast.longterm_saved'), 'memory');
    }
    // 지식 레벨 변화
    if (data.level_up) {
      jamesNotify(`🎯 지식 레벨 +${data.level_up.delta} [${data.level_up.domain}]`, 'levelup');
    }
    // 자료 없음 경고
    if (data.unified_score != null && data.unified_score < 0.1 && !data.blocked) {
      jamesNotify(t('toast.no_internal'), 'warn');
    }

    // localStorage에 자메스 답변 저장
    saveToLocal('james', data.answer || '', {mode: data.mode, paths: data.graph_paths});

  } catch (err) {
    typing.remove();
    appendMsg('james', `연결 오류: ${err.message}`);
  } finally {
    document.getElementById('send-btn').disabled = false;
  }
}

/* ════════════════════════════════
   메시지 렌더링
════════════════════════════════ */

function hideWelcome() {
  const w = document.getElementById('welcome');
  if (w) w.remove();
}

function appendMsg(role, text) {
  const messages = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  div.innerHTML = `
    <div class="avatar ${role}">${role === 'james' ? '🧠' : '👤'}</div>
    <div class="bubble">${escHtml(text)}</div>
  `;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

function appendJamesMsg(data) {
  const messages = document.getElementById('messages');
  const answer   = data.answer     || '응답 없음';
  const mode     = data.mode       || '';
  const paths    = data.graph_paths || [];
  const timing   = data.timing_sec != null ? `${data.timing_sec}s` : '';
  const dirId    = data.direction_id ||
    (data.answer ? btoa(encodeURIComponent(
      (data.mode||'') + ':' + (data.answer||'').slice(0,40)
    )).slice(0,12) : '');

  // [3-B] unified_score → 신뢰도 배지
  const score = data.unified_score;
  let confidenceBadge = '';
  if (score != null) {
    const pct = Math.round(score * 100);
    const barColor = pct >= 70 ? '#4caf7d' : pct >= 40 ? '#ffb74d' : '#f06292';
    const label    = pct >= 70 ? t('badge.source_based')
                   : pct >= 40 ? t('badge.partial')
                   : t('badge.inference_only');
    const title    = pct < 40 ? t('badge.inference_warn') : '';
    confidenceBadge = `
      <div style="display:flex;align-items:center;gap:6px;margin-top:6px" ${title ? `title="${title}"` : ''}>
        <span style="font-size:10px;color:var(--muted)">${label}</span>
        <div style="flex:1;max-width:80px;background:var(--bg);border-radius:3px;height:4px;overflow:hidden">
          <div style="width:${pct}%;height:100%;background:${barColor};border-radius:3px;transition:width .5s"></div>
        </div>
        <span style="font-size:10px;font-family:var(--font-mono);color:${barColor}">${pct}%</span>
      </div>`;
  }

  const div = document.createElement('div');
  div.className = 'msg james';

  let pathsHtml = '';
  if (paths.length > 0) {
    const list = paths.map(p => `<div>→ ${escHtml(p)}</div>`).join('');
    pathsHtml = `<div class="graph-paths"><div class="path-title">GRAPH PATHS</div>${list}</div>`;
  }

  let metaHtml = '';
  if (mode || timing) {
    metaHtml = `<div class="meta">`;
    if (mode)         metaHtml += `<span class="mode-badge">${escHtml(mode)}</span>`;
    if (timing)       metaHtml += `<span>${timing}</span>`;
    if (data.graph_used) metaHtml += `<span class="graph-badge">graph ×${data.graph_used}</span>`;
    metaHtml += `</div>`;
  }

  // 👍👎 피드백 버튼
  const fbHtml = dirId ? `
    <div class="feedback-btns" style="display:flex;gap:6px;margin-top:6px">
      <button class="fb-btn" onclick="sendFeedback('${dirId}', 'explicit_positive', this)"
        style="background:none;border:1px solid var(--border);border-radius:6px;
               padding:3px 10px;cursor:pointer;color:var(--muted);font-size:12px;
               transition:all .15s" title="좋아요">👍</button>
      <button class="fb-btn" onclick="sendFeedback('${dirId}', 'explicit_negative', this)"
        style="background:none;border:1px solid var(--border);border-radius:6px;
               padding:3px 10px;cursor:pointer;color:var(--muted);font-size:12px;
               transition:all .15s" title="별로예요">👎</button>
    </div>` : '';

  div.innerHTML = `
    <div class="avatar james">🧠</div>
    <div>
      <div class="bubble">${formatAnswer(answer)}${pathsHtml}</div>
      ${confidenceBadge}
      ${metaHtml}
      ${fbHtml}
    </div>
  `;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

/* ── 피드백 전송 ── */
async function sendFeedback(directionId, signal, btn) {
  try {
    await fetch(`${API}/feedback/`, {
      method:  'POST',
      headers: {'Content-Type':'application/json', ...getAuthHeaders()},
      body: JSON.stringify({
        api_key:      getApiKey(),
        direction_id: directionId,
        signal:       signal,
        query:        '',
      }),
    });
    // 버튼 시각적 피드백
    btn.style.background = signal === 'explicit_positive'
      ? 'rgba(76,175,125,.15)' : 'rgba(240,98,146,.12)';
    btn.style.borderColor = signal === 'explicit_positive'
      ? 'var(--success)' : 'var(--danger)';
    // 같은 그룹 반대 버튼 비활성화
    const parent = btn.parentElement;
    parent.querySelectorAll('.fb-btn').forEach(b => b.disabled = true);
  } catch (e) {
    console.warn('[FEEDBACK]', e.message);
  }
}

function appendTyping() {
  const messages = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg james';
  div.innerHTML = `
    <div class="avatar james">🧠</div>
    <div class="bubble" style="min-width:180px">
      <div id="thinking-steps" style="display:flex;flex-direction:column;gap:4px;font-size:12px">
        <div id="tstep-1" style="color:var(--accent);font-weight:600">${t('chat.thinking_search')}</div>
        <div id="tstep-2" style="color:var(--muted)">${t('chat.thinking_graph')}</div>
        <div id="tstep-3" style="color:var(--muted)">${t('chat.thinking_answer')}</div>
      </div>
    </div>
  `;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;

  // 단계별 순차 활성화 (2.5초 간격)
  const steps = ['tstep-1','tstep-2','tstep-3'];
  let cur = 0;
  const timer = setInterval(() => {
    const prev = document.getElementById(steps[cur]);
    if (prev) { prev.style.color='var(--muted)'; prev.style.fontWeight='400'; }
    if (cur < steps.length - 1) {
      cur++;
      const next = document.getElementById(steps[cur]);
      if (next) { next.style.color='var(--accent)'; next.style.fontWeight='600'; }
    }
  }, 2500);

  return {
    remove() {
      clearInterval(timer);
      div.remove();
    }
  };
}

/* ── [4-A] 특이사항 토스트 알림 ── */
function jamesNotify(msg, type = 'info') {
  const colors = {
    info:    '#7c6af7', success: '#4caf7d',
    warn:    '#ffb74d', levelup: '#f06292',
    web:     '#4fc3f7', memory:  '#ce93d8',
  };
  const t = document.createElement('div');
  t.style.cssText = `
    position:fixed;bottom:80px;right:20px;
    background:${colors[type]||colors.info};color:#fff;
    padding:8px 14px;border-radius:8px;font-size:12px;font-weight:600;
    z-index:9999;box-shadow:0 4px 12px rgba(0,0,0,.3);
    max-width:260px;line-height:1.6;pointer-events:none;
    transition:opacity .4s;`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity='0'; }, 2800);
  setTimeout(() => t.remove(), 3200);
}

/* ── 답변 포맷 ── */
/* ── 답변 포맷 (마크다운 렌더링) ── */
function formatAnswer(text) {
  const codeBlocks = [];
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push(`<pre><code class="lang-${lang||'text'}">${escHtml(code.trim())}</code></pre>`);
    return `\x00CODE${idx}\x00`;
  });
  text = escHtml(text);
  text = text.replace(/^###\s+(.+)$/gm, '<strong style="font-size:13px;color:var(--accent2)">$1</strong>');
  text = text.replace(/^##\s+(.+)$/gm,  '<strong style="font-size:14px;color:var(--accent)">$1</strong>');
  text = text.replace(/^#\s+(.+)$/gm,   '<strong style="font-size:15px;color:var(--accent)">$1</strong>');
  text = text.replace(/^---+$/gm, '<hr style="border:none;border-top:1px solid var(--border);margin:6px 0">');
  text = text.replace(/^(\d+\.\s+.+)$/gm, '<span style="display:block;padding-left:8px">$1</span>');
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
  text = text.replace(/\n{2,}/g, '<br><br>');
  text = text.replace(/\n/g, '<br>');
  codeBlocks.forEach((block, idx) => {
    text = text.replace(`\x00CODE${idx}\x00`, block);
  });
  return text;
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ── 토스트 ── */
function toast(msg, type = 'success') {
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

/* ── [P3-4] 세션 선택 ── */
let _sessionPanelOpen = false;

async function toggleSessionPanel() {
  _sessionPanelOpen = !_sessionPanelOpen;
  const panel = document.getElementById('session-panel');
  if (!panel) return;
  panel.style.display = _sessionPanelOpen ? 'block' : 'none';
  if (_sessionPanelOpen) await loadSessionList();
}

async function loadSessionList() {
  const listEl = document.getElementById('session-list');
  if (!listEl) return;
  try {
    const res = await fetch(
      `${API}/history/sessions/?api_key=${getApiKey()}`,
      { headers: { Authorization: `Bearer ${getToken()}` } }
    );
    const data = await res.json();
    const sessions = data.sessions || [];

    // 배지 업데이트
    const badge = document.getElementById('session-count-badge');
    if (badge) {
      badge.style.display = sessions.length ? 'block' : 'none';
      badge.textContent = sessions.length;
    }

    if (!sessions.length) {
      listEl.innerHTML = '<div style="color:var(--muted,#888);font-size:12px;text-align:center;padding:20px">저장된 대화 없음</div>';
      return;
    }

    listEl.innerHTML = sessions.map(s => {
      const started = s.started ? new Date(s.started).toLocaleDateString('ko-KR', {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '';
      const isCurrent = s.session_id === SESSION_ID;
      const firstQ    = (s.first_question || '').slice(0, 32) || '(제목 없음)';
      // [3-D] 사용자 지정 이름 우선 표시, 없으면 첫 질문
      const titleText = s.name || firstQ;
      const sidEsc    = s.session_id.replace(/'/g, "\\'");
      const titleEsc  = titleText.replace(/'/g, "\\'").replace(/"/g, '&quot;');

      return `
        <div data-sid="${s.session_id}"
             style="padding:10px;margin-bottom:6px;border-radius:8px;
                    border:1px solid ${isCurrent ? 'var(--accent,#7c6af7)' : 'var(--border,#333)'};
                    background:${isCurrent ? 'rgba(124,106,247,.1)' : 'var(--bg,#161616)'};
                    transition:all .15s">
          <div onclick="switchSession('${sidEsc}')" style="cursor:pointer">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
              ${s.name ? '<span style="font-size:11px">📌</span>' : ''}
              <div style="flex:1;font-size:13px;font-weight:600;
                          color:${isCurrent ? 'var(--accent,#7c6af7)' : 'var(--text,#e0e0e0)'};
                          overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                ${isCurrent ? '● ' : ''}${titleEsc}
              </div>
            </div>
            <div style="font-size:11px;color:var(--muted,#888);display:flex;
                        justify-content:space-between">
              <span>${s.turn_count || 0}턴</span>
              <span>${started}</span>
            </div>
          </div>
          <!-- [3-D] 액션 버튼 -->
          <div style="display:flex;gap:4px;margin-top:6px;
                      padding-top:6px;border-top:1px solid var(--border,#333)">
            <button onclick="renameSession('${sidEsc}', event)"
                    style="flex:1;background:none;border:1px solid var(--border,#333);
                           border-radius:4px;padding:3px 6px;font-size:10px;
                           cursor:pointer;color:var(--muted,#888)"
                    title="이름 변경">✏️ 이름</button>
            <button onclick="deleteSession('${sidEsc}', event)"
                    style="flex:1;background:none;border:1px solid var(--border,#333);
                           border-radius:4px;padding:3px 6px;font-size:10px;
                           cursor:pointer;color:#f06292"
                    title="삭제">🗑️ 삭제</button>
          </div>
        </div>`;
    }).join('');
  } catch(e) {
    listEl.innerHTML = `<div style="color:var(--muted);font-size:12px">로드 실패: ${e.message}</div>`;
  }
}

/* ── [3-D] 세션 이름 변경 ── */
async function renameSession(sessionId, event) {
  if (event) event.stopPropagation();
  const newName = prompt('세션 이름 (60자 이내):', '');
  if (!newName || !newName.trim()) return;

  try {
    const url = `${API}/history/sessions/rename/`
              + `?api_key=${getApiKey()}`
              + `&session_id=${encodeURIComponent(sessionId)}`
              + `&name=${encodeURIComponent(newName.trim())}`;
    const r = await fetch(url, {
      method: 'POST',
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    const d = await r.json();
    if (d.success) {
      toast(`이름 변경: '${newName.trim()}'`, 'success');
      await loadSessionList();
    } else {
      toast('이름 변경 실패', 'error');
    }
  } catch(e) {
    toast(`오류: ${e.message}`, 'error');
  }
}

/* ── [3-D] 세션 삭제 ── */
async function deleteSession(sessionId, event) {
  if (event) event.stopPropagation();
  if (!confirm('이 세션의 모든 대화를 삭제하시겠습니까?\n(되돌릴 수 없습니다)')) return;

  try {
    const url = `${API}/history/?api_key=${getApiKey()}&session_id=${encodeURIComponent(sessionId)}`;
    const r = await fetch(url, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    const d = await r.json();
    if (d.success) {
      toast('세션 삭제 완료', 'success');
      // 현재 세션이면 새 세션으로
      if (sessionId === SESSION_ID) {
        newSession();
      } else {
        await loadSessionList();
      }
    } else {
      toast('삭제 실패', 'error');
    }
  } catch(e) {
    toast(`오류: ${e.message}`, 'error');
  }
}


async function switchSession(sessionId) {
  if (sessionId === SESSION_ID) {
    toggleSessionPanel();
    return;
  }
  // 세션 전환: sessionStorage 업데이트 + 히스토리 로드
  sessionStorage.setItem('james_session', sessionId);
  toggleSessionPanel();

  // 현재 메시지 초기화 후 해당 세션 히스토리 표시
  const messages = document.getElementById('messages');
  if (messages) messages.innerHTML = '';

  try {
    const res = await fetch(
      `${API}/history/?api_key=${getApiKey()}&session_id=${sessionId}&limit=30`,
      { headers: { Authorization: `Bearer ${getToken()}` } }
    );
    const data = await res.json();
    const turns = data.turns || [];

    if (!turns.length) {
      toast('선택한 세션에 대화 기록이 없습니다', 'info');
      return;
    }

    hideWelcome();
    turns.forEach(t => {
      if (t.role === 'user') {
        appendMsg('user', t.content || t.text || '');
      } else {
        appendJamesMsg({
          answer: t.content || t.text || '',
          mode: t.meta?.mode || '',
          graph_paths: [],
          direction_id: '',
        });
      }
    });

    // 배지 → 현재 세션으로 갱신
    const badge = document.getElementById('session-count-badge');
    if (badge) badge.textContent = '✓';
    toast(`세션 전환 완료 (${turns.length/2}턴)`, 'success');
  } catch(e) {
    toast(`세션 로드 실패: ${e.message}`, 'error');
  }
}

function newSession() {
  // 새 세션 ID 생성
  const newSid = 'sess_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
  sessionStorage.setItem('james_session', newSid);
  toggleSessionPanel();

  // 화면 초기화
  const messages = document.getElementById('messages');
  if (messages) messages.innerHTML = '';
  document.getElementById('welcome')?.style?.setProperty('display', 'flex');
  toast('새 대화를 시작합니다', 'success');
}
