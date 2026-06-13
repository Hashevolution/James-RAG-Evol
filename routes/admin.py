"""Remaining /admin/* routes — large grab-bag.

Extracted from server_llmwiki.py per docs/design/v0.4.x-server-split.md
PR-G. 47 endpoints + 12 Pydantic models + 4 module helpers moved
verbatim — handler body byte-identical (only ``@app.<m>`` ->
``@router.<m>``).

URL invariant: ``python scripts/audit_endpoint_paths.py origin/main``
must report 0-diff against the pre-PR-G baseline.
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from config import BASE_DIR, MAX_UPLOAD_BYTES
from core.auth import ALLOWED_ROLES
from core.policy_engine import default_engine
from routes._deps import get_file_processor, get_rag_engine
from routes._helpers import (
    _AUDIT_DB,
    _bearer_username,
    _require_admin,
    _require_feature,
    _write_audit,
    get_client_ip,
    get_role_from_request,
    verify_api_key,
)

router = APIRouter()


class _LazySingleton:
    """Lazy passthrough so handlers can keep ``rag_engine.foo`` /
    ``file_processor.foo`` syntax without an explicit shim per handler.
    Every attribute access forwards to the real singleton at call time,
    matching the routes/_deps lazy-forwarder pattern that keeps tests
    monkeypatching ``server_llmwiki.rag_engine`` transparent."""

    def __init__(self, getter):
        object.__setattr__(self, "_getter", getter)

    def __getattr__(self, name):
        return getattr(self._getter(), name)


rag_engine = _LazySingleton(get_rag_engine)
file_processor = _LazySingleton(get_file_processor)

# ─── Pydantic models + helpers ─────────────────────────────────────

class WebSearchConfigUpdate(BaseModel):
    api_key:        str
    allowed_roles:  list
    threshold:      float

async def web_search_status(api_key: str):
    """현재 활성 검색 엔진 (Tavily / DuckDuckGo) 상태 반환."""
    verify_api_key(api_key)   # api_key 검증만으로 충분 (상태 조회)
    try:
        # .env 파일이 있으면 런타임에 재로드 (환경변수 누락 방지)
        env_path = os.path.join(BASE_DIR, ".env")
        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and v and k not in os.environ:
                            os.environ[k] = v

        from tools.web.web_searcher import get_search_engine_status
        status = get_search_engine_status()
        status["env_key_set"] = bool(os.environ.get("TAVILY_API_KEY", "").strip())
        return status
    except Exception as e:
        return {
            "active_engine":    "unknown",
            "tavily_key":       bool(os.environ.get("TAVILY_API_KEY", "").strip()),
            "tavily_installed": False,
            "ddg_installed":    False,
            "error":            str(e),
        }

class TraitUpdateRequest(BaseModel):
    api_key:  str
    trait_id: str
    value:    float

def _require_graph_edit_enabled() -> None:
    from core.graph_editor import graph_edit_enabled
    if not graph_edit_enabled():
        raise HTTPException(
            status_code=403,
            detail="graph_edit_disabled: set JAMES_GRAPH_EDIT=1 to enable",
        )

def _truncate_audit_blob(d: dict, cap: int = 500) -> str:
    """audit log 의 query/answer 컬럼은 500 chars cap. sources before/
    after 가 길어질 수 있으므로 JSON dump 후 잘림."""
    s = json.dumps(d, ensure_ascii=False)
    return s if len(s) <= cap else s[:cap - 3] + "..."

_AUDIT_CATEGORIES = {
    "user_mgmt": ("/admin/users/",),
    "password":  ("/password/", "/signup/"),
    "api_keys":  ("/api-keys/",),
    "auth":      ("/login/",),
    "query":     ("/query/", "/upload/"),
    "tools":     ("tool:",),
    "attack":    ("attack:",),
    "system":    ("system:",),
}

class FeatureOverrideRequest(BaseModel):
    feature_id: str
    role:       str
    allowed:    bool

class FeatureResetRequest(BaseModel):
    feature_id: str
    # role 이 명시되면 그 한 행만 reset, 비어있으면 feature 전체 reset
    role:       Optional[str] = None

def _file_mgmt_roots() -> dict:
    from config import BASE_DIR, WIKI_DIR, UPLOAD_DIR
    media = os.path.join(BASE_DIR, "media")
    return {
        "wiki":    os.path.abspath(WIKI_DIR),
        "uploads": os.path.abspath(UPLOAD_DIR),
        "media":   os.path.abspath(media),
    }

_FILE_DOWNLOAD_ALLOWED_EXTS = (
    ".md", ".txt", ".pdf", ".docx", ".doc", ".xlsx", ".xls",
    ".pptx", ".ppt", ".csv", ".html", ".htm", ".json", ".yaml", ".yml",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff",
    ".mp4", ".avi", ".mov", ".mkv", ".webm",
    ".mp3", ".wav", ".m4a", ".aac", ".flac",
    ".hwpx", ".hwp",
)

def _resolve_under_root(root_key: str, rel_path: str) -> str:
    """Validate (root_key, rel_path) → safe absolute path.

    Returns the absolute path or raises HTTPException 400 on:
      - unknown root_key
      - rel_path that escapes the root (.. traversal, drive letters,
        UNC paths, symlinks pointing outside)

    `os.path.realpath` follows symlinks, so a malicious symlink under
    the root that points to /etc/passwd is caught.
    """
    roots = _file_mgmt_roots()
    if root_key not in roots:
        raise HTTPException(status_code=400, detail="invalid root")
    root = roots[root_key]
    if not os.path.isdir(root):
        # Not yet created (e.g. media/) — return root anyway, callers
        # will produce empty listings.
        return root if not (rel_path or "").strip() else None
    rel = (rel_path or "").lstrip("/\\").strip()
    candidate = os.path.realpath(os.path.join(root, rel))
    # Final containment check.
    if not candidate.startswith(root + os.sep) and candidate != root:
        raise HTTPException(status_code=400, detail="path escapes root")
    return candidate

_FILE_VIEW_TEXT_EXTS = frozenset({
    ".md", ".txt", ".json", ".yaml", ".yml", ".csv",
    ".jsonl", ".log", ".tsv",
})

class PersonaRequest(BaseModel):
    api_key:  str
    name:     str = ""
    style:    str = ""
    language: str = ""
    custom:   str = ""

class AdminSettingsRequest(BaseModel):
    api_key:         str
    model:           str = ""
    max_loop:        int = 2
    protected_files: str = ""

class CognitiveFlagsRequest(BaseModel):
    api_key: str
    flags:   dict = {}   # {flag_key: bool, ...}

from core import change_request as _cr_mod
from core import change_request_apply as _cr_apply

class _CrProposeRequest(BaseModel):
    api_key:       str
    target_type:   str
    target_id:     str
    title:         str
    description:   str = ""
    proposed_diff: dict   # JSON-serialisable; structure is target_type-specific
    base_hash:     str
    labels:        list[str] = []

class _CrApproveRequest(BaseModel):
    api_key: str

class _CrRejectRequest(BaseModel):
    api_key: str
    reason:  str = ""

class _CrReviewRequest(BaseModel):
    api_key:  str
    decision: str            # "approve" / "request_changes" / "comment"
    body:     str = ""

def _cr_as_dict(cr) -> dict:
    """Shape a ChangeRequest dataclass for JSON output. Mirrors the
    table columns 1:1 so the UI can render without remapping."""
    return {
        "cr_id":         cr.cr_id,
        "target_type":   cr.target_type,
        "target_id":     cr.target_id,
        "title":         cr.title,
        "description":   cr.description,
        "proposed_diff": cr.proposed_diff,
        "base_hash":     cr.base_hash,
        "proposer":      cr.proposer,
        "status":        cr.status,
        "labels":        cr.labels,
        "created_at":    cr.created_at,
        "updated_at":    cr.updated_at,
        "merged_at":     cr.merged_at,
        "merged_by":     cr.merged_by,
        "reject_reason": cr.reject_reason,
    }

def _review_as_dict(rv) -> dict:
    return {
        "review_id":  rv.review_id,
        "cr_id":      rv.cr_id,
        "reviewer":   rv.reviewer,
        "decision":   rv.decision,
        "body":       rv.body,
        "created_at": rv.created_at,
    }

# ─── Endpoints ─────────────────────────────────────────────────────

@router.get("/admin/web-search-status", summary="웹 검색 엔진 상태 [3-E]")

# ── [4-B] Ollama + LLM 추천 API ──────────────────────────────────

# item #A2: 모드별 선택 가능한 모델 카탈로그.
#   - chat/retrieval/wiki_edit/self_evolve: 일반 대화/추론 (gemma 계열)
#     무게: light (e4b) → medium (12b) → heavy (27b)
#   - coding: 코딩 특화 (qwen-coder 계열) + gemma fallback
# 사용자가 mode 선택 시 두 번째 dropdown으로 후보 중 골라 사용.
# 설치되지 않은 후보는 그대로 노출하되 [⚠️ 미설치] 마커 + 설치 버튼.
# weight 분류는 어림짐작 (실제 파라미터 수가 아닌 *체감* 무게):
#   light  ≤ 4B  — 빠른 일상 대화
#   medium ≤ 13B — 균형, 분석 가능
#   heavy  ≥ 20B — 상세 분석/추론, 응답 느림

# /llm/install/ allowlist auto-derived from catalog so adding a candidate
# above does NOT also require remembering to update the install gate.























# ─── [#A6-1] Web search admin config — role permission + threshold ───

@router.get("/admin/web-search-config/", summary="웹 검색 설정 조회 [#A6-1]")
async def get_web_search_config(api_key: str,
                                 role: str = Depends(get_role_from_request)):
    """[#A6-1] Admin reads:
       - allowed_roles: which roles can trigger web search
       - threshold: unified_score below which web fallback fires
       - engine_status: live key/installed/exhausted state from
                        get_search_engine_status() so the admin UI
                        can render the right toast (TAVILY missing,
                        DDG fallback active, both missing, etc.)
    """
    _require_feature(api_key, role, "admin.settings")
    from core.web_search_config import load
    from tools.web.web_searcher import get_search_engine_status
    cfg = load()
    return {
        **cfg,
        "engine_status": get_search_engine_status(),
    }

@router.post("/admin/web-search-config/", summary="웹 검색 설정 갱신 [#A6-1]")
async def set_web_search_config(data: WebSearchConfigUpdate,
                                 role: str = Depends(get_role_from_request)):
    """Persist web-search settings. Validates role names against
    core.web_search_config.VALID_ROLES and threshold ∈ [0.0, 1.0].
    Empty allowed_roles is rejected — silently disabling web search
    is rarely the intent and harder to debug later (operator can
    clear TAVILY_API_KEY instead if they really want it off)."""
    _require_feature(data.api_key, role, "admin.settings")
    from core.web_search_config import save, validate_update
    clean_roles, clean_threshold, err = validate_update(
        data.allowed_roles, data.threshold,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    cfg = save(clean_roles, clean_threshold)
    _write_audit(role, "/admin/web-search-config/",
                 query=f"roles={clean_roles} threshold={clean_threshold}")
    return {"ok": True, **cfg}

@router.get("/admin/performance/metrics/", summary="실시간 성능 지표 [P8-EVAL]")
async def get_perf_metrics(
    api_key: str, role: str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.metrics")
    try:
        from tools.self.performance_evaluator import get_current_metrics
        from tools.self.importance_scorer import get_scorer_stats
        return {"performance": get_current_metrics(),
                "importance":  get_scorer_stats()}
    except Exception as e:
        return {"error": str(e)}

@router.post("/admin/performance/evaluate/", summary="수동 자기 채점 [P8-EVAL]")
async def manual_evaluate(
    api_key: str, role: str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.evolution")
    try:
        from tools.self.performance_evaluator import run_evaluation
        return run_evaluation()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/performance/history/", summary="평가 이력 [P8-EVAL]")
async def get_perf_history(
    api_key: str, limit: int = 20,
    role: str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.evolution")
    try:
        from tools.self.performance_evaluator import get_eval_history
        return {"history": get_eval_history(limit)}
    except Exception as e:
        return {"history": [], "error": str(e)}

@router.get("/admin/character/", summary="성향 조회 [P7-EVO-D]")
async def get_character(api_key: str, role: str = Depends(get_role_from_request)):
    _require_feature(api_key, role, "admin.character")
    try:
        # [P5c 2026-05-10] summary 필드 추가 — 16 trait 자연어 요약
        # (핵심/가치/스타일 3 라인). 프론트는 동일 룰의 JS 미러를 가지므로
        # 이 필드는 chat 등 다른 페이지가 같은 요약을 재사용할 수 있게
        # 노출하는 server-side 단일 소스 역할.
        from core.character_profile import get_profile, CharacterProfile
        profile = get_profile()
        return {
            "traits":  profile.get_with_meta(),
            "summary": CharacterProfile.build_summary(profile.get()),
        }
    except Exception as e:
        return {"traits": [], "error": str(e)}

@router.post("/admin/character/", summary="성향 설정 [P7-EVO-D]")
async def set_character(data: TraitUpdateRequest,
                         role: str = Depends(get_role_from_request)):
    _require_feature(data.api_key, role, "admin.character")
    try:
        from core.character_profile import get_profile
        result = get_profile().set_trait(data.trait_id, data.value)
        _write_audit(role, "/admin/character/",
                     query=f"{data.trait_id}={data.value}")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/character/correlations",
         summary="성향 상관관계 그래프 [P1 unified UX]")
async def get_character_correlations(api_key: str,
                                      role: str = Depends(get_role_from_request)):
    _require_feature(api_key, role, "admin.character")
    try:
        from core.character_profile import CharacterProfile
        return {
            "correlations": CharacterProfile.get_correlations(),
            "damping":      CharacterProfile.get_damping(),
        }
    except Exception as e:
        return {"correlations": [], "damping": 0.0, "error": str(e)}

@router.get("/admin/knowledge/", summary="능력 성장 현황 [P7-EVO-E]")
async def get_knowledge(api_key: str, role: str = Depends(get_role_from_request)):
    _require_feature(api_key, role, "admin.knowledge")
    try:
        from core.knowledge_tracker import get_tracker
        t = get_tracker()
        return {
            "domains":      t.get_domain_levels(),
            "capabilities": t.get_capabilities(),
            "recent_gains": t.get_recent_gains(),
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/admin/dashboard", summary="관리자 대시보드 [P7]")
async def admin_dashboard(api_key: str, role: str = Depends(get_role_from_request)):
    _require_feature(api_key, role, "admin.metrics")

    # ── 기본 카운트 ──────────────────────────────────────────
    try:    entity_count = len(rag_engine.wiki_generator.entity_id_index)
    except: entity_count = 0
    try:
        from core.auth import list_users
        user_count = len(list_users())
    except: user_count = 0

    # [Phase 4a] tool / attack 스트림 → SQLite audit_log 직접 조회.
    # 이전: james_attack_log.jsonl + james_audit_tool.jsonl 의 tail
    # 200줄을 8KB 청크 역방향 read 로 합쳤음. Phase 1+2 의 mirror 가
    # audit_log 에 tool:* / attack:* prefix 로 동일 데이터를 갖고 있어
    # ORDER BY id DESC LIMIT 200 한 번이면 됨. 인덱스 없는 단일 SELECT
    # 라도 SQLite 가 JSONL 역방향 청크보다 일관되게 빠름.
    security_events, recent_logs = 0, []
    try:
        conn = sqlite3.connect(_AUDIT_DB, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT timestamp, endpoint, user_role, query, "
            " security_event, blocked "
            "FROM audit_log "
            "WHERE endpoint LIKE 'tool:%' OR endpoint LIKE 'attack:%' "
            "ORDER BY id DESC LIMIT 200"
        ).fetchall()
        conn.close()
        for r in rows:
            ev = r["security_event"] or ""
            recent_logs.append({
                "time":    r["timestamp"],
                "event":   ev,
                "role":    r["user_role"],
                "blocked": bool(r["blocked"]),
                "detail":  (r["query"] or "")[:200],
            })
            if r["blocked"] or "BLOCK" in ev:
                security_events += 1
        # Match prior oldest-first ordering for the dashboard widget.
        recent_logs.reverse()
    except Exception:
        # audit_log 읽기 실패 시 dashboard 자체는 계속 동작.
        pass

    try:
        from tools.patch.patch_generator import list_patches
        pending_patches = len(list_patches("PENDING_APPROVAL"))
    except: pending_patches = 0
    try:
        from core.memory import MemoryStore
        stats = MemoryStore().get_stats()
        memory_count = sum(v for v in stats.values() if isinstance(v, int))
    except: memory_count = 0

    # ── [3-A] audit_log 기반 실시간 통계 ────────────────────
    today_queries   = 0
    avg_elapsed     = 0.0
    blocked_count   = 0
    elapsed_list    = []   # 응답 시간 그래프용
    recent_queries  = []   # 최근 쿼리 목록용

    try:
        from datetime import date as _date
        today_str = _date.today().isoformat()
        conn = sqlite3.connect(_AUDIT_DB, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM audit_log "
            "WHERE endpoint='/query/' "
            "ORDER BY id DESC LIMIT 200"
        ).fetchall()
        conn.close()

        for row in rows:
            ts = (row["timestamp"] or "")[:10]
            if ts == today_str:
                today_queries += 1
            if row["elapsed_sec"]:
                elapsed_list.append(round(row["elapsed_sec"], 2))
            if row["blocked"]:
                blocked_count += 1
            if row["query"]:
                recent_queries.append({
                    "q":       (row["query"] or "")[:50],
                    "mode":    "",
                    "elapsed": row["elapsed_sec"],
                    "blocked": bool(row["blocked"]),
                    "ts":      row["timestamp"],
                })

        if elapsed_list:
            avg_elapsed = round(sum(elapsed_list) / len(elapsed_list), 2)
        # 응답 시간 그래프: 최근 20회 (시간순)
        elapsed_chart = list(reversed(elapsed_list[:20]))

    except Exception:
        elapsed_chart = []

    return {
        # 기존
        "entity_count":    entity_count,
        "user_count":      user_count,
        "security_events": security_events + blocked_count,
        "pending_patches": pending_patches,
        "memory_count":    memory_count,
        "diag_score":      100,
        "recent_logs":     recent_logs[-20:],
        # [3-A] 신규 실시간 통계
        "today_queries":   today_queries,
        "avg_elapsed":     avg_elapsed,
        "blocked_count":   blocked_count,
        "elapsed_chart":   elapsed_chart,       # 최근 20회 응답 시간
        "recent_queries":  recent_queries[:10], # 최근 10개 쿼리
        "vector_count":    rag_engine.vector_store.count(),
    }

@router.get("/admin/entities", summary="Entity 현황 — search + paging [item #1]")
async def admin_entities(
    api_key: str,
    q:       str = "",
    etype:   str = "",
    limit:   int = 100,
    offset:  int = 0,
    role:    str = Depends(get_role_from_request),
):
    """Entity inventory list.

    Query params (all optional):
      q       — substring filter on name + entity_id (case-insensitive)
      etype   — exact match on entity_type (e.g. concept / org / person)
      limit   — max rows returned (default 100, hard cap 500)
      offset  — paging offset (default 0)

    `type_counts` is computed over the FULL index (not the filtered slice)
    so the operator always sees corpus-wide totals. `total` is the count
    AFTER filters are applied; `total_all` is the unfiltered count.
    """
    _require_feature(api_key, role, "admin.data")
    from pathlib import Path

    # Clamp limit defensively — 500 covers any realistic v0.2 wiki.
    limit  = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    q_norm = (q or "").strip().lower()
    et_norm = (etype or "").strip().lower()

    entity_index = rag_engine.wiki_generator.entity_id_index
    type_counts: dict[str, int] = {}
    matched: list[dict] = []

    for eid, fpath in entity_index.items():
        try:
            fm = rag_engine.wiki_generator._read_frontmatter(Path(fpath))
            if not fm:
                continue
            etype_v = fm.get("entity_type", fm.get("type", "unknown"))
            type_counts[etype_v] = type_counts.get(etype_v, 0) + 1

            # Apply filters AFTER counting (counts reflect the full corpus).
            if et_norm and etype_v.lower() != et_norm:
                continue
            name = fm.get("name", "") or ""
            if q_norm and q_norm not in name.lower() and q_norm not in eid.lower():
                continue

            matched.append({
                "entity_id":      eid,
                "name":           name,
                "entity_type":    etype_v,
                "sensitivity":    fm.get("sensitivity", "internal"),
                "relation_count": len(fm.get("relations", [])),
            })
        except Exception:
            pass

    # Newest-name-first sort for stable paging UX.
    matched.sort(key=lambda e: (e["name"] or "").lower())
    sliced = matched[offset:offset + limit]

    return {
        "entities":   sliced,
        "type_counts": type_counts,
        "total":      len(matched),         # post-filter count
        "total_all":  len(entity_index),    # corpus-wide
        "limit":      limit,
        "offset":     offset,
        "filters":    {"q": q, "etype": etype},
    }

@router.get("/admin/entities/{entity_id}", summary="Entity 상세 [item #1]")
async def admin_entity_detail(
    entity_id: str,
    api_key:   str,
    role:      str = Depends(get_role_from_request),
):
    """One entity's full frontmatter + body + neighbor names.

    Used by the admin entities page click-to-expand modal so the
    operator can audit a wiki row without leaving the admin UI.
    """
    _require_feature(api_key, role, "admin.data")
    from pathlib import Path

    fpath = rag_engine.wiki_generator.entity_id_index.get(entity_id)
    if not fpath:
        raise HTTPException(status_code=404,
                            detail=f"entity not found: {entity_id}")

    p = Path(fpath)
    if not p.exists():
        raise HTTPException(status_code=404,
                            detail=f"entity file missing on disk: {fpath}")

    fm = rag_engine.wiki_generator._read_frontmatter(p) or {}
    raw = p.read_text(encoding="utf-8", errors="replace")
    # Body = everything after the second `---` frontmatter delimiter.
    parts = raw.split("---", 2)
    body = parts[2].strip() if len(parts) >= 3 else raw

    return {
        "entity_id":   entity_id,
        "name":        fm.get("name", ""),
        "entity_type": fm.get("entity_type", fm.get("type", "unknown")),
        "sensitivity": fm.get("sensitivity", "internal"),
        "frontmatter": fm,
        "relations":   fm.get("relations", []),
        "body":        body[:10000],   # safety cap on rendering
        "path":        str(p),
    }

@router.post("/admin/wiki/resolve-relations",
          summary="Wiki UNRESOLVED relation grand sweep [v0.3 사이클 6]")
async def admin_wiki_resolve_relations(
    api_key:     str,
    source_type: str = "prod",
    role:        str = Depends(get_role_from_request),
):
    """Run WikiGenerator.resolve_pending_relations() across the wiki to
    fill in any leftover ``target_id: UNRESOLVED`` rows in frontmatter
    relations. PR #253 wires the resolver into every ingest path; this
    endpoint exposes the same primitive as a manual grand sweep for
    operators after migrations, bulk imports, or hand edits to wiki
    files that introduce new entities the existing relations could now
    point at. Returns the count of resolved relations (0 if everything
    was already linked).
    """
    _require_feature(api_key, role, "admin.data")

    src = (source_type or "prod").strip().lower()
    if src not in ("prod", "test"):
        src = "prod"

    if src == rag_engine.wiki_generator.source_type:
        gen = rag_engine.wiki_generator
    else:
        from core.wiki_generator import WikiGenerator
        gen = WikiGenerator(source_type=src)

    relations_fixed = gen.resolve_pending_relations()

    return {
        "resolved":    relations_fixed,
        "source_type": src,
    }

@router.get(
    "/admin/graph/last-change",
    summary="Most recent lifecycle event for the 'Undo recent change' UI [v0.6 Phase 4 P4.2]",
)
async def admin_graph_last_change(
    api_key:   str,
    tenant_id: Optional[str] = None,
    role:      str = Depends(get_role_from_request),
):
    """Returns metadata for the most recent lifecycle event in the
    audit_log — the data the non-developer operator's "Undo recent
    change" affordance shows in its confirmation modal.

    Empty audit log → ``{"ok": true, "no_changes": true}`` (the safe
    "nothing to undo" branch the UI handles).

    Non-empty audit log → ``{"ok": true, "no_changes": false,
    "event_type": "...", "event_payload": {...},
    "timestamp": "...", "audit_row_id": N}``.

    Honest scoping: this endpoint is a READ over the audit log. The
    actual graph-state rollback is gated on T5.A.b mutation-site
    wiring (deferred from v0.4.2). Until that wiring lands, the UI
    can SHOW what was last changed + record operator intent (via
    ``/admin/graph/log-rollback-intent``) — actual graph mutation is
    a follow-up cycle.
    """
    _require_feature(api_key, role, "admin.data")

    import sqlite3 as _sql
    try:
        conn = _sql.connect(_AUDIT_DB)
    except Exception:
        return {"ok": True, "no_changes": True}
    try:
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(audit_log)"
        ).fetchall()}
        if "event_type" not in cols or "event_payload" not in cols:
            return {"ok": True, "no_changes": True}
        where = "event_type IS NOT NULL"
        params: tuple = ()
        if tenant_id:
            # Post-parse filter is the safer pattern (matches G1.b
            # strict-exclusion semantic), but for the "last change"
            # query we use a SQL LIKE pre-filter to avoid a full
            # table scan. Both yield the same row on a well-formed
            # payload.
            where += " AND event_payload LIKE ?"
            params = ('%"tenant_id":' + json.dumps(tenant_id) + '%',)
        row = conn.execute(
            "SELECT id, timestamp, event_type, event_payload "
            f"FROM audit_log WHERE {where} "
            "ORDER BY id DESC LIMIT 1",
            params,
        ).fetchone()
    except Exception:
        return {"ok": True, "no_changes": True}
    finally:
        try: conn.close()
        except Exception: pass

    if not row:
        return {"ok": True, "no_changes": True}

    rid, ts, etype, epayload = row
    try:
        parsed = json.loads(epayload) if epayload else {}
    except Exception:
        parsed = {}
    return {
        "ok":            True,
        "no_changes":    False,
        "audit_row_id":  rid,
        "timestamp":     ts,
        "event_type":    etype,
        "event_payload": parsed,
    }


class _RollbackIntentRequest(BaseModel):
    api_key:  str
    scope:    str           # "last" | "since"
    target_t: Optional[str] = None   # ISO-8601 for scope="since"
    note:     str           = ""     # operator's reason for the rollback


@router.post(
    "/admin/graph/log-rollback-intent",
    summary="Record an operator rollback intent in audit log [v0.6 Phase 4 P4.2]",
)
async def admin_graph_log_rollback_intent(
    body: _RollbackIntentRequest,
    role: str = Depends(get_role_from_request),
):
    """Records the operator's rollback intent in the audit log.

    Two scopes:

      * ``scope=last`` — "undo the most recent change". UI calls
        ``GET /admin/graph/last-change`` first to surface what's
        about to be undone, then POSTs this with the operator's
        confirmation note.
      * ``scope=since`` — "restore the state at time T". UI calls
        ``GET /admin/graph/diff-vs-now?t=...`` first to surface the
        diff, then POSTs this with ``target_t`` set.

    The endpoint writes a single audit row with
    ``endpoint=/admin/graph/log-rollback-intent`` +
    ``security_event=rollback_intent scope=... target=... by=...`` +
    ``query=<operator note>``. The row makes the operator's
    intent forensically attestable.

    Honest scoping (v0.6 Phase 4): this endpoint records the intent
    but does NOT yet mutate the graph state. T5.A.b mutation-site
    wiring + an inverse-event emission helper land in a follow-up
    cycle; until then, the UI surfaces the operator's intent to
    auditors, but the graph state continues forward through the
    standard ingestion + supersede path. The audit row is the
    permanent record of "operator wanted to roll back at this time
    for this reason."

    The response carries ``audit_row_id`` so the UI can show the
    operator "Your rollback intent has been recorded as audit row
    #N." Auditors can later pull the row via
    ``/admin/audit/list?q=rollback_intent``.
    """
    _require_feature(body.api_key, role, "admin.data")

    scope = (body.scope or "").strip().lower()
    if scope not in ("last", "since"):
        raise HTTPException(
            status_code=400,
            detail="scope must be 'last' or 'since'",
        )
    if scope == "since":
        if not body.target_t or not body.target_t.strip():
            raise HTTPException(
                status_code=400,
                detail="target_t is required when scope='since'",
            )
        try:
            from datetime import datetime as _dt
            _dt.fromisoformat(body.target_t.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="target_t must be an ISO-8601 timestamp",
            )

    # Resolve operator identity via G2.a approval-evidence (or POSIX
    # floor when no IdP is configured). The audit row records WHO
    # initiated the rollback intent, which is the forensic
    # attestability point this endpoint exists for.
    operator_principal = "unknown"
    try:
        from core.security.approval_evidence import current_approval_evidence
        ev = current_approval_evidence()
        if ev is not None and getattr(ev, "principal", None):
            operator_principal = ev.principal
    except Exception:
        pass

    scope_target = body.target_t if scope == "since" else "(most-recent)"
    sec_event = (
        f"rollback_intent scope={scope} target={scope_target} "
        f"by={operator_principal}"
    )

    _write_audit(
        user_role=role,
        endpoint="/admin/graph/log-rollback-intent",
        query=_truncate_audit_blob({
            "scope":            scope,
            "target_t":         body.target_t,
            "operator_note":    body.note,
            "operator_principal": operator_principal,
        }),
        security_event=sec_event,
    )

    # Look up the audit row id we just wrote so the UI can echo it.
    import sqlite3 as _sql
    audit_row_id: Optional[int] = None
    try:
        conn = _sql.connect(_AUDIT_DB)
        cur = conn.execute(
            "SELECT id FROM audit_log "
            "WHERE endpoint=? ORDER BY id DESC LIMIT 1",
            ("/admin/graph/log-rollback-intent",),
        )
        row = cur.fetchone()
        if row:
            audit_row_id = row[0]
    except Exception:
        pass
    finally:
        try: conn.close()
        except Exception: pass

    return {
        "ok":                  True,
        "scope":               scope,
        "target_t":            body.target_t,
        "operator_principal":  operator_principal,
        "audit_row_id":        audit_row_id,
        "graph_mutation_applied": False,
        "graph_mutation_pending": True,
        "note": (
            "Intent recorded. Graph state mutation is gated on T5.A.b "
            "mutation-site wiring (deferred from v0.4.2); the audit "
            "row preserves the operator's rollback intent for "
            "forensic review until that wiring lands."
        ),
    }


@router.get("/admin/graph/snapshot", summary="Reasoning graph snapshot — nodes + edges [v0.2 Axis 3]")
async def admin_graph_snapshot(
    api_key:           str,
    source_type:       str  = "prod",
    include_sensitive: int  = 0,
    role:              str  = Depends(get_role_from_request),
):
    """Read-only enumeration of every wiki entity + ontology edge for
    the /admin/graph 3D visualizer. Admin-only; sensitive nodes/edges
    are dropped by default and require an explicit elevated role to
    surface (which v0.2 doesn't yet have — kept off for now).
    """
    _require_feature(api_key, role, "admin.data")
    from core.graph_snapshot import build_snapshot

    src = (source_type or "prod").strip().lower()
    if src not in ("prod", "test"):
        src = "prod"

    # v0.2: even admin cannot opt into sensitive — locked off until a
    # dedicated elevated role lands. Re-enable here when that role exists.
    include_sens = False
    _ = include_sensitive  # acknowledged but ignored at this gate

    # The shared engine's WikiGenerator is bound to its own source_type
    # at construction, so for cross-source viewing we instantiate a
    # fresh, scoped generator on demand.
    if src == rag_engine.wiki_generator.source_type:
        gen = rag_engine.wiki_generator
    else:
        from core.wiki_generator import WikiGenerator
        gen = WikiGenerator(source_type=src)

    return build_snapshot(
        wiki_generator    = gen,
        source_type       = src,
        include_sensitive = include_sens,
    )

@router.get(
    "/admin/graph/reconstruct-at",
    summary="Audit-only graph state at time T [v0.5 Track F.1 TT.b]",
)
async def admin_graph_reconstruct_at(
    api_key:   str,
    t:         str,
    limit:     int = 1000,
    tenant_id: Optional[str] = None,
    role:      str = Depends(get_role_from_request),
):
    """Replay the lifecycle event stream up to time ``t`` and return the
    resulting :class:`core.lifecycle.replay_graph.GraphSnapshot` as JSON.

    Surfaces the v0.4.2 T5 ``reconstruct_graph_at`` primitive — the
    audit-only invariant (I1): the snapshot depends solely on the
    ``audit_log`` row stream, never on the live wiki. This is what the
    Time-Travel Dashboard (Track F.1 §5.6) repaints from.

    Query params:
      - ``t``: ISO-8601 cutoff timestamp. Accepts ``...Z`` (UTC) or an
        explicit offset (``+00:00``). 400 on parse failure.
      - ``limit``: maximum number of edges / chain heads to surface in
        the response (hygiene cap for very large audit logs). Default
        1000. Counts in ``event_count`` and ``invalidated_count`` are
        always full-stream and unaffected by this cap.
      - ``tenant_id``: optional v0.5 G1.b filter (strict-exclusion).
        ``None`` (default) preserves single-tenant behaviour.

    Returns:
      ``{"ok": true, "replayed_at": "<iso>", "event_count": N,
         "edges": {edge_id: {...}, ...},
         "supersede_chains": {head_id: [edge_id, ...], ...},
         "invalidated_ids": [edge_id, ...],
         "invalidated_count": N,
         "mounted_pack_ids": [pack_id, ...],
         "truncated": bool}``

      ``edges`` / ``supersede_chains`` / ``invalidated_ids`` are
      truncated to ``limit``; ``truncated`` flags whether any cap fired.

    Pure-function contract: this handler is a read-only projection of
    the audit log. No DB write, no module-state mutation, no live-wiki
    read — same audit_log + same ``t`` always returns byte-identical
    JSON.
    """
    _require_feature(api_key, role, "admin.data")

    from datetime import datetime
    from core.lifecycle.replay_graph import reconstruct_graph_at

    raw = (t or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="missing 't' query param")
    try:
        cutoff = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="'t' must be an ISO-8601 timestamp (e.g. 2026-06-13T05:00:00Z)",
        )

    cap = max(1, min(int(limit or 1000), 10000))

    snap = reconstruct_graph_at(cutoff, tenant_id=tenant_id)

    truncated = False
    edges_out: dict = {}
    for i, (eid, edge) in enumerate(snap.edges.items()):
        if i >= cap:
            truncated = True
            break
        edges_out[eid] = edge

    chains_out: dict = {}
    for i, (head_id, chain) in enumerate(snap.supersede_chains.items()):
        if i >= cap:
            truncated = True
            break
        chains_out[head_id] = list(chain)

    invalid_list = list(snap.invalidated_ids)
    invalid_count = len(invalid_list)
    if invalid_count > cap:
        truncated = True
        invalid_list = invalid_list[:cap]

    return {
        "ok":                  True,
        "replayed_at":         snap.replayed_at.isoformat(),
        "event_count":         snap.event_count,
        "edges":               edges_out,
        "supersede_chains":    chains_out,
        "invalidated_ids":     invalid_list,
        "invalidated_count":   invalid_count,
        "mounted_pack_ids":    list(snap.mounted_pack_ids),
        "truncated":           truncated,
    }

@router.get("/admin/graph/events",
         summary="event 노드 시간 윈도우 조회 [PR-11c]")
async def admin_graph_events_get(
    api_key:         str,
    source_type:     str = "prod",
    occurred_after:  Optional[str] = None,
    occurred_before: Optional[str] = None,
    role:            str = Depends(get_role_from_request),
):
    """admin 만 호출 가능. snapshot 의 event-only 슬라이스 + 선택적
    occurred_at 윈도우 필터.

    Query params:
      - ``occurred_after`` / ``occurred_before`` 둘 다 optional, ISO 8601.
        둘 다 없을 때는 source_type 의 모든 event 반환 (filter 비활성).
      - 둘 중 하나라도 있으면 non-event 는 자동 제거 (memo §5.3).

    Returns: ``{"ok": true, "events": [{node fields...}]}``.
    Order: entity_id 사전순 — caller 가 별도 정렬이 필요하면 그쪽에서.

    400 surfacing 시나리오:
      - occurred_after / occurred_before 가 ISO 8601 파싱 실패
    """
    _require_feature(api_key, role, "admin.data")
    from core.event_time_filter import filter_entities_by_time_bucket
    from core.graph_snapshot import build_snapshot

    src = (source_type or "prod").strip().lower()
    if src not in ("prod", "test"):
        src = "prod"

    if src == rag_engine.wiki_generator.source_type:
        gen = rag_engine.wiki_generator
    else:
        from core.wiki_generator import WikiGenerator
        gen = WikiGenerator(source_type=src)

    snap = build_snapshot(
        wiki_generator=gen, source_type=src, include_sensitive=False,
    )
    # snapshot 의 node 는 `occurred_at` 을 안 싣는다 (visualizer 무관).
    # 본 endpoint 는 entity_id_index 를 직접 재방문해 frontmatter 의
    # occurred_at 까지 끌어와야 한다.
    enriched = []
    for n in snap.get("nodes", []) or []:
        if n.get("type") != "event":
            continue
        eid = n.get("id")
        path = gen.entity_id_index.get(eid)
        if not path:
            continue
        try:
            fm = gen._read_frontmatter(path) or {}
        except Exception:
            fm = {}
        enriched.append({
            **n,
            "occurred_at":           fm.get("occurred_at"),
            "occurred_at_precision": fm.get("occurred_at_precision", "day"),
        })

    try:
        filtered = filter_entities_by_time_bucket(
            enriched,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    filtered.sort(key=lambda n: n.get("id", ""))
    return {"ok": True, "events": filtered}

@router.get("/admin/graph/relation",
         summary="relation 의 sources 조회 [Knowledge Cascade Phase E]")
async def admin_graph_relation_get(
    api_key:       str,
    src_entity_id: str,
    tgt_entity_id: str,
    relation_type: str,
    role:          str = Depends(get_role_from_request),
):
    """UI 의 edit modal 이 edge 클릭 시 호출. forward 측 relation 의
    sources 배열 + 기본 메타 반환. 없으면 404.
    Snapshot 에 sources 를 안 넣은 이유와 동기: payload 격리."""
    _require_graph_edit_enabled()
    _require_feature(api_key, role, "admin.data")

    from core.graph_editor import read_relation
    try:
        rel = read_relation(
            src_entity_id, tgt_entity_id, relation_type,
            wiki_generator=rag_engine.wiki_generator,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if rel is None:
        raise HTTPException(status_code=404, detail="relation not found")
    return {"ok": True, "relation": rel}

@router.put("/admin/graph/relation",
         summary="relation 의 sources 전체 교체 [Knowledge Cascade Phase E]")
async def admin_graph_relation_put(request: Request,
                                   role: str = Depends(get_role_from_request)):
    """forward + inverse 양쪽 relation 의 sources 배열을 body 의 값으로
    교체. confidence 는 자동 derive. relation 이 없으면 새로 생성.

    Body JSON:
      {
        "api_key":       "...",
        "src_entity_id": "e_org_joby",
        "tgt_entity_id": "e_org_nvidia",
        "relation_type": "RELATED_TO",
        "sources": [
          {"doc_id": null, "weight": 0.9, "role": "manual",
           "author": "admin", "note": "..."}
        ]
      }
    """
    _require_graph_edit_enabled()
    body = await request.json()
    _require_feature(body.get("api_key", ""), role, "admin.data")

    src_id = (body.get("src_entity_id") or "").strip()
    tgt_id = (body.get("tgt_entity_id") or "").strip()
    rtype  = (body.get("relation_type") or "").strip()
    if not (src_id and tgt_id and rtype):
        raise HTTPException(
            status_code=400,
            detail="src_entity_id / tgt_entity_id / relation_type required",
        )
    sources = body.get("sources") or []
    if not isinstance(sources, list) or not sources:
        raise HTTPException(
            status_code=400,
            detail="sources (non-empty list) required — use DELETE to drop",
        )

    from core.graph_editor import replace_relation_sources
    try:
        result = replace_relation_sources(
            src_id, tgt_id, rtype, sources,
            wiki_generator=rag_engine.wiki_generator,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    _write_audit(
        role, "/admin/graph/relation [PUT]",
        query=_truncate_audit_blob({
            "src": src_id, "tgt": tgt_id, "type": rtype,
        }),
        answer=_truncate_audit_blob({
            "fwd_before_n": len(result["forward"]["before"]),
            "fwd_after_n":  len(result["forward"]["after"]),
            "inv_synced":   result["inverse"] is not None,
        }),
    )
    return {"ok": True, "result": result}

@router.post("/admin/graph/relation/source",
          summary="relation 의 sources 에 한 줄 append [Knowledge Cascade Phase E]")
async def admin_graph_relation_append(request: Request,
                                      role: str = Depends(get_role_from_request)):
    """단일 source 를 forward + inverse 양쪽 relation 의 sources 배열에
    append. 다른 admin 의 PUT 과 commutative — 같은 source 를 두 번
    append 하면 두 row 모두 남는다 (dedup 은 admin 의 일).

    Body JSON:
      {
        "api_key":       "...",
        "src_entity_id": "...",
        "tgt_entity_id": "...",
        "relation_type": "RELATED_TO",
        "source": {"doc_id": null, "weight": 0.7, "role": "manual",
                   "note": "..."}
      }
    """
    _require_graph_edit_enabled()
    body = await request.json()
    _require_feature(body.get("api_key", ""), role, "admin.data")

    src_id = (body.get("src_entity_id") or "").strip()
    tgt_id = (body.get("tgt_entity_id") or "").strip()
    rtype  = (body.get("relation_type") or "").strip()
    source = body.get("source")
    if not (src_id and tgt_id and rtype and isinstance(source, dict)):
        raise HTTPException(
            status_code=400,
            detail="src_entity_id / tgt_entity_id / relation_type / source required",
        )

    from core.graph_editor import append_relation_source
    try:
        result = append_relation_source(
            src_id, tgt_id, rtype, source,
            wiki_generator=rag_engine.wiki_generator,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    _write_audit(
        role, "/admin/graph/relation/source [POST]",
        query=_truncate_audit_blob({
            "src": src_id, "tgt": tgt_id, "type": rtype,
            "role": source.get("role"),
        }),
        answer=_truncate_audit_blob({
            "fwd_after_n": len(result["forward"]["after"]),
            "inv_synced": result["inverse"] is not None,
        }),
    )
    return {"ok": True, "result": result}

@router.put("/admin/graph/node",
         summary="node attribute 편집 [cycle 12 PR-O6]")
async def admin_graph_node_put(request: Request,
                               role: str = Depends(get_role_from_request)):
    """admin 만 호출 가능. ``JAMES_GRAPH_EDIT=1`` env opt-in.

    Body JSON::

        {
          "api_key":   "...",
          "entity_id": "e_org_anthropic",
          "patch": {
            "name":        "Anthropic, PBC",
            "entity_type": "org",
            "aliases":     ["앤스로픽", "Anthropic AI"],
            "summary":     "AI safety company...",
            "sensitivity": "normal"
          }
        }

    Allowlisted fields only (NODE_EDITABLE_FIELDS in graph_editor.py).
    ``entity_id`` is immutable and must match the existing row — admin
    cannot repurpose an id by patching it.
    """
    _require_graph_edit_enabled()
    body = await request.json()
    _require_feature(body.get("api_key", ""), role, "admin.data")

    entity_id = (body.get("entity_id") or "").strip()
    patch     = body.get("patch") or {}
    if not entity_id:
        raise HTTPException(status_code=400, detail="entity_id required")
    if not isinstance(patch, dict) or not patch:
        raise HTTPException(status_code=400, detail="patch must be a non-empty dict")

    from core.graph_node_editor import update_node_attributes
    try:
        result = update_node_attributes(
            entity_id, patch,
            wiki_generator=rag_engine.wiki_generator,
        )
    except ValueError as e:
        msg = str(e)
        # entity_id-not-found vs validation-error: both surface 400 but
        # the not-found case is more naturally 404.
        if msg.startswith("entity_id not found") or msg.startswith("entity file unreadable"):
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    _write_audit(
        role, "/admin/graph/node [PUT]",
        query=_truncate_audit_blob({
            "entity_id":      entity_id,
            "changed_fields": result["changed_fields"],
        }),
        answer=_truncate_audit_blob({
            "path":           result["path"],
            "changed_n":      len(result["changed_fields"]),
        }),
    )
    return {"ok": True, "result": result}

@router.post("/admin/graph/event",
          summary="event 노드 생성 [PR-11a-2 graph evolution]")
async def admin_graph_event_post(request: Request,
                                 role: str = Depends(get_role_from_request)):
    """admin 만 호출 가능. ``JAMES_GRAPH_EDIT=1`` env opt-in.

    PR-11 graph evolution 의 admin 진입점. ingest path 는 여전히
    person/org/concept/document 4 type 만 emit; event 는 본 endpoint
    또는 후속 PR-11d (MemoryLoom date detection) 만 생성한다.

    Body JSON::

        {
          "api_key":               "...",
          "name":                  "2026 비트코인 ETF 승인",
          "occurred_at":           "2026-01-10",
          "occurred_at_precision": "day",          // optional, default "day"
          "aliases":               ["BTC ETF 승인"],  // optional
          "source_doc_id":         "d_sec_filing", // optional → role=manual when omitted
          "source_weight":         1.0             // optional, default 1.0
        }

    Returns::

        {
          "ok":          true,
          "entity_id":   "e_event_a1b2c3d4",
          "path":        "wiki/entity/prod/event/<normalized>.md",
          "frontmatter": { ... }                   // full new-file frontmatter
        }
    """
    _require_graph_edit_enabled()
    body = await request.json()
    _require_feature(body.get("api_key", ""), role, "admin.data")

    name        = body.get("name")
    occurred_at = body.get("occurred_at")
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=400, detail="name required")
    if not isinstance(occurred_at, str) or not occurred_at.strip():
        raise HTTPException(status_code=400, detail="occurred_at required")

    precision     = body.get("occurred_at_precision", "day")
    aliases       = body.get("aliases")
    source_doc_id = body.get("source_doc_id")
    source_weight = body.get("source_weight", 1.0)

    from core.graph_node_editor import create_event_node
    try:
        result = create_event_node(
            name, occurred_at,
            wiki_generator=rag_engine.wiki_generator,
            occurred_at_precision=precision,
            aliases=aliases,
            source_doc_id=source_doc_id,
            source_weight=source_weight,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    _write_audit(
        role, "/admin/graph/event [POST]",
        query=_truncate_audit_blob({
            "name":        name,
            "occurred_at": occurred_at,
            "precision":   precision,
        }),
        answer=_truncate_audit_blob({
            "entity_id":   result["entity_id"],
            "path":        result["path"],
        }),
    )
    return {"ok": True, **result}

@router.delete("/admin/graph/relation",
            summary="relation 자체 제거 [Knowledge Cascade Phase E]")
async def admin_graph_relation_delete(request: Request,
                                      role: str = Depends(get_role_from_request)):
    """forward + inverse 양쪽 relation 을 frontmatter 에서 제거.

    Body JSON:
      {
        "api_key":       "...",
        "src_entity_id": "...",
        "tgt_entity_id": "...",
        "relation_type": "RELATED_TO"
      }
    """
    _require_graph_edit_enabled()
    body = await request.json()
    _require_feature(body.get("api_key", ""), role, "admin.data")

    src_id = (body.get("src_entity_id") or "").strip()
    tgt_id = (body.get("tgt_entity_id") or "").strip()
    rtype  = (body.get("relation_type") or "").strip()
    if not (src_id and tgt_id and rtype):
        raise HTTPException(
            status_code=400,
            detail="src_entity_id / tgt_entity_id / relation_type required",
        )

    from core.graph_editor import delete_relation
    try:
        result = delete_relation(
            src_id, tgt_id, rtype,
            wiki_generator=rag_engine.wiki_generator,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    _write_audit(
        role, "/admin/graph/relation [DELETE]",
        query=_truncate_audit_blob({
            "src": src_id, "tgt": tgt_id, "type": rtype,
        }),
        answer=_truncate_audit_blob({
            "fwd_removed": result["forward"]["removed"],
            "inv_removed": result["inverse"]["removed"],
        }),
    )
    return {"ok": True, "result": result}

@router.get("/admin/memory", summary="Memory 현황 [P7]")
async def admin_memory(api_key: str, role: str = Depends(get_role_from_request)):
    _require_feature(api_key, role, "admin.data")
    try:
        from core.memory import MemoryStore
        from core.memory.store import _connect
        stats = MemoryStore().get_stats()
        with _connect() as conn:
            prefs = [dict(r) for r in conn.execute(
                "SELECT key, value, updated_at FROM preferences ORDER BY updated_at DESC LIMIT 20"
            ).fetchall()]
        return {"stats": stats, "preferences": prefs}
    except Exception as e:
        return {"stats": {}, "preferences": [], "error": str(e)}

@router.get("/admin/trace/{trace_id}", summary="단일 trace 재생 [#81 phase 3-A]")
async def admin_trace_get(
    trace_id: str,
    api_key:  str,
    day:      str = "",
    role:     str = Depends(get_role_from_request),
):
    """Read back the per-stage JSONL entries for one `trace_id`.

    Path:
      trace_id: uuid7 hex (the value the /query/ response carries
                under `trace_id`).

    Query:
      day: YYYY-MM-DD lookup. Defaults to today. The trace files are
           date-partitioned, so this hint avoids a directory scan.

    Response:
      {"trace_id": "...", "day": "...", "count": N,
       "stages": [{"stage": "auth", "ts_ns": ..., ...}, ...]}

    404 when no trace file exists for the (trace_id, day) pair.
    Stages are returned in the order they were written (chronological).
    """
    _require_feature(api_key, role, "admin.metrics")
    from core.observability import read_trace
    # Normalize the day arg: empty/whitespace → today (read_trace default).
    day_arg = (day or "").strip() or None
    stages = read_trace(trace_id, day=day_arg)
    if not stages:
        raise HTTPException(
            status_code=404,
            detail=f"trace not found: trace_id={trace_id} day={day_arg or 'today'}",
        )
    from datetime import datetime
    return {
        "trace_id": trace_id,
        "day":      day_arg or datetime.now().strftime("%Y-%m-%d"),
        "count":    len(stages),
        "stages":   stages,
    }

@router.get(
    "/admin/graph/trace-replay",
    summary="Reasoning trail replay at time T [v0.5 Track F.1 TT.c]",
)
async def admin_graph_trace_replay(
    api_key:  str,
    trace_id: str,
    t:        str = "",
    day:      str = "",
    role:     str = Depends(get_role_from_request),
):
    """Reasoning trail replay for one ``trace_id`` filtered to events
    that occurred at or before time ``t``.

    Surfaces the per-stage JSONL trace file the chat panel renders
    live (``chat.js`` STAGE_META) — but with a cutoff so the Time-
    Travel Dashboard (Track F.1 §5.6) can show "what the reasoner
    was doing at moment T."

    Query params:
      - ``trace_id``: uuid7 hex from the ``/query/`` response.
      - ``t``: optional ISO-8601 cutoff. When empty, every stage is
        returned (equivalent to ``/admin/trace/{trace_id}``). When
        set, only stages whose ``ts_ns`` timestamp falls at or
        before ``t`` are returned.
      - ``day``: optional YYYY-MM-DD partition hint. Defaults to
        today.

    Returns:
      ``{"ok": true, "trace_id": "...", "day": "...",
         "t": "<iso or null>",
         "total_count": N, "replayed_count": M,
         "stages": [{stage, ts_ns, phase, ...}, ...]}``

    The returned stages share the schema ``read_trace`` produces, so
    the frontend can reuse its STAGE_META → 3-phase grouping
    (retrieve / expand / verify) verbatim.

    404 when no trace file exists for (trace_id, day). 400 on
    malformed ``t``.

    Pure-function contract: read-only over the trace JSONL files +
    no module-state mutation. Same trace + same t + same day always
    returns byte-identical JSON.
    """
    _require_feature(api_key, role, "admin.metrics")

    from datetime import datetime
    from core.observability import read_trace

    day_arg = (day or "").strip() or None
    stages = read_trace(trace_id, day=day_arg)
    if not stages:
        raise HTTPException(
            status_code=404,
            detail=f"trace not found: trace_id={trace_id} day={day_arg or 'today'}",
        )

    total_count = len(stages)
    cutoff_iso: Optional[str] = None
    raw_t = (t or "").strip()
    if raw_t:
        try:
            cutoff_dt = datetime.fromisoformat(raw_t.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="'t' must be an ISO-8601 timestamp (e.g. 2026-06-13T05:00:00Z)",
            )
        # Convert cutoff to ns since epoch. ts_ns is stored as
        # `time.time_ns()` which is naive UNIX ns — strip the
        # cutoff's tz offset by converting to a UTC timestamp first
        # so the comparison is meaningful for both naive and
        # tz-aware ``cutoff_dt`` values.
        if cutoff_dt.tzinfo is None:
            from datetime import timezone
            cutoff_dt = cutoff_dt.replace(tzinfo=timezone.utc)
        cutoff_ns = int(cutoff_dt.timestamp() * 1_000_000_000)
        filtered = []
        for s in stages:
            ts = s.get("ts_ns")
            if isinstance(ts, (int, float)) and ts <= cutoff_ns:
                filtered.append(s)
        stages = filtered
        cutoff_iso = cutoff_dt.isoformat()

    return {
        "ok":             True,
        "trace_id":       trace_id,
        "day":            day_arg or datetime.now().strftime("%Y-%m-%d"),
        "t":              cutoff_iso,
        "total_count":    total_count,
        "replayed_count": len(stages),
        "stages":         stages,
    }

@router.get(
    "/admin/graph/diff-vs-now",
    summary="Now-vs-T graph state diff [v0.5 Track F.1 TT.d]",
)
async def admin_graph_diff_vs_now(
    api_key:   str,
    t:         str,
    limit:     int = 500,
    tenant_id: Optional[str] = None,
    role:      str = Depends(get_role_from_request),
):
    """Compute the audit-only graph state diff between time ``t`` and
    "now" — the canonical Time-Travel "now-vs-T" view (Track F.1
    §5.6 TT.d).

    Calls :func:`core.lifecycle.replay_graph.reconstruct_graph_at`
    twice (once at ``t``, once at the current UTC moment) and returns
    a structured diff:

      * ``added_edges``: edge_ids present in NOW but not in T (newly
        created since ``t``)
      * ``removed_edges``: edge_ids present in T but not in NOW
        (typically cascade-invalidated since ``t``; can also be a
        chain extension that buried an older link in the new head's
        invalidated set)
      * ``invalidated_since``: edge_ids that moved into the
        invalidated set between T and NOW
      * ``chain_extended``: ``head_id`` → ``{at_t: [...], at_now:
        [...]}`` for chains whose link order or membership grew
      * ``mounted_packs_added`` / ``mounted_packs_removed``: pack_ids
        that mounted or unmounted between T and NOW

    Query params:
      - ``t``: ISO-8601 cutoff (the "T" past moment to diff against).
      - ``limit``: per-collection cap (default 500, max 5000). When
        any collection exceeds the cap, ``truncated`` is true.
      - ``tenant_id``: optional v0.5 G1.b strict-exclusion filter
        applied to BOTH snapshots — so the diff reflects only rows
        the operator's tenant could have seen.

    Returns:
      ``{"ok": true, "t": "<iso>", "now": "<iso>",
         "event_count_at_t": N, "event_count_at_now": M,
         "added_edges": [...], "removed_edges": [...],
         "invalidated_since": [...],
         "chain_extended": {head_id: {at_t, at_now}, ...},
         "mounted_packs_added": [...],
         "mounted_packs_removed": [...],
         "truncated": bool}``

    Pure-function contract: read-only over the audit_log; same
    audit_log + same ``t`` + the same wall-clock moment returns the
    same body. Note "now" advances each request, so the diff grows
    as new lifecycle events land — this is the intended semantics
    ("show me what changed since T").
    """
    _require_feature(api_key, role, "admin.data")

    from datetime import datetime, timezone
    from core.lifecycle.replay_graph import reconstruct_graph_at

    raw = (t or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="missing 't' query param")
    try:
        cutoff = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="'t' must be an ISO-8601 timestamp (e.g. 2026-06-13T05:00:00Z)",
        )

    cap = max(1, min(int(limit or 500), 5000))

    now_dt = datetime.now(timezone.utc)
    snap_t = reconstruct_graph_at(cutoff, tenant_id=tenant_id)
    snap_now = reconstruct_graph_at(now_dt, tenant_id=tenant_id)

    edges_t_keys = set(snap_t.edges.keys())
    edges_now_keys = set(snap_now.edges.keys())
    added = sorted(edges_now_keys - edges_t_keys)
    removed = sorted(edges_t_keys - edges_now_keys)

    invalidated_t = set(snap_t.invalidated_ids)
    invalidated_now = set(snap_now.invalidated_ids)
    invalidated_since = sorted(invalidated_now - invalidated_t)

    chain_diffs: dict = {}
    all_heads = set(snap_t.supersede_chains) | set(snap_now.supersede_chains)
    for head_id in all_heads:
        at_t = list(snap_t.supersede_chains.get(head_id, []))
        at_now = list(snap_now.supersede_chains.get(head_id, []))
        if at_t != at_now:
            chain_diffs[head_id] = {"at_t": at_t, "at_now": at_now}

    packs_t = set(snap_t.mounted_pack_ids)
    packs_now = set(snap_now.mounted_pack_ids)
    packs_added = sorted(packs_now - packs_t)
    packs_removed = sorted(packs_t - packs_now)

    truncated = False
    if len(added) > cap:
        truncated = True
        added = added[:cap]
    if len(removed) > cap:
        truncated = True
        removed = removed[:cap]
    if len(invalidated_since) > cap:
        truncated = True
        invalidated_since = invalidated_since[:cap]
    if len(chain_diffs) > cap:
        truncated = True
        # Keep insertion-ordered slice of the dict — dict preserves
        # insertion order in 3.7+, so itertools.islice is fine.
        from itertools import islice
        chain_diffs = dict(islice(chain_diffs.items(), cap))

    return {
        "ok":                    True,
        "t":                     snap_t.replayed_at.isoformat(),
        "now":                   snap_now.replayed_at.isoformat(),
        "event_count_at_t":      snap_t.event_count,
        "event_count_at_now":    snap_now.event_count,
        "added_edges":           added,
        "removed_edges":         removed,
        "invalidated_since":     invalidated_since,
        "chain_extended":        chain_diffs,
        "mounted_packs_added":   packs_added,
        "mounted_packs_removed": packs_removed,
        "truncated":             truncated,
    }

@router.get("/admin/episodic/{session_id}",
         summary="Cognitive Phase 3 PR-9b — 세션의 episodic events 조회")
async def admin_episodic_get(
    session_id: str,
    api_key:    str,
    limit:      int = 50,
    stage:      str = "",
    role:       str = Depends(get_role_from_request),
):
    """Session-scoped reasoning trail dump for debugging.

    Returns the most recent episodic events for one session. Each
    event = one cognitive-stage decision (plan / reflect / verify /
    synth) with its summary, score, and trace_id back-link.

    Path:
      session_id: the session whose trail to dump.

    Query:
      limit: 1..200, default 50.
      stage: optional comma-separated filter
             (e.g. ``stage=plan,verify``).

    Response:
      {"session_id": "...", "count": N,
       "events": [{"event_id", "turn_id", "ts", "stage", "summary",
                   "score", "extras", "trace_id"}, ...]}

    Permission: admin.metrics (same as /admin/trace/* — both are
    debugging surfaces over the reasoning audit data).
    """
    _require_feature(api_key, role, "admin.metrics")
    limit = max(1, min(int(limit or 50), 200))
    stages_filter: tuple = ()
    if stage and stage.strip():
        stages_filter = tuple(
            s.strip() for s in stage.split(",") if s.strip()
        )

    try:
        from core.memory.episodic import get_episodic_memory
        events = get_episodic_memory().recent_events(
            session_id, limit=limit, stages=stages_filter,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"episodic store unavailable: {type(e).__name__}",
        )

    return {
        "session_id": session_id,
        "count":      len(events),
        "events":     [
            {
                "event_id":  ev.event_id,
                "turn_id":   ev.turn_id,
                "ts":        ev.ts,
                "stage":     ev.stage,
                "summary":   ev.summary,
                "score":     ev.score,
                "extras":    ev.extras,
                "trace_id":  ev.trace_id,
            }
            for ev in events
        ],
    }

@router.get("/admin/metrics", summary="Per-stage 레이턴시 히스토그램 [#81 phase 3-B]")
async def admin_metrics_get(
    api_key:      str,
    window_hours: int  = 24,
    stage:        str  = "",
    role:         str  = Depends(get_role_from_request),
):
    """Per-stage latency stats over recent traces.

    Walks `reports/trace/` for the window and computes per-stage
    p50/p90/p99/max + sample count from consecutive `ts_ns` deltas.

    Query:
      window_hours: lookback window (default 24, clamped to [1, 168]).
      stage:        optional single-stage filter (e.g. `retrieve`).

    Response:
      {"window_hours": N, "stage_filter": "...",
       "stages": {"retrieve": {count, p50_ms, p90_ms, p99_ms, max_ms},
                  "graph":    {...}, ...}}

    See `core/trace_metrics.py::aggregate_metrics` for the latency
    derivation rationale (per-trace ts_ns deltas vs explicit fields).
    """
    _require_feature(api_key, role, "admin.metrics")
    from core.trace_metrics import aggregate_metrics
    stage_filter = (stage or "").strip() or None
    stats = aggregate_metrics(window_hours=window_hours,
                              stage_filter=stage_filter)
    return {
        "window_hours": max(1, min(int(window_hours or 24), 168)),
        "stage_filter": stage_filter or "",
        "stages":       stats,
    }

@router.get("/admin/audit/list", summary="감사 로그 조회 (W4 P6)")
async def admin_audit_list(
    api_key:  str,
    category: str = "all",
    q:        str = "",
    limit:    int = 100,
    offset:   int = 0,
    role:     str = Depends(get_role_from_request),
):
    """Read audit_log rows with category + free-text filter.

    Query params:
      category — "user_mgmt" | "password" | "api_keys" | "auth" |
                 "query" | "all" (default). Unknown values collapse
                 to "all" to avoid a 400 on a UI typo.
      q        — substring on (query OR security_event), case-insensitive
                 via LIKE.
      limit    — hard cap 500, default 100.
      offset   — default 0.

    Response shape (per row): id, timestamp, endpoint, user_role,
    ip_address, query (= filename for /upload/, username for
    /signup/ etc.), security_event, blocked.

    Admin-gated. The audit_log table has no per-row ACL — anyone with
    admin can see every row, including security_event strings that
    may carry sensitive context (rejected passwords are NOT logged
    verbatim by _write_audit; only the rule name surfaces).
    """
    _require_feature(api_key, role, "admin.audit_log")
    limit  = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    qstr   = (q or "").strip()
    cat    = category if category in _AUDIT_CATEGORIES else "all"

    where_parts: list = []
    params:      list = []
    if cat != "all":
        prefixes = _AUDIT_CATEGORIES[cat]
        # one LIKE per prefix joined with OR — the table is small enough
        # (audit_log is the only event surface) that a UNION is overkill.
        where_parts.append(
            "(" + " OR ".join("endpoint LIKE ?" for _ in prefixes) + ")"
        )
        params.extend(p + "%" for p in prefixes)
    if qstr:
        where_parts.append(
            "(query LIKE ? OR security_event LIKE ?)"
        )
        like = f"%{qstr}%"
        params.extend([like, like])

    where = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

    items: list = []
    total: int  = 0
    try:
        conn = sqlite3.connect(_AUDIT_DB, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        total = int(conn.execute(
            f"SELECT COUNT(*) AS c FROM audit_log{where}", params,
        ).fetchone()["c"])
        rows = conn.execute(
            f"SELECT id, timestamp, endpoint, user_role, ip_address, "
            f"query, security_event, blocked FROM audit_log{where} "
            f"ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        for r in rows:
            items.append({
                "id":             r["id"],
                "timestamp":      r["timestamp"],
                "endpoint":       r["endpoint"],
                "user_role":      r["user_role"],
                "ip_address":     r["ip_address"],
                "query":          (r["query"] or "")[:120],
                "security_event": r["security_event"] or "",
                "blocked":        bool(r["blocked"]),
            })
        conn.close()
    except Exception as e:
        return {"items": [], "total": 0, "error": str(e),
                "category": cat, "q": qstr,
                "limit": limit, "offset": offset}

    return {"items": items, "total": total,
            "category": cat, "q": qstr,
            "limit": limit, "offset": offset}

@router.get("/admin/features/list", summary="권한 매트릭스 조회 (W4-Q1)")
async def admin_features_list(
    api_key: str,
    role:    str = Depends(get_role_from_request),
):
    """Catalog + currently-effective allowed set per role.

    Response shape:
      {
        "roles":    ["admin", "manager", "employee", "external"],
        "features": [ {id, description, default_allowed, effective}, ... ]
      }

    The ``effective`` map per feature is keyed by role and carries
    ``{allowed, source}`` where ``source ∈ {"default","override"}``
    so the UI can render override rows distinctly.
    """
    _require_feature(api_key, role, "admin.policy_matrix")
    from core.feature_registry import list_effective
    return {
        "roles":    sorted(ALLOWED_ROLES),
        "features": list_effective(),
    }

@router.post("/admin/features/override",
          summary="권한 매트릭스 override 설정 (W4-Q1)")
async def admin_features_override(
    data:    FeatureOverrideRequest,
    request: Request,
    api_key: str = "",
    role:    str = Depends(get_role_from_request),
):
    """Set one (feature_id, role) override.

    Validation lives inside ``set_override`` — unknown feature_id or
    role returns False, surfaced here as 400. Idempotent: re-setting
    the same value just updates the timestamp + updated_by.
    """
    _require_feature(api_key, role, "admin.policy_matrix")
    from core.feature_registry import set_override

    # Read caller username from the JWT subject for audit-log
    # attribution. Optional — if missing (DEV_MODE / X-Role), we
    # still write the row but updated_by is None.
    try:
        from core.auth import verify_token
        caller = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            caller = (verify_token(auth_header[7:].strip()) or {}).get("sub")
    except Exception:
        caller = None

    ok = set_override(data.feature_id, data.role, data.allowed,
                      updated_by=caller)
    ip = get_client_ip(request)
    if not ok:
        _write_audit(role, "/admin/features/override",
                     query=f"{data.feature_id}/{data.role}",
                     security_event="override_failed (unknown feature or role)",
                     ip_address=ip)
        raise HTTPException(
            status_code=400,
            detail="알 수 없는 feature_id 또는 role 입니다.",
        )
    _write_audit(role, "/admin/features/override",
                 query=f"{data.feature_id}/{data.role}",
                 security_event=f"override_set allowed={data.allowed}",
                 ip_address=ip)
    return {"ok": True, "feature_id": data.feature_id,
            "role": data.role, "allowed": data.allowed}

@router.post("/admin/features/reset",
          summary="권한 매트릭스 override 제거 → 기본값 복원 (W4-Q1)")
async def admin_features_reset(
    data:    FeatureResetRequest,
    request: Request,
    api_key: str = "",
    role:    str = Depends(get_role_from_request),
):
    """Remove overrides for a feature.

    Two modes:
      - role specified  → delete that single override row.
      - role omitted/empty → delete every override for the feature
                              (full reset to default).

    Returns the number of rows actually deleted, so the UI can show
    "0개 reset" when the feature already used the defaults.
    """
    _require_feature(api_key, role, "admin.policy_matrix")
    from core.feature_registry import clear_override, clear_all_overrides_for

    ip = get_client_ip(request)
    if data.role:
        deleted = 1 if clear_override(data.feature_id, data.role) else 0
        scope_label = f"{data.feature_id}/{data.role}"
    else:
        deleted = clear_all_overrides_for(data.feature_id)
        scope_label = data.feature_id
    _write_audit(role, "/admin/features/reset",
                 query=scope_label,
                 security_event=f"override_cleared count={deleted}",
                 ip_address=ip)
    return {"ok": True, "deleted": deleted, "scope": scope_label}

@router.get("/admin/files/tree", summary="파일 트리 조회 [item #2]")
async def admin_files_tree(
    api_key:    str,
    root:       str = "wiki",
    path:       str = "",
    max_depth:  int = 3,
    role:       str = Depends(get_role_from_request),
):
    """Read-only directory listing rooted at one of the allowed roots.

    `max_depth` clamped to [1, 5] — a 5-level recursive listing on a
    big wiki could be slow and produce a fat JSON, but we don't need
    deeper. `1` lists immediate children only.
    """
    _require_feature(api_key, role, "admin.data")
    max_depth = max(1, min(int(max_depth or 3), 5))
    base = _resolve_under_root(root, path)
    if not base or not os.path.isdir(base):
        return {"root": root, "path": path, "children": [],
                "exists": False}

    def walk(dir_abs: str, depth: int) -> list:
        try:
            entries = sorted(os.listdir(dir_abs))
        except OSError:
            return []
        out = []
        for name in entries:
            if name.startswith("."):       # hide dotfiles (.git, .env shadows)
                continue
            full = os.path.join(dir_abs, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            if os.path.isdir(full):
                node = {
                    "name":     name,
                    "type":     "dir",
                    "mtime":    int(st.st_mtime),
                    "children": walk(full, depth - 1) if depth > 1 else [],
                }
            else:
                node = {
                    "name":  name,
                    "type":  "file",
                    "size":  st.st_size,
                    "mtime": int(st.st_mtime),
                }
            out.append(node)
        return out

    return {
        "root":     root,
        "path":     path,
        "exists":   True,
        "children": walk(base, max_depth),
    }

@router.get("/admin/files/search", summary="파일명 검색 [item #2]")
async def admin_files_search(
    api_key: str,
    q:       str,
    root:    str = "wiki",
    limit:   int = 100,
    role:    str = Depends(get_role_from_request),
):
    """Filename substring search under one root. Case-insensitive.

    Returns a flat list (not nested). Capped at `limit` matches (default
    100, max 500) so a one-character query doesn't dump the whole tree.
    """
    _require_feature(api_key, role, "admin.data")
    qstr  = (q or "").strip().lower()
    if not qstr:
        return {"q": "", "matches": [], "total": 0, "root": root}
    limit = max(1, min(int(limit or 100), 500))
    base  = _resolve_under_root(root, "")
    if not base or not os.path.isdir(base):
        return {"q": qstr, "matches": [], "total": 0, "root": root}

    matches = []
    for dirpath, dirnames, filenames in os.walk(base):
        # Skip hidden dirs.
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            if qstr in name.lower():
                full = os.path.join(dirpath, name)
                rel  = os.path.relpath(full, base).replace("\\", "/")
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                matches.append({
                    "name":  name,
                    "path":  rel,
                    "size":  st.st_size,
                    "mtime": int(st.st_mtime),
                })
                if len(matches) >= limit:
                    return {"q": qstr, "matches": matches,
                            "total": len(matches), "truncated": True,
                            "root": root}
    return {"q": qstr, "matches": matches, "total": len(matches),
            "root": root}

@router.get("/admin/files/view", summary="파일 인라인 보기 [item #2-view]")
async def admin_files_view(
    api_key: str,
    root:    str,
    path:    str,
    max_kb:  int = 256,
    role:    str = Depends(get_role_from_request),
):
    """Read-only inline view of a text file under an allowed root.

    Sibling to ``/admin/files/download`` but tuned for the admin-side
    file management modal: returns ``{name, size, ext, content}`` JSON
    suitable for rendering in a ``<pre>`` block. The same ``admin.data``
    feature gate applies — this endpoint is intended to be called from
    the in-page JavaScript (Authorization header automatically attached
    by ``fetch()``), unlike the download path which is a new-tab
    ``<a href>`` click and therefore loses the JWT header.

    Defenses (in order):

    1. ``admin.data`` feature gate (api_key + role).
    2. ``_resolve_under_root`` rejects unknown root + path traversal.
    3. Extension allowlist: text-only (``.md / .txt / .json / .yaml /
       .yml / .csv / .jsonl / .log / .tsv``). Binary / source-code
       extensions refused with 415 — operator should use download.
    4. ``max_kb`` cap (default 256, max 1024) — accidentally opening
       a multi-MB file in a modal would lock the browser.

    Audit log records every view.
    """
    _require_feature(api_key, role, "admin.data")
    if not (path or "").strip():
        raise HTTPException(status_code=400, detail="path required")
    full = _resolve_under_root(root, path)
    if not full or not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="not found")
    ext = os.path.splitext(full)[1].lower()
    if ext not in _FILE_VIEW_TEXT_EXTS:
        raise HTTPException(
            status_code=415,
            detail=f"extension {ext} not viewable inline; use download",
        )
    max_kb = max(1, min(int(max_kb or 256), 1024))
    try:
        size = os.path.getsize(full)
    except OSError:
        raise HTTPException(status_code=404, detail="stat failed")
    if size > max_kb * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"file {size} bytes exceeds max_kb={max_kb}; use download",
        )
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"read failed: {e}")
    _write_audit(role, "/admin/files/view/",
                 query=os.path.basename(full), elapsed_sec=0)
    return {
        "root":    root,
        "path":    path,
        "name":    os.path.basename(full),
        "size":    size,
        "ext":     ext,
        "content": content,
    }

@router.get("/admin/files/download", summary="파일 다운로드 [item #2]")
async def admin_files_download(
    api_key: str,
    root:    str,
    path:    str,
    role:    str = Depends(get_role_from_request),
):
    """Download a single file from an allowed root.

    Defenses (in order):
      1. admin gate (api_key + role)
      2. _resolve_under_root rejects unknown root + path traversal
      3. extension allowlist (no .py / .env / .db / etc.)
      4. file must exist + be a regular file (not dir, not symlink to
         outside — realpath already followed in step 2)

    Uses FileResponse — FastAPI streams the file, doesn't load it into
    memory. Audit log records every download.
    """
    _require_feature(api_key, role, "admin.data")
    if not (path or "").strip():
        raise HTTPException(status_code=400, detail="path required")
    full = _resolve_under_root(root, path)
    if not full or not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="not found")
    ext = os.path.splitext(full)[1].lower()
    if ext not in _FILE_DOWNLOAD_ALLOWED_EXTS:
        raise HTTPException(
            status_code=403,
            detail=f"extension {ext} not allowed for download",
        )
    _write_audit(role, "/admin/files/download/",
                 query=os.path.basename(full), elapsed_sec=0)
    from fastapi.responses import FileResponse
    return FileResponse(
        path=full,
        filename=os.path.basename(full),
        media_type="application/octet-stream",
    )

@router.delete("/admin/files",
            summary="업로드 파일 + 파생 cascade 삭제 [Knowledge Cascade Phase C]")
async def admin_files_delete(
    api_key: str,
    path:    str,
    role:    str = Depends(get_role_from_request),
):
    """uploads/ 의 파일 하나를 삭제하고 그로부터 파생된 모든 wiki entity /
    relation source / vector chunks 까지 cascade.

    docs/design/v0.3-knowledge-cascade.md §5 — Phase C.

    Trust boundary:
      - admin.data feature gate
      - root='uploads' 로 hard-coded (wiki/ entity 의 직접 삭제는
        기존 chat 의 ``delete_entity`` 가 처리 — 다른 cascade 의미)
      - ``_resolve_under_root`` 가 path traversal 차단
      - 파일은 ``uploads/.deleted/{ts}_{name}`` 으로 backup, 즉시 purge
        하지 않음 (N 일 후 운영 cleanup 의 일)
    """
    _require_feature(api_key, role, "admin.data")
    if not (path or "").strip():
        raise HTTPException(status_code=400, detail="path required")

    # 'uploads' root 하에서만 동작 — wiki 의 entity 직접 삭제는 다른 경로.
    full = _resolve_under_root("uploads", path)
    if not full or not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="not found")

    physical_filename = os.path.basename(full)

    from core.cascade import cascade_delete_upload
    try:
        summary = cascade_delete_upload(
            physical_filename,
            wiki_generator = rag_engine.wiki_generator,
            vector_store   = rag_engine.vector_store,
            upload_dir     = _file_mgmt_roots()["uploads"],
            user_role      = role,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 결과 + audit. cascade 결과의 핵심 숫자만 JSON 으로 압축해 answer
    # 컬럼에 저장 (max 500 chars). 자세한 summary 는 응답 본문에 그대로.
    counts = summary.get("counts", {})
    audit_blob = json.dumps({
        "doc_entity_id":           summary.get("doc_entity_id"),
        "orphan_entities_deleted": summary.get("orphan_entities_deleted"),
        "relations_recomputed":    counts.get("relations_recomputed"),
        "relations_dropped":       counts.get("relations_dropped"),
        "vector_deleted":          summary.get("vector_deleted"),
        "file_backup":             summary.get("file_backup"),
    }, ensure_ascii=False)
    _write_audit(
        role, "/admin/files/delete",
        query=physical_filename,
        answer=audit_blob,
        elapsed_sec=0,
    )
    return {"ok": True, "summary": summary}

@router.put("/admin/files",
         summary="업로드 파일 내용 교체 + 파생 cascade 갱신 [Knowledge Cascade Phase D]")
async def admin_files_modify(
    request:     Request,
    file:        UploadFile = File(...),
    api_key:     str        = Form(...),
    path:        str        = Form(...),
    role:        str        = Depends(get_role_from_request),
):
    """`uploads/` 의 기존 파일을 새 multipart file 로 교체하고 파생
    cascade 를 재실행.

    docs/design/v0.3-knowledge-cascade.md §6 — Phase D.

    Trust boundary:
      - admin.data feature gate
      - root='uploads' hard-coded, `_resolve_under_root` 가 path traversal 차단
      - 새 content 도 PolicyEngine sanitize_for_ingestion 통과
      - 옛 파일은 `uploads/.deleted/{ts}_{name}` 으로 backup
    """
    _require_feature(api_key, role, "admin.data")
    if not (path or "").strip():
        raise HTTPException(status_code=400, detail="path required")

    full = _resolve_under_root("uploads", path)
    if not full or not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="not found")

    physical_filename = os.path.basename(full)

    # 새 파일을 메모리에 모은 뒤 cascade 에 넘긴다. 동일한 size cap.
    new_bytes = b""
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        new_bytes += chunk
        if len(new_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="파일 크기 초과")

    # PolicyEngine sanitize — content extraction (텍스트 파일 / OCR 등은
    # 추후 follow-up. 이번 PR 은 텍스트 직접 교체 경로). file_processor 가
    # 일관된 entry point.
    # NOTE: process_file expects a path; 임시 파일에 dump 후 처리.
    import tempfile
    suffix = os.path.splitext(file.filename or physical_filename)[1] or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
        tf.write(new_bytes)
        tmp_path = tf.name
    try:
        tc = file_processor.process_file(tmp_path, file.filename or physical_filename)
        raw_content, _decision = default_engine.sanitize_for_ingestion(
            tc, source=file.filename or physical_filename,
        )
        new_meta = file_processor.generate_file_metadata(raw_content)
    finally:
        try: os.unlink(tmp_path)
        except OSError: pass

    from core.cascade import cascade_modify_doc
    from utils.tokenizer import split_chunks
    try:
        summary = cascade_modify_doc(
            physical_filename,
            raw_content,
            wiki_generator = rag_engine.wiki_generator,
            vector_store   = rag_engine.vector_store,
            upload_dir     = _file_mgmt_roots()["uploads"],
            new_metadata   = new_meta,
            user_role      = role,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # cascade_modify_doc 가 vector 의 add 는 하지 않으므로 (signature
    # 의존 회피), 여기서 새 chunks 를 다시 넣는다.
    try:
        new_chunks = split_chunks(raw_content)
        rag_engine.vector_store.add_documents_with_meta(
            texts=new_chunks,
            source=summary["original_filename"],
            metadata={
                "sensitivity": new_meta.get("sensitivity", "internal"),
                "owner":       new_meta.get("owner", "system"),
                "category":    new_meta.get("category", "기타"),
                "source_type": "prod",
            },
        )
    except Exception as e:
        print(f"[FILES_PUT] vector re-add fail: {e}")

    cc = summary.get("cascade_counts", {})
    audit_blob = json.dumps({
        "doc_entity_id":           summary.get("doc_entity_id"),
        "sidecar_present":         summary.get("sidecar_present"),
        "diff":                    summary.get("diff"),
        "orphan_entities_deleted": summary.get("orphan_entities_deleted"),
        "relations_dropped":       cc.get("relations_dropped"),
        "file_backup":             summary.get("file_backup"),
    }, ensure_ascii=False)
    _write_audit(
        role, "/admin/files [PUT]",
        query=physical_filename,
        answer=audit_blob,
        elapsed_sec=0,
    )
    return {"ok": True, "summary": summary}

@router.get("/admin/settings", summary="설정 조회 [P7]")
async def admin_settings_get(api_key: str, role: str = Depends(get_role_from_request)):
    _require_feature(api_key, role, "admin.settings")
    from config import GEMMA_MODEL
    try:
        from core.memory import MemoryStore
        persona = MemoryStore().get_persona()
    except Exception:
        persona = {}
    return {"model": GEMMA_MODEL, "max_loop": 2,
            "protected": os.environ.get("JAMES_PROTECTED_FILES",""),
            "persona": persona}

@router.get("/admin/persona", summary="Persona 조회 [P7]")
async def admin_persona_get(api_key: str, role: str = Depends(get_role_from_request)):
    verify_api_key(api_key)   # api_key만 검증 (role 무관)
    try:
        from core.memory import MemoryStore
        return {"persona": MemoryStore().get_persona()}
    except Exception as e:
        return {"persona": {}, "error": str(e)}

@router.post("/admin/persona", summary="Persona 설정 [P7]")
async def admin_persona_set(data: PersonaRequest,
                             role: str = Depends(get_role_from_request)):
    verify_api_key(data.api_key)   # api_key만 검증 (role 무관)
    try:
        from core.memory import MemoryStore
        from core.memory.store import _connect
        # persona 테이블 없으면 자동 생성
        with _connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS persona (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
        store = MemoryStore()
        saved = {}
        if data.name:     store.set_persona("name",     data.name);     saved["name"]     = data.name
        if data.style:    store.set_persona("style",    data.style);    saved["style"]    = data.style
        if data.language: store.set_persona("language", data.language); saved["language"] = data.language
        if data.custom is not None:
            store.set_persona("custom", data.custom); saved["custom"] = data.custom
        _write_audit(role, "/admin/persona",
                     query=f"name={data.name} style={data.style[:20]}")
        print(f"[PERSONA] 저장 완료: {saved}")
        return {"success": True, "persona": store.get_persona(), "saved": saved}
    except Exception as e:
        print(f"[PERSONA] 저장 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Persona 저장 실패: {e}")

@router.post("/admin/settings", summary="설정 변경 [P7]")
async def admin_settings_post(data: AdminSettingsRequest, role: str = Depends(get_role_from_request)):
    _require_feature(data.api_key, role, "admin.settings")
    if data.protected_files:
        os.environ["JAMES_PROTECTED_FILES"] = data.protected_files
    _write_audit(role, "/admin/settings", query=f"model={data.model}")
    return {"success": True, "applied": {"model": data.model, "max_loop": data.max_loop}}

@router.get("/admin/settings/cognitive",
         summary="cognitive feature flags 조회 [UI-IA risk #5]")
async def admin_settings_cognitive_get(
    api_key: str,
    role:    str = Depends(get_role_from_request),
):
    """Read-only snapshot of the six cognitive-layer feature flags.
    See `docs/UI_API_MAPPING.md` §8 risk signal #5 and
    `core/feature_flags.py` for the registry."""
    _require_feature(api_key, role, "admin.settings")
    from core.feature_flags import read_cognitive_flags
    return {"flags": read_cognitive_flags()}

@router.post("/admin/settings/cognitive",
          summary="cognitive feature flags 변경 [UI-IA risk #5]")
async def admin_settings_cognitive_post(
    data: CognitiveFlagsRequest,
    role: str = Depends(get_role_from_request),
):
    """Toggle one or more cognitive features. Body shape::

        {"api_key": "...", "flags": {"reflect": true, "verify": false}}

    Returns per-key (before, after) delta for the audit log.
    Persistence is in-process only — a restart reverts to the
    boot `.env` values.
    """
    _require_feature(data.api_key, role, "admin.settings")
    if not isinstance(data.flags, dict) or not data.flags:
        raise HTTPException(
            status_code=400,
            detail="flags must be a non-empty dict {flag_key: bool, ...}",
        )

    from core.feature_flags import apply_cognitive_flags
    try:
        deltas = apply_cognitive_flags(data.flags)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    _write_audit(
        role, "/admin/settings/cognitive",
        query=_truncate_audit_blob({
            "changed": [
                {"key": d["key"], "before": d["before"], "after": d["after"]}
                for d in deltas
            ],
        }),
    )
    return {"success": True, "deltas": deltas}

@router.post("/admin/cr/", summary="Change Request — propose (any auth user)")
async def cr_propose(
    data:    _CrProposeRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    # Any authenticated caller can propose. Identity is the JWT
    # subject — body carries no ``proposer`` field.
    verify_api_key(data.api_key)
    proposer = _bearer_username(request)
    if not proposer:
        raise HTTPException(status_code=401, detail="login required to propose")
    try:
        cr = _cr_mod.create_cr(
            target_type=data.target_type,
            target_id=data.target_id,
            title=data.title,
            description=data.description,
            proposed_diff=data.proposed_diff,
            base_hash=data.base_hash,
            proposer=proposer,
            labels=data.labels,
            role=role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "cr": _cr_as_dict(cr)}

@router.get("/admin/cr/", summary="Change Request — list (auth user)")
async def cr_list(
    api_key:     str,
    request:     Request,
    status:      Optional[str] = None,
    target_type: Optional[str] = None,
    proposer:    Optional[str] = None,
    limit:       int = 50,
    offset:      int = 0,
    role:        str = Depends(get_role_from_request),
):
    verify_api_key(api_key)
    caller = _bearer_username(request)
    if not caller:
        raise HTTPException(status_code=401, detail="login required")
    # Non-admins see only their own proposals — admin override
    # passes through proposer filter unchanged.
    if role != "admin":
        proposer = caller
    try:
        rows = _cr_mod.list_crs(
            status=status, target_type=target_type,
            proposer=proposer, limit=limit, offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "ok":    True,
        "items": [_cr_as_dict(cr) for cr in rows],
        "limit": limit, "offset": offset,
    }

@router.get("/admin/cr/{cr_id}", summary="Change Request — detail (auth user)")
async def cr_detail(
    cr_id:   str,
    api_key: str,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    verify_api_key(api_key)
    caller = _bearer_username(request)
    if not caller:
        raise HTTPException(status_code=401, detail="login required")
    cr = _cr_mod.get_cr(cr_id)
    if cr is None:
        raise HTTPException(status_code=404, detail="cr not found")
    # Non-admins can read a CR only if they're the proposer or have
    # left at least one review on it. Admin sees everything.
    if role != "admin" and cr.proposer != caller:
        reviews = _cr_mod.list_reviews(cr_id)
        if not any(rv.reviewer == caller for rv in reviews):
            raise HTTPException(status_code=403,
                detail="cr is not visible to this user")
    return {
        "ok":      True,
        "cr":      _cr_as_dict(cr),
        "reviews": [_review_as_dict(r) for r in _cr_mod.list_reviews(cr_id)],
    }

@router.post("/admin/cr/{cr_id}/approve",
          summary="Change Request — approve (admin only)")
async def cr_approve(
    cr_id:   str,
    data:    _CrApproveRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    _require_admin(data.api_key, role)
    approver = _bearer_username(request)
    if not approver:
        raise HTTPException(status_code=401,
            detail="admin JWT required to approve")
    try:
        cr = _cr_apply.merge_cr(cr_id, approver=approver, role=role)
    except ValueError as exc:
        # State machine refusals (self-approval, already-merged,
        # not-found) surface as 400.
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        # apply-side failure that doesn't change state.
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True, "cr": _cr_as_dict(cr)}

@router.post("/admin/cr/{cr_id}/reject",
          summary="Change Request — reject (admin only)")
async def cr_reject(
    cr_id:   str,
    data:    _CrRejectRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    _require_admin(data.api_key, role)
    reviewer = _bearer_username(request)
    if not reviewer:
        raise HTTPException(status_code=401,
            detail="admin JWT required to reject")
    try:
        cr = _cr_mod.reject_cr(
            cr_id, reviewer=reviewer, reason=data.reason, role=role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "cr": _cr_as_dict(cr)}

@router.post("/admin/cr/{cr_id}/review",
          summary="Change Request — review/comment (any auth user)")
async def cr_review(
    cr_id:   str,
    data:    _CrReviewRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    verify_api_key(data.api_key)
    reviewer = _bearer_username(request)
    if not reviewer:
        raise HTTPException(status_code=401, detail="login required to review")
    try:
        rv = _cr_mod.add_review(
            cr_id, reviewer=reviewer, decision=data.decision,
            body=data.body, role=role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "review": _review_as_dict(rv)}
