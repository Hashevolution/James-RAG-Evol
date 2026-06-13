"""Workspace-backed CRUD for user-supplied templates.

Templates are **user data**, not code assets (CLAUDE.md rule #1). They
live under ``workspace_path("templates")`` — one directory per template
holding the raw text + a small ``meta.json``. JAMES ships none; every
template here was created at runtime by an operator.

On-disk layout::

    <workspace>/templates/<template_id>/template.txt   # raw template text
    <workspace>/templates/<template_id>/meta.json       # id/name/owner/...
    <workspace>/templates/<template_id>/out/<out_id>.<ext>   # rendered outputs

Path safety: ``template_id`` / ``out_id`` must match the path-safe
identifier pattern (``^[a-z][a-z0-9_-]*$``) — the same shape the SDK
scaffolder + per-tenant workspace enforce — so a request-supplied id can
never traverse outside the templates root. See
``docs/design/v0.6-template-formatting-ui.md`` §7.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import List, Optional

from core.plugins.workspace import workspace_path

# Same path-safe identifier shape as core/plugins/workspace.py
# (_TENANT_ID_RE) and the pack scaffolder. Rules out separators, dots,
# NUL, shell metachars, and case-folding ambiguity.
_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")

VALID_MODES = ("text", "file", "image")


class TemplateStoreError(Exception):
    """Raised on invalid ids / inputs at the storage boundary."""


def _templates_root() -> Path:
    root = workspace_path("templates")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _validate_id(value: str, *, what: str = "template_id") -> str:
    if not isinstance(value, str) or not value:
        raise TemplateStoreError(f"{what} must be a non-empty string")
    if not _ID_RE.match(value):
        raise TemplateStoreError(
            f"{what} {value!r} is not path-safe; must match {_ID_RE.pattern}"
        )
    return value


def _slugify(name: str) -> str:
    """Best-effort slug from a display name; always path-safe."""
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    if not s or not s[0].isalpha():
        s = "t-" + s if s else "t"
    return s[:40].strip("-") or "t"


def _gen_id(name: str) -> str:
    return f"{_slugify(name)}-{uuid.uuid4().hex[:8]}"


def _tpl_dir(template_id: str) -> Path:
    _validate_id(template_id)
    return _templates_root() / template_id


def _read_meta(tpl_dir: Path) -> Optional[dict]:
    meta_path = tpl_dir / "meta.json"
    if not meta_path.is_file():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def create_template(
    name: str,
    raw_text: str,
    *,
    owner: str,
    mode: str = "text",
) -> dict:
    """Create a template; returns its meta dict.

    ``name`` is a display label (any text). ``owner`` is the JWT subject
    that owns the template (scopes list/get/delete). ``mode`` records how
    the raw text was sourced (text/file/image).
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise TemplateStoreError("template raw_text must be non-empty")
    if mode not in VALID_MODES:
        raise TemplateStoreError(f"mode must be one of {VALID_MODES}")
    if not owner:
        raise TemplateStoreError("owner is required")

    template_id = _gen_id(name)
    tpl_dir = _tpl_dir(template_id)
    tpl_dir.mkdir(parents=True, exist_ok=True)

    (tpl_dir / "template.txt").write_text(raw_text, encoding="utf-8")
    meta = {
        "id": template_id,
        "name": (name or template_id).strip(),
        "owner": owner,
        "mode": mode,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (tpl_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta


def get_template(
    template_id: str,
    *,
    requester: Optional[str] = None,
) -> Optional[dict]:
    """Return ``{**meta, "raw": <text>}`` or ``None``.

    When ``requester`` is given, a template owned by someone else returns
    ``None`` (so the route surfaces 404, not 403 — no existence leak).
    """
    tpl_dir = _tpl_dir(template_id)
    meta = _read_meta(tpl_dir)
    if meta is None:
        return None
    if requester is not None and meta.get("owner") != requester:
        return None
    raw_path = tpl_dir / "template.txt"
    raw = raw_path.read_text(encoding="utf-8") if raw_path.is_file() else ""
    return {**meta, "raw": raw}


def list_templates(*, owner: Optional[str] = None) -> List[dict]:
    """List template meta dicts, optionally scoped to ``owner``.

    Sorted newest-first by ``created_at``.
    """
    root = _templates_root()
    out: List[dict] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        meta = _read_meta(child)
        if meta is None:
            continue
        if owner is not None and meta.get("owner") != owner:
            continue
        out.append(meta)
    out.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return out


def delete_template(
    template_id: str,
    *,
    requester: Optional[str] = None,
) -> bool:
    """Delete a template directory. Returns ``False`` if not found or
    (when ``requester`` is given) not owned by the requester."""
    tpl_dir = _tpl_dir(template_id)
    meta = _read_meta(tpl_dir)
    if meta is None:
        return False
    if requester is not None and meta.get("owner") != requester:
        return False
    import shutil
    shutil.rmtree(tpl_dir, ignore_errors=True)
    return True


def output_dir(template_id: str) -> Path:
    """Return (creating) the ``out/`` directory for a template."""
    d = _tpl_dir(template_id) / "out"
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_output_id() -> str:
    """Generate a path-safe id for a rendered output file."""
    return f"out-{uuid.uuid4().hex[:10]}"


__all__ = [
    "TemplateStoreError",
    "VALID_MODES",
    "create_template",
    "get_template",
    "list_templates",
    "delete_template",
    "output_dir",
    "new_output_id",
]
