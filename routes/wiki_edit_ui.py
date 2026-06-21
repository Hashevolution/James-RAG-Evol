"""Workspace document-edit endpoints — load / draft / apply (v18.7).

Powers the workspace "추론 편집" modal: load a wiki entity's body onto
the screen, optionally mouse-select a region, give James a natural-
language instruction, preview the LLM-drafted new body, then apply.

Three admin-gated endpoints (all reuse the SAME audited primitives the
chat ``wiki_edit`` mode uses — ``read_entity`` / ``update_entity`` from
``tools/wiki/wiki_editor.py`` — so backup + audit log + vector/index
resync happen exactly as before):

  GET  /admin/wiki/edit/source?name=<entity>
        → {name, found, body, base_hash}
        Unblocks the base_hash gap the CR propose form has: the client
        no longer has to compute a SHA by hand.

  POST /admin/wiki/edit/draft  {name, instruction, selected_text?}
        → {name, current_body, draft_body, base_hash, model}
        Dry-run: reads the entity, asks the measured wiki_edit model
        (resolve_for_mode("wiki_edit") → gemma3:12b) to apply the
        instruction (optionally focused on the selected region), and
        returns the proposed new body WITHOUT writing.

  POST /admin/wiki/edit/apply  {name, new_body, base_hash}
        → {applied, new_hash}
        Optimistic-lock: re-reads the entity, recomputes the hash, and
        rejects (409) if it shifted since the draft was made (someone
        else edited in between). Otherwise writes via update_entity.

``base_hash`` is the SHA-256 of the entity's read_text() content; both
source and apply compute it the same way (over read_entity output) so
the conflict check is consistent.
"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routes._helpers import (
    _require_feature,
    _write_audit,
    get_role_from_request,
)

router = APIRouter()


# ─── Pydantic ───
class _DraftRequest(BaseModel):
    api_key:       str
    name:          str
    instruction:   str
    selected_text: str = ""


class _ApplyRequest(BaseModel):
    api_key:   str
    name:      str
    new_body:  str
    base_hash: str


# ─── Helpers ───
def _entity_hash(text: str) -> str:
    """SHA-256 of the entity body text. Consistent across source/apply
    (both hash read_entity() output) so the optimistic-lock conflict
    check is reliable."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _draft_prompt(current: str, instruction: str, selected_text: str) -> str:
    """Build the wiki_edit-style edit prompt. When a selection is given,
    the model is told to focus there while keeping the whole document
    consistent."""
    sel = (selected_text or "").strip()
    focus = (
        f"\n[선택한 부분]\n{sel}\n"
        "특히 이 부분을 중심으로 수정하되, 문서 전체의 일관성을 유지하라.\n"
        if sel else ""
    )
    return (
        "아래 wiki 문서를 다음 지시에 맞게 수정하라.\n"
        f"지시: {instruction}\n"
        f"{focus}"
        f"\n[현재 내용]\n{current}\n\n"
        "수정된 전체 내용만 출력하라 (frontmatter 포함, 설명 없이):"
    )


# ─── Endpoints ───
@router.get("/admin/wiki/edit/source",
            summary="문서 편집 — 현재 본문 + base_hash 로드 [v18.7]")
async def edit_source(
    name:    str,
    api_key: str,
    role:    str = Depends(get_role_from_request),
):
    """Return the entity body + its base_hash so the workspace can
    display it and later submit a conflict-checked edit."""
    _require_feature(api_key, role, "admin.data")

    from tools.wiki.wiki_editor import read_entity
    ok, content, msg = read_entity(name)
    if not ok:
        return {"name": name, "found": False, "body": "", "base_hash": "",
                "message": msg}
    return {
        "name":      name,
        "found":     True,
        "body":      content,
        "base_hash": _entity_hash(content),
    }


@router.post("/admin/wiki/edit/draft",
             summary="문서 편집 — 추론 지시로 초안 생성 (미적용) [v18.7]")
async def edit_draft(
    data: _DraftRequest,
    role: str = Depends(get_role_from_request),
):
    """Dry-run edit: LLM drafts the new body from the instruction; no
    write. Uses the measured wiki_edit model preference."""
    _require_feature(data.api_key, role, "admin.data")
    if not (data.instruction or "").strip():
        raise HTTPException(status_code=400, detail="지시(instruction)가 비었습니다.")

    from tools.wiki.wiki_editor import read_entity
    ok, current, msg = read_entity(data.name)
    if not ok:
        raise HTTPException(status_code=404, detail=msg)

    # Measured wiki_edit preference (Phase wiki_edit-c → gemma3:12b).
    model = ""
    try:
        from core.model_resolver import resolve_for_mode
        model = resolve_for_mode("wiki_edit", requested="").tag or ""
    except Exception:
        model = ""

    from core.reasoning.trace_helpers import trace_synth_call
    draft = trace_synth_call(
        _draft_prompt(current, data.instruction, data.selected_text),
        applied_rule="reasoning.synth.wiki_edit_ui_draft",
        user_role=role,
        timeout=90,
        use_cache=False,
        model=model or None,
    ) or ""
    draft = draft.strip()
    if not draft:
        raise HTTPException(status_code=502, detail="초안 생성 실패 (빈 응답)")

    return {
        "name":         data.name,
        "current_body": current,
        "draft_body":   draft,
        "base_hash":    _entity_hash(current),
        "model":        model or "(default)",
    }


@router.post("/admin/wiki/edit/apply",
             summary="문서 편집 — 초안 적용 (충돌 검사) [v18.7]")
async def edit_apply(
    data: _ApplyRequest,
    role: str = Depends(get_role_from_request),
):
    """Apply the (possibly hand-tweaked) new body. Optimistic-lock: the
    entity must still hash to base_hash, else 409 (someone edited in
    between). Reuses update_entity → backup + audit + vector resync."""
    _require_feature(data.api_key, role, "admin.data")
    if not (data.new_body or "").strip():
        raise HTTPException(status_code=400, detail="새 본문이 비었습니다.")

    from tools.wiki.wiki_editor import read_entity, update_entity
    ok, current, msg = read_entity(data.name)
    if not ok:
        raise HTTPException(status_code=404, detail=msg)

    if _entity_hash(current) != (data.base_hash or ""):
        raise HTTPException(
            status_code=409,
            detail="문서가 불러온 이후 변경되었습니다. 다시 불러와 편집하세요.",
        )

    applied, apply_msg = update_entity(data.name, data.new_body, role)
    if not applied:
        raise HTTPException(status_code=400, detail=apply_msg)

    _write_audit(role, "/admin/wiki/edit/apply", query=data.name[:80],
                 answer=apply_msg[:80])
    return {
        "applied":  True,
        "name":     data.name,
        "new_hash": _entity_hash(data.new_body),
        "message":  apply_msg,
    }
