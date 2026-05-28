"""Workspace jobs + scheduler routes.

Extracted from server_llmwiki.py per docs/design/v0.4.x-server-split.md
PR-C. 9 endpoints + 3 Pydantic models moved verbatim — handler body
byte-identical (only ``@app.<m>`` -> ``@router.<m>``).

URL invariant: ``python scripts/audit_endpoint_paths.py origin/main``
must report 0-diff against the pre-PR-C baseline.
"""
from __future__ import annotations

import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from routes._helpers import (
    _bearer_username,
    _require_feature,
    _write_audit,
    get_client_ip,
    get_role_from_request,
)

router = APIRouter()


# ─── Pydantic models ───────────────────────────────────────────────

class JobRunRequest(BaseModel):
    job_type:   str
    input_refs: list = []
    options:    Optional[dict] = None

class JobScheduleRequest(BaseModel):
    job_type:      str
    input_refs:    list = []
    options:       Optional[dict] = None
    schedule_cron: str   # "hourly" | "every:N" | "daily:HH:MM" | "weekly:DOW:HH:MM"

class JobUnscheduleRequest(BaseModel):
    job_id: str

# ─── Endpoints ─────────────────────────────────────────────────────

@router.post("/jobs/run", summary="워크스페이스 job 실행 (W8-A)")
async def jobs_run(
    data:    JobRunRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    """workspace.run_jobs feature gate. Owner is the JWT subject
    (no JWT → 401 — anonymous can't run jobs). Body has no owner
    field; the server is the source of truth."""
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "workspace.run_jobs").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (workspace.run_jobs)")
    owner = _bearer_username(request)
    if not owner:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    from core.workspace import register_job, execute_job, HANDLERS
    if data.job_type not in HANDLERS:
        raise HTTPException(status_code=400,
                            detail=f"unknown job_type: {data.job_type}")
    job_id = register_job(data.job_type, data.input_refs or [],
                          owner=owner, options=data.options)
    ip = get_client_ip(request)
    _write_audit(role, "/jobs/run", query=f"{data.job_type}/{job_id}",
                 security_event="job_started", ip_address=ip)
    row = execute_job(job_id)
    final_event = "job_done" if row["status"] == "done" else f"job_{row['status']}"
    _write_audit(role, "/jobs/run", query=f"{data.job_type}/{job_id}",
                 security_event=final_event, ip_address=ip)
    return row

@router.post("/jobs/schedule",
          summary="워크스페이스 job 예약 (정기 실행, W8-D)")
async def jobs_schedule(
    data:    JobScheduleRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    """Insert a scheduled job. ``workspace.schedule`` feature gate
    (admin only by default — cron-driven jobs touch shared resources
    so the grant is intentionally narrow).

    The DSL is validated up front: an unrecognised spec returns 400
    rather than persisting a row that the scheduler would silently
    ignore. The first ``next_run_at`` is computed from the spec; the
    Scheduler updates it after each successful tick.
    """
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "workspace.schedule").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (workspace.schedule)")
    owner = _bearer_username(request)
    if not owner:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    from core.workspace import register_job, HANDLERS
    from core.scheduler import compute_next_run
    if data.job_type not in HANDLERS:
        raise HTTPException(status_code=400,
                            detail=f"unknown job_type: {data.job_type}")

    now = int(time.time())
    next_at = compute_next_run(data.schedule_cron, now)
    if next_at is None:
        raise HTTPException(
            status_code=400,
            detail=(f"unknown schedule spec: {data.schedule_cron!r}. "
                    "Use 'hourly' / 'every:N' / 'daily:HH:MM' / "
                    "'weekly:DOW:HH:MM'."),
        )

    job_id = register_job(
        data.job_type, data.input_refs or [],
        owner=owner, options=data.options,
        schedule_cron=data.schedule_cron, next_run_at=next_at,
    )
    ip = get_client_ip(request)
    _write_audit(role, "/jobs/schedule",
                 query=f"{data.job_type}/{job_id}",
                 security_event=f"scheduled cron={data.schedule_cron}",
                 ip_address=ip)
    return {
        "ok":            True,
        "job_id":        job_id,
        "schedule_cron": data.schedule_cron,
        "next_run_at":   next_at,
    }

@router.post("/jobs/unschedule",
          summary="정기 실행 해제 (W8-D follow-up)")
async def jobs_unschedule(
    data:    JobUnscheduleRequest,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    """Converts a scheduled row back into a one-shot. Mirror of
    /jobs/schedule's authority surface — workspace.schedule
    (admin-only default). 404 when the job doesn't exist or is
    already a one-shot."""
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "workspace.schedule").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (workspace.schedule)")
    from core.scheduler import unschedule_job
    ok = unschedule_job(data.job_id)
    ip = get_client_ip(request)
    if not ok:
        _write_audit(role, "/jobs/unschedule", query=data.job_id,
                     security_event="unschedule_failed (unknown or one-shot)",
                     ip_address=ip)
        raise HTTPException(
            status_code=404,
            detail="해당 job 이 없거나 이미 정기실행이 아닙니다.",
        )
    _write_audit(role, "/jobs/unschedule", query=data.job_id,
                 security_event="unscheduled", ip_address=ip)
    return {"ok": True, "job_id": data.job_id}

@router.get("/admin/scheduler/status",
         summary="스케줄러 상태 + 다음 firing 목록 (W8-D follow-up)")
async def admin_scheduler_status(
    api_key: str,
    limit:   int = 20,
    role:    str = Depends(get_role_from_request),
):
    """Scheduler health snapshot.

    Returns the live ``default_scheduler`` state (is_running,
    poll_interval_sec, retention_days, last_retention) plus the next
    N scheduled rows sorted by ``next_run_at``. Operator can spot
    "scheduler stopped" (is_running=False), "retention never ran"
    (last_retention=0), or "this job is stuck" (next_run_at in the
    past) at a glance.

    Gated by admin.metrics (matches /admin/metrics / dashboard).
    """
    _require_feature(api_key, role, "admin.metrics")
    from core.scheduler import default_scheduler, list_upcoming_scheduled
    return {
        "is_running":         default_scheduler.is_running(),
        "poll_interval_sec":  default_scheduler.poll_interval_sec,
        "retention_days":     default_scheduler.retention_days,
        "last_retention_at":  default_scheduler._last_retention,
        "now":                int(time.time()),
        "upcoming":           list_upcoming_scheduled(limit=limit),
    }

@router.get("/jobs/list", summary="내 job 목록 (W8-A)")
async def jobs_list(
    request: Request,
    status:  str = "",
    limit:   int = 50,
    offset:  int = 0,
    role:    str = Depends(get_role_from_request),
):
    """Self-view — gated by workspace.view (lower bar than
    run_jobs; reading your own queue is universally useful)."""
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "workspace.view").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (workspace.view)")
    owner = _bearer_username(request)
    if not owner:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    from core.workspace import list_jobs, count_jobs
    s = status.strip() or None
    return {
        "items":  list_jobs(owner=owner, status=s, limit=limit, offset=offset),
        "total":  count_jobs(owner=owner, status=s),
        "status": s or "",
        "limit":  limit,
        "offset": offset,
    }

@router.get("/jobs/{job_id}", summary="내 job 상세 (W8-A)")
async def jobs_detail(
    job_id:  str,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "workspace.view").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (workspace.view)")
    owner = _bearer_username(request)
    if not owner:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    from core.workspace import get_job
    row = get_job(job_id, requester_username=owner)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return row

@router.get("/jobs/{job_id}/download", summary="job 결과 다운로드 (W8-A)")
async def jobs_download(
    job_id:  str,
    request: Request,
    role:    str = Depends(get_role_from_request),
):
    """Stream the produced file. Cross-owner access surfaces as 404
    (the row lookup returns None for non-owners; we don't leak the
    job_id space)."""
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "workspace.view").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (workspace.view)")
    owner = _bearer_username(request)
    if not owner:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    from core.workspace import get_job
    row = get_job(job_id, requester_username=owner)
    if row is None or not row.get("output_path"):
        raise HTTPException(status_code=404, detail="job result not found")
    try:
        from config import BASE_DIR
        full = os.path.join(BASE_DIR, row["output_path"])
    except ImportError:
        full = row["output_path"]
    if not os.path.exists(full):
        raise HTTPException(status_code=404, detail="output file missing on disk")
    return FileResponse(full, filename=os.path.basename(full))

@router.get("/admin/jobs/list", summary="모든 job 목록 — admin (W8-A)")
async def admin_jobs_list(
    api_key: str,
    status:  str = "",
    limit:   int = 50,
    offset:  int = 0,
    role:    str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.data")
    from core.workspace import list_jobs, count_jobs
    s = status.strip() or None
    return {
        "items":  list_jobs(status=s, limit=limit, offset=offset),
        "total":  count_jobs(status=s),
        "status": s or "",
        "limit":  limit,
        "offset": offset,
    }

@router.get("/admin/jobs/{job_id}", summary="job 상세 — admin (W8-A)")
async def admin_jobs_detail(
    job_id:  str,
    api_key: str,
    role:    str = Depends(get_role_from_request),
):
    _require_feature(api_key, role, "admin.data")
    from core.workspace import get_job
    row = get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return row
