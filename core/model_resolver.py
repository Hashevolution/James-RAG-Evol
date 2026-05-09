"""[PR plan-1, 2026-05-09] Multi-model auto-resolution.

Goal: NEVER 404 because of a missing model.

Resolution chain when `call_gemma(model=None)`:
  1. Per-call user pick (selected_model from picker — already wired
     via PR #136, not relevant here; the caller passes model=tag in
     that case and we never enter this resolver)
  2. `requested` arg — typically `config.GEMMA_MODEL` (env override
     `JAMES_LLM_MODEL`). If installed, use it.
  3. Per-mode preference list — first installed wins. Operator can
     override via `JAMES_MODEL_PREFERENCE_CHAT=...` env (comma-separated).
  4. Any installed model — last resort, with a warning.
  5. Nothing installed → returns ResolvedModel(tag="", source="none")
     with a friendly install command in the `warning` field.

Cached `installed_models()` set with 60s TTL so we don't hit the
Ollama HTTP API on every chat turn. `invalidate_cache()` is called
from /admin/llm/install handler so a fresh install is seen
immediately.

Why this layer exists
  Before this module, `call_gemma(model=None)` fell through to
  `config.GEMMA_MODEL` (default "gemma4:e4b"). On any machine that
  doesn't have that exact tag, every call 404s and the user sees
  "[Gemma 응답 없음]". The most common beginner failure was forgetting
  to set `JAMES_LLM_MODEL` in `.env` to match the model they pulled
  with `ollama pull`. After this module, that mismatch is silently
  recovered with an audit-logged fallback warning.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import List, NamedTuple, Optional, Set


# ─── Default preference lists ──────────────────────────────────────
# First entry = highest preference. Operator overrides via env.
#
# `chat` order rationale (Korean-first audience):
#   gemma3:4b   — 16GB box sweet spot, decent Korean
#   gemma3:1b   — 8GB box fallback, weaker quality
#   gemma2:2b   — older but tiny; works on legacy boxes
#   gemma3:12b  — 32GB box quality bump
#   gemma3:27b  — 32GB+ heavy
#   gemma4:e4b  — operator's existing default; kept for back-compat
#   qwen2.5:14b — non-gemma fallback with Korean
#   llama3.2:3b — emergency fallback
#   mistral:7b  — last gemma-less option
#
# `coding` order: qwen-coder family first (handle_coding routes via
#   llm.router which already prefers it). Deepseek family as fallback.
DEFAULT_PREFERENCE: dict = {
    "chat": [
        "gemma3:4b", "gemma3:1b", "gemma2:2b",
        "gemma3:12b", "gemma3:27b", "gemma4:e4b",
        "qwen2.5:14b", "llama3.2:3b", "mistral:7b",
    ],
    "coding": [
        "qwen2.5-coder:7b", "qwen2.5-coder:14b", "qwen2.5-coder:32b",
        "deepseek-coder:6.7b", "deepseek-coder:33b",
    ],
}


class ResolvedModel(NamedTuple):
    """Outcome of resolve_for_mode().

    tag           : actual Ollama tag to call (empty string if nothing
                    is installed)
    source        : how we got here — for logging/observability:
                    "requested" — caller-provided tag was installed
                    "preference"— per-mode preference list hit
                    "any"       — last-resort installed model
                    "none"      — nothing installed at all
    fallback_chain: tags tried in order (debugging)
    warning       : empty if no warning; non-empty if operator should
                    know (e.g., "requested X not installed, using Y")
    """
    tag: str
    source: str
    fallback_chain: List[str]
    warning: str


# ─── Cached installed-set ──────────────────────────────────────────
_CACHE: dict = {"installed": None, "ts": 0.0}
_CACHE_TTL_S = 60.0
_OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"


def installed_models(force: bool = False) -> Set[str]:
    """Cached set of installed Ollama tags.

    Hits Ollama's `/api/tags` HTTP endpoint at most once per
    `_CACHE_TTL_S`. Returns an empty set on Ollama-unreachable —
    callers should treat that as "no install info"; `resolve_for_mode`
    handles it by falling through to the "none" branch.

    Pass `force=True` after install/uninstall to refresh.
    """
    now = time.time()
    if (
        not force
        and _CACHE["installed"] is not None
        and (now - _CACHE["ts"]) < _CACHE_TTL_S
    ):
        return _CACHE["installed"]

    tags: Set[str] = set()
    try:
        with urllib.request.urlopen(_OLLAMA_TAGS_URL, timeout=2) as r:
            data = json.loads(r.read())
        for m in data.get("models", []):
            name = m.get("name", "")
            if name:
                tags.add(name)
    except Exception:
        # Ollama down or misconfigured — empty set; resolver falls
        # through to "none" with a clear install command.
        tags = set()

    _CACHE["installed"] = tags
    _CACHE["ts"] = now
    return tags


def invalidate_cache() -> None:
    """Drop the installed-models cache so next call hits Ollama fresh.

    Call from /admin/llm/install + /admin/llm/delete handlers so the
    resolver immediately sees the new state.
    """
    _CACHE["installed"] = None
    _CACHE["ts"] = 0.0


# ─── Preference list lookup (with env override) ────────────────────
def _preference_for(mode: str) -> List[str]:
    """Return preference list for `mode`, honoring env override.

    Env key: JAMES_MODEL_PREFERENCE_<MODE> (comma-separated tags).
    Unknown mode falls back to the chat list.
    """
    env_key = f"JAMES_MODEL_PREFERENCE_{mode.upper()}"
    raw = os.environ.get(env_key, "").strip()
    if raw:
        parsed = [t.strip() for t in raw.split(",") if t.strip()]
        if parsed:
            return parsed
    return list(DEFAULT_PREFERENCE.get(mode, DEFAULT_PREFERENCE["chat"]))


# ─── Main resolution entry point ───────────────────────────────────
def resolve_for_mode(mode: str = "chat", requested: str = "") -> ResolvedModel:
    """Find an installed model for `mode`. Never raises.

    Args:
      mode:       "chat" / "coding" / etc. Drives the preference list.
      requested:  caller's preferred tag (typically config.GEMMA_MODEL
                  or a runtime override). Empty string means "no
                  preference, just pick from the mode list".

    Returns: ResolvedModel — see class docstring. The `tag` field is
      empty iff no models are installed at all (resolver gives up
      gracefully rather than crashing).
    """
    chain: List[str] = []
    inst = installed_models()

    # Step 1: caller's explicit request (if any)
    requested = (requested or "").strip()
    if requested:
        chain.append(requested)
        if requested in inst:
            return ResolvedModel(requested, "requested", chain, "")

    # Step 2: per-mode preference list
    pref = _preference_for(mode)
    for tag in pref:
        if tag in chain:
            continue
        chain.append(tag)
        if tag in inst:
            warning = ""
            if requested and requested != tag:
                warning = (
                    f"requested model '{requested}' not installed; "
                    f"using '{tag}' from preference list"
                )
            return ResolvedModel(tag, "preference", chain, warning)

    # Step 3: any installed model (deterministic pick — sorted)
    if inst:
        any_tag = sorted(inst)[0]
        chain.append(any_tag)
        warning = (
            f"no preferred model installed for mode={mode}; "
            f"using '{any_tag}' as last resort. Consider: "
            f"ollama pull {pref[0] if pref else 'gemma3:4b'}"
        )
        return ResolvedModel(any_tag, "any", chain, warning)

    # Step 4: nothing at all
    suggested = pref[0] if pref else "gemma3:4b"
    return ResolvedModel(
        "",
        "none",
        chain,
        f"No models installed in Ollama. "
        f"Run: ollama pull {suggested} "
        f"(or visit /admin → 장비 현황 for hardware-aware recommendation).",
    )


# ─── Convenience wrappers around config defaults ───────────────────
def resolve_chat() -> ResolvedModel:
    """Resolve for chat using config.GEMMA_MODEL as the requested tag."""
    try:
        from config import GEMMA_MODEL  # type: ignore
        requested = GEMMA_MODEL or ""
    except Exception:
        requested = ""
    return resolve_for_mode("chat", requested=requested)


def resolve_coding() -> ResolvedModel:
    """Resolve for coding using config.CODING_MODEL as the requested tag."""
    try:
        from config import CODING_MODEL  # type: ignore
        requested = CODING_MODEL or ""
    except Exception:
        requested = ""
    return resolve_for_mode("coding", requested=requested)


def resolution_snapshot() -> dict:
    """Snapshot of current resolution state — for /admin/llm/resolution.

    Returned shape:
      {
        "chat":   {"tag", "source", "warning", "fallback_chain"},
        "coding": {...},
        "installed": [tags...],
        "preference": {"chat": [...], "coding": [...]},
        "ttl_s": 60,
      }
    """
    chat = resolve_chat()
    coding = resolve_coding()
    return {
        "chat": {
            "tag": chat.tag,
            "source": chat.source,
            "warning": chat.warning,
            "fallback_chain": chat.fallback_chain,
        },
        "coding": {
            "tag": coding.tag,
            "source": coding.source,
            "warning": coding.warning,
            "fallback_chain": coding.fallback_chain,
        },
        "installed": sorted(installed_models()),
        "preference": {
            "chat": _preference_for("chat"),
            "coding": _preference_for("coding"),
        },
        "ttl_s": _CACHE_TTL_S,
    }
