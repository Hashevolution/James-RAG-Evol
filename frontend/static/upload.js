/* PROJECT JAMES — Upload JS v3 (파일별 폴더 설정) */

let uploadQueue = [];

/* ── 파일 입력 처리 ── */
document.getElementById('file-input').addEventListener('change', e => {
  addFiles(Array.from(e.target.files));
  e.target.value = '';
});

/* ── 드래그 앤 드롭 ── */
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
dropZone.addEventListener('drop', e => {
  addFiles(Array.from(e.dataTransfer.files));
});

/* ── 파일 추가 ── */
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
}

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
  if (['jpg','jpeg','png','gif','webp','bmp'].includes(ext)) return '🖼️';
  if (['mp4','avi','mov','mkv','webm'].includes(ext))        return '🎬';
  if (['mp3','wav','m4a','aac','flac'].includes(ext))        return '🎵';
  if (['pdf'].includes(ext))                                  return '📄';
  if (['md','txt'].includes(ext))                             return '📝';
  if (['json','yaml','yml'].includes(ext))                    return '⚙️';
  return '📁';
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
      <button class="remove-btn" id="action-${item.id}" onclick="removeOrCancel('${item.id}')" title="제거">✕</button>
    </div>
    <div class="file-progress-row" id="progress-${item.id}" style="display:none;">
      <div class="file-progress-bar"><div class="file-progress-fill" id="progress-fill-${item.id}"></div></div>
      <span class="file-progress-pct" id="progress-pct-${item.id}">0%</span>
    </div>
    <div class="file-folder-row">
      <span class="folder-icon">📂</span>
      <input
        type="text"
        class="folder-input"
        id="folder-${item.id}"
        placeholder="저장 폴더 (예: 김철수 폴더에 | 기본: 날짜 자동)"
        oninput="updateInstruction('${item.id}', this.value)"
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
  box.style.display = '';
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

/* ── 단일 파일 업로드 (XHR + progress) — Issue #14 ──
 *  fetch()로는 upload progress 이벤트를 받을 수 없어 XMLHttpRequest로
 *  바꿨다. xhr.upload.onprogress가 e.loaded/e.total을 주므로 파일별
 *  진행률을 실시간 표시한다. xhr.abort()로 in-flight 취소 가능.
 *
 *  반환: 성공 시 server JSON, 실패/취소 시 throw (메시지 'aborted'/네트워크 등).
 */
function uploadOne(item) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    item.xhr = xhr;

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        setProgress(item.id, Math.round((e.loaded / e.total) * 100));
      }
    });
    xhr.addEventListener('load', () => {
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
    xhr.addEventListener('error', () => reject(new Error('network error')));
    xhr.addEventListener('abort', () => reject(new Error('aborted')));

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
      const aborted = err && err.message === 'aborted';
      const label   = aborted ? '취소됨' : `실패: ${(err.message || '').slice(0,20)}`;
      setStatus(item.id, 'error', label);
      item.status = 'error';
      if (!aborted) console.error(`업로드 실패: ${item.file.name}`, err);
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
    const folder = r.instruction ? `📂 ${r.instruction}` : '📂 날짜 자동 분류';
    parts.push(folder);
    if (r.category)    parts.push(`분류: ${r.category}`);
    if (r.sensitivity) parts.push(`보안: ${r.sensitivity}`);
    if (r.summary)     parts.push(`요약: ${r.summary}`);
    return `📎 **${r.name}**\n${parts.join(' | ')}`;
  }).join('\n\n');

  appendJamesMsg({
    answer:      `파일 업로드 완료:\n\n${summary}`,
    mode:        'upload',
    graph_paths: [],
    timing_sec:  null,
  });
}
