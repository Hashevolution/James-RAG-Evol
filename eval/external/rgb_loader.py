"""Cycle γ Phase A.1 — RGB (Chen et al. 2024 EMNLP) loader.

Pulls the RGB benchmark fixture directly from the published GitHub
repository (https://github.com/chen700564/RGB) and yields
:class:`ExternalQuery` records in the unified cycle γ schema.

RGB is the JAMES-unique strength validation point: its **negative
rejection** axis maps 1:1 onto the JAMES abstention F1 metric
(``score_abstention_f1`` in ``eval/qvt/oracle.py``), and the
corpus-retrieval analysis (PR #712 §6) flagged RGB as the
strongest external evidence path for the abstention claim.

Source files (raw GitHub URLs)
------------------------------

The benchmark publishes 4 variants × 2 languages:

* ``en.json`` / ``zh.json``                 — base benchmark
* ``en_refine.json`` / ``zh_refine.json``   — refined positives + corrected answers
* ``en_int.json`` / ``zh_int.json``         — information integration
* ``en_fact.json`` / ``zh_fact.json``       — counterfactual robustness

Each entry has the following primary keys (verified against the
official ``evalue.py``):

* ``id``       — unique identifier
* ``query``    — question text
* ``answer``   — gold answer (string OR list of acceptable strings)
* ``positive`` — list of supporting passages
* ``negative`` — list of distractor passages
* ``positive_wrong``  — incorrect passages (``_fact`` variant only)

Schema mapping (RGB → :class:`ExternalQuery`)
---------------------------------------------

* ``id``         → ``"rgb-<variant>-<orig_id>"``  (namespaced)
* ``benchmark``  → ``"rgb-<variant>"``
* ``question``   → ``entry["query"]``
* ``context``    → ``tuple(positive + negative)``  (loader preserves
                  both so the scorer can identify negative-rejection
                  cases via ``len(positive) == 0``)
* ``gold_answer`` → flatten ``answer`` to a single string; the
                  original list is preserved under
                  ``metadata["answer_aliases"]`` for alias matching
* ``metadata``   → ``{
    "positive_count":  int,
    "negative_count":  int,
    "positive_wrong":  list[str],  # _fact variant only
    "answer_aliases":  list[str],
    "variant":         str,
    "language":        "en" | "zh",
  }``

Dependency strategy
-------------------

Raw HTTP download via stdlib ``urllib`` — no HuggingFace ``datasets``
package, no extra dependency. The fixture is cached under
``eval/external/_fixtures/rgb/<variant>.json`` so a second run is
offline. Production callers can pre-populate the cache directory
without involving the loader; the loader only downloads when the
cache is absent.

The download itself is opt-in: ``iter_queries`` accepts a
``cache_dir`` argument. Tests pass a tmpdir with a hand-written
synthetic fixture so they neither download anything nor depend on
the live RGB repo.

Self-eval trap rule (memory ``feedback_self_evaluation_trap``):
the loader does NOT rewrite queries, does NOT curate a subset, and
does NOT modify gold answers. Every byte of the source fixture
either lands in :class:`ExternalQuery` directly or under
``metadata`` for the scorer to consume.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from eval.external.base import ExternalBenchFixture, ExternalQuery


# ─── Source registry ───────────────────────────────────────────────


# Published variants. Order matches the original GitHub repo's
# ``data/`` listing. Adding a new entry here is the only change
# needed to ship a new variant.
RGB_VARIANTS: Tuple[str, ...] = (
    "en",
    "zh",
    "en_refine",
    "zh_refine",
    "en_int",
    "zh_int",
    "en_fact",
    "zh_fact",
)


_GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/chen700564/RGB/master/data/"
)


def _default_cache_dir() -> Path:
    """Resolve the package-local cache directory.

    ``eval/external/_fixtures/rgb/`` — same tree as the loader so a
    git-cloned checkout can ship pre-populated fixtures without an
    environment-variable dance.
    """
    return (Path(__file__).resolve().parent / "_fixtures" / "rgb")


# ─── Fixture download / cache ───────────────────────────────────────


def _variant_url(variant: str) -> str:
    if variant not in RGB_VARIANTS:
        raise ValueError(
            f"unknown RGB variant: {variant!r}. "
            f"Valid: {RGB_VARIANTS}"
        )
    return f"{_GITHUB_RAW_BASE}{variant}.json"


def _cache_path(variant: str, cache_dir: Optional[Path]) -> Path:
    base = Path(cache_dir) if cache_dir else _default_cache_dir()
    return base / f"{variant}.json"


def _ensure_fixture(
    variant: str,
    cache_dir: Optional[Path],
    *,
    allow_download: bool,
) -> Path:
    """Return the on-disk path to ``<variant>.json``. Downloads it
    from GitHub if absent and ``allow_download`` is True.

    Raises:
        FileNotFoundError: when the cached fixture is missing and
            downloads are disabled (test path).
        urllib.error.URLError: when the download fails.
    """
    path = _cache_path(variant, cache_dir)
    if path.exists():
        return path
    if not allow_download:
        raise FileNotFoundError(
            f"RGB {variant!r} fixture not in cache at {path} and "
            f"download disabled (pass allow_download=True to fetch)."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    url = _variant_url(variant)
    # Stream-write so a 10+ MB fixture doesn't sit in memory twice.
    with urllib.request.urlopen(url) as resp, open(path, "wb") as f:
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            f.write(chunk)
    return path


# The published RGB fixtures are JSONL (one JSON object per line) —
# not a top-level JSON array — for the ``en`` / ``zh`` / ``*_int`` /
# ``*_fact`` variants. The ``*_refine`` variants are a single JSON
# list. Phase B smoke (2026-06-08) caught this: the loader's
# original ``json.load`` raised ``Extra data`` on the first newline.
# This helper accepts both formats so the loader stays oblivious to
# the per-variant wire shape.
def _load_rgb_fixture(path: Path, *, variant: str) -> List[Dict[str, Any]]:
    """Return a list of dict entries from an RGB fixture file.

    Detection rule (cheap, no second pass): strip leading whitespace
    and look at the first non-whitespace character. ``[`` → JSON
    array; anything else → JSONL (one object per non-empty line).

    Empty / whitespace-only lines are skipped silently so a trailing
    newline does not raise.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()
    head = text.lstrip()[:1]
    if head == "[":
        raw = json.loads(text)
        if not isinstance(raw, list):
            raise ValueError(
                f"RGB {variant!r} fixture must be a JSON list; "
                f"got {type(raw).__name__}"
            )
        return raw
    # JSONL fallback.
    out: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


# ─── Schema mapping ────────────────────────────────────────────────


def _flatten_answer(raw: Any) -> Tuple[str, List[str]]:
    """RGB ``answer`` may be a string or a list of acceptable strings.

    Returns ``(primary_answer, aliases)`` where ``primary_answer`` is
    a single string suitable for ``ExternalQuery.gold_answer`` and
    ``aliases`` is the rest of the list (empty if the source already
    was a single string).
    """
    if isinstance(raw, str):
        return raw, []
    if isinstance(raw, list):
        flat: List[str] = []
        for item in raw:
            if isinstance(item, list):
                # Sometimes nested (alias groups). Flatten one level.
                flat.extend(str(x) for x in item)
            else:
                flat.append(str(item))
        if not flat:
            return "", []
        return flat[0], flat[1:]
    # Anything else (None / int / dict) → str() fallback, no aliases.
    return ("" if raw is None else str(raw)), []


def _entry_to_query(
    entry: Dict[str, Any],
    *,
    variant: str,
) -> ExternalQuery:
    """Single-query mapping — produces ONLY the noise-robustness
    query for one fixture entry. Kept for back-compat (callers that
    construct queries directly) and re-used internally by
    :func:`_entries_to_queries`.
    """
    orig_id = str(entry.get("id", "")).strip()
    if not orig_id:
        # Fall back to a positional id only when the source row truly
        # omits it; raises in validate_queries if it stays empty.
        orig_id = "noid"
    primary, aliases = _flatten_answer(entry.get("answer"))
    positive = list(entry.get("positive") or [])
    negative = list(entry.get("negative") or [])
    positive_wrong = list(entry.get("positive_wrong") or [])

    metadata: Dict[str, Any] = {
        "positive_count":  len(positive),
        "negative_count":  len(negative),
        "answer_aliases":  aliases,
        "variant":         variant,
        "language":        ("zh" if variant.startswith("zh") else "en"),
        "setting":         "noise_robustness",
    }
    # _fact variant carries an extra distractor list.
    if positive_wrong:
        metadata["positive_wrong"] = positive_wrong

    return ExternalQuery(
        id=f"rgb-{variant}-{orig_id}-noise",
        benchmark=f"rgb-{variant}",
        question=str(entry.get("query", "")),
        context=tuple(str(p) for p in (positive + negative)),
        gold_answer=primary,
        metadata=metadata,
    )


def _entry_to_negative_rejection_query(
    entry: Dict[str, Any],
    *,
    variant: str,
) -> ExternalQuery:
    """Negative-rejection variant of one fixture entry — strips the
    positive passages so the model sees only distractors.

    Implements the RGB paper's negative-rejection setting (Chen et
    al. 2024 EMNLP, §3.2): given irrelevant docs only, does the
    model abstain? ``positive_count=0`` in metadata routes the row
    onto the scorer's abstention branch automatically.

    Cycle γ Phase B smoke (2026-06-08) discovered the published
    fixture has no rows with ``positive=[]`` natively — the
    negative-rejection axis is a *setting* the runner constructs,
    not a class of rows in the file. This helper builds that
    setting per row.
    """
    orig_id = str(entry.get("id", "")).strip() or "noid"
    primary, aliases = _flatten_answer(entry.get("answer"))
    negative = list(entry.get("negative") or [])

    metadata: Dict[str, Any] = {
        "positive_count":  0,         # → scorer routes to abstention
        "negative_count":  len(negative),
        # The original gold + aliases stay under metadata so a
        # downstream forensic step can confirm whether the model
        # somehow guessed the right answer from negative docs
        # alone (a learning-leak signal).
        "answer_aliases":  aliases,
        "variant":         variant,
        "language":        ("zh" if variant.startswith("zh") else "en"),
        "setting":         "negative_rejection",
        # Cross-link back to the paired noise-robustness query for
        # per-question analysis downstream.
        "paired_id":       f"rgb-{variant}-{orig_id}-noise",
    }

    return ExternalQuery(
        id=f"rgb-{variant}-{orig_id}-negrej",
        benchmark=f"rgb-{variant}",
        question=str(entry.get("query", "")),
        context=tuple(str(n) for n in negative),
        # Empty gold so the scorer's noise-robustness branch (which
        # is gated on positive_count > 0 anyway) cannot accidentally
        # score this row.
        gold_answer="",
        metadata=metadata,
    )


def _entries_to_queries(
    entry: Dict[str, Any],
    *,
    variant: str,
    abstention_mode: bool,
) -> List[ExternalQuery]:
    """Emit one or two queries per fixture entry.

    Always emits the noise-robustness query. When
    ``abstention_mode=True`` AND the entry has at least one positive
    passage to strip, also emits the negative-rejection variant — so
    the same fixture row drives both axes of the cycle γ table.

    The negative-rejection variant is suppressed when there are no
    positive passages to remove (the resulting query would be
    identical to the noise-robustness one, doubling cost without
    new evidence).
    """
    noise_q = _entry_to_query(entry, variant=variant)
    if not abstention_mode:
        return [noise_q]
    positive = entry.get("positive") or []
    if not positive:
        # Nothing to strip — negative-rejection would be a clone.
        return [noise_q]
    return [noise_q, _entry_to_negative_rejection_query(
        entry, variant=variant,
    )]


# ─── Loader ────────────────────────────────────────────────────────


class RGBLoader(ExternalBenchFixture):
    """Loader for one RGB variant (``en`` / ``zh`` / ``en_refine`` /
    ``en_int`` / ``en_fact`` / Chinese counterparts).

    Usage::

        loader = RGBLoader(variant="en", allow_download=True)
        queries = loader.iter_queries(n_samples=20)   # Phase B smoke
        # later, after caching:
        queries = loader.iter_queries()               # full split

    Notes:
        * ``allow_download=False`` (the default) is the safe mode for
          test environments — it raises ``FileNotFoundError`` if the
          cache is absent rather than hitting the network silently.
        * ``cache_dir`` lets tests redirect to a tmpdir; production
          callers should pass ``None`` so the loader uses
          ``eval/external/_fixtures/rgb/``.
    """

    def __init__(
        self,
        *,
        variant: str = "en",
        cache_dir: Optional[Path] = None,
        allow_download: bool = False,
        abstention_mode: bool = True,
        setting_filter: Optional[str] = None,
    ):
        """``abstention_mode`` controls whether the loader emits the
        negative-rejection variant alongside the noise-robustness
        query (default: True, which mirrors the RGB paper's dual-axis
        evaluation). Set to False to halve cost when only
        noise-robustness is needed (e.g. a cost-sensitive smoke run
        or a single-axis ablation).

        ``setting_filter`` (``None`` / ``"noise_robustness"`` /
        ``"negative_rejection"``) post-filters the emitted query
        stream to one axis only. Cycle γ Phase B JAMES-engine
        experiments need this so each measurement can target the
        workspace tuned for that axis: workspace #1 has full
        positive+negative ingestion (run with
        ``setting_filter="noise_robustness"``); workspace #2 has
        negative-only ingestion (run with
        ``setting_filter="negative_rejection"``). When ``None``,
        every emitted query passes through unchanged.
        """
        if variant not in RGB_VARIANTS:
            raise ValueError(
                f"unknown RGB variant: {variant!r}. "
                f"Valid: {RGB_VARIANTS}"
            )
        if setting_filter is not None and setting_filter not in (
            "noise_robustness", "negative_rejection",
        ):
            raise ValueError(
                f"setting_filter must be None / 'noise_robustness' / "
                f"'negative_rejection'; got {setting_filter!r}"
            )
        self._variant = variant
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._allow_download = allow_download
        self._abstention_mode = abstention_mode
        self._setting_filter = setting_filter

    @property
    def abstention_mode(self) -> bool:
        return self._abstention_mode

    @property
    def setting_filter(self) -> Optional[str]:
        return self._setting_filter

    @property
    def benchmark_id(self) -> str:
        return f"rgb-{self._variant}"

    @property
    def variant(self) -> str:
        return self._variant

    @property
    def cache_path(self) -> Path:
        return _cache_path(self._variant, self._cache_dir)

    def iter_queries(
        self,
        *,
        split: str = "dev",
        n_samples: Optional[int] = None,
    ) -> List[ExternalQuery]:
        """Load + parse the cached (or freshly-downloaded) fixture and
        yield queries in the unified schema.

        Args:
            split: Accepted purely for interface uniformity with
                other loaders. RGB does not publish train/dev/test
                splits — every variant is one flat list. The argument
                is recorded but not used.
            n_samples: see :meth:`ExternalBenchFixture.take_sample`.

        Raises:
            FileNotFoundError: cache missing + downloads disabled.
            ValueError: validation failed (empty id / dup id /
                benchmark mismatch).
            json.JSONDecodeError: cached file is corrupt.
        """
        path = _ensure_fixture(
            self._variant,
            self._cache_dir,
            allow_download=self._allow_download,
        )
        raw = _load_rgb_fixture(path, variant=self._variant)

        queries: List[ExternalQuery] = []
        for e in raw:
            if not isinstance(e, dict):
                continue
            queries.extend(_entries_to_queries(
                e,
                variant=self._variant,
                abstention_mode=self._abstention_mode,
            ))
        # Apply setting_filter BEFORE id-uniqueness validation so a
        # narrow run does not need both halves of every paired row.
        if self._setting_filter is not None:
            queries = [q for q in queries
                        if q.metadata.get("setting") == self._setting_filter]
        self.validate_queries(queries)
        # ``n_samples`` is applied to the *output* query stream — so a
        # caller asking for 50 queries gets 50 queries, regardless of
        # whether the loader expanded each fixture row 1× or 2×. This
        # matches the rest of the cycle γ runners' semantics (the cap
        # is on producer calls, not fixture rows).
        return self.take_sample(queries, n_samples)


__all__ = [
    "RGB_VARIANTS",
    "RGBLoader",
]
