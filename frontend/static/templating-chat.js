/* PROJECT JAMES — chat page (/) template-formatting engine wiring.
 *
 * v0.6 Track F (mother-level UI). The operator registers templates in
 * /workspace (file / image / pasted text); this panel is the chat-side
 * *apply* entry point: pick one of your own templates, paste raw
 * content, and JAMES reshapes it into the template's structure as a
 * downloadable file.
 *
 * Deliberately self-contained:
 *   - reads auth (james_token / james_api_key) from localStorage
 *     directly, the same keys chat.js / workspace.js use;
 *   - registers its OWN document-level click delegation for the
 *     ``tplc-*`` actions, so it never has to touch chat.js's 2773-line
 *     send pipeline (chat.js's delegation simply ignores unknown
 *     actions — both listeners fire, each handles its own set);
 *   - only shared dependency is the global ``t()`` from i18n.js, which
 *     is loaded first.
 *
 * Backend contract (routes/templating.py — owner-scoped):
 *   GET  /templates/mine/list               list my templates
 *   GET  /templates/{id}                     detail + parsed spec
 *   POST /templates/{id}/apply               reshape raw → output file
 *   GET  /templates/{id}/output/{out_id}     download
 *
 * Domain-agnostic: every template is runtime user data — JAMES ships
 * none — so this UI carries no vertical coupling (CLAUDE.md rule #1).
 */
(function () {
  'use strict';

  var _curId = null;     // currently selected template id
  var _outId = null;     // last generated output id (for download)

  function _tok() {
    try { return localStorage.getItem('james_token') || ''; } catch (_) { return ''; }
  }
  function _key() {
    try { return localStorage.getItem('james_api_key') || ''; } catch (_) { return ''; }
  }
  function _tt(k, fb) {
    return (typeof t === 'function') ? t(k) : (fb || k);
  }
  function _esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /* GET helper — api_key in the query string + JWT in the header,
     mirroring _apiFetch in workspace.js. */
  async function _get(path) {
    var sep = path.indexOf('?') === -1 ? '?' : '&';
    var url = path + sep + 'api_key=' + encodeURIComponent(_key());
    var r = await fetch(url, {
      headers: _tok() ? { Authorization: 'Bearer ' + _tok() } : {},
    });
    if (!r.ok) {
      var d = '' + r.status;
      try { d = (await r.json()).detail || d; } catch (_) {}
      throw new Error(d);
    }
    return r.json();
  }

  /* POST helper — api_key folded into the JSON body, matching the
     FastAPI request models (extra fields are ignored by Pydantic). */
  async function _post(path, body) {
    var r = await fetch(path, {
      method: 'POST',
      headers: Object.assign(
        { 'Content-Type': 'application/json' },
        _tok() ? { Authorization: 'Bearer ' + _tok() } : {}),
      body: JSON.stringify(Object.assign({ api_key: _key() }, body || {})),
    });
    if (!r.ok) {
      var d = '' + r.status;
      try { d = (await r.json()).detail || d; } catch (_) {}
      throw new Error(d);
    }
    return r.json();
  }

  function _setMsg(text) {
    var el = document.getElementById('tplc-msg');
    if (el) el.textContent = text || '';
  }

  async function openModal() {
    var m = document.getElementById('tplc-modal');
    if (!m) return;
    m.classList.remove('hidden');
    _curId = null;
    _outId = null;
    _setMsg('');
    document.getElementById('tplc-result').style.display = 'none';
    document.getElementById('tplc-download-btn').style.display = 'none';
    var copyBtnInit = document.getElementById('tplc-copy-btn');
    if (copyBtnInit) copyBtnInit.style.display = 'none';
    document.getElementById('tplc-placeholders').innerHTML = '';
    var sel = document.getElementById('tplc-select');
    sel.innerHTML = '<option value="">' + _esc(_tt('common.loading', '…')) + '</option>';
    if (!_tok()) {
      _setMsg('❌ ' + _tt('tplchat.login_required', 'Login required.'));
      sel.innerHTML = '<option value="">—</option>';
      return;
    }
    try {
      var data = await _get('/templates/mine/list');
      var items = data.items || [];
      if (!items.length) {
        sel.innerHTML = '<option value="">' +
          _esc(_tt('tplchat.no_templates', 'No templates — register one in Workspace.')) +
          '</option>';
        return;
      }
      sel.innerHTML =
        '<option value="">' + _esc(_tt('tplchat.pick_ph', '— choose a template —')) + '</option>' +
        items.map(function (it) {
          return '<option value="' + _esc(it.id) + '">' + _esc(it.name) + '</option>';
        }).join('');
    } catch (e) {
      sel.innerHTML = '<option value="">—</option>';
      _setMsg('❌ ' + e.message);
    }
  }

  function closeModal() {
    var m = document.getElementById('tplc-modal');
    if (m) m.classList.add('hidden');
  }

  async function onSelect() {
    var sel = document.getElementById('tplc-select');
    var ph = document.getElementById('tplc-placeholders');
    _curId = sel.value || null;
    _outId = null;
    _setMsg('');
    document.getElementById('tplc-result').style.display = 'none';
    document.getElementById('tplc-download-btn').style.display = 'none';
    var copyBtnSel = document.getElementById('tplc-copy-btn');
    if (copyBtnSel) copyBtnSel.style.display = 'none';
    ph.innerHTML = '';
    if (!_curId) return;
    try {
      var data = await _get('/templates/' + encodeURIComponent(_curId));
      var phs = (data.spec && data.spec.placeholders) || [];
      ph.innerHTML = phs.length
        ? phs.map(function (p) {
            return '<span class="chip" style="font-size:11px;padding:2px 8px;' +
              'border:1px solid var(--border);border-radius:10px;color:var(--muted)">' +
              _esc(p) + '</span>';
          }).join('')
        : '<span style="color:var(--muted);font-size:11px">' +
            _esc(_tt('tplchat.no_placeholders', 'No placeholders — free-form template.')) +
          '</span>';
    } catch (e) {
      _setMsg('❌ ' + e.message);
    }
  }

  async function apply() {
    if (!_curId) {
      _setMsg('❌ ' + _tt('tplchat.need_template', 'Pick a template first.'));
      return;
    }
    var content = document.getElementById('tplc-content').value;
    var fmt = document.getElementById('tplc-fmt').value;
    var instEl = document.getElementById('tplc-instruction');
    var instruction = (instEl && instEl.value || '').trim();
    if (!content.trim()) {
      _setMsg('❌ ' + _tt('tplchat.need_content', 'Paste some content first.'));
      return;
    }
    var btn = document.getElementById('tplc-apply-btn');
    var orig = btn.textContent;
    btn.disabled = true;
    btn.textContent = '⏳';
    _setMsg('');
    try {
      var payload = { raw_content: content, fmt: fmt };
      if (instruction) payload.instruction = instruction;
      var r = await _post(
        '/templates/' + encodeURIComponent(_curId) + '/apply',
        payload);
      _outId = r.out_id;
      document.getElementById('tplc-preview').textContent = r.preview || '';
      document.getElementById('tplc-result').style.display = 'block';
      document.getElementById('tplc-download-btn').style.display = '';
      var copyBtn = document.getElementById('tplc-copy-btn');
      if (copyBtn) copyBtn.style.display = '';
      _setMsg('✅ ' + (r.filename || ''));
    } catch (e) {
      _setMsg('❌ ' + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = orig;
    }
  }

  async function copyPreview() {
    var pre = document.getElementById('tplc-preview');
    var text = pre && pre.textContent || '';
    if (!text) return;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      _setMsg('' + _tt('tplchat.copy_done', 'Copied to clipboard.'));
    } catch (e) {
      _setMsg('❌ ' + e.message);
    }
  }

  async function download() {
    if (!_curId || !_outId) return;
    var path = '/templates/' + encodeURIComponent(_curId) +
               '/output/' + encodeURIComponent(_outId) +
               '?api_key=' + encodeURIComponent(_key());
    try {
      var r = await fetch(path, {
        headers: _tok() ? { Authorization: 'Bearer ' + _tok() } : {},
      });
      if (!r.ok) {
        var d = '' + r.status;
        try { d = (await r.json()).detail || d; } catch (_) {}
        throw new Error(d);
      }
      var blob = await r.blob();
      var cd = r.headers.get('Content-Disposition') || '';
      var mm = /filename="?([^"]+)"?/.exec(cd);
      var name = mm ? mm[1] : (_outId + '.bin');
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url; a.download = name;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      _setMsg('❌ ' + e.message);
    }
  }

  /* Own click delegation — independent of chat.js. */
  document.addEventListener('click', function (e) {
    var el = e.target.closest && e.target.closest('[data-action]');
    if (!el) return;
    switch (el.getAttribute('data-action')) {
      case 'tplc-open':     e.preventDefault(); openModal(); break;
      case 'tplc-close':    closeModal(); break;
      case 'tplc-apply':    apply(); break;
      case 'tplc-copy':     copyPreview(); break;
      case 'tplc-download': download(); break;
    }
  });

  window.addEventListener('DOMContentLoaded', function () {
    var sel = document.getElementById('tplc-select');
    if (sel) sel.addEventListener('change', onSelect);
    var ov = document.getElementById('tplc-modal');
    if (ov) ov.addEventListener('click', function (e) {
      if (e.target === ov) closeModal();
    });
  });
})();
