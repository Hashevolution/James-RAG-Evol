"""LRB v0.2.4 + Track C C2 — answer generation pipeline.

Given retrieved context, generate a natural-language answer. Used by:
  * v0.2.4 HR axis (LRB-S1 / LRB-S2 answers + NLI scoring)
  * Track C reasoning bench measurements (TimeQA / TempReason / MuSiQue
    answer F1 / EM / NLI)

Design:
  * Direct Ollama HTTP (deterministic: temperature=0, seed=42)
  * Same dispatch pattern as `llm_rerank.py` (same operator footprint)
  * Lean prompt — no chain-of-thought, no formatting tricks; we measure
    base reasoning capability of the (SUT-retrieved context + model)
    combination, not prompt-engineering wins
  * Returns generated text + total latency

This module does NOT pick the retrieval order — caller passes already-
retrieved docs (typically from an LRB SUT adapter).
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List, Optional, Tuple


# ──────────────────────────────────────────────────────────────────────
# Prompt
# ──────────────────────────────────────────────────────────────────────


_BENCH_ANSWER_PROMPT = """Answer the question using ONLY the provided context.

If the context does not contain the answer, reply with "Insufficient Information."
Be concise. Do not invent facts.

Context:
{context}

Question: {question}

Answer:"""


def build_prompt(question: str,
                 doc_snippets: List[Tuple[str, str, str]],
                 *, max_chars_per_doc: int = 800) -> str:
    """Build the answer prompt.

    Args:
      question:    user question
      doc_snippets: list of (doc_id, title, text) ordered by retrieval
                   rank (best-first)
      max_chars_per_doc: truncate each doc body to N chars (keeps total
                         prompt under typical context window)
    """
    blocks: List[str] = []
    for i, (doc_id, title, text) in enumerate(doc_snippets, start=1):
        snippet = text[:max_chars_per_doc].replace("\n", " ").strip()
        blocks.append(f"[{i}] {title} ({doc_id}): {snippet}")
    context = "\n".join(blocks) if blocks else "(no documents retrieved)"
    return _BENCH_ANSWER_PROMPT.format(
        context=context, question=question)


# ──────────────────────────────────────────────────────────────────────
# Model dispatch (mirrors llm_rerank)
# ──────────────────────────────────────────────────────────────────────


OLLAMA_MODEL_PREFIXES = ("gemma", "mixtral", "mistral", "llama",
                          "qwen", "phi", "deepseek")
CLAUDE_MODEL_PREFIXES = ("claude-",)


def _is_ollama_model(model: str) -> bool:
    name = model.split(":")[0].lower()
    return any(name.startswith(p) for p in OLLAMA_MODEL_PREFIXES)


def _is_claude_model(model: str) -> bool:
    return any(model.lower().startswith(p)
               for p in CLAUDE_MODEL_PREFIXES)


# ──────────────────────────────────────────────────────────────────────
# Generation
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GenerationResult:
    answer: str
    model: str
    elapsed_s: float
    truncated: bool = False
    error: Optional[str] = None


def generate_answer(question: str,
                     doc_snippets: List[Tuple[str, str, str]],
                     *,
                     model: str,
                     ollama_url: str = "http://localhost:11434",
                     timeout: float = 60.0,
                     max_tokens: int = 512) -> GenerationResult:
    """Generate an answer.

    Returns ``GenerationResult`` with empty ``answer`` and an ``error``
    string on failure — caller decides how to score (per LRB v0.2.4
    prereg §2.3 empty answer → HR=1.0 abstention).
    """
    import time
    prompt = build_prompt(question, doc_snippets)
    start = time.perf_counter()

    if _is_ollama_model(model):
        text, err = _call_ollama_generate(prompt, model=model,
                                            ollama_url=ollama_url,
                                            timeout=timeout,
                                            max_tokens=max_tokens)
    elif _is_claude_model(model):
        text, err = _call_claude_cli_generate(prompt, model=model,
                                                timeout=timeout)
    else:
        return GenerationResult(answer="", model=model,
                                 elapsed_s=time.perf_counter() - start,
                                 error=f"unsupported model {model!r}")

    return GenerationResult(
        answer=text.strip() if text else "",
        model=model,
        elapsed_s=round(time.perf_counter() - start, 4),
        error=err,
    )


def _call_ollama_generate(prompt: str, *, model: str, ollama_url: str,
                           timeout: float,
                           max_tokens: int) -> Tuple[str, Optional[str]]:
    payload = {
        "model":   model,
        "prompt":  prompt,
        "stream":  False,
        "options": {"temperature": 0.0, "seed": 42,
                    "num_predict": max_tokens},
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
    except urllib.error.URLError as e:
        return "", f"ollama URLError: {e}"
    except (json.JSONDecodeError, TimeoutError) as e:
        return "", f"ollama parse/timeout: {e}"

    return data.get("response", ""), None


def _call_claude_cli_generate(prompt: str, *, model: str,
                                timeout: float
                                ) -> Tuple[str, Optional[str]]:
    """Headless ``claude -p``. Direction α S5c env-whitelist applied."""
    import os

    base_env = {}
    for var in ("SystemRoot", "APPDATA", "LOCALAPPDATA",
                 "USERPROFILE", "TEMP", "TMP", "Path", "PATH",
                 "HOME", "ANTHROPIC_API_KEY"):
        if var in os.environ:
            base_env[var] = os.environ[var]

    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", model],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tempfile.gettempdir(),
            env=base_env,
        )
        if proc.returncode != 0:
            return "", f"claude CLI returncode={proc.returncode}: {proc.stderr[:200]}"
        return proc.stdout, None
    except FileNotFoundError:
        return "", "claude CLI not in PATH (operator action: install)"
    except subprocess.TimeoutExpired:
        return "", "claude CLI timeout"
    except OSError as e:
        return "", f"claude CLI OSError: {e}"


# ──────────────────────────────────────────────────────────────────────
# Convenience: fetch + generate from an LRB adapter
# ──────────────────────────────────────────────────────────────────────


def answer_from_adapter(adapter,
                         question: str,
                         *,
                         k: int = 5,
                         query_time: int,
                         valid_time: int,
                         model: str,
                         ollama_url: str = "http://localhost:11434",
                         timeout: float = 60.0,
                         max_tokens: int = 512
                         ) -> Tuple[GenerationResult, List[str]]:
    """Fetch top-k docs from adapter at the given (qt, vt), then
    generate an answer using the given model.

    Returns (GenerationResult, retrieved_doc_ids).
    """
    retrieved = adapter.retrieve_at(question, k, query_time, valid_time)
    snippets: List[Tuple[str, str, str]] = []
    for doc_id in retrieved:
        rec = adapter.get_doc(doc_id)
        if rec is None:
            continue
        title, text = rec
        snippets.append((doc_id, title, text))

    result = generate_answer(question, snippets, model=model,
                              ollama_url=ollama_url,
                              timeout=timeout,
                              max_tokens=max_tokens)
    return result, retrieved


__all__ = [
    "build_prompt", "GenerationResult", "generate_answer",
    "answer_from_adapter",
]
