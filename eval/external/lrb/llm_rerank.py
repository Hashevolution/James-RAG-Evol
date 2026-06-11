"""LRB v0.2.1 — LLM-grounded reranker for cross-model measurement.

Per prereg `docs/research/lrb-v021-cross-model-preregistration-2026-06-11.md`:

  retrieve_at(mode="llm-grounded"):
    top_20 = token_overlap_top_k(q, 20, vt)
    llm_scores = llm_rerank(top_20, q, model=model)
    return top_k_by_score(top_20, llm_scores, k)

Design discipline:
  * Independent of the project's full LLM router — direct HTTP to
    Ollama / direct subprocess to claude CLI. External reproducer can
    re-run with stock Ollama, no JAMES-internal dependencies.
  * Deterministic: temperature=0, fixed seed where supported, JSON
    output format.
  * Robust parse: extract first JSON object even if model adds prose.
  * Graceful degradation: if the model fails to return valid JSON or
    enough scores, fall back to token-overlap order (preserves
    determinism + monotone tie-break).

This module does NOT change SUT scoring math (RAB H1 정합: LLM is at
retrieval-rerank step only, not at scoring step).
"""
from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Sequence, Tuple

# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def rerank(query: str,
           candidates: Sequence[Tuple[str, str, str]],
           *,
           model: str,
           ollama_url: str = "http://localhost:11434",
           timeout: float = 60.0) -> List[Tuple[str, float]]:
    """Rerank candidates by LLM relevance score.

    Args:
      query:       the user query string.
      candidates:  ordered list of ``(doc_id, title, text)`` tuples.
                   Order is the token-overlap rank (best-first); LLM
                   may reorder.
      model:       canonical model name. Dispatch table:
                     ``gemma4:e4b`` / ``gemma3:12b`` / ``mixtral:8x7b``
                       → Ollama local HTTP
                     ``claude-haiku-4-5`` / ``claude-sonnet-4-6`` /
                     ``claude-opus-4-7``
                       → subprocess to ``claude -p`` (Max-plan headless)
      ollama_url:  Ollama service URL (default localhost:11434).
      timeout:     per-call timeout in seconds.

    Returns:
      ``[(doc_id, score), ...]`` sorted by descending score. Scores are
      LLM-provided floats in [0, 10]; tie-break by original (token-
      overlap) rank to preserve determinism.
    """
    if not candidates:
        return []

    prompt = _build_prompt(query, candidates)

    if _is_ollama_model(model):
        scores = _call_ollama(prompt, model=model,
                              ollama_url=ollama_url, timeout=timeout)
    elif _is_claude_model(model):
        scores = _call_claude_cli(prompt, model=model, timeout=timeout)
    else:
        raise ValueError(
            f"unknown model {model!r}; supported: gemma4:e4b, "
            f"gemma3:12b, mixtral:8x7b, claude-haiku-4-5, "
            f"claude-sonnet-4-6, claude-opus-4-7")

    # If the LLM produced fewer scores than candidates, pad with 0.0
    # (relevance unknown → end of list, but preserve token-overlap
    # rank by stable sort + index tie-break).
    n = len(candidates)
    if len(scores) < n:
        scores = list(scores) + [0.0] * (n - len(scores))
    elif len(scores) > n:
        scores = scores[:n]

    # Pair, then stable-sort by score desc, idx asc (= original rank)
    paired = [(candidates[i][0], float(scores[i]), i)
              for i in range(n)]
    paired.sort(key=lambda x: (-x[1], x[2]))
    return [(doc_id, score) for doc_id, score, _ in paired]


# ──────────────────────────────────────────────────────────────────────
# Prompt construction
# ──────────────────────────────────────────────────────────────────────


def _build_prompt(query: str,
                  candidates: Sequence[Tuple[str, str, str]]) -> str:
    """Build deterministic prompt asking model to score each candidate
    0-10 on relevance. JSON output enforced.
    """
    lines = [
        "You are a retrieval reranker. Score each candidate document "
        "for relevance to the query on a 0-10 scale (0 = irrelevant, "
        "10 = perfect match).",
        "",
        f"Query: {query}",
        "",
        "Candidates:",
    ]
    for i, (doc_id, title, text) in enumerate(candidates, start=1):
        snippet = text[:300].replace("\n", " ")
        lines.append(f"{i}. [{doc_id}] {title}: {snippet}")
    lines.extend([
        "",
        "Return ONLY a JSON object of the form:",
        '  {"scores": [<int>, <int>, ...]}',
        f"with exactly {len(candidates)} integer scores in the same "
        "order as the candidates above. Output nothing else.",
    ])
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# Model dispatch
# ──────────────────────────────────────────────────────────────────────

OLLAMA_MODEL_PREFIXES = ("gemma", "mixtral", "mistral", "llama", "qwen",
                          "phi", "deepseek")
CLAUDE_MODEL_PREFIXES = ("claude-",)


def _is_ollama_model(model: str) -> bool:
    name = model.split(":")[0].lower()
    return any(name.startswith(p) for p in OLLAMA_MODEL_PREFIXES)


def _is_claude_model(model: str) -> bool:
    return any(model.lower().startswith(p)
               for p in CLAUDE_MODEL_PREFIXES)


# ──────────────────────────────────────────────────────────────────────
# Ollama HTTP
# ──────────────────────────────────────────────────────────────────────


def _call_ollama(prompt: str, *, model: str, ollama_url: str,
                 timeout: float) -> List[float]:
    """POST to /api/generate with format=json + temperature=0 + seed=42
    for determinism. Returns the parsed score list, or [] on failure
    (caller pads → token-overlap fallback).
    """
    payload = {
        "model":   model,
        "prompt":  prompt,
        "stream":  False,
        "format":  "json",
        "options": {"temperature": 0.0, "seed": 42},
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return []

    text = data.get("response", "")
    return _parse_scores(text)


# ──────────────────────────────────────────────────────────────────────
# Claude CLI subprocess
# ──────────────────────────────────────────────────────────────────────


def _call_claude_cli(prompt: str, *, model: str,
                     timeout: float) -> List[float]:
    """Run ``claude -p`` headless. Per Direction α S5c (memory
    `feedback_measurement_smoke_caught_wiring_bugs`): default cwd =
    neutral temp dir, env whitelist must include SystemRoot / APPDATA /
    LOCALAPPDATA / USERPROFILE / TEMP / TMP on Windows.

    For LRB v0.2.1 smoke this falls back to [] if claude CLI is
    unavailable — operator runs the full sweep with claude wiring
    pre-flighted via Direction α S4 measurement.
    """
    import os
    from pathlib import Path as _Path

    # Minimal env whitelist for Windows + claude CLI (Node-wrapped)
    base_env = {}
    for var in ("SystemRoot", "APPDATA", "LOCALAPPDATA",
                "USERPROFILE", "TEMP", "TMP", "Path", "PATH",
                "HOME", "ANTHROPIC_API_KEY"):
        if var in os.environ:
            base_env[var] = os.environ[var]

    # cwd = project root (Claude Code auto-mode classifier rejects
    # cwd outside project scope as "scope escalation").
    project_root = _Path(__file__).resolve().parents[3]

    # On Windows, subprocess Popen can't find `claude` (which is a
    # shim) — it needs `claude.cmd` or shell=True. Use the .cmd
    # extension when on Windows + npm shim path.
    cmd_executable = "claude"
    if os.name == "nt":
        npm_claude_cmd = (_Path(os.environ.get("APPDATA", ""))
                          / "npm" / "claude.cmd")
        if npm_claude_cmd.exists():
            cmd_executable = str(npm_claude_cmd)

    try:
        proc = subprocess.run(
            [cmd_executable, "-p", "--model", model],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(project_root),
            env=base_env,
            shell=False,
        )
        if proc.returncode != 0:
            return []
        return _parse_scores(proc.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


# ──────────────────────────────────────────────────────────────────────
# Score parsing
# ──────────────────────────────────────────────────────────────────────

_JSON_OBJ = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _parse_scores(text: str) -> List[float]:
    """Extract a list of floats from a model's text response.

    Tries strict JSON first; falls back to first ``{...}`` substring.
    Returns [] if neither yields a list of numbers.
    """
    text = text.strip()
    if not text:
        return []

    # Strict JSON parse (Ollama format=json output)
    try:
        obj = json.loads(text)
        scores = obj.get("scores") if isinstance(obj, dict) else None
        if isinstance(scores, list):
            return [_clip(_to_float(s)) for s in scores]
    except (json.JSONDecodeError, ValueError):
        pass

    # Loose extraction (claude / non-JSON-mode Ollama)
    for match in _JSON_OBJ.finditer(text):
        try:
            obj = json.loads(match.group(0))
            scores = obj.get("scores") if isinstance(obj, dict) else None
            if isinstance(scores, list):
                return [_clip(_to_float(s)) for s in scores]
        except (json.JSONDecodeError, ValueError):
            continue

    return []


def _to_float(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _clip(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 10.0:
        return 10.0
    return x


__all__ = ["rerank"]
