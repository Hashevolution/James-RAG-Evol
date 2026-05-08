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
  // item #3-a: 이전 대화 복원 (자가 호출 누락 버그 fix).
  // restoreHistory는 정의만 되어 있고 호출되지 않아 매번 빈 화면이었음.
  // localStorage에 저장된 HISTORY_KEY 데이터 그대로 화면에 재구성한다.
  try { restoreHistory(); } catch (e) { console.warn('[JAMES] restoreHistory 실패:', e); }
});


/* ════════════════════════════════
   대화 세션 관리
════════════════════════════════ */

// 세션 ID — localStorage 영속화 (item #3-a, 2026-05-08).
// 이전: sessionStorage → 폰 브라우저 닫으면 소실 → HISTORY_KEY 변경 →
// 옛 history는 localStorage에 남았지만 표시 안 됨 (orphan).
// 지금: localStorage라 같은 사용자가 다시 들어와도 같은 세션 ID 유지,
// "새 대화 시작" 버튼(clearHistory)으로 명시적 종료 시에만 새 세션.
function getSessionId() {
  let sid = localStorage.getItem('james_session');
  if (!sid) {
    sid = 'sess_' + Date.now() + '_' + Math.random().toString(36).slice(2,8);
    localStorage.setItem('james_session', sid);
  }
  return sid;
}

const SESSION_ID = getSessionId();
const HISTORY_KEY = `james_history_${SESSION_ID}`;
// item #3-a: 50 → 200. 50턴은 ~25 사용자-자메스 페어로 모바일 사용 한 번이면
// 금방 cap. 200이면 ~100 페어, 며칠치 대화 보존 가능. localStorage 5MB 한도
// 안에 안전 (200턴 × 평균 1KB ≈ 200KB).
const MAX_STORED  = 200;

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
  // item #3-a: session_id가 localStorage에 영속이라, 초기화하면 신규 세션
  // ID 발급해야 다음 reload 시 옛 SID가 다시 살아나지 않음.
  localStorage.removeItem('james_session');
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

  // Real reasoning stream: client-generated trace_id is sent to the
  // server, which uses it as the trace key. Frontend immediately
  // starts polling /trace/poll/{trace_id} so we can display each
  // reasoning stage as it actually happens (vs. the v0.2.0 fake
  // 2.5s timer placeholder).
  const traceId = (crypto.randomUUID ? crypto.randomUUID() : 't_' + Date.now() + '_' + Math.random().toString(36).slice(2,8))
                  .replace(/-/g, '').slice(0, 32);
  const typing = appendTyping(traceId);
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
        trace_id:         traceId,
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

  // 👍👎 피드백 버튼 + 📥 export 드롭다운 (item #4)
  // export 트리거는 메시지 단위로 — 사용자가 마음에 드는 답변만 저장 가능.
  // 답변 텍스트는 data attr에 그대로 보관 (formatAnswer는 HTML 변환이라
  // 다운로드용 원본을 별도 보관해야 함).
  const answerEscapedAttr = encodeURIComponent(answer);
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
      <button class="fb-btn" onclick="exportAnswer(this, 'md')" data-content="${answerEscapedAttr}"
        style="background:none;border:1px solid var(--border);border-radius:6px;
               padding:3px 10px;cursor:pointer;color:var(--muted);font-size:12px;
               transition:all .15s" title=".md 다운로드">📥 .md</button>
      <button class="fb-btn" onclick="exportAnswer(this, 'docx')" data-content="${answerEscapedAttr}"
        style="background:none;border:1px solid var(--border);border-radius:6px;
               padding:3px 10px;cursor:pointer;color:var(--muted);font-size:12px;
               transition:all .15s" title=".docx 다운로드 (Word)">📥 .docx</button>
      <button class="fb-btn" onclick="exportAnswer(this, 'txt')" data-content="${answerEscapedAttr}"
        style="background:none;border:1px solid var(--border);border-radius:6px;
               padding:3px 10px;cursor:pointer;color:var(--muted);font-size:12px;
               transition:all .15s" title=".txt 다운로드 (Notepad)">📥 .txt</button>
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

/* ── item #4: 답변 export 다운로드 ──
   서버 /export/에 POST → blob 받아 a[download] 트릭으로 다운로드.
   docx fallback (python-docx 미설치 시 .md로 저장)이 발생하면 X-James-
   Export-Fallback 헤더가 와서 사용자에게 toast로 알림. */
async function exportAnswer(btn, fmt) {
  const content = decodeURIComponent(btn.dataset.content || '');
  if (!content.trim()) {
    alert('답변 내용이 비어 있어 저장할 수 없습니다.');
    return;
  }
  const orig = btn.textContent;
  btn.textContent = '⏳ 저장 중...';
  btn.disabled = true;
  try {
    const r = await fetch(`${API}/export/`, {
      method:  'POST',
      headers: {'Content-Type': 'application/json', ...getAuthHeaders()},
      body: JSON.stringify({
        api_key: getApiKey(),
        content: content,
        format:  fmt,
      }),
    });
    if (!r.ok) {
      const err = await r.text();
      throw new Error(`export ${r.status}: ${err.slice(0, 120)}`);
    }
    const blob   = await r.blob();
    const actual = r.headers.get('X-James-Export-Format') || fmt;
    const fallbk = r.headers.get('X-James-Export-Fallback') || '';
    // Content-Disposition에서 filename 추출
    const cd = r.headers.get('Content-Disposition') || '';
    const m  = cd.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/);
    const name = m ? decodeURIComponent(m[1] || m[2]) : `james_answer.${actual}`;

    const url = URL.createObjectURL(blob);
    const a   = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 500);

    if (fallbk) {
      // 다운로드는 됐지만 요청 포맷이 fallback으로 내려간 경우 알림
      alert(`다운로드 완료 (${actual}). 참고: ${fallbk}`);
    }
  } catch (e) {
    alert(`저장 실패: ${e.message}`);
  } finally {
    btn.textContent = orig;
    btn.disabled = false;
  }
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

/* ── Real reasoning stream — polls /trace/poll/{trace_id} ──
   v0.2.0의 fake 2.5초 타이머를 진짜 stage event 폴링으로 교체.
   각 stage(auth → retrieve → graph → answer → complete)가 실제로
   서버에서 발생할 때마다 클라이언트가 잡아서 라인을 추가한다.

   Stage별 메타데이터를 함께 표시:
     retrieve · top_k=8 · top_vec=0.82 (250ms 누적)
     graph    · entities=3 · paths=15 (+180ms)
     answer   · 1820ms · 412 chars
*/
function appendTyping(traceId) {
  const messages = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg james';
  div.innerHTML = `
    <div class="avatar james">🧠</div>
    <div class="bubble" style="min-width:220px">
      <div id="thinking-${traceId}" class="thinking-stream">
        <div class="thinking-placeholder">
          <span class="thinking-spinner-dot"></span>
          <span class="thinking-shimmer-text">추론 시작 중</span>
        </div>
      </div>
    </div>
  `;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;

  // 폴링 상태
  const seenStages = new Set();   // stage 종류별 1회만 표시
  let lastNs   = 0;
  let stopped  = false;
  let activeLine = null;          // 현재 spinner 돌고 있는 line (item #1)
  const t0     = Date.now();

  // Stage별 메타 — 아이콘은 이모지 + spinner 클래스 분리,
  // 색상은 CSS 변수로 라인에 inject (shimmer + spinner border 색)
  const STAGE_META = {
    auth:        { icon: '🔐', label: '권한 확인',          color: '#999'    },
    risky_coding_blocked: { icon: '🛑', label: '위험 명령 차단', color: '#f06292' },
    retrieve:    { icon: '🔍', label: '내부 자료 검색',     color: '#7c6af7' },
    rerank:      { icon: '🎯', label: '재정렬',              color: '#7c6af7' },
    graph:       { icon: '🕸️', label: '관계 그래프 탐색',   color: '#3da78a' },
    tool:        { icon: '🔧', label: '도구 호출',           color: '#ffb74d' },
    coding_route: { icon: '⌨️', label: '코딩 LLM 라우팅',    color: '#ffb74d' },
    coding_llm_pick: { icon: '⚙️', label: '모델 선택',       color: '#ffb74d' },
    coding_done: { icon: '✓',  label: '코딩 완료',           color: '#4caf7d' },
    coding_llm_error: { icon: '⚠️', label: '코더 LLM 오류',  color: '#f06292' },
    coding_fallback_done: { icon: '↻', label: 'Fallback 완료', color: '#ffb74d' },
    answer:      { icon: '🤖', label: 'LLM 답변 생성',       color: '#f06292' },
    complete:    { icon: '✅', label: '완료',                color: '#4caf7d' },
  };

  // 현재 active line을 done으로 마감 (다음 stage 시작 시 호출)
  const markActiveAsDone = () => {
    if (activeLine) {
      activeLine.classList.remove('thinking-active');
      activeLine.classList.add('thinking-done');
      activeLine = null;
    }
  };

  const apply = (events) => {
    const container = document.getElementById(`thinking-${traceId}`);
    if (!container) return;
    // 첫 진짜 이벤트 도착 시 placeholder 제거
    if (events.length > 0) {
      const ph = container.querySelector('.thinking-placeholder');
      if (ph) ph.remove();
    }
    events.forEach(ev => {
      const stage = ev.stage;
      if (!stage || seenStages.has(stage)) return;
      seenStages.add(stage);

      // 새 stage 도착 → 이전 active를 done으로
      markActiveAsDone();

      const m = STAGE_META[stage] || { icon: '·', label: stage, color: '#888' };
      const ms = Date.now() - t0;

      // 의미있는 detail 필드 일부만
      const detail = [];
      if (ev.top_k != null)              detail.push(`top_k=${ev.top_k}`);
      if (ev.top_vector_score != null)   detail.push(`vec=${ev.top_vector_score.toFixed(2)}`);
      if (ev.entities_extracted != null) detail.push(`ent=${ev.entities_extracted}`);
      if (ev.paths_walked != null)       detail.push(`paths=${ev.paths_walked}`);
      if (ev.latency_ms != null)         detail.push(`${ev.latency_ms}ms`);
      if (ev.answer_len != null)         detail.push(`${ev.answer_len}자`);
      if (ev.elapsed_ms != null)         detail.push(`총 ${ev.elapsed_ms}ms`);
      const detailStr = detail.length ? ` · ${detail.join(' · ')}` : '';

      const line = document.createElement('div');
      // complete stage는 즉시 done 표시 (spinner 없음)
      const isFinal = (stage === 'complete' || stage.endsWith('_done')
                       || stage === 'coding_llm_error');
      line.className = 'thinking-line ' + (isFinal ? 'thinking-done' : 'thinking-active');
      line.style.setProperty('--stage-color', m.color);

      line.innerHTML = `
        <span class="thinking-icon">${m.icon}</span>
        <span class="thinking-label thinking-shimmer-text">${escHtml(m.label)}</span>
        <span class="thinking-detail">${escHtml(detailStr)} <span class="thinking-elapsed">@${ms}ms</span></span>
      `;
      container.appendChild(line);

      if (!isFinal) {
        activeLine = line;
      } else {
        activeLine = null;
      }
    });
    // 폴링이 complete 받으면 모든 라인 done으로
    messages.scrollTop = messages.scrollHeight;
  };

  // 200ms 폴링 (auth → retrieve → graph → answer 보통 1-3초 안에 도착)
  const poll = async () => {
    if (stopped) return;
    try {
      const r = await fetch(`${API}/trace/poll/${traceId}?api_key=${encodeURIComponent(getApiKey())}&after_ns=${lastNs}`, {
        headers: getAuthHeaders(),
      });
      if (r.ok) {
        const data = await r.json();
        const evs = data.events || [];
        if (evs.length > 0) {
          lastNs = evs[evs.length - 1].ts_ns || lastNs;
          apply(evs);
        }
        if (data.complete) {
          stopped = true;
          markActiveAsDone();   // 마지막 active line 마감 (item #1)
          return;
        }
      }
    } catch (_) {
      // 네트워크 일시 오류는 무시 — 다음 tick에 재시도
    }
    if (!stopped) setTimeout(poll, 200);
  };
  // 첫 호출 약간 지연 (서버에 첫 stage 도달 시간 확보)
  setTimeout(poll, 100);

  return {
    remove() {
      stopped = true;
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
  localStorage.setItem('james_session', sessionId);
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
  localStorage.setItem('james_session', newSid);
  toggleSessionPanel();

  // 화면 초기화
  const messages = document.getElementById('messages');
  if (messages) messages.innerHTML = '';
  document.getElementById('welcome')?.style?.setProperty('display', 'flex');
  toast('새 대화를 시작합니다', 'success');
}
