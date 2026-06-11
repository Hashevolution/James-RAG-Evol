"""Cycle γ Phase A.5 — unified external-benchmark runner core.

This module is the *engine* the ``scripts/external_bench_run.py``
CLI dispatches to. Keeping the engine in ``eval/external/`` (pure
Python, no ``argparse``, no ``sys.exit``) means the same code path
can be unit-tested without a subprocess shell-out and reused from
notebook / orchestrator code if a future phase needs to.

Three pluggable parts
---------------------

1. **Loader dispatch** — :func:`build_loader` maps
   ``("rgb"|"alce"|"musique"|"2wiki", <variant_or_split>, cache_dir)``
   to a concrete :class:`ExternalBenchFixture` subclass. Cycle γ
   already shipped four loaders (A.1 – A.3); this dispatch is the
   one-stop import surface for the CLI.

2. **Scorer dispatch** — :func:`build_scorer` mirrors the loader
   side for the four :class:`ExternalScorer` subclasses (A.4.1 –
   A.4.4). The dispatch makes the runner benchmark-agnostic.

3. **Answer producer** — the runner does NOT prescribe how an
   answer is produced. Production callers wire one of:

   * :class:`ClosedCorpusGemmaProducer` — passes ``query.context``
     as evidence to a local Ollama Gemma call (mirrors the Phase
     B / Layer B paper-aligned baseline pattern from
     ``scripts/research/multihop_raw_run.py``).
   * :class:`JamesEngineProducer` — full JAMES stack via
     :class:`ReasoningEngine`, using JAMES's own retrieval rather
     than the fixture context. The cycle γ premise (production-mirror
     evaluation) is *both* are valid measurement modes, so both
     ship.
   * A test stub conforming to the :class:`AnswerProducer` Protocol.
     The unit tests use one so the engine is exercised end-to-end
     without an LLM dependency.

The :func:`run_external_bench` function plumbs queries from a
loader, through a producer, into a scorer, and returns one
JSON-serialisable result dict. The dict shape is the cross-bench
table the Phase C / D analysis consumes.

Self-eval trap rule (memory ``feedback_self_evaluation_trap``):
the runner is *only* plumbing — it does not write fixtures, oracles,
or scoring logic. Every fact the runner emits is either (a) a row
straight from a published fixture, (b) a model's free-text answer,
or (c) a number a published scorer computed. JAMES-internal logic
is confined to the producer (system under test), never the oracle.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

from eval.external import (
    ExternalBenchFixture,
    ExternalQuery,
    ExternalScorer,
    ScoreAxis,
)


# ─── Loader dispatch ───────────────────────────────────────────────


# Stable benchmark IDs accepted by ``build_loader`` and the CLI.
SUPPORTED_BENCHES: Tuple[str, ...] = ("rgb", "alce", "musique", "2wiki")


def build_loader(
    bench: str,
    *,
    variant: Optional[str] = None,
    split: Optional[str] = None,
    cache_dir: Optional[Path] = None,
    allow_download: bool = False,
    setting_filter: Optional[str] = None,
    abstention_mode: bool = True,
) -> ExternalBenchFixture:
    """Construct one of the four cycle γ loaders by name.

    Args:
        bench: One of ``SUPPORTED_BENCHES``.
        variant: Required for benches with variants (rgb/alce/musique);
            ignored for 2wiki.
        split: Required for benches with splits (musique/2wiki);
            ignored for rgb/alce (single-split).
        cache_dir: Optional cache directory; loader-specific.
        allow_download: Only honoured by the RGB loader (the rest
            require the fixture to be pre-downloaded).
        setting_filter: RGB-only — restrict the emitted query stream
            to one axis (``"noise_robustness"`` or
            ``"negative_rejection"``). Cycle γ Phase B JAMES-engine
            experiments use this to pair an axis-specific workspace
            with an axis-specific query slice.
        abstention_mode: RGB-only — emit the negative-rejection
            variant alongside the noise-robustness query (default
            True; the dual-axis evaluation).

    Raises:
        ValueError: unknown bench / missing required variant or split.
    """
    bench = bench.strip().lower()
    if bench == "rgb":
        from eval.external.rgb_loader import RGBLoader
        return RGBLoader(
            variant=variant or "en",
            cache_dir=cache_dir,
            allow_download=allow_download,
            abstention_mode=abstention_mode,
            setting_filter=setting_filter,
        )
    if bench == "alce":
        from eval.external.alce_loader import ALCELoader
        return ALCELoader(
            variant=variant or "asqa",
            cache_dir=cache_dir,
        )
    if bench == "musique":
        from eval.external.musique_loader import MuSiQueLoader
        return MuSiQueLoader(
            variant=variant or "ans",
            split=split or "dev",
            cache_dir=cache_dir,
        )
    if bench == "2wiki":
        from eval.external.wikimulti_loader import WikiMultiLoader
        return WikiMultiLoader(
            split=split or "dev",
            cache_dir=cache_dir,
        )
    raise ValueError(
        f"unknown bench: {bench!r}. Valid: {SUPPORTED_BENCHES}"
    )


# ─── Scorer dispatch ───────────────────────────────────────────────


def build_scorer(
    bench: str,
    *,
    variant: Optional[str] = None,
    verifier: Optional[Any] = None,
) -> ExternalScorer:
    """Construct the matching scorer for a benchmark.

    The variant must align with the loader's variant — the runner
    enforces this implicitly via ``ExternalScorer.validate_queries``
    on the first :meth:`score` call.

    ``verifier`` is the ALCE-specific NLI verifier callable
    (:class:`eval.external.alce_scorer.NLIVerifier`); ignored by
    the other scorers.
    """
    bench = bench.strip().lower()
    if bench == "rgb":
        from eval.external.rgb_scorer import RGBScorer
        return RGBScorer(variant=variant or "en")
    if bench == "alce":
        from eval.external.alce_scorer import ALCEScorer
        return ALCEScorer(
            variant=variant or "asqa",
            verifier=verifier,
        )
    if bench == "musique":
        from eval.external.musique_scorer import MuSiQueScorer
        return MuSiQueScorer(variant=variant or "ans")
    if bench == "2wiki":
        from eval.external.wikimulti_scorer import WikiMultiScorer
        return WikiMultiScorer()
    raise ValueError(
        f"unknown bench: {bench!r}. Valid: {SUPPORTED_BENCHES}"
    )


# ─── AnswerProducer interface ──────────────────────────────────────


class AnswerProducer(Protocol):
    """Every producer maps one :class:`ExternalQuery` to one bench
    row in the JAMES bench-JSON shape.

    The minimum row keys are ``id`` (mirrors ``query.id``) and
    ``answer`` (the model's free-text output). Producers MAY emit
    additional keys the scorer reads — e.g.
    ``predicted_supporting_facts`` for 2Wiki, ``predicted_support_idx``
    for MuSiQue. The runner does not interpret these keys; it
    just hands the row to the scorer verbatim.
    """

    name: str

    def produce(self, query: ExternalQuery) -> Dict[str, Any]: ...


class StubProducer:
    """Test producer — answers via a caller-supplied callable.

    Used by the cycle γ unit tests so the runner is exercised
    end-to-end without an LLM. Also useful for ablation runs that
    replay a fixed answer per query id.
    """

    name = "stub"

    def __init__(self, answer_fn: Callable[[ExternalQuery], Dict[str, Any]]):
        if not callable(answer_fn):
            raise TypeError("answer_fn must be callable")
        self._fn = answer_fn

    def produce(self, query: ExternalQuery) -> Dict[str, Any]:
        row = self._fn(query) or {}
        if not isinstance(row, dict):
            raise TypeError(
                f"answer_fn must return a dict; got {type(row).__name__}"
            )
        return row


class ClosedCorpusGemmaProducer:
    """Closed-corpus producer — feeds ``query.context`` as evidence to
    a local Ollama Gemma call.

    Closed-corpus mode is the publishable baseline: every model sees
    the *same* gold context the benchmark publishes, so cross-model
    deltas are not confounded by retrieval differences. The cycle γ
    paper-aligned table uses this mode.

    The producer does NOT import :mod:`core.gemma_client` at module
    import time — it imports inside :meth:`produce` so the runner
    module stays importable in environments without Ollama (the
    unit-test environment, for instance).
    """

    name = "closed-corpus-gemma"

    def __init__(
        self,
        *,
        model: str = "gemma4:e4b",
        max_tokens: int = 8192,
        timeout: int = 180,
        think: bool = False,
        use_cache: bool = False,
        context_separator: str = "\n\n",
        max_prompt_chars: int = 200_000,
    ):
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._think = think
        self._use_cache = use_cache
        self._sep = context_separator
        # Lift the GemmaClient prompt cap for external-bench runs;
        # default 4000 in the client silently truncates multi-doc
        # evidence (cycle γ Phase B smoke #2, 2026-06-08). The runner
        # passes this through the env var GemmaClient now reads
        # (JAMES_GEMMA_MAX_PROMPT_CHARS) — production callers that
        # never construct this producer keep the original 4000.
        self._max_prompt_chars = max_prompt_chars

    def _prompt(self, query: ExternalQuery) -> str:
        ctx = self._sep.join(query.context)
        return (
            "Answer the question using only the provided context. "
            "If the context is insufficient, answer "
            "'Insufficient Information'.\n\n"
            f"Context:\n{ctx}\n\n"
            f"Question: {query.question}\n"
        )

    def produce(self, query: ExternalQuery) -> Dict[str, Any]:
        from core.gemma_client import GemmaClient   # late import
        # Lift the cap for this call. The env var is read per-call by
        # _resolve_max_prompt_len so the override is scoped to this
        # process; no global mutation that could leak to other
        # GemmaClient consumers.
        os.environ["JAMES_GEMMA_MAX_PROMPT_CHARS"] = str(
            self._max_prompt_chars
        )
        client = GemmaClient()
        ans = client.call_gemma(
            self._prompt(query),
            model=self._model,
            max_tokens=self._max_tokens,
            think=self._think,
            use_cache=self._use_cache,
            timeout=self._timeout,
        )
        return {
            "id":       query.id,
            "answer":   ans,
            "sources":  list(query.context[:1]) if query.context else [],
            "mode":     "closed-corpus",
            "model":    self._model,
        }


class JamesEngineProducer:
    """Full-JAMES producer — routes the question through
    :class:`core.reasoning.engine.ReasoningEngine`.

    Ignores ``query.context``: JAMES uses its own retrieval against
    the corpus configured by ``JAMES_WORKSPACE``. Cycle γ Phase B/C
    operators are responsible for building a JAMES corpus that
    mirrors the benchmark's source documents — that's a separate
    operator task; this producer just plumbs the engine call.

    Like the closed-corpus producer, the engine import is deferred to
    :meth:`produce` so the runner module is importable in the
    test environment.
    """

    name = "james-engine"

    def __init__(
        self,
        *,
        model: str = "gemma4:e4b",
        response_style: str = "",
        user_role: str = "admin",
        mode_override: str = "retrieval",
        session_prefix: str = "external-bench",
    ):
        self._model = model
        self._response_style = response_style
        self._user_role = user_role
        self._mode_override = mode_override
        self._session_prefix = session_prefix

    def produce(self, query: ExternalQuery) -> Dict[str, Any]:
        from core.reasoning.engine import ReasoningEngine   # late import
        eng = ReasoningEngine()
        out = eng.query(
            query.question,
            user_role=self._user_role,
            response_style=self._response_style,
            selected_model=self._model,
            mode_override=self._mode_override,
            session_id=f"{self._session_prefix}-{query.id}",
        )
        ans = out.get("answer", "") if isinstance(out, dict) else str(out)
        srcs = ((out.get("sources") or out.get("docs") or [])
                if isinstance(out, dict) else [])
        source_names: List[str] = []
        if isinstance(srcs, (list, tuple)):
            for s in srcs:
                if isinstance(s, dict):
                    name = (s.get("source") or s.get("title")
                            or s.get("filename") or s.get("file") or "")
                elif isinstance(s, str):
                    name = s
                else:
                    name = ""
                name = (name or "").strip()
                if name:
                    source_names.append(name)
        return {
            "id":           query.id,
            "answer":       ans,
            "sources":      source_names,
            "sources_count": len(source_names),
            "mode":         "james-engine",
            "model":        self._model,
        }


# ─── Core run loop ─────────────────────────────────────────────────


def _axis_to_dict(axis: ScoreAxis) -> Dict[str, Any]:
    """Serialise one ``ScoreAxis`` for JSON output.

    Floats round to 4 decimals — the publishable tables only carry
    that many significant digits and round-tripping deeper precision
    encourages over-reading noise.
    """
    return {
        "name":      axis.name,
        "score":     round(float(axis.score), 4),
        "n_queries": int(axis.n_queries),
        "per_query": dict(axis.per_query),
        "notes":     axis.notes,
    }


def run_external_bench(
    *,
    loader: ExternalBenchFixture,
    scorer: ExternalScorer,
    producer: AnswerProducer,
    split: str = "dev",
    n_samples: Optional[int] = None,
    progress_every: int = 10,
    on_progress: Optional[Callable[[int, int, float], None]] = None,
) -> Dict[str, Any]:
    """Drive ``loader → producer → scorer`` end-to-end and return one
    cross-bench result dict.

    The returned shape::

        {
          "benchmark":  "<scorer.benchmark_id>",
          "loader":     "<loader.benchmark_id>",
          "producer":   "<producer.name>",
          "split":      "<split>",
          "n_queries":  <int>,
          "n_rows":     <int>,
          "n_errors":   <int>,
          "elapsed_s":  <float>,
          "started_at": "<ISO-8601 UTC>",
          "axes":       [<axis-dict>, ...],
          "rows":       [<bench-row>, ...]
        }

    The axes list IS the publishable table. The rows list is the
    raw per-query bench output — Phase D analysis reads it for
    per-row breakdowns, per-question-type cross-tabs, etc.
    """
    # Loader / scorer benchmark id must match — catch a misrouted
    # CLI call before the LLM-cost run starts.
    if loader.benchmark_id != scorer.benchmark_id:
        raise ValueError(
            f"loader/scorer benchmark id mismatch: "
            f"loader={loader.benchmark_id!r}, "
            f"scorer={scorer.benchmark_id!r}"
        )

    queries = loader.iter_queries(split=split, n_samples=n_samples)
    rows: List[Dict[str, Any]] = []
    n_errors = 0
    t0 = time.time()
    started = _dt.datetime.now(_dt.timezone.utc).isoformat()

    for i, q in enumerate(queries, 1):
        try:
            row = producer.produce(q)
            if not isinstance(row, dict):
                raise TypeError(
                    f"producer.produce returned {type(row).__name__}, "
                    f"expected dict"
                )
            row.setdefault("id", q.id)
            row.setdefault("status", "ok")
        except Exception as exc:                       # one bad query
            n_errors += 1                              # must not kill
            row = {                                    # the whole run
                "id":     q.id,
                "answer": f"[ERROR] {exc!r}",
                "status": "error",
                "error":  "".join(
                    traceback.format_exception_only(type(exc), exc)
                ).strip(),
            }
        rows.append(row)

        if (on_progress is not None
                and (i % max(progress_every, 1) == 0 or i == len(queries))):
            on_progress(i, len(queries), time.time() - t0)

    axes = scorer.score(queries, rows)

    return {
        "benchmark":  scorer.benchmark_id,
        "loader":     loader.benchmark_id,
        "producer":   getattr(producer, "name", type(producer).__name__),
        "split":      split,
        "n_queries":  len(queries),
        "n_rows":     len(rows),
        "n_errors":   n_errors,
        "elapsed_s":  round(time.time() - t0, 3),
        "started_at": started,
        "axes":       [_axis_to_dict(a) for a in axes],
        "rows":       rows,
    }


def write_result(result: Dict[str, Any], out_path: Path) -> Path:
    """Atomic-ish JSON write: write to ``<out>.tmp`` then rename.

    Returns the final path so callers can log it.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    os.replace(tmp, out_path)
    return out_path


__all__ = [
    "SUPPORTED_BENCHES",
    "AnswerProducer",
    "ClosedCorpusGemmaProducer",
    "JamesEngineProducer",
    "StubProducer",
    "build_loader",
    "build_scorer",
    "run_external_bench",
    "write_result",
]
