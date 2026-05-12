/* PROJECT JAMES — Chat JS */

// Same-origin: works on PC (http://127.0.0.1:8000), phone via
// Tailscale Serve (https://james.xxx.ts.net), or any future reverse
// proxy. Avoids the mixed-content block when the page is loaded
// over https but the API was hardcoded to http.
const API = window.location.origin;
let SOURCE_TYPE = 'prod';
// [#A8-4] SSO — token + role을 localStorage에 저장. sessionStorage는
// per-tab이라 챗 ↔ 어드민 새 탭에서 인식 안 됨. localStorage는 같은 origin
// 내 모든 탭/창 공유. JWT 자체에 만료(exp) 박혀있어서 server-side 검증
// 시점에 거절되므로 localStorage 잔존이 보안 위협 안 됨.
// 이전 sessionStorage에 저장된 token이 있으면 마이그레이션해서 사용성
// 깨지지 않도록 한 번 옮긴다.
(function _migrateSessionToLocal() {
  for (const k of ['james_token', 'james_role']) {
    const sess = sessionStorage.getItem(k);
    if (sess && !localStorage.getItem(k)) localStorage.setItem(k, sess);
  }
})();
let token    = localStorage.getItem('james_token') || '';
let userRole = localStorage.getItem('james_role')  || '';

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

/* ── 토큰 유틸 [#A8-4 SSO localStorage] ── */
function getToken()  { return localStorage.getItem('james_token') || token || ''; }
function saveToken(t, role) {
  token = t; userRole = role;
  localStorage.setItem('james_token', t);
  localStorage.setItem('james_role',  role);
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
    localStorage.removeItem('james_token');
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

/* ── §5 인라인 핸들러 위임 (CSP-친화) ──
 * index.html / chat.js / upload.js 에는 더 이상 ``onclick=`` /
 * ``onkeydown=`` / ``oninput=`` 같은 인라인 핸들러가 없다. 정적
 * 요소는 ``data-action`` 을 가지며 document 단의 click 위임이
 * 라우팅한다. ``oninput`` 은 ``data-input-action`` 으로 분리해
 * 별도 input 위임이 처리한다. 안정적 id 를 가진 요소
 * (#chat-input textarea, login/forgot/signup 모달 overlay) 는
 * DOMContentLoaded 시점에 id 로 직접 바인딩한다 — innerHTML 로
 * 다시 그려지지 않는 요소들이기 때문. */
function _bindFrontendEvents() {
  document.addEventListener('click', (e) => {
    const t = e.target.closest && e.target.closest('[data-action]');
    if (!t) return;
    const action = t.getAttribute('data-action');
    switch (action) {
      // Header / source toggle
      case 'set-source':                setSource(t.getAttribute('data-source'), t); break;
      case 'toggle-lang':               toggleLang(); break;
      case 'clear-history':             clearHistory(); break;
      case 'toggle-session-panel':      toggleSessionPanel(); break;
      case 'show-login':                showLogin(); break;
      case 'new-session':               newSession(); break;
      // Sidebar
      case 'toggle-sidebar':            toggleSidebar(); break;
      case 'switch-sidebar-mode':       switchSidebarMode(t.getAttribute('data-mode')); break;
      case 'trigger-file-input':
        document.getElementById('file-input').click();
        break;
      case 'trigger-folder-input':
        e.stopPropagation();
        document.getElementById('folder-input').click();
        break;
      case 'upload-files':              uploadFiles(); break;
      // Welcome chips
      case 'use-chip':                  useChip(t); break;
      // Mode/model
      case 'trigger-model-install':     triggerModelInstall(); break;
      case 'accept-mode-recommend':     acceptModeRecommend(); break;
      case 'copy-conversation':         copyConversation(); break;
      // Send + login
      case 'send-message':              sendMessage(); break;
      case 'toggle-api-key-visibility': toggleApiKeyVisibility(); break;
      case 'close-login':               closeLogin(); break;
      case 'do-login':                  doLogin(); break;
      case 'open-forgot-password-modal':
        e.preventDefault(); openForgotPasswordModal(); break;
      case 'close-forgot-password-modal':
        closeForgotPasswordModal(); break;
      case 'submit-password-reset':     submitPasswordReset(); break;
      case 'open-signup-modal':
        e.preventDefault(); openSignupModal(); break;
      case 'close-signup':              closeSignup(); break;
      case 'do-signup':                 doSignup(); break;
      // Dynamic answer-card buttons
      case 'logout':                    logout(); break;
      case 'approve-wiki-save':         approveWikiSave(t); break;
      case 'ask-with-force-web':        askWithForceWeb(t); break;
      case 'export-answer':
        exportAnswer(t, t.getAttribute('data-format'));
        break;
      case 'send-feedback':
        sendFeedback(
          t.getAttribute('data-dir-id'),
          t.getAttribute('data-signal'),
          t,
        );
        break;
      case 'copy-answer-text':          copyAnswerText(t); break;
      case 'ask-suggestion':
        askSuggestion(parseInt(t.getAttribute('data-index'), 10), t);
        break;
      // Session-panel rows
      case 'switch-session':            switchSession(t.getAttribute('data-sid')); break;
      case 'rename-session':            renameSession(t.getAttribute('data-sid'), e); break;
      case 'delete-session':            deleteSession(t.getAttribute('data-sid'), e); break;
      // upload.js mini-thumbnails
      case 'chat-attach-click':         _chatAttachClick(); break;
      case 'remove-or-cancel':          removeOrCancel(t.getAttribute('data-item-id')); break;
    }
  });

  // Per-input updates (upload.js folder-input rows). Registering at
  // module load is safe — events only fire once the inputs exist.
  document.addEventListener('input', (e) => {
    const t = e.target.closest && e.target.closest('[data-input-action]');
    if (!t) return;
    if (t.getAttribute('data-input-action') === 'update-instruction') {
      updateInstruction(t.getAttribute('data-item-id'), t.value);
    }
  });
}

function _bindStableInputs() {
  const ci = document.getElementById('chat-input');
  if (ci) {
    ci.addEventListener('input',   () => autoResize(ci));
    ci.addEventListener('keydown', (e) => handleKey(e));
    ci.addEventListener('paste',   (e) => handleChatPaste(e));
  }
  const lpw = document.getElementById('login-pw');
  if (lpw) lpw.addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); });
  const lk = document.getElementById('login-api-key');
  if (lk)  lk.addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); });
  const rn = document.getElementById('reset-new-pw');
  if (rn)  rn.addEventListener('keydown', (e) => { if (e.key === 'Enter') submitPasswordReset(); });
  const su = document.getElementById('signup-pw');
  if (su)  su.addEventListener('keydown', (e) => { if (e.key === 'Enter') doSignup(); });
  const mp = document.getElementById('mode-picker');
  if (mp)  mp.addEventListener('change', () => onModePickerChange());
  const mdp = document.getElementById('model-picker');
  if (mdp) mdp.addEventListener('change', () => onModelPickerChange());
  // Modal-overlay click-outside → close. Each overlay's existing
  // close*Outside fn already checks ``e.target === overlay`` so we
  // forward the event unchanged.
  const lm = document.getElementById('login-modal');
  if (lm)  lm.addEventListener('click', (e) => closeLoginOutside(e));
  const fm = document.getElementById('forgot-password-modal');
  if (fm)  fm.addEventListener('click', (e) => closeForgotPasswordOutside(e));
  const sm = document.getElementById('signup-modal');
  if (sm)  sm.addEventListener('click', (e) => closeSignupOutside(e));
}

_bindFrontendEvents();
window.addEventListener('DOMContentLoaded', _bindStableInputs);

/* ── 초기화 ── */
window.addEventListener('DOMContentLoaded', () => {
  // [#1-C] API key는 더 이상 native prompt()로 묻지 않는다 — 폰에서
  // 매번 system 프롬프트 띄우는 게 깨지는 UX였고, 값 변경/확인이 어려웠음.
  // 이제 로그인 모달의 visible field에 입력. 키가 없으면 모달을 자동
  // 띄워서 사용자가 거기서 입력 가능하도록 안내.
  if (!localStorage.getItem('james_api_key')) {
    setTimeout(() => showLogin(), 200);
  }
  updateRoleBadge();
  // item #3-a: 이전 대화 복원 (자가 호출 누락 버그 fix).
  // restoreHistory는 정의만 되어 있고 호출되지 않아 매번 빈 화면이었음.
  // localStorage에 저장된 HISTORY_KEY 데이터 그대로 화면에 재구성한다.
  try { restoreHistory(); } catch (e) { console.warn('[JAMES] restoreHistory 실패:', e); }

  // item #6: 모드 picker 옵션 로드 + 자동 추천 등록
  try { loadModePickerOptions(); } catch (e) { console.warn('[JAMES] mode picker 로드 실패:', e); }
});

/* ── item #6: 모드 picker + 자동 추천 ──
   서버에서 role-allowed 모드 옵션을 받아 dropdown 채움. 사용자 입력에
   따라 키워드 매치로 자동 추천 배지 표시 (현재 선택과 다를 때만).
   사용자가 명시적으로 모드를 고르면 selectedMode = 그 값, /query/에
   mode_override로 전달. "auto"면 mode_override 빈 문자열 → 서버는
   intent_classifier로 자동 분류. */
let MODE_OPTIONS = [];          // [{key, label, desc, keywords, models}]
let selectedMode = 'auto';      // current mode-picker value
let selectedModel = '';         // [#A2] current model-picker value (secondary dropdown)
let recommendedMode = '';       // last-recommended (auto-suggest)

/* [#A2] localStorage 키 — 모드별 선택한 모델 기억. 다른 세션/탭에서도
   동일 선택을 유지. */
function _modelKey(mode) { return `james_model_${mode}`; }

async function loadModePickerOptions() {
  try {
    const r = await fetch(`${API}/llm/modes/?api_key=${encodeURIComponent(getApiKey())}`, {
      headers: getAuthHeaders(),
    });
    if (!r.ok) return;
    const data = await r.json();
    MODE_OPTIONS = data.modes || [];
    const sel = document.getElementById('mode-picker');
    if (!sel) return;
    // item #6: 옵션 라벨에 실제 모델명 + 설치 상태 표시
    sel.innerHTML = MODE_OPTIONS.map(m => {
      const modelTag = m.model ? ` (${m.model})` : '';
      const status = m.installed ? '' : ' ⚠️ 미설치';
      return `<option value="${escHtml(m.key)}"
                      title="${escHtml(m.desc || '')}${modelTag}"
                      data-model="${escHtml(m.model || '')}"
                      data-installed="${m.installed ? '1' : '0'}">${escHtml(m.label)}${escHtml(modelTag)}${status}</option>`;
    }).join('');
    sel.value = selectedMode;
    refreshModelPicker();
    updateInstallButton();
  } catch (e) {
    console.warn('[JAMES] /llm/modes/ fetch 실패:', e);
  }
}

/* ── [#A2] 두 번째 dropdown — 모드별 모델 후보 ──
   모드가 바뀌면 그 모드의 models[] 후보로 다시 채운다. 후보가 0-1개
   이거나 mode가 auto/meta면 picker 숨김.
   weight 표기:
     light  → 🪶 (가벼움 / 빠름)
     medium → ⚖️
     heavy  → 🐘 (무거움 / 정확)
   미설치 모델은 ⚠️ 마커 + 설치 버튼이 그 모델 install 동작. */
function refreshModelPicker() {
  const wrap = document.getElementById('model-picker-wrap');
  const sel  = document.getElementById('model-picker');
  if (!wrap || !sel) return;
  const opt = MODE_OPTIONS.find(m => m.key === selectedMode);
  const models = opt && Array.isArray(opt.models) ? opt.models : [];
  if (models.length < 2) {
    // 후보 1개 이하 — 두 번째 dropdown은 가치 X. 숨김.
    wrap.style.display = 'none';
    selectedModel = (models[0] && models[0].tag) || (opt && opt.model) || '';
    return;
  }
  wrap.style.display = 'inline-flex';
  // localStorage에서 직전 선택 복구; 없으면 default 모델.
  const saved = localStorage.getItem(_modelKey(selectedMode)) || '';
  const savedValid = models.some(m => m.tag === saved);
  selectedModel = savedValid
                ? saved
                : (models.find(m => m.default) || models[0]).tag;
  const weightIcon = w => w === 'light' ? '🪶'
                       : w === 'heavy' ? '🐘'
                       : '⚖️';
  // [item #1, 2026-05-09] explicit installed marker so user can scan
  // the dropdown and immediately see which models are ready vs need
  // a pull. Previously absence of ⚠️ silently meant "installed" — too
  // subtle.
  sel.innerHTML = models.map(m => {
    const marker = m.installed ? ' ✓' : ' ⚠️ 미설치';
    const titleStatus = m.installed
      ? '설치됨'
      : '미설치 — 선택 후 옆 버튼으로 설치 가능 (admin)';
    return `<option value="${escHtml(m.tag)}"
                    data-installed="${m.installed ? '1' : '0'}"
                    data-weight="${escHtml(m.weight)}"
                    title="${escHtml(m.weight)} · ${titleStatus}">${weightIcon(m.weight)} ${escHtml(m.tag)}${marker}</option>`;
  }).join('');
  sel.value = selectedModel;
}

function onModelPickerChange() {
  const sel = document.getElementById('model-picker');
  if (!sel) return;
  selectedModel = sel.value;
  localStorage.setItem(_modelKey(selectedMode), selectedModel);
  updateInstallButton();
}

function onModePickerChange() {
  const sel = document.getElementById('mode-picker');
  selectedMode = sel ? sel.value : 'auto';
  hideModeRecommend();
  refreshModelPicker();
  updateInstallButton();
}

/* ── item #6 + #A2 + item #1: 선택된 모드+모델이 미설치면 "설치" 버튼 노출 ──
   [item #1, 2026-05-09 / decision C-1] admin role에게만 노출. 비-admin은
   server-side install endpoint가 어차피 거부하므로(/llm/install/ admin
   guard) 일반 사용자가 클릭해도 의미 없음. 토스트로 "관리자에게 요청"
   안내하던 이전 동작은 사용자에게 "할 수 있을 것 같다"는 잘못된 신호 →
   완전히 숨기는 게 정직.

   [#A2 변경] 후보 dropdown이 활성화된 모드는 *현재 선택한* 후보의
   설치 상태를 보고 결정. dropdown 없는 모드는 기본 모델로 폴백. */
function updateInstallButton() {
  const btn = document.getElementById('mode-install-btn');
  if (!btn) return;
  // [item #1 / C-1] admin only.
  if (userRole !== 'admin') {
    btn.style.display = 'none';
    return;
  }
  const opt = MODE_OPTIONS.find(m => m.key === selectedMode);
  if (!opt) { btn.style.display = 'none'; return; }
  // [#A2] 현재 선택한 모델로 install 결정
  let target = '';
  let installed = true;
  const models = Array.isArray(opt.models) ? opt.models : [];
  if (models.length >= 2) {
    const cur = models.find(m => m.tag === selectedModel)
              || models.find(m => m.default)
              || models[0];
    target    = cur.tag;
    installed = !!cur.installed;
  } else {
    target    = opt.model || '';
    installed = !!opt.installed;
  }
  if (!target || installed) {
    btn.style.display = 'none';
    return;
  }
  btn.style.display = 'inline-block';
  btn.dataset.model = target;
  btn.textContent = `📦 ${target} 설치`;
  btn.title = `${target} 모델이 Ollama에 없습니다. 클릭하여 설치 시작.`;
}

/* [#A8-8 2026-05-09] 모델 설치 — 진행률 표시 + non-blocking 페이지 이동.
   서버는 ollama HTTP /api/pull 스트림을 백그라운드 thread로 파싱해서
   _install_progress 딕트에 percent/status를 기록.
   클라는 2.5s 간격으로 GET /admin/llm/install-progress?model=... 폴링.
   설치 버튼이 "📦 X 설치" → "⏳ 23.5% (X)" → "✅ 설치됨" 으로 라이브 갱신.
   사용자가 다른 페이지로 이동해도 서버 백그라운드 thread는 계속 돌아감. */
let _installPollTimer = null;

function _stopInstallPoll() {
  if (_installPollTimer) { clearInterval(_installPollTimer); _installPollTimer = null; }
}

async function _pollInstallProgress(model, btn) {
  try {
    const r = await fetch(
      `${API}/admin/llm/install-progress?api_key=${encodeURIComponent(getApiKey())}&model=${encodeURIComponent(model)}`,
      { headers: getAuthHeaders() },
    );
    if (!r.ok) {
      // 401이면 admin 권한 잃음 — poll 중단.
      if (r.status === 401) _stopInstallPoll();
      return;
    }
    const p = await r.json();
    if (!btn || !btn.isConnected) {
      // 버튼이 사라졌으면 (모드 picker 재로드 등) — 최소 한 번 더 알림.
      _stopInstallPoll();
      return;
    }
    if (p.error) {
      btn.textContent = `❌ ${model} 실패`;
      btn.title = p.error;
      _stopInstallPoll();
      btn.disabled = false;
      toast(`설치 실패: ${p.error}`, 'error');
      return;
    }
    if (p.done) {
      btn.textContent = `✅ ${model} 설치 완료`;
      btn.style.background = 'rgba(76,175,125,.18)';
      _stopInstallPoll();
      btn.disabled = true;   // 완료된 모델은 다시 설치 불필요
      toast(`✅ ${model} 설치 완료`, 'success');
      // 모드 picker 갱신 → installed=true로 라벨 새로고침
      setTimeout(loadModePickerOptions, 600);
      return;
    }
    // 진행 중 — percent 또는 status 표시.
    const pctStr = p.percent != null ? `${p.percent}%` : '';
    const statusStr = p.status || '진행 중';
    if (p.percent != null) {
      btn.textContent = `⏳ ${pctStr} (${model})`;
    } else {
      btn.textContent = `⏳ ${statusStr}...`;
    }
    btn.title = `${model} 설치 — ${statusStr}${p.completed != null && p.total != null ?
      ` (${(p.completed/1e9).toFixed(2)}/${(p.total/1e9).toFixed(2)} GB)` : ''}`;
  } catch (e) {
    // 네트워크 일시 단절 — 다음 tick에 다시 시도. 폴링 멈추진 않음.
    console.warn('[install-poll]', e);
  }
}

async function triggerModelInstall() {
  const btn = document.getElementById('mode-install-btn');
  const model = btn?.dataset?.model;
  if (!model) return;
  // [item #1 / C-1] 버튼은 admin에게만 노출되지만, console/script로
  // 직접 호출 가능하므로 클라이언트 측 가드도 유지. 서버 /llm/install/
  // 도 admin 가드 있음 (이중 방어).
  if (userRole !== 'admin') {
    toast('설치는 admin 권한 필요.', 'error');
    return;
  }
  if (!confirm(`Ollama에 ${model} 모델을 설치합니다.\n수 GB 다운로드 — 백그라운드로 진행됩니다.\n진행 중에도 다른 페이지 이동 가능합니다.\n계속할까요?`)) return;
  btn.textContent = '⏳ 설치 시작...';
  btn.disabled = true;
  try {
    const r = await fetch(`${API}/llm/install/?api_key=${encodeURIComponent(getApiKey())}&model=${encodeURIComponent(model)}`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${r.status}`);
    }
    // 설치 시작 OK — 진행률 폴링 시작.
    _stopInstallPoll();   // 이전 폴링 잔재 제거
    _pollInstallProgress(model, btn);   // 즉시 1회
    _installPollTimer = setInterval(() => _pollInstallProgress(model, btn), 2500);
  } catch (e) {
    toast(`설치 실패: ${e.message}`, 'error');
    btn.disabled = false;
    btn.textContent = `📦 ${model} 설치`;
  }
}

function acceptModeRecommend() {
  if (!recommendedMode) return;
  const sel = document.getElementById('mode-picker');
  if (sel) {
    sel.value = recommendedMode;
    selectedMode = recommendedMode;
  }
  hideModeRecommend();
}

function hideModeRecommend() {
  const banner = document.getElementById('mode-recommend');
  if (banner) banner.style.display = 'none';
  recommendedMode = '';
}

// 입력 시 keyword 매치 → 다른 모드 추천
let _recTimer = null;
function checkModeRecommendation(text) {
  if (!text || text.length < 4) { hideModeRecommend(); return; }
  if (_recTimer) clearTimeout(_recTimer);
  _recTimer = setTimeout(() => {
    if (selectedMode !== 'auto') return;   // 명시적으로 골랐으면 간섭 X
    if (!MODE_OPTIONS.length) return;
    const lower = text.toLowerCase();
    let best = null;
    for (const m of MODE_OPTIONS) {
      if (m.key === 'auto') continue;
      const kws = m.keywords || [];
      const hit = kws.some(k => lower.includes(k.toLowerCase()));
      if (hit) { best = m; break; }
    }
    if (best && best.key !== selectedMode) {
      recommendedMode = best.key;
      const banner = document.getElementById('mode-recommend');
      if (banner) {
        banner.textContent = `💡 ${best.label} 권장 — 클릭하여 전환`;
        banner.style.display = 'inline-block';
      }
    } else {
      hideModeRecommend();
    }
  }, 350);
}


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
  // [#1-C] API key 필드 pre-fill — 이전에 저장된 값 표시. 비어있으면
  // 빈 칸으로 두고 사용자가 입력. 첫 visit 시점엔 뭐가 들어갈 자리인지
  // 명확히 보이는 게 prompt()보다 친화적.
  const apiKeyInput = document.getElementById('login-api-key');
  if (apiKeyInput) apiKeyInput.value = getApiKey();
  document.getElementById('login-id').focus();
  document.getElementById('login-error').textContent = '';
}

/* [#1-C] API key 보기/숨기기 토글. password 입력 필드의 type을
   "password" ↔ "text" 로 swap. 폰에서 긴 키 복붙 시 검증 용도. */
function toggleApiKeyVisibility() {
  const input = document.getElementById('login-api-key');
  const btn   = document.getElementById('login-api-key-toggle');
  if (!input) return;
  if (input.type === 'password') {
    input.type = 'text';
    if (btn) btn.textContent = '🙈';
  } else {
    input.type = 'password';
    if (btn) btn.textContent = '👁️';
  }
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
  // [#1-C] API key는 모달 입력 필드에서 직접 받음. 비어있으면
  // localStorage 기존 값 사용 (back-compat — 기존 사용자는 변경 불필요).
  const apiKeyInput = document.getElementById('login-api-key');
  const apiKeyEntered = (apiKeyInput?.value || '').trim();
  const apiKeyToUse = apiKeyEntered || getApiKey();
  const errEl    = document.getElementById('login-error');
  errEl.textContent = '';

  if (!username || !password) {
    errEl.textContent = '아이디와 비밀번호를 입력하세요.';
    return;
  }
  if (!apiKeyToUse) {
    errEl.textContent = 'API Key를 입력하세요. (.env의 JAMES_API_KEY)';
    apiKeyInput?.focus();
    return;
  }
  // 새로 입력된 값이면 localStorage에 저장 (다음 로그인 시 pre-fill).
  if (apiKeyEntered && apiKeyEntered !== getApiKey()) {
    localStorage.setItem('james_api_key', apiKeyEntered);
  }

  try {
    const r = await fetch(`${API}/login/`, {
      method:  'POST',
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify({
        username, password,
        api_key: apiKeyToUse,
      }),
    });

    const data = await r.json();

    if (!r.ok) {
      errEl.textContent = data.detail || '로그인 실패';
      return;
    }

    // 토큰 저장 [#A8-4 SSO]
    token    = data.access_token;
    userRole = data.role || 'employee';
    localStorage.setItem('james_token', token);
    localStorage.setItem('james_role',  userRole);

    closeLogin();
    updateRoleBadge();
    // [item #1] role 변경 시 install 버튼 가시성 즉시 갱신
    // (admin login → 미설치 모델 선택 중이면 즉시 버튼 노출, 반대로
    //  external/employee로 다시 로그인하면 즉시 숨김)
    try { updateInstallButton(); } catch (_) {}
    document.getElementById('login-pw').value = '';

    toast(`✅ ${username} (${userRole}) 로그인 완료`, 'success');

  } catch (e) {
    errEl.textContent = `서버 오류: ${e.message}`;
  }
}

function logout() {
  token    = '';
  userRole = '';
  localStorage.removeItem('james_token');
  localStorage.removeItem('james_role');
  updateRoleBadge();
  // [item #1] admin 권한 잃으면 install 버튼 즉시 숨김
  try { updateInstallButton(); } catch (_) {}
  toast('로그아웃 완료', 'success');
}

/* ── W8-B: 사이드바 "내 자료" 모드 ──
   W5 의 placeholder 를 /artifacts/mine 데이터로 채움. 사용자가 rail
   의 🕘 아이콘 클릭 시 switchSidebarMode('recent') 가 이 함수를
   호출 (index.html 의 switchSidebarMode 안 wire). JWT 없으면
   안내 메시지만 보여줌.
*/
function loadMineSidebar() {
  const target = document.getElementById('sidebar-mine-list');
  if (!target) return;
  if (!token) {
    target.innerHTML = `<div style="color:var(--muted);font-size:11px;padding:16px;text-align:center;line-height:1.5">
      로그인하면<br>본인 업로드가 표시됩니다.
    </div>`;
    return;
  }
  target.innerHTML = `<div style="color:var(--muted);font-size:11px;padding:8px;text-align:center">로딩 중...</div>`;
  const ak = getApiKey();
  fetch(`${API}/artifacts/mine/list?limit=20&api_key=${encodeURIComponent(ak || '')}`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(r => {
    if (r.status === 401) {
      token = '';
      localStorage.removeItem('james_token');
      updateRoleBadge();
      throw new Error('인증이 만료되었습니다.');
    }
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  }).then(data => {
    const items = data.items || [];
    if (!items.length) {
      target.innerHTML = `<div style="color:var(--muted);font-size:11px;padding:16px;text-align:center;line-height:1.5">
        업로드한 파일이 아직 없습니다.<br>(왼쪽 📂 모드에서 추가)
      </div>`;
      return;
    }
    target.innerHTML = items.map(it => {
      const status = it.status || 'unknown';
      const time = it.uploaded_at
        ? new Date(it.uploaded_at * 1000).toLocaleString('ko-KR', {
            month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
          })
        : '-';
      const statusColor = status === 'indexed' ? '#1e7a3e'
                        : status === 'failed'  ? '#7a1e1e'
                        : 'var(--muted)';
      return `<div style="padding:8px 10px;border-bottom:1px solid var(--border-2);font-size:11px">
        <div style="color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
             title="${(it.origin_name || '').replace(/"/g,'&quot;')}">${it.origin_name || ''}</div>
        <div style="display:flex;justify-content:space-between;margin-top:3px">
          <span style="color:var(--muted);font-family:var(--font-mono);font-size:10px">${time}</span>
          <span style="color:${statusColor};font-family:var(--font-mono);font-size:10px">${status}</span>
        </div>
      </div>`;
    }).join('');
  }).catch(e => {
    target.innerHTML = `<div style="color:var(--danger);font-size:11px;padding:8px;text-align:center">${e.message}</div>`;
  });
}

/* ── W4 P4: signup modal ──
   Public POST /signup/ from anonymous user. Success and duplicate
   share one server response (enumeration defense) so the modal
   shows a single "submitted" confirmation in either case. The
   account stays pending until an admin approves via the admin
   panel (W4 P2-A).
*/
function openSignupModal() {
  closeLogin();
  const m = document.getElementById('signup-modal');
  if (!m) return;
  m.classList.remove('hidden');
  document.getElementById('signup-error').textContent   = '';
  document.getElementById('signup-success').style.display = 'none';
  document.getElementById('signup-id').focus();
}

function closeSignup() {
  const m = document.getElementById('signup-modal');
  if (!m) return;
  m.classList.add('hidden');
  // Wipe inputs — anonymous form values shouldn't linger after close.
  for (const id of ['signup-id', 'signup-pw']) {
    const el = document.getElementById(id);
    if (el) el.value = '';
  }
}

function closeSignupOutside(e) {
  if (e.target === document.getElementById('signup-modal')) closeSignup();
}

/* ── W4 P5: forgot-password (chat-page anonymous flow) ──
   Mirror of admin.html's forgot-password modal. Public
   POST /password/reset/confirm — bare fetch, no Bearer, no
   api_key query. Token-error responses collapse to 401 by
   design (enumeration defense).
*/
function openForgotPasswordModal() {
  closeLogin();
  const m = document.getElementById('forgot-password-modal');
  if (!m) return;
  m.classList.remove('hidden');
  document.getElementById('reset-error').textContent = '';
  document.getElementById('reset-username').focus();
}

function closeForgotPasswordModal() {
  const m = document.getElementById('forgot-password-modal');
  if (!m) return;
  m.classList.add('hidden');
  // Wipe — a screen-share moment after a reset shouldn't leak values.
  for (const id of ['reset-username', 'reset-token', 'reset-new-pw']) {
    const el = document.getElementById(id);
    if (el) el.value = '';
  }
  // Return user to the login modal — they still need to log in once
  // the reset completes.
  showLogin();
}

function closeForgotPasswordOutside(e) {
  if (e.target === document.getElementById('forgot-password-modal')) {
    closeForgotPasswordModal();
  }
}

async function submitPasswordReset() {
  const username = document.getElementById('reset-username').value.trim();
  const token    = document.getElementById('reset-token').value.trim();
  const newPw    = document.getElementById('reset-new-pw').value;
  const errEl    = document.getElementById('reset-error');
  errEl.textContent = '';
  if (!username || !token || !newPw) {
    errEl.textContent = '아이디, 토큰, 새 비밀번호를 모두 입력하세요.';
    return;
  }
  try {
    const r = await fetch(`${API}/password/reset/confirm`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ username, token, new_password: newPw }),
    });
    if (r.ok) {
      toast('✅ 비밀번호가 재설정되었습니다. 새 비밀번호로 로그인하세요.', 'success');
      closeForgotPasswordModal();
      return;
    }
    let detail = `${r.status}`;
    try { detail = (await r.json()).detail || detail; } catch (_e) {}
    errEl.textContent = detail;
  } catch (e) {
    errEl.textContent = `서버 오류: ${e.message}`;
  }
}

async function doSignup() {
  const username = document.getElementById('signup-id').value.trim();
  const password = document.getElementById('signup-pw').value;
  const errEl    = document.getElementById('signup-error');
  const okEl     = document.getElementById('signup-success');
  errEl.textContent   = '';
  okEl.style.display  = 'none';

  if (!username || !password) {
    errEl.textContent = '아이디와 비밀번호를 입력하세요.';
    return;
  }
  try {
    const r = await fetch(`${API}/signup/`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ username, password }),
    });
    if (r.ok) {
      const data = await r.json();
      okEl.textContent  = data.message ||
        '가입 신청이 접수되었습니다. 관리자 승인 후 사용 가능합니다.';
      okEl.style.display = 'block';
      // Wipe password — username can stay so the user remembers what
      // they signed up as.
      document.getElementById('signup-pw').value = '';
      return;
    }
    // Policy rejection surfaces a 400 with a verbatim rule message.
    let detail = `${r.status}`;
    try { detail = (await r.json()).detail || detail; } catch (_e) {}
    errEl.textContent = detail;
  } catch (e) {
    errEl.textContent = `서버 오류: ${e.message}`;
  }
}

/* [#A8-4] cross-tab sync — 다른 탭(어드민 페이지 등)에서 로그인/로그아웃
   하면 즉시 이 탭에도 반영. localStorage의 storage 이벤트는 *다른* 탭의
   변경만 받음 (자기 자신 변경 제외) — chat에서 로그인하고 어드민 새 탭
   열면 어드민이 즉시 로그인 상태로 보이고, 반대로 어드민에서 로그아웃
   하면 chat 탭의 role-badge도 즉시 갱신된다. */
window.addEventListener('storage', (e) => {
  if (e.key === 'james_token' || e.key === 'james_role') {
    token    = localStorage.getItem('james_token') || '';
    userRole = localStorage.getItem('james_role')  || '';
    try { updateRoleBadge(); } catch (_) {}
    // [item #1] cross-tab role 변경 시 install 버튼 가시성도 동기화
    try { updateInstallButton(); } catch (_) {}
  }
});

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
      <button class="logout-btn" data-action="logout" title="로그아웃">✕</button>
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
  // item #6: 입력 시 모드 추천 키워드 매치 (debounced)
  try { checkModeRecommendation(el.value || ''); } catch (_) {}
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

// item #4: 사용자가 "보고서로 / 파일로 만들어줘" 등 export 요청을 한
// 직후에만 다음 답변에 다운로드 버튼이 뜬다. 일반 chat에는 버튼 없음.
// 단순 module-scope flag — sendMessage가 set, appendJamesMsg가 read+clear.
let pendingReportRequest = false;
const REPORT_REQUEST_KEYWORDS =
  /보고서|레포트|문서로|문서\s*로\s*만들|파일로\s*만들|파일\s*로\s*저장|다운로드|export|report\s*(file|format)?/i;

// [#A8-6] 가장 최근 사용자 질문을 기억 → 답변 bubble의 "🌐 웹으로 더
// 조사" chip 클릭 시 그대로 다시 보낸다 (force_web_search=true).
// askWithForceWeb이 직접 sendMessage를 호출하기보단 입력값을 채우고
// 저장 후 _runQuery 핵심 로직을 직접 부르므로 입력창에 잠깐 보였다
// 사라지는 짜증을 피한다.
let lastUserQuestion = '';
// [#A8-6] sendMessage가 다음 호출 1회만 force_web_search=true로 보낼지.
// askWithForceWeb이 set, sendMessage가 read+clear (단발성).
let _forceWebOnce = false;

async function sendMessage() {
  const input = document.getElementById('chat-input');
  const text  = input.value.trim();
  if (!text) return;

  // item #4: 다음 답변이 다운로드 버튼을 보일지 결정
  pendingReportRequest = REPORT_REQUEST_KEYWORDS.test(text);

  // [#A8-6] 사용자 질문 보관 — 이후 chip이 재사용
  lastUserQuestion = text;
  // 단발성 force flag (askWithForceWeb이 직전 set)
  const forceWeb = _forceWebOnce;
  _forceWebOnce = false;

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
        // item #6: mode_override (auto면 빈 문자열 → 서버 자동 분류)
        mode_override:    (selectedMode && selectedMode !== 'auto') ? selectedMode : '',
        // [#A8-6] chip 클릭으로 도착한 경우만 true — 평상시 false.
        force_web_search: forceWeb,
        // [#A2 phase 2] secondary picker로 고른 LLM tag. 서버 catalog
        // 검증 후 mode handler의 call_gemma(model=...)로 전달.
        selected_model:   selectedModel || '',
      }),
    });

    typing.remove();

    if (r.status === 401) {
      token = '';
      localStorage.removeItem('james_token');
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

  // [#A8-7] 웹 검색 답변에 "📥 위키 저장" chip — 사용자 직접 승인 흐름.
  // pending_save_proposal_id가 있고 admin role이면 chip 노출. click →
  // /admin/proposals/{id}/approve로 직접 wiki entity 생성. 비-admin은
  // chip 미표시 (서버에서 거절될 거라 무의미). data 객체에 chip 상태 보관.
  let saveWikiChip = '';
  if (data.web_used && data.pending_save_proposal_id && userRole === 'admin') {
    saveWikiChip = `
      <div style="margin-top:6px">
        <button class="next-action-chip save-wiki-btn"
                data-action="approve-wiki-save"
                data-proposal-id="${escHtml(data.pending_save_proposal_id)}"
                style="text-align:left;background:rgba(76,175,125,.10);
                       border:1px solid rgba(76,175,125,.45);border-radius:8px;
                       padding:8px 12px;cursor:pointer;color:var(--text);
                       font-size:12px;width:100%;font-family:inherit;
                       transition:all .15s">
          <span style="color:#4caf7d;font-weight:600;margin-right:6px">📥</span>
          <span>이 자료를 위키로 저장 (장기 기억화)</span>
        </button>
      </div>`;
  }

  // [#A6-2] 웹 검색 사용됨 배지 + 출처 URL
  // 답변에 외부 데이터(low-trust web)가 섞였음을 사용자에게 명시.
  // 출처 URL 노출로 신뢰도 자가 판단 가능. internal-only 답변엔 미표시.
  let webBadge = '';
  if (data.web_used) {
    const sources = Array.isArray(data.web_sources) ? data.web_sources : [];
    const engine  = sources[0]?.engine || 'web';
    const engineLabel = engine === 'tavily' ? 'Tavily'
                      : engine === 'duckduckgo' ? 'DuckDuckGo'
                      : '웹';
    const sourceLines = sources.slice(0, 5).map(s => {
      const url = s.url || '';
      const title = (s.title || url).slice(0, 80);
      return `<li style="margin-top:3px"><a href="${escHtml(url)}" target="_blank" rel="noopener noreferrer"
              style="color:var(--accent-fg);text-decoration:none;font-size:11px"
              title="${escHtml(url)}">${escHtml(title)}</a></li>`;
    }).join('');
    webBadge = `
      <details class="web-used-details" style="margin-top:6px">
        <summary style="cursor:pointer;font-size:11px;color:#4fc3f7;
                        font-weight:600;user-select:none;display:inline-block;
                        background:rgba(79,195,247,.10);padding:3px 9px;
                        border-radius:6px;border:1px solid rgba(79,195,247,.30)">
          🌐 웹 검색 사용됨 (${escHtml(engineLabel)} · ${sources.length}건) — 출처 보기
        </summary>
        ${sourceLines ? `<ul style="margin:6px 0 0 18px;padding:0;font-family:var(--font-ui)">${sourceLines}</ul>` : ''}
      </details>`;
  }

  // [3-B] unified_score는 web chip + confidence badge 모두 참조 — 한 번만 읽기.
  const score = data.unified_score;

  // [#A8-6] 자료 부족 + 웹 검색 미사용일 때 "웹으로 더 조사" chip.
  //   - web_used=false (이미 웹 자료 받았으면 다시 보낼 필요 없음)
  //   - unified_score < 0.50 (확신 낮은 답변 — internal-only로는 부족)
  //   - 사용자 자체 질문은 lastUserQuestion에 보관 → 클릭 시 force flag로 재전송.
  let forceWebChip = '';
  if (!data.web_used && (score == null || score < 0.50)) {
    const q = lastUserQuestion || '';
    if (q.trim()) {
      forceWebChip = `
        <div style="margin-top:8px">
          <button class="next-action-chip force-web-btn"
                  data-action="ask-with-force-web"
                  data-question="${encodeURIComponent(q)}"
                  style="text-align:left;background:rgba(79,195,247,.10);
                         border:1px solid rgba(79,195,247,.45);border-radius:8px;
                         padding:8px 12px;cursor:pointer;color:var(--text);
                         font-size:12px;width:100%;font-family:inherit;
                         transition:all .15s">
            <span style="color:#4fc3f7;font-weight:600;margin-right:6px">🌐</span>
            <span>웹 검색으로 더 자세히 조사하기</span>
          </button>
        </div>`;
    }
  }

  // [3-B] unified_score → 신뢰도 배지 ([#A8-6 통합] score는 위에서 이미 읽음)
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

  // item #5-B: graph paths는 기본 hidden — 사용자가 "그래프 보기"
  // 토글 클릭 시 펼침. 답변 가시성을 해치는 큰 paths 리스트 (최대
  // 50개)가 매번 깔리던 문제 해결.
  //
  // HANDOVER §3 follow-up — paths are rendered as mint-outlined
  // node chips instead of plain "→ A → B → C" text. Each path is
  // a string like "Entity → Entity → Entity"; split on the arrow,
  // wrap each node in `.path-node` (chip) and each separator in
  // `.path-arrow` (muted). Empty / malformed splits fall back to
  // a single chip carrying the whole string so we never lose data.
  const renderPathRow = (p) => {
    const nodes = String(p).split('→').map(n => n.trim()).filter(Boolean);
    if (nodes.length === 0) return '';
    const inner = nodes.map((n, i) =>
      (i > 0 ? '<span class="path-arrow">→</span>' : '') +
      `<span class="path-node">${escHtml(n)}</span>`
    ).join('');
    return `<div class="path-row">${inner}</div>`;
  };

  let pathsHtml = '';
  if (paths.length > 0) {
    const pathsId = 'gp_' + Math.random().toString(36).slice(2, 9);
    const list = paths.map(renderPathRow).join('');
    pathsHtml = `
      <details class="graph-paths-details" style="margin-top:6px">
        <summary class="graph-paths-toggle"
                 style="cursor:pointer;font-size:11px;color:var(--muted);
                        font-family:var(--font-mono);user-select:none;
                        padding:2px 0">
          🕸️ 그래프 경로 ${paths.length}개 보기
        </summary>
        <div id="${pathsId}" class="graph-paths" style="margin-top:6px">
          <div class="path-title">GRAPH PATHS</div>${list}
        </div>
      </details>`;
  }

  let metaHtml = '';
  if (mode || timing) {
    metaHtml = `<div class="meta">`;
    if (mode)         metaHtml += `<span class="mode-badge">${escHtml(mode)}</span>`;
    if (timing)       metaHtml += `<span>${timing}</span>`;
    if (data.graph_used) metaHtml += `<span class="graph-badge">graph ×${data.graph_used}</span>`;
    metaHtml += `</div>`;
  }

  // 👍👎 피드백 버튼 (모든 답변) + 📥 export 버튼 (조건부)
  // item #4: export 버튼은 사용자가 직전 질문에 "보고서로 / 파일로
  // 만들어줘" 같은 키워드를 넣었을 때만 표시. 평상시 chat 답변엔
  // 시각적 잡음 없음. 답변 단위로 결정 — 다음 답변엔 다시 hidden.
  // [#A4-B] 답변에 ```code``` 블록이 있으면 .py 버튼도 추가 — 사용자가
  // "파이썬 파일로" 명시 안 해도 코드 블록 답변엔 항상 .py export 가능.
  const showExportBtns = !!pendingReportRequest;
  pendingReportRequest = false;   // consume the flag
  const hasCodeBlock = /```[\s\S]*?```/.test(answer);
  const answerEscapedAttr = encodeURIComponent(answer);
  const _expBtnStyle = "background:none;border:1px solid var(--border);border-radius:6px;padding:3px 10px;cursor:pointer;color:var(--muted);font-size:12px;transition:all .15s";
  const pyExportBtn = hasCodeBlock ? `
      <button class="fb-btn export-btn" data-action="export-answer" data-format="py" data-content="${answerEscapedAttr}"
        style="${_expBtnStyle}" title=".py 다운로드 (코드 블록만 추출)">📥 .py</button>` : '';
  const exportButtons = showExportBtns ? `
      <button class="fb-btn export-btn" data-action="export-answer" data-format="md" data-content="${answerEscapedAttr}"
        style="${_expBtnStyle}" title=".md 다운로드">📥 .md</button>
      <button class="fb-btn export-btn" data-action="export-answer" data-format="docx" data-content="${answerEscapedAttr}"
        style="${_expBtnStyle}" title=".docx 다운로드 (Word)">📥 .docx</button>
      <button class="fb-btn export-btn" data-action="export-answer" data-format="txt" data-content="${answerEscapedAttr}"
        style="${_expBtnStyle}" title=".txt 다운로드 (Notepad)">📥 .txt</button>${pyExportBtn}`
    : pyExportBtn;
  const dirIdEsc = dirId ? escHtml(dirId) : '';
  const fbHtml = dirId ? `
    <div class="feedback-btns" style="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap">
      <button class="fb-btn" data-action="send-feedback" data-dir-id="${dirIdEsc}" data-signal="explicit_positive"
        style="background:none;border:1px solid var(--border);border-radius:6px;
               padding:3px 10px;cursor:pointer;color:var(--muted);font-size:12px;
               transition:all .15s" title="좋아요">👍</button>
      <button class="fb-btn" data-action="send-feedback" data-dir-id="${dirIdEsc}" data-signal="explicit_negative"
        style="background:none;border:1px solid var(--border);border-radius:6px;
               padding:3px 10px;cursor:pointer;color:var(--muted);font-size:12px;
               transition:all .15s" title="별로예요">👎</button>
      <button class="fb-btn" data-action="copy-answer-text" data-content="${answerEscapedAttr}"
        style="background:none;border:1px solid var(--border);border-radius:6px;
               padding:3px 10px;cursor:pointer;color:var(--muted);font-size:12px;
               transition:all .15s" title="이 답변 복사">📋 복사</button>
      ${exportButtons}
    </div>` : '';

  // item #1-B: 답변 끝의 "(1) ... (2) ... (3) ..." 다음-행동 제안을
  // 클릭 가능한 chip으로 변환. 클릭 → 입력창에 그 제안 텍스트 채움 +
  // 자동 전송 (사용자가 다음 차례를 한 클릭으로 진행).
  const suggestions = extractNextActionSuggestions(answer);
  let suggestionsHtml = '';
  if (suggestions.length > 0) {
    suggestionsHtml = `
      <div class="next-actions" style="display:flex;flex-direction:column;gap:6px;
                                       margin-top:8px">
        ${suggestions.map((s, i) => `
          <button class="next-action-chip"
                  data-action="ask-suggestion"
                  data-index="${i}"
                  data-suggestion="${encodeURIComponent(s.text)}"
                  style="text-align:left;background:var(--surface-2);
                         border:1px solid var(--border);border-radius:8px;
                         padding:8px 12px;cursor:pointer;color:var(--text);
                         font-size:13px;transition:all .15s;width:100%;
                         font-family:inherit">
            <span style="color:var(--accent);font-weight:600;margin-right:6px">→</span>
            <span>${escHtml(s.text)}</span>
          </button>
        `).join('')}
      </div>`;
  }

  div.innerHTML = `
    <div class="avatar james">🧠</div>
    <div>
      <div class="bubble">${formatAnswerWithParagraphs(answer)}${pathsHtml}</div>
      ${webBadge}
      ${saveWikiChip}
      ${confidenceBadge}
      ${metaHtml}
      ${forceWebChip}
      ${suggestionsHtml}
      ${fbHtml}
    </div>
  `;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

/* ── item #1-B + #A1: 다음-행동 제안 추출 (다중 포맷 지원) ──
   v1은 "(1) X (2) Y (3) Z" 한 형식만 매칭 → LLM이 "1) X" "1. X"
   "① X" 같은 변형으로 답하면 chip이 안 나오는 간헐 누락 발생
   (사용자 보고 2026-05-08).

   v2는 SUGGESTION_PATTERNS 배열을 순서대로 시도. 첫 번째로 ≥2개를
   찾는 패턴의 결과를 채택. 패턴 우선순위:
     ① "(1) X (2) Y (3) Z"   — strict, 우리가 권장하는 포맷
     ② "1) X 2) Y 3) Z"      — 우괄호만
     ③ "1. X\n2. Y\n3. Z"    — 다행 번호 목록
     ④ "① X ② Y ③ Z"          — 원문자

   답변 끝 600자만 검사 — 본문 중간 "(1) 첫째" 등을 제안으로
   오해하지 않도록 tail 제한. */
const SUGGESTION_PATTERNS = [
  /\((\d)\)\s*([^\n()][^\n(]*?)(?=\s*\(\d\)|\s*$)/g,
  /(?:^|[\s\n])(\d)\)\s+([^\n)]+?)(?=\s+\d\)|\n|$)/g,
  /(?:^|\n)\s*(\d)\.\s+([^\n]+)/g,
  /([①②③④⑤⑥⑦⑧⑨])\s+([^\n①-⑨]+?)(?=\s*[①-⑨]|$)/g,
];

function extractNextActionSuggestions(answerText) {
  if (!answerText) return [];
  const tail = answerText.length > 600
             ? answerText.slice(-600)
             : answerText;
  for (const re of SUGGESTION_PATTERNS) {
    re.lastIndex = 0;
    const out = [];
    let m;
    while ((m = re.exec(tail)) !== null) {
      const text = m[2].trim().replace(/[\.。]+$/, '');
      if (text.length >= 4 && text.length <= 200) {
        // 동일 텍스트 중복 제거 (예: "1. X" 다음 "1) X" 둘 다 매칭 방지)
        if (!out.some(o => o.text === text)) {
          out.push({ n: out.length + 1, text });
        }
      }
      if (out.length >= 5) break;
    }
    // 최소 2개 — 단일 매칭은 본문 잔재(예: "1단계: ...")일 가능성.
    if (out.length >= 2) return out;
  }
  return [];
}

/* [#A8-7] "📥 위키 저장" chip 클릭 핸들러.
   chat 답변에 노출된 pending_save_proposal_id로 /admin/proposals/{id}/approve
   직접 호출. admin role 필요 (chip 자체가 admin에게만 보이지만 server-side
   에서도 거절). 성공 시 toast + chip을 "✓ 저장됨" 으로 disable. */
async function approveWikiSave(btn) {
  if (!btn || btn.disabled) return;
  const id = btn.dataset.proposalId || '';
  if (!id) return;
  if (!confirm('이 검색 결과를 wiki entity로 영구 저장합니다.\n저장 후 retrieval에 활용됩니다.\n계속하시겠습니까?')) return;
  btn.disabled = true;
  btn.style.opacity = '0.55';
  const labelEl = btn.querySelector('span:last-child');
  if (labelEl) labelEl.textContent = '저장 중...';
  try {
    const r = await fetch(
      `${API}/admin/proposals/${encodeURIComponent(id)}/approve?api_key=${encodeURIComponent(getApiKey())}`,
      {
        method:  'POST',
        headers: getAuthHeaders(),
        body:    JSON.stringify({api_key: getApiKey()}),
      },
    );
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${r.status}`);
    }
    const data = await r.json();
    if (data.success === false) {
      throw new Error(data.message || '저장 실패');
    }
    if (labelEl) labelEl.textContent = '✓ 위키에 저장됨';
    btn.style.background = 'rgba(76,175,125,.18)';
    toast(`✅ 위키 저장 완료${data.details?.path ? ': ' + data.details.path : ''}`, 'success');
  } catch (e) {
    btn.disabled = false;
    btn.style.opacity = '';
    if (labelEl) labelEl.textContent = '이 자료를 위키로 저장 (장기 기억화)';
    toast(`저장 실패: ${e.message}`, 'error');
  }
}

/* [#A8-6] "🌐 웹 검색으로 더 조사" chip 클릭 핸들러.
   사용자의 직전 질문을 force_web_search=true로 다시 전송.
   chip은 한 번 클릭되면 disabled로 바꿔서 중복 트리거 방지. */
function askWithForceWeb(btn) {
  if (!btn) return;
  if (btn.disabled) return;
  const q = decodeURIComponent(btn.dataset.question || '');
  if (!q.trim()) {
    toast('이전 질문을 찾을 수 없습니다.', 'error');
    return;
  }
  // 입력창에 채우지 않고 force flag만 set + sendMessage 직접 트리거.
  // 입력창은 빈 상태 유지해서 사용자가 다음 질문 바로 입력 가능.
  const input = document.getElementById('chat-input');
  if (!input) return;
  input.value = q;
  _forceWebOnce = true;
  btn.disabled = true;
  btn.style.opacity = '0.55';
  btn.querySelector('span:last-child').textContent = '웹 검색 중...';
  setTimeout(() => sendMessage(), 100);
}

/* 제안 chip 클릭 → 입력창에 채우고 즉시 전송 */
function askSuggestion(idx, btn) {
  const text = decodeURIComponent(btn.dataset.suggestion || '');
  if (!text.trim()) return;
  const input = document.getElementById('chat-input');
  if (!input) return;
  input.value = text;
  // 부드러운 UX — 입력창에 잠깐 보였다가 sendMessage. 사용자가 직전
  // 제안에서 단어 하나 바꾸고 싶으면 클릭 후 입력창에 보이는 동안
  // 멈출 수 있도록 작은 delay.
  autoResize(input);
  setTimeout(() => sendMessage(), 200);
}

/* ── item #4: 단일 답변 텍스트 복사 ──
   data-content (URI-encoded)에서 원본을 꺼내 navigator.clipboard에
   write. clipboard API 미지원 환경(예: 일부 모바일 비-HTTPS)을 위해
   textarea fallback. */
async function copyAnswerText(btn) {
  const text = decodeURIComponent(btn.dataset.content || '');
  if (!text.trim()) {
    toast('복사할 내용이 없습니다.', 'error');
    return;
  }
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
    }
    const orig = btn.textContent;
    btn.textContent = '✓ 복사됨';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  } catch (e) {
    toast(`복사 실패: ${e.message}`, 'error');
  }
}

/* ── item #4: 전체 대화 복사 ──
   localStorage HISTORY_KEY의 모든 턴을 텍스트로 직렬화해서 클립보드로.
   포맷: "[사용자] ...\n[자메스] ...\n\n" 반복. 외부 메모장 / 메일에
   바로 붙여넣을 수 있는 plain text. */
async function copyConversation() {
  let history = [];
  try {
    history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
  } catch (_) { history = []; }
  if (!history.length) {
    toast('복사할 대화가 없습니다.', 'info');
    return;
  }
  const lines = history.map(turn => {
    const who = turn.role === 'user' ? '[사용자]' : '[자메스]';
    const time = turn.time ? ' (' + new Date(turn.time).toLocaleString() + ')' : '';
    return `${who}${time}\n${turn.text || ''}`;
  });
  const text = lines.join('\n\n');
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
    }
    toast(`대화 ${history.length}턴이 복사되었습니다.`, 'success');
  } catch (e) {
    toast(`복사 실패: ${e.message}`, 'error');
  }
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
/* [#1-A] 추론 단계용 SVG 아이콘 — 로봇 헤드 윤곽 + 내부에 3개 뉴런
   노드 + 노드 간 연결선. 활성 시 각 뉴런이 phase가 다른 깜빡임 +
   pulse glow. CSS .brain-pulse-active에 의해 애니메이션 활성/정지.
   stage-color CSS 변수로 색상 inject (chat.js의 stage 메타와 연동). */
function brainPulseSvg(active = true) {
  const cls = 'brain-pulse' + (active ? ' brain-pulse-active' : '');
  return `<span class="${cls}" aria-hidden="true">
    <svg viewBox="0 0 24 24">
      <!-- 로봇 헤드 외곽 — 부드러운 둥근 사각형 + 안테나 -->
      <path class="brain-outline"
            d="M5 7 Q5 4 8 4 L16 4 Q19 4 19 7 L19 16 Q19 19 16 19 L8 19 Q5 19 5 16 Z" />
      <line class="brain-outline" x1="12" y1="2" x2="12" y2="4" />
      <circle class="brain-outline" cx="12" cy="2" r="1" />
      <!-- 뉴런 연결선 (먼저 그려서 노드 아래) -->
      <path class="neuron-link" d="M8.5 8 L12 12 L15.5 8" />
      <path class="neuron-link" d="M12 12 L9 15" />
      <path class="neuron-link" d="M12 12 L15 15" />
      <!-- 뉴런 노드 3개, 각각 다른 phase로 깜빡 -->
      <circle class="neuron neuron-1" cx="8.5" cy="8"  r="1.6" />
      <circle class="neuron neuron-2" cx="15.5" cy="8" r="1.6" />
      <circle class="neuron neuron-3" cx="12" cy="14"  r="1.6" />
    </svg>
  </span>`;
}

/* [item #3, 2026-05-09] placeholder는 단일 정적 텍스트.
   이전(PR #126 #A8-1)은 1.6s 타이머로 8개 멘트를 회전시켰는데,
   이게 형식적 "순차 반복"이라 실제 서버 진행과 무관하게 돌았다.
   사용자 피드백:
     "답변창에 추론 답변 준비중에 나오는 애니메이션이 형식적으로
      순차적으로 반복되는것이 아니라 실제 서버에서 디버그 되는
      상황에서 따라 답변 마무리 정리 타이밍에 맞춰서 실제 자메스의
      추론 과정을 맞춰서 진행해줘"
   → 진짜 진행 신호 = `/trace/poll` 폴링이 잡는 stage 이벤트.
     첫 stage 도착 전엔 brain 애니메이션 + 정적 placeholder만 보이고,
     이벤트 도착 즉시 STAGE_META 기반 라인 stacking으로 자연 전환.
     auth → retrieve → graph → answer → complete 가 실시간 표시되며
     `complete` event에서 답변 마무리와 정확히 동기화된다. */
function appendTyping(traceId) {
  const messages = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg james';
  div.innerHTML = `
    <div class="avatar james">🧠</div>
    <div class="bubble" style="min-width:220px">
      <div id="thinking-${traceId}" class="thinking-stream">
        <div class="thinking-placeholder">
          ${brainPulseSvg(true)}
          <span class="thinking-shimmer-text thinking-label thinking-placeholder-text"
                data-trace="${traceId}">JAMES 추론 중</span>
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
  // 색상은 CSS 변수로 라인에 inject (shimmer + spinner border 색).
  // [§4 #3 phase grouping, 2026-05-12] phase 필드는 추론 timeline
  // 의 세 구간 중 어디에 라인을 끼울지 결정한다:
  //   retrieve  — 권한 게이트 + 내부 자료 검색 (소스 찾기)
  //   expand    — 관계 그래프 / 도구 / 코딩 LLM 라우팅 (탐색)
  //   verify    — 답변 생성 + 종료 단계 (검증/마무리)
  // 백엔드(server_llmwiki.py · core/reasoning/modes.py)가 실제로
  // 내보내는 stage 와 1:1 대응되며, 빈 phase 컨테이너는 lazy 생성.
  const STAGE_META = {
    auth:        { icon: '🔐', label: '권한 확인',          color: '#999',    phase: 'retrieve' },
    risky_coding_blocked: { icon: '🛑', label: '위험 명령 차단', color: '#f06292', phase: 'retrieve' },
    retrieve:    { icon: '🔍', label: '내부 자료 검색',     color: '#7c6af7', phase: 'retrieve' },
    rerank:      { icon: '🎯', label: '재정렬',              color: '#7c6af7', phase: 'retrieve' },
    graph:       { icon: '🕸️', label: '관계 그래프 탐색',   color: '#3da78a', phase: 'expand' },
    tool:        { icon: '🔧', label: '도구 호출',           color: '#ffb74d', phase: 'expand' },
    coding_route: { icon: '⌨️', label: '코딩 LLM 라우팅',    color: '#ffb74d', phase: 'expand' },
    coding_llm_pick: { icon: '⚙️', label: '모델 선택',       color: '#ffb74d', phase: 'expand' },
    coding_user_pick: { icon: '👤', label: '사용자 모델 선택', color: '#ffb74d', phase: 'expand' },
    coding_done: { icon: '✓',  label: '코딩 완료',           color: '#4caf7d', phase: 'verify' },
    coding_llm_error: { icon: '⚠️', label: '코더 LLM 오류',  color: '#f06292', phase: 'verify' },
    coding_fallback_done: { icon: '↻', label: 'Fallback 완료', color: '#ffb74d', phase: 'verify' },
    coding_fallback_error: { icon: '⚠️', label: 'Fallback 오류', color: '#f06292', phase: 'verify' },
    coding_user_pick_done: { icon: '✓', label: '사용자 모델 완료', color: '#4caf7d', phase: 'verify' },
    coding_user_pick_error: { icon: '⚠️', label: '사용자 모델 오류', color: '#f06292', phase: 'verify' },
    answer:      { icon: '🤖', label: 'LLM 답변 생성',       color: '#f06292', phase: 'verify' },
    complete:    { icon: '✅', label: '완료',                color: '#4caf7d', phase: 'verify' },
  };

  // [§4 #3] Phase 단위 메타 — 컨테이너 헤더에 표시. 순서는 timeline
  // 진행 순서를 강제한다: RETRIEVE → EXPAND → VERIFY. 한 phase 가
  // 생략되어도(예: graph 사용 안 한 빠른 답변) 다음 phase 가 빈
  // 자리를 그대로 받는다 — 사용자에겐 진행이 한 칸 점프한 것처럼
  // 보임. 비어 있는 phase 컨테이너는 절대 만들지 않는다(lazy).
  const PHASE_META = {
    retrieve: { icon: '🔎', label: 'RETRIEVE', order: 1 },
    expand:   { icon: '🕸️', label: 'EXPAND',   order: 2 },
    verify:   { icon: '🤖', label: 'VERIFY',   order: 3 },
  };

  // 현재 active line을 done으로 마감 (다음 stage 시작 시 호출)
  const markActiveAsDone = () => {
    if (activeLine) {
      activeLine.classList.remove('thinking-active');
      activeLine.classList.add('thinking-done');
      activeLine = null;
    }
  };

  // [§4 #3 phase grouping] 한 phase 컨테이너를 가져오거나 첫 등장
  // 시점에 만들어 timeline 순서대로 끼워 넣는다. 빈 phase 는 만들지
  // 않으므로 graph 사용 안 한 빠른 답변은 RETRIEVE + VERIFY 두 칸
  // 만 보임 — phase 자체가 진행 상태의 의미적 단서.
  const getOrCreatePhase = (phaseKey) => {
    const container = document.getElementById(`thinking-${traceId}`);
    if (!container) return null;
    let phase = container.querySelector(
      `.thinking-phase[data-phase="${phaseKey}"]`);
    if (phase) return phase;

    const meta = PHASE_META[phaseKey];
    if (!meta) return null;
    phase = document.createElement('div');
    phase.className = 'thinking-phase thinking-phase-active';
    phase.setAttribute('data-phase', phaseKey);
    phase.setAttribute('data-order', String(meta.order));
    phase.innerHTML = `
      <div class="thinking-phase-header">
        <span class="thinking-phase-icon">${meta.icon}</span>
        <span class="thinking-phase-label">${escHtml(meta.label)}</span>
      </div>
      <div class="thinking-phase-body"></div>
    `;

    // Insert in the canonical order (1 → 2 → 3) so a late-arriving
    // earlier phase still sorts before later ones — defensive only;
    // the backend emits in order, but the contract test asserts this
    // independent of arrival sequence so render output stays stable.
    const existing = Array.from(
      container.querySelectorAll('.thinking-phase'));
    const insertBefore = existing.find(p =>
      parseInt(p.getAttribute('data-order'), 10) > meta.order);
    if (insertBefore) {
      container.insertBefore(phase, insertBefore);
    } else {
      container.appendChild(phase);
    }
    return phase;
  };

  // When the last active line in a phase closes, the phase itself
  // flips to ``thinking-phase-done`` so the header stops shimmering.
  const refreshPhaseState = (phaseEl) => {
    if (!phaseEl) return;
    const stillActive = phaseEl.querySelector('.thinking-line.thinking-active');
    if (stillActive) {
      phaseEl.classList.add('thinking-phase-active');
      phaseEl.classList.remove('thinking-phase-done');
    } else {
      phaseEl.classList.remove('thinking-phase-active');
      phaseEl.classList.add('thinking-phase-done');
    }
  };

  const apply = (events) => {
    const container = document.getElementById(`thinking-${traceId}`);
    if (!container) return;
    // 첫 진짜 stage event 도착 시 정적 placeholder 제거.
    // (이후 STAGE_META 기반 라인 stacking이 인계 — 서버 진행에 정확히 동기화)
    if (events.length > 0) {
      const ph = container.querySelector('.thinking-placeholder');
      if (ph) ph.remove();
    }
    events.forEach(ev => {
      const stage = ev.stage;
      if (!stage || seenStages.has(stage)) return;
      seenStages.add(stage);

      // 새 stage 도착 → 이전 active를 done으로
      const previousActivePhase = activeLine ? activeLine.closest(
        '.thinking-phase') : null;
      markActiveAsDone();
      refreshPhaseState(previousActivePhase);

      const m = STAGE_META[stage] || {
        icon: '·', label: stage, color: '#888', phase: 'verify',
      };
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

      // [§4 #3] Drop the line into the right phase body — falls back
      // to the top-level container if PHASE_META is somehow missing
      // an entry (defensive; shouldn't happen).
      const phaseEl = getOrCreatePhase(m.phase);
      if (phaseEl) {
        phaseEl.querySelector('.thinking-phase-body').appendChild(line);
      } else {
        container.appendChild(line);
      }

      if (!isFinal) {
        activeLine = line;
        if (phaseEl) {
          phaseEl.classList.add('thinking-phase-active');
          phaseEl.classList.remove('thinking-phase-done');
        }
      } else {
        activeLine = null;
        refreshPhaseState(phaseEl);
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
/* ── [#A4-A] 답변을 문단 단위로 split + 각 문단 복사 버튼 ──
   사용자 요청: "대화 내용중 핵심 답변 내용 문단을 복사할수 있게 버튼
   별도로 붙이기".

   split 기준: 빈 줄 (\n\s*\n+). 코드블록은 같은 paragraph로 유지
   (분리되면 ``` 마커가 깨져 syntax highlight 사라짐).

   1문단 짜리 짧은 답변은 wrapper 없이 formatAnswer 그대로 — 시각적
   잡음 방지 (전체 복사 버튼이 이미 답변 하단에 있음). */
function formatAnswerWithParagraphs(text) {
  if (!text) return '';
  // 코드블록 보존 — 멀티라인이라도 한 chunk로.
  const codeBlocks = [];
  const withoutCode = text.replace(/```[\s\S]*?```/g, (match) => {
    codeBlocks.push(match);
    return `\x01CB${codeBlocks.length - 1}\x01`;
  });
  const parts = withoutCode.split(/\n\s*\n+/).map(p => p.trim()).filter(Boolean);
  if (parts.length <= 1) {
    // 단일 문단 — 기존 렌더링 유지 (불필요 wrapper 제거).
    return formatAnswer(text);
  }
  return parts.map(part => {
    let restored = part;
    codeBlocks.forEach((b, i) => {
      restored = restored.replace(`\x01CB${i}\x01`, b);
    });
    const escapedAttr = encodeURIComponent(restored);
    return `<div class="paragraph">
      <div class="paragraph-content">${formatAnswer(restored)}</div>
      <button class="paragraph-copy-btn"
              data-action="copy-answer-text"
              data-content="${escapedAttr}"
              title="이 문단 복사"
              aria-label="이 문단 복사">📋</button>
    </div>`;
  }).join('');
}

function formatAnswer(text) {
  const codeBlocks = [];
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push(`<pre><code class="lang-${lang||'text'}">${escHtml(code.trim())}</code></pre>`);
    return `\x00CODE${idx}\x00`;
  });
  text = escHtml(text);
  text = text.replace(/^###\s+(.+)$/gm, '<strong style="font-size:13px;color:var(--brand-2)">$1</strong>');
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

      const sidAttr = escHtml(s.session_id);
      return `
        <div data-sid="${sidAttr}"
             style="padding:10px;margin-bottom:6px;border-radius:8px;
                    border:1px solid ${isCurrent ? 'var(--accent,#7c6af7)' : 'var(--border,#333)'};
                    background:${isCurrent ? 'rgba(124,106,247,.1)' : 'var(--bg,#161616)'};
                    transition:all .15s">
          <div data-action="switch-session" data-sid="${sidAttr}" style="cursor:pointer">
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
            <button data-action="rename-session" data-sid="${sidAttr}"
                    style="flex:1;background:none;border:1px solid var(--border,#333);
                           border-radius:4px;padding:3px 6px;font-size:10px;
                           cursor:pointer;color:var(--muted,#888)"
                    title="이름 변경">✏️ 이름</button>
            <button data-action="delete-session" data-sid="${sidAttr}"
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
