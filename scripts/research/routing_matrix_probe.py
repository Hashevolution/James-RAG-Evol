"""Live routing-matrix probe — what model does each mode actually call?

v0.6.1 v18.7 (2026-06-16). Operator asked for the routing table to be
"정리해두고 실제 확인" — pinned down AND verified against live behavior,
not guessed from reading the code.

This script forces each mode via ``mode_override`` (so the
IntentClassifier is bypassed and we measure the model-resolution path
in isolation), runs a short query through the real ``ReasoningEngine``,
and parses the stdout routing breadcrumbs:

  [ROUTER] mode=...                  — which mode the engine settled on
  [MODEL] mode=chat auto-routed → X  — Phase 2c chat auto-route
  [MODEL] mode=... using user-selected X  — secondary picker path
  [MODEL_RESOLVE] ...                — call_gemma model=None fallback warning
  [coding_route] / coding_llm_pick   — coding router path

The point is ground truth: the table in the handover / CLAUDE.md is
only as good as the code, and the code has multiple resolution paths
(engine auto-route for chat, call_gemma(model=None)→resolve_chat for
retrieval/wiki/self_evolve, llm.router for coding, fast-path no-LLM for
meta). This probe collapses all of that into one observed table.

Usage (from repo root):

    python scripts/research/routing_matrix_probe.py
    python scripts/research/routing_matrix_probe.py --no-llm   # resolve only, skip generation

``--no-llm`` uses the resolver introspection path (fast, no Ollama
generation) — useful when you only want the model NAME each mode would
pick, not a full answer. Default runs the real engine so the observed
model is the one that actually received the synth call.
"""
from __future__ import annotations

import argparse
import io
import contextlib
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# Probe queries — short, one per mode. mode_override forces the mode so
# IntentClassifier mis-routing can't confound the model-resolution read.
PROBES = [
    ("chat",        "안녕하세요. 오늘 기분이 어때요?"),
    ("retrieval",   "내부 자료에서 보안 정책을 알려줘."),
    ("meta",        "어떤 자료들이 있어?"),
    ("coding",      "파이썬으로 quicksort 함수를 짜줘."),
    ("wiki_edit",   "이 문서 내용을 수정해줘."),
    ("self_evolve", "너 자신의 기능을 개선하는 방법을 제안해봐."),
]

# Lines we treat as routing breadcrumbs.
_PAT_MODEL = re.compile(r"\[MODEL\]\s+(.*)")
_PAT_RESOLVE = re.compile(r"\[MODEL_RESOLVE\]\s+(.*)")
_PAT_ROUTER = re.compile(r"\[ROUTER\]\s+(.*)")
_PAT_CODING = re.compile(r"\[?(coding_route|coding_llm_pick|coding_user_pick)\]?")
_PAT_LLM_ROUTER = re.compile(r"\[LLM_ROUTER\]\s+(.*)")
# Extract a model tag from an auto-route / user-select line.
_PAT_TAG = re.compile(r"→\s*'([^']+)'|using user-selected '([^']+)'")


def _extract_model(lines: List[str]) -> str:
    """Best-effort pull of the actually-called model tag from the
    captured routing lines. Returns '' if none found (e.g. meta
    fast-path that never calls the LLM)."""
    for ln in lines:
        m = _PAT_TAG.search(ln)
        if m:
            return m.group(1) or m.group(2) or ""
    return ""


def probe_mode_llm(mode: str, query: str, *, user_role: str,
                   timeout_note: str = "") -> Dict[str, object]:
    """Run one mode through the real engine, capture routing lines."""
    from core.reasoning.engine import ReasoningEngine
    eng = ReasoningEngine()
    buf = io.StringIO()
    t0 = time.time()
    err = ""
    try:
        with contextlib.redirect_stdout(buf):
            eng.query(query, user_role=user_role, mode_override=mode)
    except Exception as e:   # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    elapsed = round(time.time() - t0, 1)
    out = buf.getvalue()
    routing_lines: List[str] = []
    for ln in out.splitlines():
        if (_PAT_MODEL.search(ln) or _PAT_RESOLVE.search(ln)
                or _PAT_ROUTER.search(ln) or _PAT_CODING.search(ln)
                or _PAT_LLM_ROUTER.search(ln)):
            routing_lines.append(ln.strip())
    model = _extract_model(routing_lines)
    # coding router doesn't print a → tag; infer from CODING_MODEL.
    if not model and mode == "coding":
        try:
            from config import CODING_MODEL
            model = f"{CODING_MODEL} (via llm.router, inferred)"
        except Exception:
            model = "qwen-coder (via llm.router)"
    if not model and mode == "meta":
        model = "(fast-path — no LLM call expected)"
    # Silent default paths (retrieval / wiki_edit / self_evolve):
    # call_gemma(model=None) → resolve_chat() emits NO [MODEL] line in
    # the happy path (only on a fallback warning). Infer the model the
    # same way the code would, and label it clearly so the table is
    # complete without falsely claiming we observed a log line.
    if not model and mode in ("retrieval", "wiki_edit", "self_evolve"):
        try:
            from core.model_resolver import resolve_chat
            rc = resolve_chat()
            model = f"{rc.tag} (silent default path — inferred)"
        except Exception:
            model = "(silent default path — resolve failed)"
    return {
        "mode": mode,
        "model": model or "(none observed)",
        "elapsed_sec": elapsed,
        "routing_lines": routing_lines,
        "error": err,
    }


def probe_mode_resolve_only(mode: str) -> Dict[str, object]:
    """Fast path: introspect the resolver decision without generating.
    Mirrors engine.py's resolution branches so the NAME matches what a
    real call would pick — but does not exercise the synth path."""
    from core.model_resolver import resolve_for_mode, resolve_chat

    note = ""
    if mode in ("chat", "retrieval"):
        if os.environ.get("JAMES_DISABLE_MODE_AWARE_ROUTING"):
            rm = resolve_chat()
            note = "kill-switch ON → resolve_chat()/GEMMA_MODEL"
        else:
            rm = resolve_for_mode(mode, requested="")
            phase = "Phase 2c" if mode == "chat" else "Phase 3c"
            note = f"{phase} auto-route (measured preference top)"
        model = rm.tag
    elif mode == "coding":
        try:
            from config import CODING_MODEL
            model = f"{CODING_MODEL} (llm.router task=coding)"
        except Exception:
            model = "qwen-coder"
        note = "separate coding router path"
    elif mode == "meta":
        model = "(fast-path — no LLM)"
        note = "inventory generated without LLM"
    else:  # wiki_edit / self_evolve (retrieval now handled above)
        rm = resolve_chat()
        model = rm.tag
        note = "legacy: call_gemma(model=None) → resolve_chat() → GEMMA_MODEL"
    return {"mode": mode, "model": model or "(none)", "note": note}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true",
                    help="resolver introspection only (no generation)")
    ap.add_argument("--tier-ladder", action="store_true",
                    help="show the v18.7 Phase 3a local complexity-tier "
                         "ladder (light/standard/deep → ollama tag) and exit")
    ap.add_argument("--user-role", default="admin",
                    help="role to probe under (admin sees all modes)")
    args = ap.parse_args()

    if args.tier_ladder:
        from core.model_resolver import installed_models
        from core.model_resolver_tiers import (
            LOCAL_TIER_LADDER, resolve_local_tier,
        )
        inst = installed_models()
        print("\n=== v18.7 Phase 3a — local complexity-tier ladder ===")
        print("(DEFINED but NOT YET consumed by the pipeline — Phase 3b "
              "measures + wires)\n")
        print(f'{"rung":<10} | {"mapped tag":<14} | {"installed?":<10} | '
              f'{"resolves to":<16} | source')
        print("-" * 78)
        for rung in ("light", "standard", "deep"):
            mapped = LOCAL_TIER_LADDER[rung]
            rm = resolve_local_tier(rung)
            print(f'{rung:<10} | {mapped:<14} | '
                  f'{"yes" if mapped in inst else "NO":<10} | '
                  f'{rm.tag:<16} | {rm.source}')
        print()
        return 0

    print(f"\n=== JAMES routing matrix probe "
          f"({'resolve-only' if args.no_llm else 'live engine'}) ===")
    try:
        from config import GEMMA_MODEL, CODING_MODEL
        print(f"config.GEMMA_MODEL  = {GEMMA_MODEL}")
        print(f"config.CODING_MODEL = {CODING_MODEL}")
    except Exception as e:
        print(f"[warn] config read failed: {e}")
    print(f"JAMES_DISABLE_MODE_AWARE_CHAT = "
          f"{os.environ.get('JAMES_DISABLE_MODE_AWARE_CHAT', '(unset)')}")
    print()

    rows: List[Dict[str, object]] = []
    if args.no_llm:
        for mode, _q in PROBES:
            rows.append(probe_mode_resolve_only(mode))
        print(f'{"mode":<13} | {"model":<40} | note')
        print("-" * 95)
        for r in rows:
            print(f'{r["mode"]:<13} | {str(r["model"]):<40} | {r["note"]}')
    else:
        for mode, q in PROBES:
            print(f"[probe] mode={mode:<12} query={q[:30]!r} … ",
                  end="", flush=True)
            r = probe_mode_llm(mode, q, user_role=args.user_role)
            rows.append(r)
            tag = r["model"]
            print(f"→ {tag}  ({r['elapsed_sec']}s)"
                  + (f"  ERR={r['error']}" if r["error"] else ""))
        print()
        print(f'{"mode":<13} | {"observed model":<42} | elapsed')
        print("-" * 75)
        for r in rows:
            print(f'{r["mode"]:<13} | {str(r["model"]):<42} | '
                  f'{r["elapsed_sec"]}s')
        print("\n--- routing breadcrumbs (per mode) ---")
        for r in rows:
            print(f"\n[{r['mode']}]")
            for ln in r["routing_lines"]:
                print(f"  {ln}")
            if r["error"]:
                print(f"  ERROR: {r['error']}")
    print()
    return 0


if __name__ == "__main__":   # pragma: no cover
    raise SystemExit(main())
