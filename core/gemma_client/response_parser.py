"""``<think>`` block 3-stage recovery + post-processing for Gemma
client responses.

Extracted from the legacy single-file ``core/gemma_client.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour
is byte-identical to the pre-split file — the same call-order, the
same regex set, the same "...done thinking." marker handling, the
same final ``[Gemma 응답 없음]`` fallback when every recovery stage
collapses.

Used by both ``call_gemma`` (with all 3 stages) and
``call_gemma_vision`` (with a simpler 1-stage variant). Both code
paths share the post-processing tail (``</?s>`` strip + "done
thinking" marker skip).
"""
from __future__ import annotations

import re


def _strip_response_tail(result: str) -> str:
    """Common post-processing — remove ``<s>`` / ``</s>`` markers and
    skip past any "...done thinking." / "done thinking." marker that
    Gemma occasionally emits at the boundary between the hidden
    reasoning trace and the visible answer.

    Returns the cleaned string. Returns the input unchanged if it is
    empty or the canonical ``[Gemma 응답 없음]`` fallback.
    """
    if not result or result == "[Gemma 응답 없음]":
        return result
    result = re.sub(r'</?s>', '', result)
    for marker in ["...done thinking.", "done thinking."]:
        idx = result.find(marker)
        if idx != -1:
            result = result[idx + len(marker):]
            break
    return result.strip()


def recover_think_block(output: str) -> str:
    """3-stage recovery for Gemma responses that may carry a
    ``<think>...</think>`` block surrounding (or replacing) the
    visible answer.

    Stage 1 — strip ``<think>...</think>`` and return the remainder
    if substantive.

    Stage 2 — if stripping yielded empty AND a closing ``</think>``
    exists in the raw output, return the text after the closing tag
    (the LLM resumed the real answer outside the thinking block).

    Stage 3 — if neither succeeded but a ``<think>...</think>`` is
    present, extract the LAST 2 sentences from inside the thinking
    block (or the trailing 300 chars when sentence splitting fails)
    as a best-effort recovery.

    Returns the canonical ``[Gemma 응답 없음]`` string when every
    stage collapses — the upstream caller treats that as a recognised
    error response (see ``ERROR_PREFIXES`` / ``is_cacheable_response``)
    and will refuse to cache it.

    All three stages preserve the call-order + print-side-effects of
    the pre-split implementation so log lines downstream operators
    rely on (`[GEMMA] ⚠️ <think> 이후 복구: …자`) stay byte-identical.
    """
    if not output:
        return "[Gemma 응답 없음]"

    raw_output = output

    # Stage 1: <think>...</think> 제거 후 내용 있으면 정상
    cleaned = re.sub(r'<think>.*?</think>', '', output,
                     flags=re.DOTALL).strip()
    if cleaned:
        return _strip_response_tail(cleaned)

    # Stage 2: </think> 이후 텍스트 추출
    if '</think>' in raw_output:
        after_think = raw_output.split('</think>', 1)[-1].strip()
        if after_think:
            print(f"[GEMMA] ⚠️ <think> 이후 복구: {len(after_think)}자")
            return _strip_response_tail(after_think)

        # Stage 3: <think> 내부 마지막 문장 추출
        think_match = re.search(r'<think>(.*?)</think>', raw_output,
                                re.DOTALL)
        if think_match:
            think_body = think_match.group(1).strip()
            sentences = [s.strip() for s in
                         re.split(r'(?<=[.。!?])\s+', think_body)
                         if s.strip()]
            recovered = (" ".join(sentences[-2:])
                         if sentences else think_body[-300:])
            print(f"[GEMMA] ⚠️ think 내부 복구: {len(recovered)}자")
            result = recovered if recovered else "[Gemma 응답 없음]"
            return _strip_response_tail(result)

        return "[Gemma 응답 없음]"

    # <think> 없는데 빈 문자열 → 원본 재시도
    if raw_output.strip():
        return _strip_response_tail(raw_output.strip())
    return "[Gemma 응답 없음]"


def recover_vision_response(output: str) -> str:
    """Simpler 1-stage recovery for ``call_gemma_vision`` — strip
    ``<think>...</think>`` and apply the post-processing tail.

    Vision responses rarely emit thinking blocks (Gemma's vision
    pipeline doesn't run the same CoT prompt), so the call_gemma
    3-stage recovery is overkill; this stage 1 + tail strip is the
    pre-split behaviour preserved byte-identical.
    """
    if not output:
        return "[Gemma Vision 응답 없음]"
    cleaned = re.sub(r'<think>.*?</think>', '', output,
                     flags=re.DOTALL).strip()
    result = cleaned if cleaned else output.strip()
    return _strip_response_tail(result)


__all__ = [
    "recover_think_block",
    "recover_vision_response",
    "_strip_response_tail",
]
