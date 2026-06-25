/* PROJECT JAMES — Upload JS v3 (파일별 폴더 설정) */

let uploadQueue = [];

/* ── 파일 입력 처리 (file + webkitdirectory 둘 다 지원) ── */
function _captureRelPath(f) {
  // <input type="file" webkitdirectory>로 폴더를 선택한 경우
  // file.webkitRelativePath에 "folder/sub/file.ext" 형태. 큐 표시 +
  // 서버 전송 시 활용을 위해 file.relPath로 보존.
  if (f.webkitRelativePath) {
    try { f.relPath = f.webkitRelativePath; } catch (_) {}
  }
  return f;
}
document.getElementById('file-input').addEventListener('change', e => {
  addFiles(Array.from(e.target.files).map(_captureRelPath));
  e.target.value = '';
});
// item #8: 폴더 선택 input (별도 hidden input, webkitdirectory)
const _folderInput = document.getElementById('folder-input');
if (_folderInput) {
  _folderInput.addEventListener('change', e => {
    const files = Array.from(e.target.files).map(_captureRelPath);
    addFiles(files);
    if (typeof toast === 'function' && files.length > 0) {
      toast(`폴더에서 파일 ${files.length}개 추가됨`, 'success');
    }
    e.target.value = '';
  });
}
// v0.6 — 모바일 카메라 직접 진입용 input (capture="environment"). 폰에선
// 후면 카메라가 즉시 열리고 1장 캡처 후 큐에 add. PC 에선 일반 파일 피커.
const _cameraInput = document.getElementById('camera-input');
if (_cameraInput) {
  _cameraInput.addEventListener('change', e => {
    const files = Array.from(e.target.files).map(_captureRelPath);
    addFiles(files);
    e.target.value = '';
  });
}

/* ── item #8: DataTransfer에서 파일 추출 (폴더 재귀 지원) ──
   dataTransfer.files는 폴더 안의 파일을 안 펼침. webkitGetAsEntry()로
   FileSystemEntry를 받아 디렉토리 traversal. 미지원 환경은 dataTransfer.
   files로 fallback (top-level 파일만).

   재귀 readEntries는 한 번에 최대 100개까지 반환 — empty 받을 때까지
   loop. createReader 인스턴스 재사용해야 다음 batch가 옴 (중요).
*/
async function _filesFromEntry(entry, pathPrefix = '') {
  if (!entry) return [];
  if (entry.isFile) {
    return new Promise((resolve) => {
      entry.file(file => {
        try { file.relPath = pathPrefix + file.name; } catch (_) {}
        resolve([file]);
      }, () => resolve([]));   // 권한 거부 등 — 빈 배열로 무시
    });
  }
  if (entry.isDirectory) {
    const reader = entry.createReader();
    let all = [];
    // readEntries는 batch별로 최대 ~100. 빈 배열 올 때까지 반복.
    while (true) {
      const batch = await new Promise((resolve) => {
        reader.readEntries(resolve, () => resolve([]));
      });
      if (!batch || batch.length === 0) break;
      for (const child of batch) {
        const childPath = pathPrefix + entry.name + '/';
        const subFiles = await _filesFromEntry(child, childPath);
        all = all.concat(subFiles);
      }
    }
    return all;
  }
  return [];
}

async function _filesFromDataTransfer(dataTransfer) {
  // 1. items API (폴더 traversal 가능)
  if (dataTransfer.items && dataTransfer.items.length > 0) {
    const entries = [];
    for (const item of dataTransfer.items) {
      if (item.kind !== 'file') continue;
      const getEntry = item.webkitGetAsEntry || item.getAsEntry;
      if (typeof getEntry === 'function') {
        const entry = getEntry.call(item);
        if (entry) {
          entries.push(entry);
          continue;
        }
      }
      // entry API 없는 경우 직접 file만
      const f = item.getAsFile?.();
      if (f) entries.push({ isFile: true, isDirectory: false,
                             file: cb => cb(f), name: f.name });
    }
    let all = [];
    for (const entry of entries) {
      const files = await _filesFromEntry(entry, '');
      all = all.concat(files);
    }
    if (all.length > 0) return all;
  }
  // 2. fallback: 평탄한 dataTransfer.files (폴더 traversal 불가)
  return Array.from(dataTransfer.files || []);
}

/* ── 드래그 앤 드롭 (사이드바 dropzone) ── */
const dropZone = document.getElementById('drop-zone');
['dragenter','dragover'].forEach(ev =>
  dropZone.addEventListener(ev, e => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  })
);
['dragleave','drop'].forEach(ev =>
  dropZone.addEventListener(ev, e => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
  })
);
dropZone.addEventListener('drop', async e => {
  // item #8: 폴더 통째 드롭 시 webkitGetAsEntry로 재귀 traverse.
  const files = await _filesFromDataTransfer(e.dataTransfer);
  if (files.length > 0) addFiles(files);
});

/* ── item #7: 챗 페이지 전체에 드래그 앤 드롭 ──
   메시지 입력하기 전에 파일을 어디든 떨어뜨리면 자동으로 큐에 추가.
   드래그 진입 시 풀스크린 오버레이로 "여기에 놓아주세요" 시각 신호.

   주의: drop 이벤트는 일반 윈도우에선 default가 "브라우저가 파일 열기"
   라서 드래그가 페이지 밖으로 나가도 preventDefault 안 하면 새 탭에서
   파일이 열림. 따라서 window 단위로 dragover/drop 모두 preventDefault.
*/
(function setupChatDropzone() {
  // chat 페이지에서만 활성. admin.html에는 messages 컨테이너 없음.
  if (!document.getElementById('messages')) return;

  // 드래그 카운터 — dragenter/leave가 자식 요소에서도 발생해서
  // 단순 boolean으론 깜빡임. counter로 진짜 leave 추적.
  let dragDepth = 0;
  let overlay = null;

  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'chat-drop-overlay';
    overlay.style.cssText = `
      position:fixed; inset:0;
      background:rgba(99,102,241,0.18);
      backdrop-filter: blur(2px);
      border:3px dashed var(--accent, #6366f1);
      border-radius:12px;
      z-index:10000;
      display:none;
      align-items:center; justify-content:center;
      pointer-events:none;
      transition:opacity .15s ease;
    `;
    overlay.innerHTML = `
      <div style="background:var(--surface,#14161a); padding:24px 32px;
                  border-radius:16px; border:1px solid var(--border,#25282f);
                  box-shadow:0 12px 40px rgba(0,0,0,.5); text-align:center;
                  pointer-events:none">
        <div style="margin-bottom:8px"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg></div>
        <div style="font-size:16px; font-weight:600; color:var(--text,#fff)">
          여기에 놓으면 업로드 큐에 추가됩니다
        </div>
        <div style="font-size:12px; color:var(--muted,#888); margin-top:6px">
          이미지 / PDF / Word / 텍스트 파일 지원
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    return overlay;
  }

  function showOverlay() {
    ensureOverlay().style.display = 'flex';
  }
  function hideOverlay() {
    if (overlay) overlay.style.display = 'none';
  }

  // window 전체에 등록 — 페이지 안 어느 곳이든 드롭 가능
  window.addEventListener('dragenter', e => {
    // 파일 드래그만 처리 (텍스트 드래그/링크는 무시)
    if (!e.dataTransfer || !e.dataTransfer.types) return;
    if (!e.dataTransfer.types.includes('Files')) return;
    e.preventDefault();
    dragDepth++;
    if (dragDepth === 1) {
      showOverlay();
      // W6: switch sidebar to upload mode so the user sees the drop
      // target before they release. switchSidebarMode 는 W5 의 공개
      // entry point. 사이드바가 collapsed 상태면 expand 도 함께.
      if (typeof switchSidebarMode === 'function') {
        switchSidebarMode('upload');
      }
    }
  });

  window.addEventListener('dragover', e => {
    if (!e.dataTransfer || !e.dataTransfer.types) return;
    if (!e.dataTransfer.types.includes('Files')) return;
    e.preventDefault();   // 새 탭에서 파일 열리는 default 차단
    e.dataTransfer.dropEffect = 'copy';
  });

  window.addEventListener('dragleave', e => {
    if (!e.dataTransfer || !e.dataTransfer.types) return;
    if (!e.dataTransfer.types.includes('Files')) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) hideOverlay();
  });

  window.addEventListener('drop', async e => {
    if (!e.dataTransfer) return;
    e.preventDefault();
    dragDepth = 0;
    hideOverlay();
    // item #8: 폴더 드롭 시 재귀 traverse — sidebar drop과 동일 함수 사용
    const files = await _filesFromDataTransfer(e.dataTransfer);
    if (files.length === 0) return;

    addFiles(files);
    // W6: switchSidebarMode 가 expand 까지 처리 — 명시적으로 보장.
    if (typeof switchSidebarMode === 'function') {
      switchSidebarMode('upload');
    } else if (typeof toggleSidebar === 'function') {
      // Fallback for any host without W5 (e.g. older cached page).
      const sb = document.getElementById('sidebar');
      if (sb && sb.classList.contains('collapsed')) toggleSidebar();
    }
    if (typeof toast === 'function') {
      const folderHint = files.some(f => f.relPath && f.relPath.includes('/'))
                        ? ' (폴더 포함)' : '';
      toast(`파일 ${files.length}개 추가됨${folderHint}`, 'success');
    }
  });
})();

/* ── 파일 추가 ──
   [video-asr 2026-05-11] 영상 파일은 server 가 ffmpeg+Whisper 로
   처리하므로 frontend 필터 제거. 운영자 환경에 ffmpeg 가 없으면
   서버가 친절한 에러 메시지를 돌려준다.
*/
function addFiles(files) {
  files.forEach(f => {
    const dup = uploadQueue.find(q => q.file.name === f.name && q.file.size === f.size);
    if (dup) return;
    const item = {
      file:        f,
      id:          Date.now() + '_' + Math.random().toString(36).slice(2,6),
      status:      'ready',
      instruction: '',   // 파일별 저장 지시
      xhr:         null, // in-flight XMLHttpRequest (set during upload, cleared after)
    };
    uploadQueue.push(item);
    renderFileItem(item);
  });
  updateUploadBtn();
  // W6: refresh the chat-input mini-thumbnails row.
  if (typeof renderChatAttachmentRow === 'function') {
    renderChatAttachmentRow();
  }
}


/* ── W6: 챗 input 위 미니썸네일 row ──
   사이드바 file-list 와 같은 uploadQueue 를 mirror 표시. 이미지는
   FileReader 로 readAsDataURL 해서 base64 thumb, 그 외는 getFileIcon
   이모지. 클릭 → 사이드바 업로드 모드 전환 + expand. 빈 큐 = 숨김.
*/
const _thumbDataCache = new Map(); // id → dataURL (이미지만)

function _maybeLoadThumb(item) {
  if (!item || !item.file) return;
  if (_thumbDataCache.has(item.id)) return;
  if (!/^image\//.test(item.file.type || '')) return;
  const reader = new FileReader();
  reader.onload = () => {
    _thumbDataCache.set(item.id, reader.result);
    // Re-render to swap the icon for the loaded thumb. Cheap — the
    // row is only N items, and renderChatAttachmentRow is O(N).
    renderChatAttachmentRow();
  };
  // No onerror handler — failure leaves the icon fallback in place.
  try { reader.readAsDataURL(item.file); } catch (_) {}
}

function renderChatAttachmentRow() {
  const row = document.getElementById('chat-attachment-row');
  if (!row) return;
  const queue = (typeof uploadQueue !== 'undefined') ? uploadQueue : [];
  if (!queue.length) {
    row.style.display = 'none';
    row.innerHTML = '';
    return;
  }
  row.style.display = 'flex';
  row.innerHTML = queue.map(it => {
    _maybeLoadThumb(it);
    const isImg  = /^image\//.test(it.file.type || '');
    const thumb  = isImg && _thumbDataCache.has(it.id)
      ? `<img src="${_thumbDataCache.get(it.id)}" alt=""
              style="width:100%;height:100%;object-fit:cover;border-radius:5px">`
      : `<span style="font-size:18px">${
          (typeof getFileIcon === 'function') ? getFileIcon(it.file.name) : 'DOC'
        }</span>`;
    const status = it.status === 'upload' ? '↑'
                 : it.status === 'done'   ? '✅'
                 : it.status === 'error'  ? '❌'
                 : '';
    // Truncate the display name — 16 chars + ext keeps the chip narrow.
    const name = it.file.name.length > 22
      ? it.file.name.slice(0, 16) + '…' + it.file.name.slice(-5)
      : it.file.name;
    return `
      <div data-action="chat-attach-click"
           title="${it.file.name.replace(/"/g, '&quot;')}"
           style="display:flex;align-items:center;gap:6px;padding:4px 8px 4px 4px;
                  background:var(--surface-2);border:1px solid var(--border);
                  border-radius:8px;cursor:pointer;font-size:11px;color:var(--text-soft);
                  max-width:200px;font-family:var(--font-ui)">
        <span style="width:24px;height:24px;display:flex;align-items:center;
                     justify-content:center;background:var(--bg);border-radius:5px;
                     overflow:hidden;flex-shrink:0">${thumb}</span>
        <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
          ${name}
        </span>
        ${status ? `<span style="flex-shrink:0">${status}</span>` : ''}
      </div>`;
  }).join('');
}

// Single click target for the whole row — opens sidebar on the
// upload mode so the user can inspect / remove / start the upload.
window._chatAttachClick = function () {
  if (typeof switchSidebarMode === 'function') {
    switchSidebarMode('upload');
  } else if (typeof toggleSidebar === 'function') {
    const sb = document.getElementById('sidebar');
    if (sb && sb.classList.contains('collapsed')) toggleSidebar();
  }
};


/* ── W6: 챗 input 에 paste — 클립보드의 파일/이미지를 큐에 추가 ──
   브라우저에서 이미지를 복사하면 ClipboardItem 으로 File-like 객체가
   넘어옴. 텍스트 paste 는 무시하고 textarea 의 기본 동작 유지.
*/
window.handleChatPaste = function (e) {
  if (!e.clipboardData || !e.clipboardData.items) return;
  const files = [];
  for (const item of e.clipboardData.items) {
    if (item.kind === 'file') {
      const f = item.getAsFile();
      if (f) files.push(f);
    }
  }
  if (!files.length) return;   // 일반 텍스트 paste 는 그대로
  e.preventDefault();
  addFiles(files);
  if (typeof switchSidebarMode === 'function') {
    switchSidebarMode('upload');
  }
  if (typeof toast === 'function') {
    toast(`클립보드에서 파일 ${files.length}개 추가됨`, 'success');
  }
};

/* ── 파일 제거 또는 진행 중 취소 ──
 *  Issue #14: when upload is in flight (item.status === 'upload' and xhr
 *  exists), the same per-file button now aborts the XMLHttpRequest instead
 *  of removing from the queue. The 'abort' handler in uploadOne() then
 *  surfaces it as `error` with label '취소됨'.
 */
function removeOrCancel(id) {
  const item = uploadQueue.find(i => String(i.id) === String(id));
  if (item && item.status === 'upload' && item.xhr) {
    try { item.xhr.abort(); } catch (_) {}
    return;   // do not remove DOM yet — uploadFiles loop will reach the catch and re-render
  }
  uploadQueue = uploadQueue.filter(i => String(i.id) !== String(id));
  const el = document.getElementById(`file-${id}`);
  if (el) el.remove();
  updateUploadBtn();
  // W6: keep the chat-input mini-thumbnail row in sync.
  if (typeof renderChatAttachmentRow === 'function') {
    _thumbDataCache.delete(id);
    renderChatAttachmentRow();
  }
}
// Backwards-compat alias for any inline onclick that still calls removeFile
function removeFile(id) { removeOrCancel(id); }

/* ── 업로드 버튼 상태 ── */
function updateUploadBtn() {
  const pending = uploadQueue.filter(i => i.status === 'ready').length;
  const btn = document.getElementById('upload-btn');
  btn.disabled = pending === 0;
  btn.textContent = pending > 0 ? `업로드 및 분석 (${pending}개)` : '업로드 및 분석';
}

/* ── 아이콘 ── */
function getFileIcon(name) {
  const ext = name.split('.').pop().toLowerCase();
  if (['jpg','jpeg','png','gif','webp','bmp'].includes(ext)) return 'IMG';
  if (['mp4','avi','mov','mkv','webm'].includes(ext))        return 'VID';
  if (['mp3','wav','m4a','aac','flac'].includes(ext))        return 'AUD';
  if (['pdf'].includes(ext))                                  return 'PDF';
  if (['md','txt'].includes(ext))                             return 'TXT';
  if (['json','yaml','yml'].includes(ext))                    return 'CFG';
  return 'DIR';
}

function formatSize(bytes) {
  if (bytes < 1024)      return bytes + 'B';
  if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + 'KB';
  return (bytes/1024/1024).toFixed(1) + 'MB';
}

/* ── 파일 아이템 렌더링 (파일별 폴더 입력 포함) ── */
function renderFileItem(item) {
  const list = document.getElementById('file-list');
  const div  = document.createElement('div');
  div.className = 'file-item';
  div.id = `file-${item.id}`;
  div.innerHTML = `
    <div class="file-item-top">
      <span class="file-icon">${getFileIcon(item.file.name)}</span>
      <div class="file-info">
        <div class="file-name" title="${item.file.name}">${item.file.name}</div>
        <div class="file-size">${formatSize(item.file.size)}</div>
      </div>
      <span class="file-status status-ready" id="status-${item.id}">대기</span>
      <button class="remove-btn" id="action-${item.id}" data-action="remove-or-cancel" data-item-id="${escHtml(item.id)}" title="제거">✕</button>
    </div>
    <div class="file-progress-row" id="progress-${item.id}" style="display:none;">
      <div class="file-progress-bar"><div class="file-progress-fill" id="progress-fill-${item.id}"></div></div>
      <span class="file-progress-pct" id="progress-pct-${item.id}">0%</span>
    </div>
    <div class="file-folder-row">
      <span class="folder-icon"></span>
      <input
        type="text"
        class="folder-input"
        id="folder-${item.id}"
        placeholder="저장 폴더 (예: 김철수 폴더에 | 기본: 날짜 자동)"
        data-input-action="update-instruction"
        data-item-id="${escHtml(item.id)}"
      >
    </div>
  `;
  list.appendChild(div);
}

/* ── 파일별 instruction 업데이트 ── */
function updateInstruction(id, value) {
  const item = uploadQueue.find(i => String(i.id) === String(id));
  if (item) item.instruction = value;
}

function setStatus(id, status, label) {
  const el = document.getElementById(`status-${id}`);
  if (!el) return;
  el.className = `file-status status-${status}`;
  el.textContent = label;
  // Action button: stays visible across all states; title swaps to '취소' during upload.
  const btn = document.getElementById(`action-${id}`);
  if (btn) {
    if (status === 'upload')      { btn.style.display = ''; btn.title = '취소'; }
    else if (status === 'done')   { btn.style.display = 'none'; }
    else                           { btn.style.display = ''; btn.title = '제거'; }
  }
  // Per-file progress bar visible only during upload.
  const prog = document.getElementById(`progress-${id}`);
  if (prog) prog.style.display = (status === 'upload') ? '' : 'none';
  // W6: keep the chat-input mini-thumbnail status indicator in sync
  // (⬆️ / ✅ / ❌).
  if (typeof renderChatAttachmentRow === 'function') {
    renderChatAttachmentRow();
  }
}

function setProgress(id, pct) {
  const fill = document.getElementById(`progress-fill-${id}`);
  if (fill) fill.style.width = pct + '%';
  const lbl  = document.getElementById(`progress-pct-${id}`);
  if (lbl)  lbl.textContent = pct + '%';
}

/* ── 큐 진행 표시 (Issue #14) ──
 *  pass `total + 1` for current to hide the queue indicator after the run.
 */
function setQueueProgress(current, total, filename) {
  const box = document.getElementById('queue-progress');
  if (!box) return;
  if (current > total || total <= 0) { box.style.display = 'none'; return; }
  box.style.display = ''; box.classList.remove('d-none');  // CSP migration
  const txt = document.getElementById('queue-progress-text');
  if (txt) txt.textContent = `업로드 중 ${current}/${total} — ${filename}`;
  const fill = document.getElementById('queue-progress-fill');
  if (fill) fill.style.width = Math.round(((current - 1) / total) * 100) + '%';
}

/* ── 전체 공통 지시 → 빈 파일에 적용 ── */
function applyGlobalInstruction() {
  const global = document.getElementById('save-instruction')?.value.trim() || '';
  if (!global) return;
  uploadQueue.forEach(item => {
    if (!item.instruction) {
      item.instruction = global;
      const inp = document.getElementById(`folder-${item.id}`);
      if (inp) inp.value = global;
    }
  });
}

/* [#7-B] Upload timeout — server hang에서 client-side 5분 cutoff.
   Tunnel(Tailscale Serve) 환경에서 무응답 시 무한 대기하던 문제.
   파일 크기 ≤ 100MB 가정이라 5분이면 충분 (실측 평균 < 30초). */
const UPLOAD_TIMEOUT_MS = 5 * 60 * 1000;

/* [#7-B] 진행 stall 감지 — 30초간 progress 이벤트 없으면 hung 판정.
   네트워크 단절 / Wi-Fi 전환 시 xhr.error 발생 안 하고 그냥 멎는 사례
   대비. progress callback이 last_progress_ms를 갱신, 별도 인터벌이
   30초 이상 stall 시 abort. */
const UPLOAD_STALL_MS = 30 * 1000;

/* ── 단일 파일 업로드 (XHR + progress) — Issue #14 / #7-B 보강 ──
 *  fetch()로는 upload progress 이벤트를 받을 수 없어 XMLHttpRequest로
 *  바꿨다. xhr.upload.onprogress가 e.loaded/e.total을 주므로 파일별
 *  진행률을 실시간 표시한다. xhr.abort()로 in-flight 취소 가능.
 *
 *  [#7-B 추가]
 *  - xhr.timeout / ontimeout — 5분 hard limit
 *  - stall watchdog — 30초간 progress 이벤트 없으면 abort + 'stalled'
 *
 *  반환: 성공 시 server JSON, 실패/취소 시 throw (메시지 'aborted'/
 *        'stalled'/'timeout'/네트워크 등).
 */
function uploadOne(item) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    item.xhr = xhr;
    let lastProgressMs = Date.now();
    let stallTimer = null;
    const clearStall = () => {
      if (stallTimer) { clearInterval(stallTimer); stallTimer = null; }
    };

    xhr.upload.addEventListener('progress', (e) => {
      lastProgressMs = Date.now();
      if (e.lengthComputable) {
        setProgress(item.id, Math.round((e.loaded / e.total) * 100));
      }
    });
    xhr.addEventListener('load', () => {
      clearStall();
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText || '{}')); }
        catch (_) { reject(new Error('invalid JSON response')); }
      } else {
        let detail = `${xhr.status} ${xhr.statusText}`;
        try {
          const body = JSON.parse(xhr.responseText || '{}');
          if (body && body.detail) detail = body.detail;
        } catch (_) {}
        reject(new Error(detail));
      }
    });
    xhr.addEventListener('error',   () => { clearStall(); reject(new Error('network error')); });
    xhr.addEventListener('abort',   () => { clearStall(); reject(new Error('aborted')); });
    xhr.addEventListener('timeout', () => { clearStall(); reject(new Error('timeout')); });

    // [#7-B] hard timeout
    xhr.timeout = UPLOAD_TIMEOUT_MS;

    // [#7-B] stall watchdog — 5초마다 progress 시각 체크.
    stallTimer = setInterval(() => {
      if (Date.now() - lastProgressMs > UPLOAD_STALL_MS) {
        clearStall();
        try { xhr.abort(); } catch(_) {}
        reject(new Error('stalled'));
      }
    }, 5000);

    const form = new FormData();
    form.append('file',        item.file);
    form.append('api_key',     getApiKey());
    form.append('source_type', SOURCE_TYPE);
    if (item.instruction.trim())
      form.append('instruction', item.instruction.trim());

    xhr.open('POST', `${API}/upload/`);
    const tok = localStorage.getItem('james_token') || '';
    if (tok) xhr.setRequestHeader('Authorization', `Bearer ${tok}`);
    xhr.send(form);
  });
}

/* [#7-B] Beforeunload guard — 진행 중 업로드가 있을 때 페이지 닫기/
   새로고침 시도하면 브라우저 confirm dialog. 모바일 폰에서 중간에
   화면 닫아 업로드 끊기는 사례 방지. */
window.addEventListener('beforeunload', (e) => {
  const inFlight = (typeof uploadQueue !== 'undefined' ? uploadQueue : [])
                   .filter(i => i.status === 'upload');
  if (inFlight.length > 0) {
    e.preventDefault();
    e.returnValue = '';   // Chrome/Safari 표준
    return '';
  }
});

/* ── 업로드 실행 ── */
async function uploadFiles() {
  const pending = uploadQueue.filter(i => i.status === 'ready');
  if (!pending.length) return;

  // 전체 공통 지시를 빈 파일에 먼저 적용
  applyGlobalInstruction();

  const btn = document.getElementById('upload-btn');
  btn.disabled = true;
  btn.textContent = '업로드 중...';

  let successCount = 0;
  const results = [];
  const total   = pending.length;

  for (let idx = 0; idx < pending.length; idx++) {
    const item = pending[idx];
    item.status = 'upload';
    setStatus(item.id, 'upload', '전송 중');
    setProgress(item.id, 0);
    setQueueProgress(idx + 1, total, item.file.name);
    try {
      const data = await uploadOne(item);
      setProgress(item.id, 100);
      setStatus(item.id, 'done', '완료');
      item.status = 'done';
      successCount++;
      results.push({
        name:        item.file.name,
        instruction: item.instruction,
        ...data,
      });
    } catch (err) {
      // [#7-B] 새 에러 타입 분기:
      //   'aborted'  — 사용자 취소
      //   'timeout'  — 5분 hard cutoff
      //   'stalled'  — 30초간 progress 끊김 (Wi-Fi 전환 등)
      //   기타        — 서버 응답 / 네트워크 오류
      const msg = err && err.message;
      let label;
      if (msg === 'aborted')      label = '취소됨';
      else if (msg === 'timeout') label = '시간 초과 (5분)';
      else if (msg === 'stalled') label = '연결 끊김 (재시도 필요)';
      else                        label = `실패: ${(msg || '').slice(0,20)}`;
      setStatus(item.id, 'error', label);
      item.status = 'error';
      const benign = msg === 'aborted';
      if (!benign) console.error(`업로드 실패: ${item.file.name} (${msg})`, err);
    } finally {
      item.xhr = null;
    }
  }

  setQueueProgress(total + 1, total, '');   // hide
  btn.textContent = '업로드 및 분석';
  updateUploadBtn();

  if (successCount > 0) {
    toast(`✅ ${successCount}개 파일 업로드 완료`, 'success');
    showUploadResult(results);
    // 완료 항목 DOM + 큐 제거
    uploadQueue.filter(i => i.status === 'done').forEach(i => {
      document.getElementById(`file-${i.id}`)?.remove();
    });
    uploadQueue = uploadQueue.filter(i => i.status !== 'done');
    if (uploadQueue.length === 0) {
      const inp = document.getElementById('save-instruction');
      if (inp) inp.value = '';
    }
    updateUploadBtn();
  }
}

/* ── 업로드 결과 챗에 표시 ── */
function showUploadResult(results) {
  if (!results.length) return;
  hideWelcome();

  const summary = results.map(r => {
    const parts = [];
    const folder = r.instruction ? `${r.instruction}` : '날짜 자동 분류';
    parts.push(folder);
    if (r.category)    parts.push(`분류: ${r.category}`);
    if (r.sensitivity) parts.push(`보안: ${r.sensitivity}`);
    if (r.summary)     parts.push(`요약: ${r.summary}`);
    return `**${r.name}**\n${parts.join(' | ')}`;
  }).join('\n\n');

  appendJamesMsg({
    answer:      `파일 업로드 완료:\n\n${summary}`,
    mode:        'upload',
    graph_paths: [],
    timing_sec:  null,
  });
}
