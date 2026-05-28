"""Phase 7 self-evolution + learn + patch routes.

Extracted from server_llmwiki.py per docs/design/v0.4.x-server-split.md
PR-E. 12 endpoints + 1 Pydantic model + 1 module helper moved verbatim —
handler body byte-identical (only ``@app.<m>`` -> ``@router.<m>``).

URL invariant: ``python scripts/audit_endpoint_paths.py origin/main``
must report 0-diff against the pre-PR-E baseline.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from routes._helpers import (
    _bearer_username,
    _require_feature,
    _write_audit,
    get_role_from_request,
)

router = APIRouter()


# ─── Pydantic models ───────────────────────────────────────────────

class RejectionRequest(BaseModel):
    proposal_id: str
    reason:      str

# ─── Module helpers ────────────────────────────────────────────────

def _cr_shadow_proposal_create(proposal_id: str, approver: str, role: str,
                               action: str) -> Optional[str]:
    """Stage B / CR-E.3 — best-effort shadow CR row for proposal events.

    Returns the cr_id on success, None on any failure. The legacy
    /admin/proposals/{id}/approve|reject flow continues regardless —
    the CR row is additive shadow with a no-op apply handler (CR-E.1).
    """
    try:
        import hashlib as _hashlib
        from core.change_request import (
            TARGET_SELF_EVO_PROPOSAL, create_cr as _cr_create,
        )
        _base = _hashlib.sha256(
            f"proposal:{proposal_id}:{action}".encode("utf-8")
        ).hexdigest()[:16]
        shadow = _cr_create(
            target_type   = TARGET_SELF_EVO_PROPOSAL,
            target_id     = proposal_id,
            title         = f"proposal:{action}:{proposal_id}",
            description   = f"endpoint=/admin/proposals/{proposal_id}/{action}",
            proposed_diff = {"proposal_id": proposal_id, "action": action,
                             "approver": approver},
            base_hash = _base,
            proposer  = approver,
            role      = role,
        )
        return shadow.cr_id
    except Exception:
        return None

# ─── Endpoints ─────────────────────────────────────────────────────

@router.get("/admin/proposals/", summary="자기진화 제안 목록 [P7-EVO]")
async def list_proposals(
    api_key: str,
    status:  str = "pending",
    role:    str = Depends(get_role_from_request),
):
    """admin 검토 대기 중인 자기진화 제안 목록."""
    _require_feature(api_key, role, "admin.evolution")
    try:
        from tools.self.evo_analyzer import list_proposals as _list
        return {"proposals": _list(status), "status_filter": status}
    except Exception as e:
        return {"proposals": [], "error": str(e)}

@router.post("/admin/proposals/{proposal_id}/approve",
          summary="제안 승인 → 자동 실행 [P7-EVO]")
async def approve_proposal(
    proposal_id: str,
    api_key:     str,
    request:     Request,
    role:        str = Depends(get_role_from_request),
):
    """
    admin이 제안을 승인하면 즉시 자동 실행 + 결과 보고.
    실행 결과를 응답으로 반환.
    """
    _require_feature(api_key, role, "admin.evolution")

    # Stage B / CR-E.3 — shadow CR row. Best-effort dual-write so the
    # unified audit shape covers proposal approvals alongside patch
    # approvals + wiki/run_jobs CRs. The legacy james_evo_log.jsonl +
    # _write_audit(...) below remain authoritative.
    approver = _bearer_username(request) or f"<role:{role}>"
    cr_shadow_id = _cr_shadow_proposal_create(
        proposal_id, approver, role, action="approve",
    )

    try:
        from tools.self.evo_analyzer import approve_and_execute
        report = approve_and_execute(proposal_id)
        _write_audit(role, "/admin/proposals/approve",
                     query=proposal_id,
                     answer=f"success={report.get('success')}")

        # CR-E.3 close — merge on success, reject on executor failure.
        if cr_shadow_id is not None:
            try:
                if report.get("success"):
                    from core.change_request_apply import merge_cr as _cr_merge
                    _cr_merge(cr_shadow_id, approver=approver)
                else:
                    from core.change_request import reject_cr as _cr_reject
                    _cr_reject(
                        cr_shadow_id, reviewer=approver,
                        reason=f"executor_failed: {str(report)[:100]}",
                    )
            except Exception:
                pass

        return report
    except Exception as e:
        if cr_shadow_id is not None:
            try:
                from core.change_request import reject_cr as _cr_reject
                _cr_reject(cr_shadow_id, reviewer=approver,
                           reason=f"exception: {str(e)[:100]}")
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/admin/proposals/{proposal_id}/reject",
          summary="제안 거부 [P7-EVO]")
async def reject_proposal_api(
    proposal_id: str,
    api_key:     str,
    request:     Request,
    reason:      str = "",
    role:        str = Depends(get_role_from_request),
):
    """[4-C] 제안 거부 + 사유 장기기억 저장."""
    _require_feature(api_key, role, "admin.evolution")

    # Stage B / CR-E.3 — shadow CR row for reject path. Same dual-write
    # rationale as approve_proposal above.
    approver = _bearer_username(request) or f"<role:{role}>"
    cr_shadow_id = _cr_shadow_proposal_create(
        proposal_id, approver, role, action="reject",
    )

    try:
        from tools.self.evo_analyzer import reject_proposal
        ok = reject_proposal(proposal_id, reason)
        _write_audit(role, "/admin/proposals/reject", query=proposal_id)

        # CR-E.3 close — reject_cr regardless of `ok` (the endpoint
        # IS the reject action; ok=False just means the storage write
        # failed). Reason mirrors the admin-supplied reason.
        if cr_shadow_id is not None:
            try:
                from core.change_request import reject_cr as _cr_reject
                _cr_reject(
                    cr_shadow_id, reviewer=approver,
                    reason=(reason or "admin_rejected")[:200]
                           + (" (storage_failed)" if not ok else ""),
                )
            except Exception:
                pass

        return {"success": ok, "proposal_id": proposal_id}
    except Exception as e:
        if cr_shadow_id is not None:
            try:
                from core.change_request import reject_cr as _cr_reject
                _cr_reject(cr_shadow_id, reviewer=approver,
                           reason=f"exception: {str(e)[:100]}")
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/admin/memory/save-rejection", summary="거부 사유 장기기억 저장 [4-C]")
async def save_rejection_memory(
    data:    RejectionRequest,
    api_key: str,
    role:    str = Depends(get_role_from_request),
):
    """[4-C] 거부 사유 → memory_store 장기기억 저장."""
    _require_feature(api_key, role, "admin.evolution")
    try:
        from core.memory import MemoryStore
        ms  = MemoryStore()
        key = f"rejection:{data.proposal_id[:12]}"
        ms.save_preference({
            "key":         key,
            "value":       data.reason,
            "type":        "rejection_reason",
            "proposal_id": data.proposal_id,
        })
        return {"ok": True, "saved_key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/evo-reports/", summary="자기진화 실행 보고서 [P7-EVO]")
async def get_evo_reports(
    api_key: str,
    limit:   int = 20,
    role:    str = Depends(get_role_from_request),
):
    """자기진화 실행 결과 보고서 목록."""
    _require_feature(api_key, role, "admin.evolution")
    try:
        from tools.self.evo_analyzer import list_reports
        return {"reports": list_reports(limit)}
    except Exception as e:
        return {"reports": [], "error": str(e)}

@router.post("/admin/proposals/generate/",
          summary="수동 제안 생성 [P7-EVO]")
async def generate_proposals(
    api_key: str, role: str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.evolution")
    try:
        from tools.self.evo_analyzer import generate_proposals_from_signals
        from llm.router import RouterWrapper
        proposals = generate_proposals_from_signals(RouterWrapper("general"))
        return {"generated": len(proposals),
                "proposals": [{"id": p["proposal_id"],
                               "title": p["title"],
                               "type": p["type"]} for p in proposals]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/admin/learn/topic/", summary="주제 학습 [P8-LEARN / 3-E 경로B]")
async def learn_topic_api(
    api_key:    str,
    topic:      str,
    use_web:    bool = True,
    role: str = Depends(get_role_from_request),
):
    """
    [경로 B / U-1 개선] 어드민 자기학습 → 웹검색 → URL본문fetch → LLM깊이처리 → 장기 지식.

    파이프라인:
      1. 웹 검색 (Tavily/DDG)
      2. 상위 2개 URL 본문 fetch
      3. LLM이 본문 + snippet 통합 → 구조화된 지식 생성
      4. wiki entity 저장 + vector 인덱싱
      5. domain 태그 자동 분류 + 지식 레벨 +5점
    """
    _require_feature(api_key, role, "admin.knowledge")
    if not topic:
        raise HTTPException(status_code=400, detail="topic 파라미터 필요")
    try:
        if use_web:
            from tools.web.web_searcher import (
                search_web, enrich_results_with_content,
                save_as_longterm,
                update_knowledge_level, classify_domain,
            )

            # ① 검색
            results = search_web(topic, max_results=5)
            if not results:
                return {"success": False, "message": "웹 검색 결과 없음"}

            # ② URL 본문 fetch (상위 2개)
            results = enrich_results_with_content(results, max_fetch=2)

            # ③ domain 자동 분류
            domain = classify_domain(topic, results)

            # ④ LLM 처리 — 컨텍스트 최소화 (한국어는 토큰 2~3배)
            # num_ctx=2048 기준: 입력 800자 이내가 안전 (#13: router 경유)
            from llm.router import RouterWrapper
            llm = RouterWrapper("extract")

            # snippet만 사용 (body 제외) — 짧고 정제된 내용
            snippet_ctx = "\n".join([
                f"{i}. {r['title']}: {r.get('snippet','')[:150]}"
                for i, r in enumerate(results[:3], 1)
                if r.get('snippet') or r.get('title')
            ])

            # 짧고 명확한 프롬프트
            knowledge_prompt = (
                f"'{topic}' 핵심 요약 (200자 이내):\n\n"
                f"{snippet_ctx[:500]}\n\n"
                f"요약:"
            )

            print(f"[LEARN] 프롬프트 길이: {len(knowledge_prompt)}자")
            knowledge = llm.call_gemma(
                knowledge_prompt, timeout=60, use_cache=False, max_tokens=300
            )

            # ⑤ LLM 0자 / 오류 sentinel → snippet 기반 fallback.
            # The old condition `len < 10` let `[Gemma 응답 없음]` (13
            # chars) and `[Gemma 오류] ...` through. Those then got
            # written to `attributes.summary` and the body's `## 요약`
            # — the graph node detail panel showed the sentinel string
            # to the operator. Treat any ERROR_PREFIXES response as
            # equivalent to empty so the fallback kicks in.
            from core.gemma_client import ERROR_PREFIXES
            _knowledge_stripped = (knowledge or "").strip()
            if (
                not _knowledge_stripped
                or len(_knowledge_stripped) < 10
                or _knowledge_stripped.startswith(ERROR_PREFIXES)
            ):
                print(f"[LEARN] LLM empty/error ('{_knowledge_stripped[:30]}') → fallback 사용")
                parts = []
                for r in results[:3]:
                    title = r.get('title', '')
                    snip = r.get('snippet', '') or r.get('body', '')[:200]
                    if title or snip:
                        parts.append(f"{title}: {snip[:150]}")
                knowledge = f"{topic} 요약:\n" + "\n".join(parts) if parts else f"{topic}: 웹 검색 결과 참조"

            # ⑥ wiki entity 저장 — 예외 완전 격리
            path = None
            try:
                path = save_as_longterm(
                    query=topic, results=results,
                    summary=knowledge, user_role="admin",
                    domain=domain,
                )
            except Exception as save_err:
                print(f"[LEARN] wiki 저장 실패 (무시): {save_err}")
                # 저장 실패해도 학습 내용은 반환

            # ⑥ 지식 레벨 +5점 (의도적 장기 학습)
            update_knowledge_level(topic, is_longterm=True)

            sources = [r["url"] for r in results if r.get("url")]
            fetched = sum(1 for r in results if r.get("body"))

            return {
                "success":      True,
                "topic":        topic,
                "domain":       domain,
                "knowledge":    knowledge[:300],
                "wiki_path":    str(path) if path else None,
                "sources":      sources[:3],
                "fetched_urls": fetched,
                "method":       "web_search + url_fetch + llm",
            }

        # use_web=False → 기존 LLM 자기학습
        from tools.self.self_learner import learn_topic
        result = learn_topic(topic)
        if not result:
            return {"success": False, "message": "학습 실패 또는 품질 미달"}
        return {"success": True, "topic": result["topic"],
                "quality": result["quality"], "sources": result["sources"],
                "proposal_id": result["proposal"].get("proposal_id", "")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/admin/learn/from-errors/", summary="오류 쿼리 자동 학습 [P8-LEARN]")
async def learn_from_errors_api(
    api_key: str, role: str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.knowledge")
    try:
        from tools.self.self_learner import learn_from_errors
        results = learn_from_errors()
        return {"learned": len(results),
                "topics": [{"topic": r["topic"],
                            "quality": r["quality"]} for r in results]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/learn/error-queries/", summary="반복 오류 쿼리 [P8-LEARN]")
async def get_error_queries(
    api_key: str, min_count: int = 2,
    role: str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.evolution")
    try:
        from tools.self.importance_scorer import get_repeated_errors
        return {"error_queries": get_repeated_errors(min_count)}
    except Exception as e:
        return {"error_queries": [], "error": str(e)}

@router.get("/admin/patches", summary="Patch 이력 [P7]")
async def admin_patches(api_key: str, status: str = "all",
                        role: str = Depends(get_role_from_request)):
    _require_feature(api_key, role, "admin.evolution")
    try:
        from tools.patch.patch_generator import list_patches
        return {"patches": list_patches(status)}
    except Exception as e:
        return {"patches": [], "error": str(e)}

@router.post("/admin/patch/approve", summary="Patch 승인 [#48 phase 1]")
async def admin_patch_approve(request: Request, role: str = Depends(get_role_from_request)):
    """Approve + deploy a pending patch.

    #48 phase 1 contract:
      - 403 unless `JAMES_ENABLE_EVOLUTION=1` (operator opt-in).
      - Caller must include `approver_username` in the JSON body —
        the audit log records WHO approved each deployed patch.
      - Caller's resolved role must equal `JAMES_EVOLUTION_APPROVER_ROLE`
        (default "admin"). Other admin endpoints already enforce
        admin via `_require_admin`; this gate adds the explicit
        "approver-role" check so the env var stays load-bearing.
      - On success the patch JSON is updated in place with
        `approver_username` / `approver_role` / `approved_at` /
        `approval_method`, and the lifecycle is recorded in
        `james_patch_log.jsonl` (visible via /admin/audit).
    """
    body = await request.json()
    _require_feature(body.get("api_key",""), role, "admin.evolution")

    # #48 phase 1 — opt-in gate.
    from config import EVOLUTION_ENABLED, APPROVER_ROLE
    if not EVOLUTION_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="evolution_disabled: set JAMES_ENABLE_EVOLUTION=1 to enable",
        )
    if role != APPROVER_ROLE:
        raise HTTPException(
            status_code=403,
            detail=f"approver_role_mismatch: required {APPROVER_ROLE!r}, got {role!r}",
        )

    patch_id          = body.get("patch_id", "").strip()
    approver_username = (body.get("approver_username") or "").strip()
    approval_method   = (body.get("approval_method") or "api").strip()

    if not patch_id:
        raise HTTPException(status_code=400, detail="patch_id required")
    if not approver_username:
        raise HTTPException(status_code=400, detail="approver_username required (#48 audit)")

    try:
        from tools.patch.patch_generator import load_patch
        from tools.patch.patch_validator import validate_patch
        from tools.patch.patch_applier   import apply as patch_apply
        from tools.patch.approval        import record_approval, record_outcome

        patch = load_patch(patch_id)
        if not patch:
            raise HTTPException(status_code=404, detail="Patch 없음")

        passed, failures = validate_patch(patch)
        if not passed:
            return {"success": False, "failures": failures}

        # Record approver BEFORE apply — if apply crashes, the audit
        # log still shows who tried to deploy what. Restoring this
        # ordering is the entire reason this PR exists.
        rec_ok, rec = record_approval(
            patch_id          = patch_id,
            approver_username = approver_username,
            approver_role     = role,
            approval_method   = approval_method,
        )
        if not rec_ok:
            raise HTTPException(status_code=500, detail=f"approval_record_failed: {rec.get('error')}")

        # Stage B / CR-E.2 (2026-05-24) — shadow Change Request row.
        # Best-effort dual-write so /admin/audit/cr can surface the
        # approval event with the same shape as wiki_entity / run_jobs
        # CRs. The legacy james_patch_log.jsonl + record_outcome below
        # remain authoritative for the deploy timeline; the CR row is
        # additive and its apply handler is a no-op (Stage B CR-E.1
        # in core/change_request_apply.py). Failures here NEVER block
        # the deploy path.
        cr_shadow_id = None
        try:
            import hashlib as _hashlib
            import json as _json_cr
            from core.change_request import (
                TARGET_SELF_EVO_PATCH, create_cr as _cr_create,
            )
            _patch_canon = _json_cr.dumps(rec, sort_keys=True, ensure_ascii=False)
            _base_hash = _hashlib.sha256(_patch_canon.encode("utf-8")).hexdigest()[:16]
            _shadow = _cr_create(
                target_type   = TARGET_SELF_EVO_PATCH,
                target_id     = patch_id,
                title         = f"patch:{patch_id}",
                description   = f"approval_method={approval_method}",
                proposed_diff = {
                    "target":            rec.get("target", ""),
                    "patch_id":          patch_id,
                    "approver_username": approver_username,
                    "approval_method":   approval_method,
                },
                base_hash = _base_hash,
                proposer  = approver_username or "<system>",
                role      = role,
            )
            cr_shadow_id = _shadow.cr_id
        except Exception:
            pass

        # Re-load with approval fields baked in so apply() sees the
        # final patch shape (forward-compat — applier may grow to
        # honor approval metadata).
        patch = rec
        ok, msg = patch_apply(patch, validated=True)

        # If apply() itself failed, no bench gate to run — record and exit.
        if not ok:
            record_outcome(patch_id, "rolled_back", detail=f"apply failed: {msg}")
            if cr_shadow_id is not None:
                try:
                    from core.change_request import reject_cr as _cr_reject
                    _cr_reject(cr_shadow_id, reviewer=approver_username,
                               reason=f"apply_failed: {msg[:100]}")
                except Exception:
                    pass
            return {
                "success":           False,
                "message":           msg,
                "outcome":           "rolled_back",
                "patch_id":          patch_id,
                "approver_username": approver_username,
                "approver_role":     role,
                "approval_method":   approval_method,
            }

        # #68 phase 2-A: bench eval gate. Re-runs STEP 7 against the
        # live server in a subprocess (asyncio.to_thread so the event
        # loop can serve the bench's incoming /query/ requests). On
        # regression, the gate auto-rolls-back inside run_bench_gate
        # and returns outcome_label='rolled_back'.
        from tools.patch.bench_gate import run_bench_gate
        gate = await run_bench_gate(patch_id, patch.get("target", ""))

        record_outcome(
            patch_id, gate.outcome_label,
            detail=gate.detail,
            before_metrics=gate.before_metrics,
            after_metrics=gate.after_metrics,
        )

        # Stage B / CR-E.2 — close the shadow CR row. Bench-gate pass
        # → merge_cr; regression → reject_cr (legacy lifecycle already
        # rolled back the file). Best-effort.
        if cr_shadow_id is not None:
            try:
                if gate.passed:
                    from core.change_request_apply import merge_cr as _cr_merge
                    _cr_merge(cr_shadow_id, approver=approver_username)
                else:
                    from core.change_request import reject_cr as _cr_reject
                    _cr_reject(
                        cr_shadow_id,
                        reviewer=approver_username,
                        reason=f"bench_regression: {gate.outcome_label}: "
                               f"{(gate.detail or '')[:100]}",
                    )
            except Exception:
                pass

        return {
            "success":           gate.passed,
            "message":           msg,
            "outcome":           gate.outcome_label,
            "before_metrics":    gate.before_metrics,
            "after_metrics":     gate.after_metrics,
            "patch_id":          patch_id,
            "approver_username": approver_username,
            "approver_role":     role,
            "approval_method":   approval_method,
        }
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/patch/audit", summary="Patch 라이프사이클 감사 조회 [#68 phase 2-C]")
async def admin_patch_audit(
    api_key:        str,
    since:          str  = "",
    approver:       str  = "",
    outcome:        str  = "",
    limit:          int  = 200,
    include_shadow: bool = True,
    role:           str  = Depends(get_role_from_request),
):
    """Filtered, newest-first slice of `james_patch_log.jsonl`.

    Filters (all optional; combine for AND semantics):
      since:    ISO 8601 lower bound (e.g. "2026-05-08" or full datetime)
      approver: case-insensitive exact `approver_username` match
      outcome:  case-insensitive `outcome` match — `deployed` /
                `rolled_back` / `deployed_gate_skipped`
      limit:    max entries returned (default 200, hard cap 1000)
      include_shadow: when True (default), merges projected self-evolution
                     CR-shadow rows (Stage B / CR-E) into the feed. Each
                     shadow row carries ``_source='cr_shadow'``. Set False
                     to get the byte-identical pre-CR-E view.

    See `tools/patch/audit_query.py` for filter semantics + rationale.
    Composes with `/admin/audit` (the broader, multi-source feed) —
    this endpoint is the patch-specific view.
    """
    _require_feature(api_key, role, "admin.evolution")
    from tools.patch.audit_query import query_patch_audit
    rows = query_patch_audit(
        since=since or None,
        approver=approver or None,
        outcome=outcome or None,
        limit=limit,
        include_shadow=include_shadow,
    )
    return {
        "filters": {
            "since":          since,
            "approver":       approver,
            "outcome":        outcome,
            "limit":          limit,
            "include_shadow": include_shadow,
        },
        "count": len(rows),
        "events": rows,
    }

@router.post("/admin/patch/reject", summary="Patch 거부 [P7]")
async def admin_patch_reject(request: Request, role: str = Depends(get_role_from_request)):
    body = await request.json()
    _require_feature(body.get("api_key",""), role, "admin.evolution")
    patch_id = body.get("patch_id","")
    from pathlib import Path
    pf = Path(f"./workspace/patches/{patch_id}.json")
    if pf.exists():
        d = json.loads(pf.read_text(encoding="utf-8"))
        d["status"] = "REJECTED"
        pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True, "patch_id": patch_id, "status": "REJECTED"}
