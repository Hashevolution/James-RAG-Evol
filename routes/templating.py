"""Template Formatting Engine routes (v0.6, horizontal).

Operator registers a template (user data), pastes raw content, and JAMES
reshapes it onto the template structure and returns a downloadable file.
JAMES ships zero templates (CLAUDE.md rule #1) — every template here is
runtime workspace data. See docs/design/v0.6-template-formatting-ui.md +
ARCHITECTURE §5.7.14.

Authorization mirrors routes/artifacts.py: endpoints require a logged-in
JWT subject (the owner) and gate on the ``data.view_own`` feature. A
template owned by someone else surfaces 404 (no existence leak).
"""
from __future__ import annotations

from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel

from core.templating import (
    TemplateStoreError,
    create_template,
    delete_template,
    format_content,
    get_template,
    ingest_image,
    list_outputs,
    list_templates,
    new_output_id,
    parse_template,
    read_output,
    render,
    save_output,
)
from core.templating.render import VALID_FORMATS, extension_for
from routes._helpers import (
    _bearer_username,
    _write_audit,
    get_role_from_request,
)

router = APIRouter()


# ─── Pydantic ───────────────────────────────────────────────────────

class CreateTemplateRequest(BaseModel):
    name: str
    raw_text: str
    mode: str = "text"


class ApplyTemplateRequest(BaseModel):
    raw_content: str
    fmt: str = "md"
    max_tokens: int = 2048


# ─── Helpers ────────────────────────────────────────────────────────

def _owner_or_401(request: Request, role: str) -> str:
    """Resolve the JWT subject + feature gate, else raise 401/403."""
    from core.policy_engine import default_engine as _pe
    if not _pe.can_use_feature(role, "data.view_own").allowed:
        raise HTTPException(status_code=403,
                            detail="권한이 부족합니다. (data.view_own)")
    username = _bearer_username(request)
    if not username:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return username


# ─── Endpoints ──────────────────────────────────────────────────────

@router.post("/templates/", summary="양식 등록 (v0.6 template engine)")
async def create_template_route(
    body: CreateTemplateRequest,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    """Register a template from pasted text / decoded file content.

    Image-sourced templates are decoded to text by the caller (PR-5)
    and posted here with ``mode="image"``.
    """
    owner = _owner_or_401(request, role)
    try:
        meta = create_template(
            body.name, body.raw_text, owner=owner, mode=body.mode
        )
    except TemplateStoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _write_audit(role, "/templates/", query=f"create:{meta['id']}")
    return meta


# Cap the OCR upload so a hostile client can't exhaust disk/CPU. 12 MB
# is generous for a scanned form page; tune via the constant if needed.
_MAX_IMAGE_BYTES = 12 * 1024 * 1024


@router.post("/templates/ingest-image", summary="이미지 양식 → OCR 텍스트")
async def ingest_image_route(
    request: Request,
    file: UploadFile = File(...),
    role: str = Depends(get_role_from_request),
):
    """OCR an uploaded image to raw template text (image input mode).

    Returns ``{"raw_text": ..., "mode": "image"}``. The caller reviews
    the extracted text, then POSTs it to ``/templates/`` with
    ``mode="image"`` to register the template. OCR runs on-box
    (Tesseract) — the image bytes never leave the machine.
    """
    _owner_or_401(request, role)
    import os
    import tempfile

    ext = os.path.splitext(file.filename or "")[1].lower() or ".png"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"이미지가 너무 큽니다 (최대 {_MAX_IMAGE_BYTES // (1024*1024)}MB).",
        )

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="james_tpl_ocr_")
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        try:
            raw_text = ingest_image(tmp_path)
        except TemplateStoreError as e:
            raise HTTPException(status_code=400, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    _write_audit(role, "/templates/ingest-image",
                 query=f"ocr:{file.filename or '?'}")
    return {"raw_text": raw_text, "mode": "image"}


@router.get("/templates/mine/list", summary="내 양식 목록")
async def list_templates_route(
    request: Request,
    role: str = Depends(get_role_from_request),
):
    owner = _owner_or_401(request, role)
    return {"items": list_templates(owner=owner)}


@router.get("/templates/{template_id}", summary="양식 상세 + 파싱 구조")
async def get_template_route(
    template_id: str,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    owner = _owner_or_401(request, role)
    try:
        tpl = get_template(template_id, requester=owner)
    except TemplateStoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if tpl is None:
        raise HTTPException(status_code=404, detail="template not found")
    spec = parse_template(tpl["raw"])
    return {**tpl, "spec": spec.to_dict(), "outputs": list_outputs(template_id)}


@router.delete("/templates/{template_id}", summary="양식 삭제")
async def delete_template_route(
    template_id: str,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    owner = _owner_or_401(request, role)
    try:
        ok = delete_template(template_id, requester=owner)
    except TemplateStoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="template not found")
    _write_audit(role, "/templates/", query=f"delete:{template_id}")
    return {"deleted": True, "id": template_id}


@router.post("/templates/{template_id}/apply", summary="양식 적용 — raw 내용 → 포맷 파일")
async def apply_template_route(
    template_id: str,
    body: ApplyTemplateRequest,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    """Reshape ``raw_content`` onto the template; render + store output.

    Returns the output id/filename + a text preview. Download via
    ``GET /templates/{id}/output/{out_id}``.
    """
    owner = _owner_or_401(request, role)
    if body.fmt not in VALID_FORMATS:
        raise HTTPException(status_code=400,
                            detail=f"fmt must be one of {VALID_FORMATS}")
    try:
        tpl = get_template(template_id, requester=owner)
    except TemplateStoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if tpl is None:
        raise HTTPException(status_code=404, detail="template not found")

    try:
        formatted = format_content(
            body.raw_content,
            template_raw=tpl["raw"],
            max_tokens=max(256, min(int(body.max_tokens or 2048), 8192)),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"formatting failed: {e}")

    out_id = new_output_id()
    data = render(formatted, body.fmt, title=tpl.get("name") or template_id)
    save_output(template_id, out_id, extension_for(body.fmt), data)
    _write_audit(role, "/templates/", query=f"apply:{template_id}",
                 answer=f"out:{out_id} fmt:{body.fmt}")
    return {
        "template_id": template_id,
        "out_id": out_id,
        "fmt": body.fmt,
        "filename": f"{out_id}{extension_for(body.fmt)}",
        "preview": formatted[:2000],
    }


_MEDIA = {".md": "text/markdown; charset=utf-8",
          ".txt": "text/plain; charset=utf-8",
          ".html": "text/html; charset=utf-8"}


@router.get("/templates/{template_id}/output/{out_id}", summary="결과 파일 다운로드")
async def download_output_route(
    template_id: str,
    out_id: str,
    request: Request,
    role: str = Depends(get_role_from_request),
):
    owner = _owner_or_401(request, role)
    try:
        tpl = get_template(template_id, requester=owner)
        if tpl is None:
            raise HTTPException(status_code=404, detail="template not found")
        found = read_output(template_id, out_id)
    except TemplateStoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if found is None:
        raise HTTPException(status_code=404, detail="output not found")
    data, filename = found
    import os
    media = _MEDIA.get(os.path.splitext(filename)[1], "application/octet-stream")
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
