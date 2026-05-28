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
# ---------------------------------------------------------------------------

@dataclass
class PathCoverageQueryRow:
    id: int
    expected_count: int
    hits: int
    recall: float


@dataclass
class PathCoverageAxis:
    mean_recall: float
    queries_with_expected_path: int
    queries_at_full_recall: int
    per_query: List[PathCoverageQueryRow] = field(default_factory=list)


def score_path_coverage(
    bench_results: Dict[str, Any],
    fixture: Dict[str, Any],
) -> PathCoverageAxis:
    """Aggregate bench.py's per-query `path_metrics` block.

    Skips queries without `expected_path` (the denominator is "annotated
    queries", not "all queries"). The fixture parameter is accepted for
    API symmetry but currently unused — bench.py already joined against
    the fixture when producing `path_metrics`.
    """
    _ = fixture  # reserved for future use (e.g. min_recall threshold)
    rows: List[PathCoverageQueryRow] = []
    for r in bench_results.get("results", []):
        pm = r.get("path_metrics")
        if not pm:
            continue
        rows.append(PathCoverageQueryRow(
            id=int(r["id"]),
            expected_count=int(pm.get("expected_count", 0)),
            hits=int(pm.get("hits", 0)),
            recall=float(pm.get("path_recall", 0.0)),
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


def _matches_signal(
    answer_lower: str,
    signal: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """Return (hit, matched_form) — whether the answer contains the
    signal's term or any of its aliases (case-insensitive substring)."""
    term = signal.get("term", "")
    if isinstance(term, str) and term and term.lower() in answer_lower:
        return True, term
    for alias in signal.get("aliases", []) or []:
        if isinstance(alias, str) and alias and alias.lower() in answer_lower:
            return True, alias
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
