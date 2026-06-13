/* PROJECT JAMES — knowledge rollback affordance (Phase 4 P4.2).
 *
 * Drives `frontend/knowledge-rollback.html`. Two flows:
 *
 *   A. Undo recent change
 *      1. fetch GET /admin/graph/last-change
 *      2. show what was the most recent change (or "nothing to undo")
 *      3. confirmation modal → POST /admin/graph/log-rollback-intent
 *         scope=last
 *
 *   B. Restore to time T
 *      1. operator picks a datetime
 *      2. fetch GET /admin/graph/diff-vs-now?t=<iso>
 *      3. show preview (added since T / invalidated since T / chain
 *         changes)
 *      4. confirmation modal → POST /admin/graph/log-rollback-intent
 *         scope=since&target_t=<iso>
 *
 * Both flows record the operator's intent in the audit log. Actual
 * graph-state mutation is gated on T5.A.b mutation-site wiring
 * (deferred from v0.4.2) — the UI says so honestly in the result
 * panel after the intent is recorded.
 *
 * Plain ES5 (same convention as the rest of frontend/static/).
 * Per CLAUDE.md rule #1 — domain-agnostic; vertical-specific
 * undo affordances land post-LOI.
 */
(function () {
  'use strict';

  var pendingConfirm = null;  /* { scope, target_t, summaryHtml } */

  function $(id) { return document.getElementById(id); }

  function t(key, fallback) {
    if (typeof window.t === 'function') {
      try { return window.t(key) || fallback; } catch (_) { return fallback; }
    }
    return fallback;
  }

  function escapeHtml(s) {
    if (s === null || typeof s === 'undefined') return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function getCreds() {
    var apiKey = (window.localStorage &&
                  window.localStorage.getItem('james_api_key')) || '';
    var token = (window.localStorage &&
                 window.localStorage.getItem('james_token')) || '';
    return { apiKey: apiKey, token: token };
  }

  /* Request helper — JSON XHR; returns parsed body on 2xx, calls
   * onError(httpStatus, parsedOrNull) otherwise. */
  function request(method, url, body, onOk, onError) {
    var creds = getCreds();
    if (!creds.apiKey) {
      onError(401, { detail: t('rollback.err.admin_required',
                                'admin login required') });
      return;
    }
    var xhr = new XMLHttpRequest();
    xhr.open(method, url, true);
    xhr.setRequestHeader('Accept', 'application/json');
    if (body) xhr.setRequestHeader('Content-Type', 'application/json');
    if (creds.token) {
      xhr.setRequestHeader('Authorization', 'Bearer ' + creds.token);
    }
    xhr.onload = function () {
      var parsed = null;
      try { parsed = JSON.parse(xhr.responseText); } catch (_) {}
      if (xhr.status >= 200 && xhr.status < 300) {
        if (parsed && parsed.ok === false) {
          onError(xhr.status, parsed);
          return;
        }
        onOk(parsed || {});
      } else {
        onError(xhr.status, parsed);
      }
    };
    xhr.onerror = function () {
      onError(0, { detail: t('rollback.err.network', 'network error') });
    };
    xhr.send(body ? JSON.stringify(body) : null);
  }

  /* ── Flow A: undo last change ───────────────────────────────── */

  function loadLastChange() {
    var preview = $('rollback-undo-last-preview');
    if (!preview) return;
    preview.removeAttribute('hidden');
    preview.innerHTML = '<div class="loading">' +
      escapeHtml(t('rollback.loading', '불러오는 중…')) + '</div>';

    var creds = getCreds();
    var url = '/admin/graph/last-change?api_key=' +
              encodeURIComponent(creds.apiKey);

    request('GET', url, null,
      function (body) {
        if (body.no_changes) {
          preview.innerHTML =
            '<div class="empty-state">' +
            escapeHtml(t('rollback.undo_last.empty',
              '되돌릴 변경 사항이 없습니다. 시스템에 기록된 라이프사이클 ' +
              '이벤트가 없습니다 (정상 상태입니다).')) +
            '</div>';
          return;
        }
        var when = body.timestamp || '';
        var what = body.event_type || '';
        var who = '';
        if (body.event_payload && body.event_payload.operator_principal) {
          who = body.event_payload.operator_principal;
        }
        var html =
          '<div class="preview-card">' +
          '<h3>' + escapeHtml(t('rollback.undo_last.preview_title',
            '가장 최근 변경')) + '</h3>' +
          '<dl>' +
          '<dt>' + escapeHtml(t('rollback.field.when', '언제')) + '</dt>' +
          '<dd>' + escapeHtml(when) + '</dd>' +
          '<dt>' + escapeHtml(t('rollback.field.what', '무슨 일')) + '</dt>' +
          '<dd>' + escapeHtml(humanizeEventType(what)) + '</dd>' +
          (who ? ('<dt>' + escapeHtml(t('rollback.field.who', '누가')) +
                  '</dt><dd>' + escapeHtml(who) + '</dd>') : '') +
          '</dl>' +
          '<button id="rollback-confirm-undo-last"' +
          ' type="button" class="onb-btn onb-btn-primary">' +
          escapeHtml(t('rollback.undo_last.confirm_button',
            '이 변경을 되돌리기')) +
          '</button>' +
          '</div>';
        preview.innerHTML = html;
        var btn = document.getElementById('rollback-confirm-undo-last');
        if (btn) btn.addEventListener('click', function () {
          openConfirmModal({
            scope: 'last',
            target_t: null,
            summaryHtml:
              '<p>' + escapeHtml(t('rollback.confirm.summary_last',
                '가장 최근 변경을 되돌립니다.')) + '</p>' +
              '<dl><dt>' + escapeHtml(t('rollback.field.when',
                '언제')) + '</dt>' +
              '<dd>' + escapeHtml(when) + '</dd>' +
              '<dt>' + escapeHtml(t('rollback.field.what',
                '무슨 일')) + '</dt>' +
              '<dd>' + escapeHtml(humanizeEventType(what)) + '</dd></dl>',
          });
        });
      },
      function (status, parsed) {
        renderError(preview, status, parsed);
      });
  }

  function humanizeEventType(et) {
    var map = {
      'lifecycle.supersede.edge_created':   t('rollback.evt.edge_created',
        '관계 추가됨'),
      'lifecycle.supersede.chain_extended': t('rollback.evt.chain_extended',
        '관계 갱신됨'),
      'lifecycle.cascade.invalidate':       t('rollback.evt.invalidated',
        '관계 비활성화'),
      'lifecycle.t1.expiration_cascade':    t('rollback.evt.expired',
        '유효기간 만료'),
      'lifecycle.ontology.pack_mounted':    t('rollback.evt.pack_mounted',
        '온톨로지 팩 추가'),
      'lifecycle.ontology.pack_unmounted':  t('rollback.evt.pack_unmounted',
        '온톨로지 팩 제거')
    };
    return map[et] || et || '?';
  }

  function renderError(target, status, parsed) {
    var msg = (parsed && parsed.detail) || '';
    if (status === 401 || status === 403) {
      msg = t('rollback.err.admin_required', '관리자 로그인이 필요합니다');
    } else if (status === 400 && !msg) {
      msg = t('rollback.err.bad_request', '요청이 잘못되었습니다');
    } else if (!msg) {
      msg = t('rollback.err.unknown', '알 수 없는 오류') +
            ' (HTTP ' + status + ')';
    }
    target.innerHTML =
      '<div class="rollback-error">' + escapeHtml(msg) + '</div>';
  }

  /* ── Flow B: restore to time T ──────────────────────────────── */

  function loadRestorePreview() {
    var input = $('rollback-restore-time');
    var preview = $('rollback-restore-preview');
    if (!input || !preview) return;
    var v = (input.value || '').trim();
    if (!v) {
      preview.removeAttribute('hidden');
      preview.innerHTML = '<div class="rollback-error">' +
        escapeHtml(t('rollback.restore_to.empty_pick',
          '먼저 돌아갈 시점을 선택하세요')) + '</div>';
      return;
    }
    var iso = v;
    if (!/[zZ]|[+\-]\d{2}:?\d{2}$/.test(iso)) iso = iso + ':00Z';

    preview.removeAttribute('hidden');
    preview.innerHTML = '<div class="loading">' +
      escapeHtml(t('rollback.loading', '불러오는 중…')) + '</div>';

    var creds = getCreds();
    var url = '/admin/graph/diff-vs-now?api_key=' +
              encodeURIComponent(creds.apiKey) +
              '&t=' + encodeURIComponent(iso);

    request('GET', url, null,
      function (body) {
        var added = (body.added_edges || []).length;
        var removed = (body.removed_edges || []).length;
        var invalidated = (body.invalidated_since || []).length;
        var packs_added = (body.mounted_packs_added || []).length;
        var packs_removed = (body.mounted_packs_removed || []).length;
        var chains_keys = body.chain_extended || {};
        var chains = 0;
        for (var k in chains_keys) {
          if (Object.prototype.hasOwnProperty.call(chains_keys, k)) chains++;
        }
        var total = added + removed + invalidated + chains +
                    packs_added + packs_removed;

        var summaryRows = '';
        function row(label, n) {
          return '<dt>' + escapeHtml(label) + '</dt>' +
                 '<dd>' + escapeHtml(String(n)) + '</dd>';
        }
        summaryRows += row(t('rollback.diff.added',
          'T 이후 추가된 항목'), added);
        summaryRows += row(t('rollback.diff.invalidated',
          'T 이후 비활성화된 항목'), invalidated);
        summaryRows += row(t('rollback.diff.chains',
          '갱신된 관계 체인'), chains);
        summaryRows += row(t('rollback.diff.packs_added',
          '추가된 온톨로지 팩'), packs_added);
        summaryRows += row(t('rollback.diff.packs_removed',
          '제거된 온톨로지 팩'), packs_removed);

        var emptyMsg = '';
        if (total === 0) {
          emptyMsg = '<div class="empty-state">' +
            escapeHtml(t('rollback.restore_to.no_changes',
              '선택한 시점과 현재 사이에 변경 사항이 없습니다. ' +
              '롤백할 필요가 없습니다.')) + '</div>';
        }

        var html =
          '<div class="preview-card">' +
          '<h3>' + escapeHtml(t('rollback.restore_to.preview_title',
            'T → 현재 비교')) + '</h3>' +
          '<dl class="diff-summary">' + summaryRows + '</dl>' +
          emptyMsg +
          (total > 0 ?
            '<button id="rollback-confirm-restore-to"' +
            ' type="button" class="onb-btn onb-btn-primary">' +
            escapeHtml(t('rollback.restore_to.confirm_button',
              '이 시점으로 복원')) + '</button>' : '') +
          '</div>';
        preview.innerHTML = html;
        var btn = document.getElementById('rollback-confirm-restore-to');
        if (btn) btn.addEventListener('click', function () {
          openConfirmModal({
            scope: 'since',
            target_t: iso,
            summaryHtml:
              '<p>' + escapeHtml(t('rollback.confirm.summary_since',
                'T 시점으로 복원합니다.')) + '</p>' +
              '<dl><dt>T</dt><dd>' + escapeHtml(iso) + '</dd>' +
              '<dt>' + escapeHtml(t('rollback.diff.affected',
                '영향 받는 항목')) + '</dt>' +
              '<dd>' + escapeHtml(String(total)) + '</dd></dl>',
          });
        });
      },
      function (status, parsed) {
        renderError(preview, status, parsed);
      });
  }

  /* ── confirmation modal ─────────────────────────────────────── */

  function openConfirmModal(opts) {
    pendingConfirm = opts;
    var modal = $('rollback-confirm-modal');
    var summary = $('rollback-confirm-summary');
    var note = $('rollback-note');
    if (modal && summary) {
      summary.innerHTML = opts.summaryHtml || '';
      if (note) note.value = '';
      modal.removeAttribute('hidden');
      modal.classList.add('show');
      if (note) try { note.focus(); } catch (_) {}
    }
  }

  function closeConfirmModal() {
    pendingConfirm = null;
    var modal = $('rollback-confirm-modal');
    if (modal) {
      modal.setAttribute('hidden', 'hidden');
      modal.classList.remove('show');
    }
  }

  function confirmAndSubmit() {
    if (!pendingConfirm) return;
    var creds = getCreds();
    var note = $('rollback-note');
    var body = {
      api_key:  creds.apiKey,
      scope:    pendingConfirm.scope,
      target_t: pendingConfirm.target_t,
      note:     note ? (note.value || '') : ''
    };
    request('POST', '/admin/graph/log-rollback-intent', body,
      function (resp) {
        closeConfirmModal();
        renderResult(resp);
      },
      function (status, parsed) {
        var result = $('rollback-result-panel');
        if (result) {
          result.removeAttribute('hidden');
          result.innerHTML = '<div class="rollback-error">' +
            escapeHtml((parsed && parsed.detail) ||
              t('rollback.err.unknown', '알 수 없는 오류') +
              ' (HTTP ' + status + ')') + '</div>';
        }
        closeConfirmModal();
      });
  }

  function renderResult(resp) {
    var panel = $('rollback-result-panel');
    if (!panel) return;
    panel.removeAttribute('hidden');
    panel.innerHTML =
      '<div class="rollback-success">' +
      '<h3>' + escapeHtml(t('rollback.result.title', '의도 기록 완료')) +
      '</h3>' +
      '<p>' + escapeHtml(t('rollback.result.intro',
        '롤백 의도가 감사 로그에 기록되었습니다.')) + '</p>' +
      '<dl>' +
      '<dt>' + escapeHtml(t('rollback.result.audit_row',
        '감사 로그 ID')) + '</dt>' +
      '<dd>#' + escapeHtml(String(resp.audit_row_id || '?')) + '</dd>' +
      '<dt>' + escapeHtml(t('rollback.result.principal',
        '운영자 신원')) + '</dt>' +
      '<dd>' + escapeHtml(resp.operator_principal || '?') + '</dd>' +
      '</dl>' +
      '<div class="rollback-pending-note">' +
      escapeHtml(t('rollback.result.pending_note',
        '⚠️ 그래프 상태 자체의 자동 변경은 T5.A.b 라이프사이클 ' +
        '이벤트 wiring 완료 후 적용됩니다. 현재는 운영자의 의도가 ' +
        '감사 로그에 영구 기록된 상태입니다.')) + '</div>' +
      '</div>';
  }

  /* ── wire ────────────────────────────────────────────────────── */

  function wire() {
    var btnA = $('rollback-undo-last-btn');
    if (btnA) btnA.addEventListener('click', loadLastChange);

    var btnB = $('rollback-restore-preview-btn');
    if (btnB) btnB.addEventListener('click', loadRestorePreview);

    var cancel = $('rollback-cancel-btn');
    if (cancel) cancel.addEventListener('click', closeConfirmModal);

    var confirm = $('rollback-confirm-btn');
    if (confirm) confirm.addEventListener('click', confirmAndSubmit);

    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') {
        var modal = $('rollback-confirm-modal');
        if (modal && modal.style.display !== 'none' &&
            !modal.hasAttribute('hidden')) {
          closeConfirmModal();
        }
      }
    });

    var modal = $('rollback-confirm-modal');
    if (modal) {
      modal.addEventListener('click', function (ev) {
        if (ev.target === modal) closeConfirmModal();
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }

  // Expose for tests + downstream.
  window.JAMES_KnowledgeRollback = {
    loadLastChange:     loadLastChange,
    loadRestorePreview: loadRestorePreview,
    openConfirmModal:   openConfirmModal,
    closeConfirmModal:  closeConfirmModal
  };
})();
