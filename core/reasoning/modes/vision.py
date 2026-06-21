"""``handle_vision`` — image → text analysis via the local vision model.

The reasoning-engine peer to ``handle_chat`` / ``handle_meta`` /
``handle_wiki_edit`` for the ``vision`` mode. It is the dispatch + routing
shell, NOT a re-implementation of the vision pipeline — the actual
EXIF + llava work stays in ``tools.multimodal.image_analyzer.analyze_image``.

Why this differs from the text modes
------------------------------------
chat / retrieval / wiki_edit each went through an a/b/c quality
measurement (3-cell paired) because they have several candidate text
models. Vision has a SINGLE local candidate (llava), so there is no
marginal ranking to measure — a 3-cell QDC is moot. The "routing" work
here is therefore *resolution robustness*, not model selection:

  - pick the vision model through ``resolve_for_mode("vision")`` so it is
    installed-checked with a graceful fallback + operator warning, instead
    of a blind ``config.MULTIMODAL_MODEL`` reference (which, as of v18.7,
    is not even defined in config.py → silently hardcoded to ``llava:13b``
    with no install check); and
  - honour the shared ``JAMES_DISABLE_MODE_AWARE_ROUTING`` kill-switch so
    one env var reverts ALL mode-aware routing (chat / retrieval /
    wiki_edit / vision) to the legacy path.

Trust (#44)
-----------
Vision output is ``source="vision"`` ``trust="low"`` — model hallucination
plus prompt-injection text baked into an image can flow through an
OCR-like path. ``handle_vision`` RETURNS the analysis to the user but
never feeds it back into a downstream synth prompt, so no quarantine gate
is needed on this path; the ``trust`` marker is carried in
``vision_meta`` for any caller that later does compose it.

Plumb-first (v0.6.1 v18.7 vision-handler)
-----------------------------------------
This handler is exported + unit-tested but ``engine.py`` does NOT dispatch
to ``mode == "vision"`` yet, and images do not yet flow through the
``/query`` path (they arrive via the dedicated ``/analyze/image/`` REST
route). Behaviour is byte-identical until the follow-up vision-wire PR
adds the engine dispatch + ``VALID_OVERRIDES`` entry + image plumbing.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Tuple


def _resolve_vision_model(selected_model: str) -> Tuple[str, str, str]:
    """Return ``(tag, source, warning)`` for the vision model.

    Priority:
      1. explicit user pick (``selected_model``) — trusted by the caller.
      2. ``JAMES_DISABLE_MODE_AWARE_ROUTING`` set → legacy config default
         (``MULTIMODAL_MODEL`` if defined, else ``llava:13b``) with NO
         install check — same kill-switch semantics as the text modes.
      3. ``resolve_for_mode("vision")`` → preference list (currently a
         single entry, ``llava:13b``) with install-check + graceful
         fallback + warning.

    ``tag`` is empty only when nothing at all is installed in Ollama, in
    which case the handler surfaces a friendly install hint.
    """
    sel = (selected_model or "").strip()
    if sel:
        return sel, "requested", ""

    if os.environ.get("JAMES_DISABLE_MODE_AWARE_ROUTING"):
        try:
            from config import MULTIMODAL_MODEL  # type: ignore
            legacy = (MULTIMODAL_MODEL or "").strip() or "llava:13b"
        except Exception:
            legacy = "llava:13b"
        return legacy, "legacy_killswitch", ""

    try:
        from core.model_resolver import resolve_for_mode
        rm = resolve_for_mode("vision", requested="")
        return rm.tag, rm.source, rm.warning
    except Exception:
        # Resolver unreachable (e.g. Ollama down at import) → assume the
        # canonical local vision tag; the downstream llava client does its
        # own is_available() check and degrades to EXIF-only.
        return "llava:13b", "fallback", ""


def handle_vision(
    engine,
    safe_query: str,
    image_path: str,
    user_role: str,
    t_start: float,
    selected_model: str = "",
) -> Dict[str, Any]:
    """Analyse ``image_path`` and return the standard reasoning-engine row.

    ``safe_query`` is the (optional) user text accompanying the image —
    "이 사진 어디야?" etc. When empty, the analyzer's default structured
    prompt is used.
    """
    t_vision = time.time()

    def _row(answer: str, *, blocked: bool = False, **extra) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "answer":        answer,
            "mode":          "vision",
            "graph_paths":   [],
            "graph_used":    0,
            "sources":       [image_path] if image_path else [],
            "blocked":       blocked,
            "role_used":     user_role,
            "timing_sec":    round(time.time() - t_start, 2),
            "unified_score": 1.0,
            "loop_count":    0,
        }
        row.update(extra)
        return row

    # No image attached → friendly guidance. Keeps the (future) engine
    # dispatch safe even when the /query path routes mode="vision" without
    # an image payload.
    if not (image_path or "").strip():
        return _row(
            "이미지가 첨부되지 않았습니다. 분석할 이미지를 첨부한 뒤 다시 질문해 주세요."
        )

    model_tag, source, warning = _resolve_vision_model(selected_model)
    if not model_tag:
        return _row(
            "비전 모델이 설치되어 있지 않습니다. "
            "먼저 `ollama pull llava:13b` 를 실행해 주세요."
        )
    if warning:
        print(f"[VISION] {warning}")
    print(f"[VISION] model={model_tag} (source={source}) image={image_path}")

    answer = ""
    vision_meta: Dict[str, Any] = {}
    try:
        from tools.multimodal.image_analyzer import analyze_image

        result = analyze_image(image_path, role=user_role, model=model_tag)

        if result.get("error"):
            return _row(f"❌ 이미지 분석 실패: {result['error']}")

        description = (result.get("description") or "").strip()
        location    = (result.get("location") or "").strip()
        date        = (result.get("date") or "").strip()
        persons     = result.get("persons") or []
        tags        = result.get("tags") or []

        lines = []
        if description:
            lines.append(description)
        meta_bits = []
        if date:
            meta_bits.append(f"날짜: {date}")
        if location:
            meta_bits.append(f"장소: {location}")
        if persons:
            meta_bits.append("인물: " + ", ".join(str(p) for p in persons))
        if tags:
            meta_bits.append("태그: " + ", ".join(str(t) for t in tags))
        if meta_bits:
            if lines:
                lines.append("")
            lines.extend(f"- {b}" for b in meta_bits)
        answer = "\n".join(lines).strip() or (
            "이미지에서 분석 가능한 정보를 찾지 못했습니다."
        )

        vision_meta = {
            "model":    model_tag,
            "source":   "vision",   # #44 trust classification
            "trust":    "low",
            "date":     date,
            "location": location,
            "persons":  persons,
            "tags":     tags,
        }
    except Exception as e:
        engine._log("vision", e, user_role)
        answer = f"❌ 이미지 분석 중 오류: {e}"

    engine._elapsed(t_vision, "VISION")
    return _row(answer, vision_meta=vision_meta)


__all__ = ["handle_vision"]
