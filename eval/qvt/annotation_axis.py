"""Annotation axis — score verify's warnings the five axes cannot see.

Why this exists
---------------
The 2026-09-27 n=3 contrast (`reports/research-runs/cognitive-stages-n3-20260927.md`)
found the cognitive stages flat on every quality axis while costing 62%
of query latency — and could not conclude anything from that, because
**none of the five axes scores verify's output**. With the stages off,
verify produced zero annotations where ON produced 3, 7 and 4 per 18
queries, and one of that class caught "Alex Karp" offered as
Anthropic's CEO. `abstention_f1` being flat says nothing about whether
those warnings were right.

This axis treats each `annotate` as a claim — "this answer is not
supported" — and scores the claim.

Ground truth, and the self-evaluation trap
------------------------------------------
Scoring a component with a yardstick built for the purpose is the
`feedback_self_evaluation_trap` ("엄마 100점"): my fixture, my oracle,
my verdict. So this axis introduces **no new gold**. Whether an answer
was right or wrong is decided only by what the fixture already carried
before verify was touched, through the oracle's own functions:

  * ``abstention_truth`` (present / absent) — fixture label
  * ``detect_abstention`` — the oracle's detector, unchanged
  * ``score_graded_answer`` — the oracle's gold-signal scorer, unchanged

  answer is WRONG  when  truth=absent  and the system answered
                   or    truth=present and the system refused
  answer is RIGHT  when  truth=absent  and the system refused
                   or    truth=present, answered, and graded == 1.0
  UNSCORED         when  truth=present, answered, graded < 1.0

The last row is deliberately excluded rather than guessed. A partial
graded score cannot say whether the *annotated claim* is the wrong part
of the answer, and substring signals are already known to credit a wrong
denial with 1.0 (2026-09-24 report §5) — so "right" requires the
strongest evidence the fixture has, and everything weaker is counted
but not scored.

  WRONG + annotated     → true alarm
  WRONG + not annotated → miss
  RIGHT + annotated     → false alarm
  RIGHT + not annotated → correct silence

Precision / recall / F1 over the scored cells.

Contamination
-------------
Classification runs on the answer **with verify's note stripped**. The
note is appended to the answer, and `detect_abstention` substring-
matches broad phrases ("없습니다", "할 수 없"); if the LLM-written claim
text inside a note tripped one, verify's own output would change the
verdict it is being scored against. Measured on 2026-09-28 over 22
step7 bench files: 11 answers carried a note inside the oracle's
300-character preview and **0** flipped — but the axis is built so it
does not depend on that count staying zero.

Not a sixth canonical axis
--------------------------
`score_five_axis` and the `baseline_<sha>.json` schema are untouched.
Folding this in would change what every stored baseline means, which is
a decision for a later cycle. It is reported alongside, not inside.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from eval.qvt.oracle import detect_abstention, score_graded_answer

# The note ``Verifier._format`` appends on `annotate`. Kept here, on the
# measurement side, rather than imported from core/ — verify builds it
# with an inline f-string. `tests/test_qvt_annotation_axis.py` asserts
# this pattern strips what `_format` actually produces, so the two
# cannot drift silently.
NOTE_RE = re.compile(r"\n\n\(검증: .*$|\n\n\(Verification: .*$", re.S)

RIGHT, WRONG, UNSCORED = "right", "wrong", "unscored"
TRUE_ALARM, FALSE_ALARM = "true_alarm", "false_alarm"
MISS, CORRECT_SILENCE = "miss", "correct_silence"


def strip_note(answer: Optional[str]) -> str:
    """The answer as verify received it, before its own annotation."""
    return NOTE_RE.sub("", answer or "").strip()


def classify_correctness(truth: str, abstained: bool,
                         graded: Optional[float], *,
                         strict: bool = True) -> str:
    """Right / wrong / unscored from fixture labels only. See module doc.

    ``strict`` (default) decides correctness **by abstention alone** and
    never consults ``graded``. The graded mode was the first design and
    it has a blind spot found on its first real run (2026-09-28): an
    answer can hit every gold signal *and* add claims the evidence does
    not carry — "…구조적 다리 역할을 한다는 점이 가장 중요합니다" on a
    BlackRock question, unrequested access-control advice on "RAG가
    무엇인가?". verify flagging those embellishments is a correct
    warning, and graded mode scored it as a false alarm, because
    graded == 1.0 means "contains the answer", not "contains nothing
    else". Telling the two apart needs claim-level gold, which this axis
    refuses to invent. So strict mode leaves every answered
    truth=present query unscored, and graded mode is kept, labelled,
    for the signal it does carry (see the report).
    """
    t = (truth or "").strip().lower()
    if t == "absent":
        return RIGHT if abstained else WRONG
    if t == "present":
        if abstained:
            return WRONG
        if strict:
            return UNSCORED
        if graded is not None and graded >= 1.0:
            return RIGHT
        return UNSCORED
    return UNSCORED


def cell_for(correctness: str, annotated: bool) -> str:
    if correctness == WRONG:
        return TRUE_ALARM if annotated else MISS
    if correctness == RIGHT:
        return FALSE_ALARM if annotated else CORRECT_SILENCE
    return UNSCORED


@dataclass
class AnnotationRow:
    id: int
    truth: str
    abstained: bool
    graded: Optional[float]
    correctness: str
    annotated: bool
    cell: str


@dataclass
class AnnotationAxis:
    true_alarm: int = 0
    false_alarm: int = 0
    miss: int = 0
    correct_silence: int = 0
    unscored: int = 0
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    n_scored: int = 0
    n_annotated: int = 0
    per_query: List[AnnotationRow] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["per_query"] = [asdict(r) for r in self.per_query]
        return d

    def summary(self) -> str:
        def f(x):
            return "n/a" if x is None else f"{x:.4f}"
        return (f"annotation P={f(self.precision)} R={f(self.recall)} "
                f"F1={f(self.f1)} (TA={self.true_alarm} FA={self.false_alarm} "
                f"miss={self.miss} CS={self.correct_silence} "
                f"unscored={self.unscored})")


def score_annotations(episodes: List[Mapping[str, Any]],
                      fixture: Mapping[str, Any], *,
                      strict: bool = True) -> AnnotationAxis:
    """Score verify's annotations over a run.

    ``episodes``: one dict per answered query — ``id`` (fixture id),
    ``final_answer`` (as the user received it, note included) and
    ``annotated`` (verify's recommendation was ``annotate``). Episodes
    whose id is not in the fixture are skipped.
    """
    fq = {int(q["id"]): q for q in fixture.get("queries", [])}
    fixture_d = dict(fixture)

    axis = AnnotationAxis()
    for e in episodes:
        qid = int(e.get("id", -1))
        if qid not in fq:
            continue
        # Per EPISODE, never per id. The first version keyed answers by
        # fixture id, so repeated samples of one query (n runs combined,
        # or the bare-claim probe's 10x) collapsed onto whichever answer
        # came last — three Q17 episodes, "Alex Karp" twice and a refusal
        # once, all scored as the refusal.
        answer = strip_note(e.get("final_answer"))
        truth = str(fq[qid].get("abstention_truth") or "")
        abstained = detect_abstention(answer)
        g_rows = score_graded_answer(
            {"results": [{"id": qid, "answer": answer}]}, fixture_d
        ).per_query
        g = g_rows[0].score if g_rows else None
        correctness = classify_correctness(truth, abstained, g,
                                           strict=strict)
        annotated = bool(e.get("annotated"))
        cell = cell_for(correctness, annotated)
        axis.per_query.append(AnnotationRow(qid, truth, abstained, g,
                                            correctness, annotated, cell))
        axis.n_annotated += int(annotated)
        if cell == TRUE_ALARM:
            axis.true_alarm += 1
        elif cell == FALSE_ALARM:
            axis.false_alarm += 1
        elif cell == MISS:
            axis.miss += 1
        elif cell == CORRECT_SILENCE:
            axis.correct_silence += 1
        else:
            axis.unscored += 1

    axis.n_scored = (axis.true_alarm + axis.false_alarm
                     + axis.miss + axis.correct_silence)
    flagged = axis.true_alarm + axis.false_alarm
    wrong = axis.true_alarm + axis.miss
    if flagged:
        axis.precision = round(axis.true_alarm / flagged, 4)
    if wrong:
        axis.recall = round(axis.true_alarm / wrong, 4)
    if axis.precision is not None and axis.recall is not None and (
            axis.precision + axis.recall):
        axis.f1 = round(2 * axis.precision * axis.recall
                        / (axis.precision + axis.recall), 4)
    return axis


__all__ = [
    "NOTE_RE", "strip_note", "classify_correctness", "cell_for",
    "AnnotationRow", "AnnotationAxis", "score_annotations",
    "RIGHT", "WRONG", "UNSCORED",
    "TRUE_ALARM", "FALSE_ALARM", "MISS", "CORRECT_SILENCE",
]
