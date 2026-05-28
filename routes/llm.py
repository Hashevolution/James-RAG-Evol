"""LLM / Ollama routes.

Extracted from server_llmwiki.py per docs/design/v0.4.x-server-split.md
PR-B. 12 endpoints + 3 module-level helpers
(``_install_progress`` / ``_install_lock``,
``_start_install_with_progress``, ``_list_installed_ollama_models``)
moved verbatim — handler body byte-identical (only
``@app.<m>`` -> ``@router.<m>``).

URL invariant: ``python scripts/audit_endpoint_paths.py origin/main``
must report 0-diff against the pre-PR-B baseline.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from routes._helpers import (
    _require_feature,
    _write_audit,
    get_role_from_request,
    verify_api_key,
)

router = APIRouter()


# ─── Module-level state + helpers ──────────────────────────────────

def _model_catalog():
    """Mode → ordered list of (tag, weight) candidates.

    [#A2 phase 2] Implementation moved to `core.model_catalog` so the
    reasoning engine can validate `selected_model` without importing
    server_llmwiki (circular dep). Public name kept for back-compat
    with `tests/test_model_catalog_per_mode.py:test_catalog_function_exists`.
    """
    from core.model_catalog import model_catalog
    return model_catalog()

def _allowed_install_models():
    out = set()
    for cands in _model_catalog().values():
        for tag, _ in cands:
            if tag:
                out.add(tag)
    return out

# [#A8-8] In-memory install progress tracker. Keyed by model tag.
# Populated by the background thread that streams Ollama's pull API.
# Frontend polls /admin/llm/install-progress?model=... every 2s.
# Survives single server lifetime — restart wipes (operator can re-pull
# if needed; partial Ollama downloads resume on retry).
_install_progress: dict = {}   # model -> {status, percent, completed, total, error}
_install_lock     = None       # set lazily — threading import deferred


def _start_install_with_progress(model: str) -> None:
    """Background thread: stream Ollama's POST /api/pull and write
    progress to _install_progress[model]. Ollama returns NDJSON like:
        {"status": "pulling manifest"}
        {"status": "downloading", "digest": "...", "total": N, "completed": N}
        {"status": "verifying sha256"}
        {"status": "success"}
    We compute percent = completed / total when both fields present.
    """
    import threading, urllib.request, json as _json
    global _install_lock
    if _install_lock is None:
        _install_lock = threading.Lock()

    def _runner():
        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/pull",
                data=_json.dumps({"name": model, "stream": True}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3600) as r:
                for raw in r:   # NDJSON line stream
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue
                    try:
                        evt = _json.loads(line)
                    except Exception:
                        continue
                    status    = evt.get("status", "")
                    completed = evt.get("completed")
                    total     = evt.get("total")
                    percent   = None
                    if isinstance(completed, (int, float)) and isinstance(total, (int, float)) and total > 0:
                        percent = round((completed / total) * 100, 1)
                    with _install_lock:
                        _install_progress[model] = {
                            "status":    status,
                            "completed": completed,
                            "total":     total,
                            "percent":   percent,
                            "error":     "",
                            "done":      status == "success",
                        }
                    if status == "success":
                        # [PR plan-1] resolver cache invalidation so
                        # the freshly-installed model is selectable
                        # immediately on the next /query/ without
                        # waiting 60s TTL.
                        try:
                            from core.model_resolver import invalidate_cache
                            invalidate_cache()
                        except Exception:
                            pass
                        break
        except Exception as e:
            with _install_lock:
                _install_progress[model] = {
                    "status":    "error",
                    "completed": None,
                    "total":     None,
                    "percent":   None,
                    "error":     f"{type(e).__name__}: {e}",
                    "done":      True,
                }

    t = threading.Thread(target=_runner, daemon=True, name=f"ollama-pull-{model}")
    t.start()

def _list_installed_ollama_models() -> set:
    """ollama list 결과에서 설치된 모델 이름 set 반환. 실패 시 빈 set."""
    try:
        import urllib.request, json as _json
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as r:
            data = _json.loads(r.read())
        return {m.get("name", "") for m in data.get("models", []) if m.get("name")}
    except Exception:
        return set()

# ─── Endpoints ─────────────────────────────────────────────────────

@router.get("/llm/modes/", summary="챗 페이지 모드 picker 옵션 [item #6 + #A2]")
async def llm_modes(api_key: str, role: str = Depends(get_role_from_request)):
    """Mode picker가 채울 옵션 목록 + 모델 후보 카탈로그.

    api_key만 검증 (admin 아님). role-allowed 모드만 반환해서 클라이언트
    가 권한 없는 모드를 보지 않도록 한다.

    각 옵션:
      key:         서버에 보낼 mode_override 값
      label:       사용자 노출 라벨
      desc:        한 줄 설명
      keywords:    자동 추천에 사용 (클라이언트 측 keyword match)
      model:       기본(default) 모델 태그 — backward compat
      installed:   기본 모델 설치 상태 — backward compat
      models:      [item #A2] 후보 리스트 — 두 번째 dropdown용
                   각 원소: {"tag": str, "weight": "light|medium|heavy",
                            "installed": bool, "default": bool}
    """
    verify_api_key(api_key)
    from core.intent_classifier import ROLE_ALLOWED
    from config import GEMMA_MODEL, CODING_MODEL
    allowed = ROLE_ALLOWED.get(role, {"chat", "retrieval"})

    # 설치된 모델 set 한 번에 조회 (Ollama API).
    installed_set = set()
    try:
        import urllib.request
        with urllib.request.urlopen(
            "http://localhost:11434/api/tags", timeout=2,
        ) as r:
            data = json.loads(r.read())
        for m in data.get("models", []):
            installed_set.add(m.get("name", ""))
    except Exception:
        pass   # Ollama 미실행 — installed=False로 모두 표시됨

    def _mark(model: str) -> bool:
        """Ollama list와 매칭. 정확 일치 OR 태그 prefix (e.g.
        gemma4:e4b ≈ gemma4)."""
        if not model:
            return True   # meta 같이 LLM 안 쓰는 모드는 항상 'installed'
        if model in installed_set:
            return True
        prefix = model.split(":", 1)[0]
        return any(name.startswith(prefix + ":") or name == prefix
                   for name in installed_set)

    catalog = _model_catalog()

    def _models_for(mode_key: str, default_tag: str) -> list:
        """Build the candidate list dict for a mode."""
        cands = catalog.get(mode_key, [])
        out = []
        for tag, weight in cands:
            out.append({
                "tag":       tag,
                "weight":    weight,
                "installed": _mark(tag),
                "default":   tag == default_tag,
            })
        return out

    # `label_key` / `desc_key` follow the i18n contract used elsewhere
    # in the admin UI (LLM_TASK_TYPES, PROTECTED_CANDIDATES, Feature,
    # CAPABILITIES, TRAITS — PR #393/#394/#395/#396/#397 series).
    # frontend chat.js binds via data-i18n and falls back to label/desc
    # on i18n table miss.
    options = [
        {"key": "auto",     "label": "🤖 자동",
         "label_key": "mode.auto",
         "desc": "질문 의도를 자동 분류 (기본)",
         "desc_key": "mode.auto_desc",
         "keywords": [],
         "model": "", "installed": True, "models": []},
        {"key": "chat",     "label": "💬 일상 대화",
         "label_key": "mode.chat",
         "desc": "검색 없이 LLM 직답",
         "desc_key": "mode.chat_desc",
         "keywords": ["안녕", "고마워", "hi", "hello"],
         "model": GEMMA_MODEL, "installed": _mark(GEMMA_MODEL),
         "models": _models_for("chat", GEMMA_MODEL)},
        {"key": "retrieval","label": "🔍 자료 검색",
         "label_key": "mode.retrieval",
         "desc": "내부 wiki + 그래프 추론",
         "desc_key": "mode.retrieval_desc",
         "keywords": ["뭐야", "무엇", "설명", "알려줘", "what is"],
         "model": GEMMA_MODEL, "installed": _mark(GEMMA_MODEL),
         "models": _models_for("retrieval", GEMMA_MODEL)},
        {"key": "meta",     "label": "📚 자료 목록",
         "label_key": "mode.meta",
         "desc": "보유 wiki 인벤토리 (LLM 미사용)",
         "desc_key": "mode.meta_desc",
         "keywords": ["목록", "리스트", "어떤 자료", "list"],
         "model": "", "installed": True, "models": []},
        {"key": "coding",   "label": "💻 코딩",
         "label_key": "mode.coding",
         "desc": "코딩 특화 모델",
         "desc_key": "mode.coding_desc",
         "keywords": ["코드", "함수", "버그", "python", "def ",
                      "javascript", "code", "function"],
         "model": CODING_MODEL, "installed": _mark(CODING_MODEL),
         "models": _models_for("coding", CODING_MODEL)},
        {"key": "wiki_edit","label": "✏️ Wiki 편집 (admin)",
         "label_key": "mode.wiki_edit",
         "desc": "지식 추가/수정/삭제",
         "desc_key": "mode.wiki_edit_desc",
         "keywords": ["수정해", "추가해", "삭제해"],
         "model": GEMMA_MODEL, "installed": _mark(GEMMA_MODEL),
         "models": _models_for("wiki_edit", GEMMA_MODEL)},
        {"key": "self_evolve","label": "🧬 자기진화 (admin)",
         "label_key": "mode.self_evolve",
         "desc": "코드 분석 / 자기 개선",
         "desc_key": "mode.self_evolve_desc",
         "keywords": ["네 코드", "구조 분석", "스스로"],
         "model": GEMMA_MODEL, "installed": _mark(GEMMA_MODEL),
         "models": _models_for("self_evolve", GEMMA_MODEL)},
    ]
    # auto는 항상 허용. 나머지는 role 권한 확인.
    filtered = [o for o in options if o["key"] == "auto" or o["key"] in allowed]
    return {"modes": filtered, "role": role}

@router.post("/llm/install/", summary="Ollama 모델 설치 (admin) [item #6 + #A8-8]")
async def llm_install(api_key: str, model: str,
                      role: str = Depends(get_role_from_request)):
    """Trigger `ollama pull <model>` via Ollama's HTTP streaming API
    in a background thread. Returns immediately so the admin page can
    show a progress bar while the multi-GB download runs.

    Admin-gated. Model name validated against catalog allowlist.

    [#A8-8 2026-05-09] Replaced subprocess.Popen with HTTP streaming —
    the CLI fire-and-forget had no progress visibility. Now the
    background thread parses Ollama's NDJSON pull stream and writes
    {percent, completed, total, status} to _install_progress[model],
    which the admin UI polls.
    """
    _require_feature(api_key, role, "admin.settings")
    ALLOWED_MODELS = _allowed_install_models() | {"llava:13b"}
    if model not in ALLOWED_MODELS:
        raise HTTPException(
            status_code=400,
            detail="model not in allowlist. Use admin /admin/llm/install for arbitrary models.",
        )
    # Reset any prior progress entry so the polling client gets fresh state.
    _install_progress[model] = {
        "status":    "starting",
        "completed": None,
        "total":     None,
        "percent":   0.0,
        "error":     "",
        "done":      False,
    }
    try:
        _start_install_with_progress(model)
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="ollama API에 접근할 수 없습니다 (localhost:11434). ollama 서비스가 실행 중인지 확인.",
        )
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"install 시작 실패: {type(e).__name__}: {e}")
    return {"ok": True, "model": model,
            "message": f"{model} 설치 시작됨. 진행 상황은 admin 페이지 또는 "
                       f"GET /admin/llm/install-progress?model={model} 로 확인."}

@router.get("/admin/llm/install-progress", summary="모델 설치 진행률 [item #A8-8]")
async def llm_install_progress(api_key: str, model: str,
                                role: str = Depends(get_role_from_request)):
    """Frontend polls this every 2-3s while the install button is in
    progress mode. Returns the latest snapshot of the background
    thread's progress dict, or {status: 'idle'} if no install is/was
    running for this model.

    Response shape:
      {status, percent, completed, total, done, error, model}
    """
    _require_feature(api_key, role, "admin.settings")
    snap = _install_progress.get(model)
    if not snap:
        return {"model": model, "status": "idle",
                "percent": None, "completed": None, "total": None,
                "done": False, "error": ""}
    return {"model": model, **snap}

@router.get("/admin/llm/installed", summary="설치된 Ollama 모델 목록 [4-B]")
async def llm_installed(api_key: str, role: str = Depends(get_role_from_request)):
    """현재 Ollama에 설치된 모델 목록."""
    _require_feature(api_key, role, "admin.settings")
    try:
        import urllib.request, json as _json
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            data = _json.loads(r.read())
        models = [
            {
                "name":     m.get("name",""),
                "size_gb":  round(m.get("size",0) / 1e9, 1),
                "modified": m.get("modified_at","")[:10],
            }
            for m in data.get("models", [])
        ]
        return {"ok": True, "models": models, "count": len(models)}
    except Exception as e:
        return {"ok": False, "models": [], "error": str(e),
                "hint": "Ollama가 실행 중인지 확인하세요 (ollama serve)"}

@router.get("/llm/active",
         summary="현재 chat 모델 indicator [v0.4 Sprint 2 #3a]")
async def llm_active(api_key: str, _role: str = Depends(get_role_from_request)):
    """[v0.4 Sprint 2 #3a] Lightweight public-ish resolver snapshot
    for the chat-header indicator chip.

    Differs from /admin/llm/resolution: api_key check only (no
    admin.settings feature gate), and returns just `chat` mode +
    omits `fallback_chain` / `installed` / `preference` (already
    surfaced in admin). Chat users on any role see which model is
    actually serving their requests right now.

    Returned shape:
      {"tag": str, "source": str, "warning": str}
    """
    verify_api_key(api_key)
    from core.model_resolver import resolve_chat
    r = resolve_chat()
    return {"tag": r.tag, "source": r.source, "warning": r.warning}

@router.get("/admin/llm/resolution",
         summary="현재 모델 resolution 상태 [PR plan-1, 2026-05-09]")
async def llm_resolution(api_key: str, role: str = Depends(get_role_from_request)):
    """[PR plan-1] 운영자 가시성 — call_gemma(model=None)이 어떤 모델을
    실제 사용하는지 + 폴백 사유.

    설치된 모델이 config의 default와 다를 때 어디로 fallback 됐는지
    감지하기 위함. resolver는 silent하게 동작하지만 결정 사유는 여기서
    조회 가능.

    Returned shape:
      {chat: {tag, source, warning, fallback_chain},
       coding: {tag, source, warning, fallback_chain},
       installed: [...],
       preference: {chat: [...], coding: [...]},
       ttl_s: 60}
    """
    _require_feature(api_key, role, "admin.settings")
    from core.model_resolver import resolution_snapshot
    return resolution_snapshot()

@router.get("/admin/llm/recommend", summary="하드웨어 기반 LLM 추천 [4-B]")
async def llm_recommend(api_key: str, role: str = Depends(get_role_from_request)):
    """현재 하드웨어 스펙에 맞는 LLM 모델 추천."""
    _require_feature(api_key, role, "admin.settings")
    try:
        from tools.system.hardware_inspector import get_hardware_specs, get_llm_recommendations
        specs = get_hardware_specs()
        recs  = get_llm_recommendations(specs)
        return {
            "ok":      True,
            "specs_summary": {
                "gpu":    f"{specs['gpu'].get('name','?')} ({specs['gpu'].get('vram_gb',0)}GB VRAM)",
                "ram":    f"{specs['ram'].get('total_gb',0)}GB RAM",
                "level":  specs.get("overall_level", 0),
            },
            "recommendations": recs,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.post("/admin/llm/pull", summary="Ollama 모델 다운로드 [4-B]")
async def llm_pull(
    api_key: str,
    model:   str,
    role: str = Depends(get_role_from_request),
):
    """Ollama 모델 pull (다운로드). 시간이 걸릴 수 있음."""
    _require_feature(api_key, role, "admin.settings")
    if not model or len(model) > 60:
        raise HTTPException(status_code=400, detail="model명 오류")
    # 보안: 허용 모델만
    from tools.system.hardware_inspector import LLM_CATALOG
    allowed = {m["tag"] for m in LLM_CATALOG}
    if model not in allowed:
        raise HTTPException(status_code=400, detail=f"허용되지 않은 모델: {model}")
    try:
        import urllib.request, json as _json
        body = _json.dumps({"name": model, "stream": False}).encode()
        req  = urllib.request.Request(
            "http://localhost:11434/api/pull",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=600) as r:
            resp = _json.loads(r.read())
        _write_audit(role, "/admin/llm/pull", query=model, elapsed_sec=0)
        return {"ok": True, "model": model, "status": resp.get("status","done")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/admin/llm/delete", summary="Ollama 모델 삭제 [4-B]")
async def llm_delete(
    api_key: str,
    model:   str,
    role: str = Depends(get_role_from_request),
):
    """Ollama 모델 삭제."""
    _require_feature(api_key, role, "admin.settings")
    try:
        import urllib.request, json as _json
        body = _json.dumps({"name": model}).encode()
        req  = urllib.request.Request(
            "http://localhost:11434/api/delete",
            data=body,
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        urllib.request.urlopen(req, timeout=10)
        # [PR plan-1] resolver cache invalidation — deleted model must
        # not be used on the next /query/.
        try:
            from core.model_resolver import invalidate_cache
            invalidate_cache()
        except Exception:
            pass
        _write_audit(role, "/admin/llm/delete", query=model, elapsed_sec=0)
        return {"ok": True, "model": model, "deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/llm/selections", summary="task별 LLM 매핑 조회 [#15]")
async def llm_selections_get(
    api_key: str,
    role: str = Depends(get_role_from_request),
):
    """현재 ``llm.selection`` 의 ``task_type → model`` 매핑 전체 반환."""
    _require_feature(api_key, role, "admin.settings")
    from llm.selection import get_all_selections
    return {"selections": get_all_selections()}

@router.post("/admin/llm/select", summary="task별 LLM 매핑 저장 [#15]")
async def llm_select_set(
    api_key:   str,
    task_type: str,
    model:     str,
    role: str = Depends(get_role_from_request),
):
    """``task_type`` 의 추론에 사용할 model을 지정. ollama에 설치된 model만 허용."""
    _require_feature(api_key, role, "admin.settings")
    task_type = (task_type or "").strip()
    model     = (model or "").strip()
    if not task_type or len(task_type) > 32:
        raise HTTPException(status_code=400, detail="task_type 필수 (1-32자)")
    if not model or len(model) > 80:
        raise HTTPException(status_code=400, detail="model 필수 (1-80자)")

    installed = _list_installed_ollama_models()
    if installed and model not in installed:
        raise HTTPException(
            status_code=400,
            detail=f"'{model}' 미설치 (ollama list 기준). /admin/llm/installed 확인.",
        )

    from llm.selection import set_model_for_task
    set_model_for_task(task_type, model)
    _write_audit(role, "/admin/llm/select", query=f"{task_type}={model}", elapsed_sec=0)
    return {"ok": True, "task_type": task_type, "model": model}

@router.delete("/admin/llm/select", summary="task별 LLM 매핑 제거 [#15]")
async def llm_select_remove(
    api_key:   str,
    task_type: str,
    role: str = Depends(get_role_from_request),
):
    """``task_type`` 매핑 제거. 기본 model로 fallback."""
    _require_feature(api_key, role, "admin.settings")
    from llm.selection import remove_model_for_task
    removed = remove_model_for_task(task_type)
    _write_audit(role, "/admin/llm/select#delete", query=task_type, elapsed_sec=0)
    return {"ok": True, "task_type": task_type, "removed": removed}
