"""QVT α-3 non-saturating quality oracle — 3-axis scoring.

Consumes a bench JSON (output of `python scripts/bench.py --suite=step7
--mode=retrieval`) and the v5 fixture (`eval/regression/step7_queries.json`)
and produces three orthogonal quality scores plus a per-query breakdown.

Axes (design memo §2):

  1. Path Coverage — fraction of `expected_path.nodes` hit by graph_paths.
     Currently 5/16 fixture queries annotated; pass-through aggregate of
     bench.py's `path_recall_aggregate` block.

  2. Graded Answer Accuracy — for every query, count how many of its 3
     `gold_signals` (term OR any alias) appear as a case-insensitive
     substring of the answer. Score = hits / 3. Mean across all queries.

  3. Calibrated Abstention F1 — treats "system abstained" as the positive
     class. Compared against `abstention_truth`:
       TP = should-abstain (truth=absent) AND did-abstain (correct refusal)
       FP = should-answer  (truth=present) AND did-abstain (incorrect_abstention)
       FN = should-abstain (truth=absent) AND did-answer  (hallucination)
       TN = should-answer  (truth=present) AND did-answer (correct answer)
     F1 = 2·P·R / (P + R) where P=TP/(TP+FP), R=TP/(TP+FN).

The oracle is deterministic — no LLM judge, no embedding lookups, just
substring matching. Trade-off: misses paraphrased / negated / quantitative
matches. Re-evaluation with an LLM judge is a v0.5+ candidate (see memo §6).

Bench JSON answer field — `answer_preview` (300 chars, current) preferred
when present; falls back to `answer` (full) when bench.py is updated to
emit the full string. Graded answer scores against whichever is available;
when both are absent (timeout / error) the row is treated as abstention.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Abstention phrase set
# ---------------------------------------------------------------------------
#
# Substring-matched (case-insensitive) against the answer text. Korean and
# English variants of "I don't know / cannot answer / refuse" — picked so
# that JAMES's actual output phrasings under the gemma4:e4b default model
# hit at least one phrase per genuine abstention. If α-3 baseline capture
# reveals a phrasing the system uses that doesn't trip any of these, add
# it here in a small follow-up PR (not a schema change).

_ABSTENTION_PHRASES: Tuple[str, ...] = (
    "정보가 없",
    "자료에 없",          # JAMES security-block phrasing
    "내부 자료에 없",
    "확인할 수 없",
    "찾을 수 없",
    "모르겠",
    "없습니다",
    "근거 부족",
    "근거가 부족",
    "근거를 찾",
    "할 수 없",
    "공개할 수 없",
    "제공할 수 없",
    "안내할 수 없",
    "응답할 수 없",
    "차단",                # security policy refusal marker
    "보안 정책",           # security policy refusal marker
    "i don't have",
    "i cannot",
    "i can't",
    "cannot find",
    "no information",
    "unable to",
    "refuse",
    "decline",
    # α-5 findings 2026-05-31 — gemma4:e4b's grounding training uses
    # strong refusal phrasings for null queries that the original list
    # missed. Validated against bench_f7762a3_multihop_rag_*: of the
    # 19 "FN_hallucination" rows, 14 actually abstain using one of the
    # phrases below. Kept narrow on purpose: hedges like "does not
    # contain" / "lack the specific" appear in PARTIAL-answer rows
    # ("The company is Amazon. However, the source material does not
    # contain ...") too, so over-eager phrases generate FPs on
    # truth=present queries. The phrases below only appear in unhedged
    # refusal positions.
    "impossible to answer",
    "impossible to determine",
    "impossible to identify",
    "cannot be determined",
    "cannot be answered",
    "cannot be confirmed",     # α-5 R cycle 2026-05-31: q58 etc
    "cannot be identified",    # q69
    "none of the provided",    # q51 ("Source files: None of the provided …")
    "insufficient information",
    "insufficient data",
    # α-7 sub-finding 2026-06-02 — gemma3:12b refusal style caught
    # by 4-step rule audit (`scripts/research/audit_12b_null_query_refusal_shape.py`).
    # Cross-tier audit (1b/4b/12b/27b C_minus + 12b/27b C_rag-full = 6
    # benches × 25 nulls = 150 audited answers) found 1 missed pattern
    # at gemma3:12b id=58: "The data provided doesn't explicitly link
    # a specific Zimbabwean finance minister to a partnership ...".
    # Narrow on purpose (subject = data/information + verb = link) —
    # broader patterns (e.g. plain "doesn't have") FP-flood per α-5
    # #619 lesson. Quality delta: shifts 12b pure abst_f1 0.000 →
    # ~0.077, locking the "plateau with 4b" framing in the recovery
    # curve doc. See reports/research-runs/alpha-7-bucket-d-oracle-phrase-gap.md.
    "data doesn't link",
    "data does not link",
    "data doesn't explicitly link",
    "data does not explicitly link",
    "information doesn't link",
    "information does not link",
    # α-7 baseline audit follow-up 2026-06-02 — 2 narrow phrases found
    # in cross-tier audit of post-α-7 M_M C_rag-full + α-6 baseline.
    # "cannot be completed" caught in α-7 null #5 ("The deduction
    # cannot be completed because the source material...").
    # "not available" caught in α-6 null #24 ("the articles ... is
    # not available in the current data set"). Narrow: verb-tied
    # (cannot + completed; not + available) — broader patterns like
    # "not in" or "cannot" alone FP-flood per α-5 #619 lesson.
    "cannot be completed",
    "is not available",
    "are not available",
    "was not available",
    "were not available",
)


def detect_abstention(answer: Optional[str]) -> bool:
    """True if `answer` is empty or contains any known abstention phrase.

    An empty answer (timeout / error / blocked) is treated as an abstention
    by default — the system implicitly "didn't answer".
    """
    if not answer:
        return True
    lower = answer.lower()
    for phrase in _ABSTENTION_PHRASES:
        if phrase.lower() in lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Path Coverage
#
# α-5 plan §findings 2026-05-31 — the path axis is now scored against
# BOTH `graph_paths` entities (per-query `path_metrics` from bench.py)
# AND `sources` (top-3 source documents citation field, per
# `core/reasoning/pipeline.py:343`). MultiHop-RAG's
# `evidence_list.title` semantic ("did the system cite the right
# source") doesn't match graph_paths (entity-centric) but does match
# the `sources` field (document-centric). Both signal types contribute
# to a unified path-recall axis after slug normalisation.
# ---------------------------------------------------------------------------

# Slug normaliser — used to bring three different naming surfaces into
# a single comparable form:
#
#   - fixture expected node: "The FTX trial is bigger than Sam …"
#   - graph entity name    : "Sam Bankman-Fried"
#   - source document file : "multihop_0009_SBF-Trial-The-latest-…txt"
#
# All three become lowercase ascii-alphanumeric-dash strings capped at
# 80 chars. The `multihop_<id>_` prefix and `.txt` suffix on source
# filenames are stripped before slugging so the comparable form is just
# the article slug.
import re as _re  # noqa: E402

_SOURCE_PREFIX_RE = _re.compile(r"^multihop_\d+_")
_SLUG_BAD_RE = _re.compile(r"[^a-z0-9\-]+")
_SLUG_MAX = 80


def _slug_for_match(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    # Drop multihop_<id>_ prefix on source filenames.
    s = _SOURCE_PREFIX_RE.sub("", s)
    # Drop common file extensions on source filenames.
    if s.lower().endswith(".txt"):
        s = s[:-4]
    elif s.lower().endswith(".pdf"):
        s = s[:-4]
    s = s.lower()
    s = _SLUG_BAD_RE.sub("-", s).strip("-")
    return s[:_SLUG_MAX]


@dataclass
class PathCoverageQueryRow:
    id: int
    expected_count: int
    hits: int
    recall: float
    via_graph: int = 0        # how many hits came from graph_paths
    via_sources: int = 0      # how many hits came from `sources` citations


@dataclass
class PathCoverageAxis:
    mean_recall: float
    queries_with_expected_path: int
    queries_at_full_recall: int
    per_query: List[PathCoverageQueryRow] = field(default_factory=list)


def _graph_node_slugs_from_bench_row(r: Dict[str, Any]) -> set:
    """Best-effort recovery of graph entity names from a bench row.

    bench.py's per-row `path_metrics` block has aggregate counts but not
    the raw `actual_paths` list. The unified recall axis can still match
    via `sources` (always captured post-2026-05-31). For graph-path
    matching, the row needs to have stored either `graph_paths` (list of
    path strings) or a `path_metrics.actual_nodes` field. When absent,
    graph-side returns the empty set and `sources` carries the axis.
    """
    nodes: set = set()
    raw_paths = r.get("graph_paths") or []
    if raw_paths:
        # Strings like "<src> -[REL]→ <tgt> -[REL]→ <tgt2>". The same
        # parsing bench.py uses pre-`_path_metrics` — but we re-derive
        # here because the raw list isn't stored in path_metrics.
        for ps in raw_paths:
            if not isinstance(ps, str):
                continue
            parts = ps.split(" -[")
            if parts and parts[0].strip():
                nodes.add(_slug_for_match(parts[0].strip()))
            for part in parts[1:]:
                if "]→ " in part:
                    target = part.split("]→ ", 1)[1].strip()
                    if target:
                        nodes.add(_slug_for_match(target))
    return nodes


def score_path_coverage(
    bench_results: Dict[str, Any],
    fixture: Dict[str, Any],
) -> PathCoverageAxis:
    """Unified path-recall axis against expected nodes (titles or entity
    names), with hits credited from BOTH graph_paths entities AND the
    `sources` document-citation field (post-α-5 plan §findings).

    Match semantics: slug-normalise both sides (lowercase, dash-separated,
    `multihop_<id>_` prefix stripped from source filenames, `.txt`/`.pdf`
    extension stripped). A hit on either side counts toward recall.

    The fixture parameter is currently used to map row → expected nodes
    when the bench row didn't store `path_metrics` (queries with
    `expected_path` set but no `path_metrics` block — bench.py emits one
    when graph_paths is non-empty; we keep the fixture as authority).
    """
    # Map fixture queries by id for expected-nodes lookup.
    fixture_map: Dict[int, Dict[str, Any]] = {
        int(q["id"]): q for q in fixture.get("queries", [])
    }
    rows: List[PathCoverageQueryRow] = []
    for r in bench_results.get("results", []):
        qid = int(r.get("id", -1))
        fq = fixture_map.get(qid)
        # Legacy compatibility — when no fixture context is available
        # but bench already stored `path_metrics`, trust those numbers.
        # The new unified scorer requires fixture lookup for slug
        # comparison; this branch lets historic bench JSONs (step7 v5/v6
        # or tests with empty fixture) keep working unchanged.
        if not fq:
            pm = r.get("path_metrics")
            if not pm:
                continue
            hits = int(pm.get("hits", 0))
            rows.append(PathCoverageQueryRow(
                id=qid,
                expected_count=int(pm.get("expected_count", 0)),
                hits=hits,
                recall=float(pm.get("path_recall", 0.0)),
                via_graph=hits,
                via_sources=0,
            ))
            continue
        ep = fq.get("expected_path") or {}
        expected_nodes = ep.get("nodes") or []
        if not expected_nodes:
            continue
        expected_slugs = {_slug_for_match(n) for n in expected_nodes
                          if isinstance(n, str)}
        expected_slugs.discard("")
        if not expected_slugs:
            continue

        # Graph-side hits: prefer row.graph_paths (added when present);
        # fall back to bench.py's aggregate path_metrics.hits if raw
        # paths aren't stored. The latter is graph-only and loses the
        # source-side credit.
        graph_slugs = _graph_node_slugs_from_bench_row(r)
        # Source-side hits: the citation list.
        source_slugs = {_slug_for_match(s) for s in (r.get("sources") or [])
                        if isinstance(s, str)}
        source_slugs.discard("")

        via_graph = len(expected_slugs & graph_slugs)
        via_sources = len(expected_slugs & source_slugs)
        # A title can be hit via either side; dedup so recall ≤ 1.0.
        union_hits = len(expected_slugs & (graph_slugs | source_slugs))

        # When bench.py emitted no graph_paths AND no sources, fall back
        # to whatever path_metrics.hits says so legacy bench JSONs
        # without the new fields don't regress to all-zero.
        if not graph_slugs and not source_slugs:
            pm = r.get("path_metrics")
            if pm:
                union_hits = int(pm.get("hits", 0))
                via_graph = union_hits  # treat all as graph-side legacy

        recall = union_hits / len(expected_slugs) if expected_slugs else 0.0
        rows.append(PathCoverageQueryRow(
            id=qid,
            expected_count=len(expected_slugs),
            hits=union_hits,
            recall=round(recall, 4),
            via_graph=via_graph,
            via_sources=via_sources,
        ))
    if not rows:
        return PathCoverageAxis(
            mean_recall=0.0,
            queries_with_expected_path=0,
            queries_at_full_recall=0,
            per_query=[],
        )
    mean = sum(r.recall for r in rows) / len(rows)
    full = sum(1 for r in rows if r.recall >= 1.0)
    return PathCoverageAxis(
        mean_recall=round(mean, 4),
        queries_with_expected_path=len(rows),
        queries_at_full_recall=full,
        per_query=rows,
    )


# ---------------------------------------------------------------------------
# Graded Answer Accuracy
# ---------------------------------------------------------------------------

@dataclass
class GradedAnswerQueryRow:
    id: int
    hits: int
    total: int
    score: float
    matched_signals: List[str] = field(default_factory=list)


@dataclass
class GradedAnswerAxis:
    mean_accuracy: float
    queries_with_signals: int
    per_query: List[GradedAnswerQueryRow] = field(default_factory=list)


def _answer_text(result_row: Dict[str, Any]) -> str:
    """Pick the best available answer string from a bench result row.

    Order: `answer` (full, if bench.py emits it) → `answer_preview` (300
    chars, current default) → empty string.
    """
    answer = result_row.get("answer")
    if isinstance(answer, str) and answer:
        return answer
    preview = result_row.get("answer_preview")
    if isinstance(preview, str):
        return preview
    return ""


# α-5 prereq §1.b (#612 follow-up) — negation guard. A literal
# substring match counts "Anthropic does not develop Claude" as a hit on
# both "Anthropic" and "Claude" gold_signals, inflating graded_answer.
# This window scans for KO/EN negation markers near the match:
#   - English: prefix markers ("not", "doesn't", …) in the N chars BEFORE
#   - Korean:  prefix markers ("못", "안") in the N chars before, AND
#              suffix markers ("아니다", "않다", "없다") in the N chars
#              after the match — Korean negation is post-positional.
# Window=12 chars on each side catches typical syntax while staying
# short enough that an unrelated earlier "not" doesn't bleed in.
_NEGATION_WINDOW_CHARS = 12
_NEGATION_MARKERS_BEFORE: Tuple[str, ...] = (
    # English
    "not ", "no ", "n't ", "without ", "never ", "lack ", "absent ",
    # Korean — short morphemes that prefix the negated verb/noun
    "못 ", "안 ",
)
_NEGATION_MARKERS_AFTER: Tuple[str, ...] = (
    # Korean — trailing negation copula / verb. "X이 아니다" / "X 없다" /
    # "X 않다" all negate the closest preceding noun/verb.
    "아니", "없", "않",
)


def _has_negation_around(answer_lower: str, match_start: int, match_end: int) -> bool:
    """True if any negation marker is adjacent to the match (KO/EN).

    Prefix markers ("not", "못", "안", ...) are searched in the N chars
    immediately before `match_start`. Suffix markers ("아니", "없", "않"),
    Korean post-positional negation, are searched in the N chars
    immediately after `match_end`. Both windows are short by design —
    unrelated earlier/later negations should not bleed in.
    """
    # Before the match.
    if match_start > 0:
        before = answer_lower[max(0, match_start - _NEGATION_WINDOW_CHARS):match_start]
        if any(m in before for m in _NEGATION_MARKERS_BEFORE):
            return True
    # After the match.
    if match_end < len(answer_lower):
        after = answer_lower[match_end:match_end + _NEGATION_WINDOW_CHARS]
        if any(m in after for m in _NEGATION_MARKERS_AFTER):
            return True
    return False


def _matches_signal(
    answer_lower: str,
    signal: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """Return (hit, matched_form) — whether the answer contains the
    signal's term or any of its aliases (case-insensitive substring),
    skipping matches preceded by a negation marker (§1.b)."""
    candidates: List[str] = []
    term = signal.get("term", "")
    if isinstance(term, str) and term:
        candidates.append(term)
    for alias in signal.get("aliases", []) or []:
        if isinstance(alias, str) and alias:
            candidates.append(alias)
    for form in candidates:
        form_lower = form.lower()
        idx = answer_lower.find(form_lower)
        while idx >= 0:
            end = idx + len(form_lower)
            if not _has_negation_around(answer_lower, idx, end):
                return True, form
            # Skip past this negated occurrence and try the next one —
            # later in the answer the same claim may appear positively.
            idx = answer_lower.find(form_lower, idx + 1)
    return False, None


def score_graded_answer(
    bench_results: Dict[str, Any],
    fixture: Dict[str, Any],
) -> GradedAnswerAxis:
    """For each fixture query that has gold_signals, count how many
    signals were hit in the bench's answer text. Score = hits / total."""
    fixture_map: Dict[int, Dict[str, Any]] = {
        int(q["id"]): q for q in fixture.get("queries", [])
    }
    rows: List[GradedAnswerQueryRow] = []
    for r in bench_results.get("results", []):
        qid = int(r.get("id", -1))
        fq = fixture_map.get(qid)
        if not fq:
            continue
        signals = fq.get("gold_signals") or []
        if not signals:
            continue
        answer_lower = _answer_text(r).lower()
        hits = 0
        matched: List[str] = []
        for sig in signals:
            ok, which = _matches_signal(answer_lower, sig)
            if ok:
                hits += 1
                if which:
                    matched.append(which)
        total = len(signals)
        score = round(hits / total, 4) if total else 0.0
        rows.append(GradedAnswerQueryRow(
            id=qid,
            hits=hits,
            total=total,
            score=score,
            matched_signals=matched,
        ))
    if not rows:
        return GradedAnswerAxis(
            mean_accuracy=0.0,
            queries_with_signals=0,
            per_query=[],
        )
    mean = sum(r.score for r in rows) / len(rows)
    return GradedAnswerAxis(
        mean_accuracy=round(mean, 4),
        queries_with_signals=len(rows),
        per_query=rows,
    )


# ---------------------------------------------------------------------------
# Calibrated Abstention F1
# ---------------------------------------------------------------------------

@dataclass
class AbstentionQueryRow:
    id: int
    truth: str        # "present" or "absent"
    abstained: bool   # system behavior
    classification: str  # tp_abstain / fp_incorrect / fn_hallucination / tn_answer


@dataclass
class AbstentionF1Axis:
    f1: float
    precision: float
    recall: float
    tp_abstain: int            # truth=absent  AND abstained (correct refusal)
    fp_incorrect_abstention: int  # truth=present AND abstained (over-cautious)
    fn_hallucination: int      # truth=absent  AND answered  (worst — fabricated)
    tn_answer: int             # truth=present AND answered  (correct answer)
    n_queries: int
    per_query: List[AbstentionQueryRow] = field(default_factory=list)


def score_abstention_f1(
    bench_results: Dict[str, Any],
    fixture: Dict[str, Any],
) -> AbstentionF1Axis:
    """F1 on the binary abstention classifier the system implicitly runs.

    Positive class = "system abstained". Rows from queries without an
    `abstention_truth` annotation are silently skipped.

    A result row is treated as an abstention when any of these holds:
      - `status != "ok"` (timeout / error)
      - `blocked is True` (policy-blocked — e.g. JAMES security policy
        returns ``status=ok`` + ``blocked=true`` + a refusal message,
        which is semantically a refusal even though the HTTP layer
        looks successful)
      - the answer text contains a phrase in ``_ABSTENTION_PHRASES``
    """
    fixture_map: Dict[int, Dict[str, Any]] = {
        int(q["id"]): q for q in fixture.get("queries", [])
    }
    rows: List[AbstentionQueryRow] = []
    tp_abstain = fp_incorrect = fn_hallucination = tn_answer = 0

    for r in bench_results.get("results", []):
        qid = int(r.get("id", -1))
        fq = fixture_map.get(qid)
        if not fq:
            continue
        truth = fq.get("abstention_truth")
        if truth not in ("present", "absent"):
            continue
        if r.get("status") != "ok":
            abstained = True
        elif r.get("blocked") is True:
            abstained = True
        else:
            abstained = detect_abstention(_answer_text(r))

        if truth == "absent" and abstained:
            cls = "tp_abstain"
            tp_abstain += 1
        elif truth == "absent" and not abstained:
            cls = "fn_hallucination"
            fn_hallucination += 1
        elif truth == "present" and abstained:
            cls = "fp_incorrect_abstention"
            fp_incorrect += 1
        else:  # truth == "present" and not abstained
            cls = "tn_answer"
            tn_answer += 1

        rows.append(AbstentionQueryRow(
            id=qid,
            truth=truth,
            abstained=abstained,
            classification=cls,
        ))

    tp = tp_abstain
    fp = fp_incorrect
    fn = fn_hallucination
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0 else 0.0
    )

    return AbstentionF1Axis(
        f1=round(f1, 4),
        precision=round(precision, 4),
        recall=round(recall, 4),
        tp_abstain=tp_abstain,
        fp_incorrect_abstention=fp_incorrect,
        fn_hallucination=fn_hallucination,
        tn_answer=tn_answer,
        n_queries=len(rows),
        per_query=rows,
    )


# ---------------------------------------------------------------------------
# Cost axes (Step 5 of α-5 plan — quality×cost integrated matrix)
#
# bench.py captures per-query ``elapsed`` (seconds) directly. ``eval_count``
# (Ollama-side token count) is NOT exposed by the server's /query/ response
# today, so token cost is approximated by ``answer_len`` (characters in
# the response). ~4 chars/token English / ~2 chars/token Korean — the
# proxy is monotonic but biased by language mix. Operators interpreting
# Δ_token_cost across cells should focus on within-tier comparison
# (same prompt language) rather than cross-tier absolute values.
#
# A future PR can wire Ollama ``eval_count`` through the server response
# and swap this proxy for the real number; the axis interface stays
# identical (mean + p95 + per_query rows).
# ---------------------------------------------------------------------------


@dataclass
class CostQueryRow:
    id: int
    elapsed_s: float
    answer_chars: int   # token-cost proxy until server forwards eval_count


@dataclass
class TokenCostAxis:
    """Per-query answer chars (token-cost proxy). Lower is better."""
    mean_chars: float
    p95_chars: float
    n_queries: int
    per_query: List[CostQueryRow] = field(default_factory=list)


@dataclass
class LatencyCostAxis:
    """Per-query wall-clock elapsed. Lower is better."""
    mean_s: float
    p95_s: float
    n_queries: int
    per_query: List[CostQueryRow] = field(default_factory=list)


def _percentile(values: List[float], p: float) -> float:
    """Nearest-rank percentile (good enough for n≥20 cells)."""
    if not values:
        return 0.0
    s = sorted(values)
    if p <= 0:
        return s[0]
    if p >= 1.0:
        return s[-1]
    # nearest-rank: index = ceil(p * n) - 1
    import math
    idx = max(0, min(len(s) - 1, math.ceil(p * len(s)) - 1))
    return s[idx]


def _collect_cost_rows(bench_results: Dict[str, Any]) -> List[CostQueryRow]:
    rows: List[CostQueryRow] = []
    for r in bench_results.get("results", []):
        # Successful + answered queries only — timeouts / errors would
        # bias the cost axis toward "very cheap" (zero output) when in
        # practice they are operational failures, not efficiency wins.
        if r.get("status") != "ok":
            continue
        elapsed = r.get("elapsed")
        if elapsed is None:
            continue
        # Prefer explicit answer_len when bench.py emitted it; fall back
        # to answer_preview length (300-char truncated) for older runs.
        chars = r.get("answer_len")
        if chars is None:
            chars = len(r.get("answer_preview", "") or "")
        rows.append(CostQueryRow(
            id=int(r.get("id", -1)),
            elapsed_s=float(elapsed),
            answer_chars=int(chars),
        ))
    return rows


def score_token_cost(bench_results: Dict[str, Any]) -> TokenCostAxis:
    rows = _collect_cost_rows(bench_results)
    if not rows:
        return TokenCostAxis(mean_chars=0.0, p95_chars=0.0, n_queries=0)
    chars = [r.answer_chars for r in rows]
    return TokenCostAxis(
        mean_chars=round(sum(chars) / len(chars), 2),
        p95_chars=round(_percentile([float(c) for c in chars], 0.95), 2),
        n_queries=len(rows),
        per_query=rows,
    )


def score_latency_cost(bench_results: Dict[str, Any]) -> LatencyCostAxis:
    rows = _collect_cost_rows(bench_results)
    if not rows:
        return LatencyCostAxis(mean_s=0.0, p95_s=0.0, n_queries=0)
    elapsed = [r.elapsed_s for r in rows]
    return LatencyCostAxis(
        mean_s=round(sum(elapsed) / len(elapsed), 3),
        p95_s=round(_percentile(elapsed, 0.95), 3),
        n_queries=len(rows),
        per_query=rows,
    )


# ---------------------------------------------------------------------------
# Three-axis unified result
# ---------------------------------------------------------------------------

@dataclass
class ThreeAxisResult:
    git_sha: Optional[str]
    suite: Optional[str]
    fixture_version: Optional[str]
    n_queries: int
    path_coverage: PathCoverageAxis
    graded_answer: GradedAnswerAxis
    abstention: AbstentionF1Axis

    def summary(self) -> str:
        """One-line human-readable summary, suitable for stdout."""
        return (
            f"path_recall={self.path_coverage.mean_recall:.4f}"
            f" ({self.path_coverage.queries_at_full_recall}/"
            f"{self.path_coverage.queries_with_expected_path}) "
            f"graded={self.graded_answer.mean_accuracy:.4f}"
            f" (n={self.graded_answer.queries_with_signals}) "
            f"abstention_f1={self.abstention.f1:.4f}"
            f" (TP={self.abstention.tp_abstain}"
            f" FP={self.abstention.fp_incorrect_abstention}"
            f" FN={self.abstention.fn_hallucination}"
            f" TN={self.abstention.tn_answer})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serializable dict (uses dataclasses.asdict)."""
        return {
            "git_sha": self.git_sha,
            "suite": self.suite,
            "fixture_version": self.fixture_version,
            "n_queries": self.n_queries,
            "path_coverage": asdict(self.path_coverage),
            "graded_answer": asdict(self.graded_answer),
            "abstention": asdict(self.abstention),
        }


def _load_json(path: Union[str, Path]) -> Dict[str, Any]:
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def score_three_axis(
    bench_results_path: Union[str, Path, Dict[str, Any]],
    fixture_path: Union[str, Path, Dict[str, Any]],
) -> ThreeAxisResult:
    """Top-level entry — compute all three axes from a bench JSON +
    a fixture JSON.

    Both arguments accept either a file path or an already-parsed dict
    (handy for tests + for chaining multiple runs in α-3 baseline capture).
    """
    bench = (
        bench_results_path
        if isinstance(bench_results_path, dict)
        else _load_json(bench_results_path)
    )
    fixture = (
        fixture_path
        if isinstance(fixture_path, dict)
        else _load_json(fixture_path)
    )
    return ThreeAxisResult(
        git_sha=bench.get("git_sha"),
        suite=bench.get("suite"),
        fixture_version=fixture.get("version"),
        n_queries=len(bench.get("results", [])),
        path_coverage=score_path_coverage(bench, fixture),
        graded_answer=score_graded_answer(bench, fixture),
        abstention=score_abstention_f1(bench, fixture),
    )


# ---------------------------------------------------------------------------
# Five-axis result — α-5 quality×cost integrated (Step 5)
# ---------------------------------------------------------------------------


@dataclass
class FiveAxisResult:
    """3 quality axes (existing) + 2 cost axes (new). Used by the α-5
    ablation matrix runner to express verdicts on the (quality, cost)
    Pareto plane rather than quality alone.

    The 3 quality axes are *delegated* to the existing `ThreeAxisResult`
    so any caller that already understands the 3-axis schema keeps
    working — `.three_axis` gives the unchanged object. Cost axes are
    additive fields.
    """
    three_axis: ThreeAxisResult
    token_cost: TokenCostAxis
    latency_cost: LatencyCostAxis

    # Convenience accessors — keep call sites short.
    @property
    def git_sha(self) -> Optional[str]:
        return self.three_axis.git_sha

    @property
    def suite(self) -> Optional[str]:
        return self.three_axis.suite

    @property
    def fixture_version(self) -> Optional[str]:
        return self.three_axis.fixture_version

    @property
    def n_queries(self) -> int:
        return self.three_axis.n_queries

    @property
    def path_coverage(self) -> PathCoverageAxis:
        return self.three_axis.path_coverage

    @property
    def graded_answer(self) -> GradedAnswerAxis:
        return self.three_axis.graded_answer

    @property
    def abstention(self) -> AbstentionF1Axis:
        return self.three_axis.abstention

    def summary(self) -> str:
        return (
            f"{self.three_axis.summary()} "
            f"token_cost(chars)={self.token_cost.mean_chars:.1f}/"
            f"p95={self.token_cost.p95_chars:.1f} "
            f"latency(s)={self.latency_cost.mean_s:.2f}/"
            f"p95={self.latency_cost.p95_s:.2f}"
        )

    def to_dict(self) -> Dict[str, Any]:
        d = self.three_axis.to_dict()
        d["token_cost"] = asdict(self.token_cost)
        d["latency_cost"] = asdict(self.latency_cost)
        return d


def score_five_axis(
    bench_results_path: Union[str, Path, Dict[str, Any]],
    fixture_path: Union[str, Path, Dict[str, Any]],
) -> FiveAxisResult:
    """Top-level α-5 entry — quality 3-axis (path/graded/abstention) +
    cost 2-axis (token, latency).

    Backward-compatible: callers that only need 3-axis can still use
    ``score_three_axis``; ``FiveAxisResult.three_axis`` exposes the
    same shape so legacy code paths keep working when migrated.
    """
    three = score_three_axis(bench_results_path, fixture_path)
    # Re-load bench dict once for the cost axes (cheap — file already cached
    # by the OS after the 3-axis pass). Accept dict to skip when caller
    # already has it.
    bench = (
        bench_results_path
        if isinstance(bench_results_path, dict)
        else _load_json(bench_results_path)
    )
    return FiveAxisResult(
        three_axis=three,
        token_cost=score_token_cost(bench),
        latency_cost=score_latency_cost(bench),
    )


# ---------------------------------------------------------------------------
# Per-question_type 5-axis breakdown (α-5 plan Step 6 cross-tab)
# ---------------------------------------------------------------------------


def score_five_axis_by_question_type(
    bench_results_path: Union[str, Path, Dict[str, Any]],
    fixture_path: Union[str, Path, Dict[str, Any]],
) -> Dict[str, FiveAxisResult]:
    """Return one FiveAxisResult per `question_type` present in the
    bench output (Step 6 cross-tab).

    Requires both the bench rows and the fixture queries to carry the
    `question_type` field (MultiHop-RAG fixture does this; step7 does
    not — returns an empty dict in that case). The function partitions
    both the bench results and the fixture queries by question_type,
    then runs the 5-axis scorer on each partition independently. Two
    partitions of size 0 (no overlap) are skipped silently.

    Sum-up: per-type results carry the same FiveAxisResult schema as
    the global one, so the matrix runner can compute Δ per (type, layer,
    tier) using the same machinery.
    """
    bench = (
        bench_results_path
        if isinstance(bench_results_path, dict)
        else _load_json(bench_results_path)
    )
    fixture = (
        fixture_path
        if isinstance(fixture_path, dict)
        else _load_json(fixture_path)
    )
    bench_rows = bench.get("results", [])
    fixture_queries = fixture.get("queries", [])

    # Collect question types observed on the bench side.
    types_seen: set[str] = set()
    for r in bench_rows:
        qt = r.get("question_type")
        if isinstance(qt, str) and qt:
            types_seen.add(qt)
    if not types_seen:
        return {}

    out: Dict[str, FiveAxisResult] = {}
    for qt in sorted(types_seen):
        sub_bench = {
            **{k: v for k, v in bench.items() if k != "results"},
            "results": [r for r in bench_rows if r.get("question_type") == qt],
        }
        sub_fixture = {
            **{k: v for k, v in fixture.items() if k != "queries"},
            "queries": [q for q in fixture_queries if q.get("question_type") == qt],
        }
        if not sub_bench["results"] or not sub_fixture["queries"]:
            continue
        out[qt] = score_five_axis(sub_bench, sub_fixture)
    return out
