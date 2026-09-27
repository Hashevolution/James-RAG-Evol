# The bare-claim annotation fires, and it caught "Alex Karp" (2026-09-27)

> **Design**: option A — leave `BARE_CLAIM_ANSWER_CHARS = 30` alone and
> observe the path at default settings. Stratified sampling: all three
> short answers ever observed came from one query shape, so the three
> bare-entity queries in the step7 fixture were repeated **10× each** on
> `main` `dba2c3d`, unmodified, with the standard pinned measurement env.
> 30 episodes, 0 failures. ~15 minutes.
>
> Runner: `scripts/research/bare_claim_frequency.py --repeats 10`.
> Server lifecycle and the pinned env are **imported** from
> `qvt_capture_baseline.py`, not copied (#1149).

## 1. Why sampling and not a fixture

Forcing short answers with `JAMES_RESPONSE_STYLE=terse` was considered
and rejected. terse v4 deliberately carries **no** length cap: v2's
"MAXIMUM 30 words" was caught as measurement-fitting and rolled back
(the history block in `core/response_style_presets.py` records it).
Choosing a knob so that a threshold fires is the same move.

What is legitimate is sampling the stratum where the phenomenon already
occurs. Nothing about the system was changed — only how often these
queries were asked.

| step7 id | query | abstention_truth |
|---|---|---|
| 15 | David Soria Parra가 누구야? | present |
| 17 | **Anthropic의 CEO는 누구야?** | **absent** |
| 18 | Tesla의 창립자는 누구야? | present |

Q17 is the trap: the corpus does not carry Anthropic's CEO, but it does
carry Palantir's. That is what produced "Alex Karp" on 2026-09-26.

## 2. The path fires — 4 of 10 on Q17

| pre-note answer | chars | recommendation | correct? |
|---|---:|---|---|
| `Dario Amodei` | 12 | annotate | ✅ true in the world, **not in the corpus** — unsupported is the right verdict |
| `ANSWER: Alex Karp` | 17 | annotate | ✅ wrong (Palantir's CEO) |
| `ANSWER: Alex Karp` | 17 | annotate | ✅ wrong |
| `Alex Karp` | 9 | annotate | ✅ **the exact answer that motivated #1154** |

**All four annotations are correct.** Under the pre-#1154 code every one
of them shipped unannotated, and worse — the `len(answer) < 30` gate
skipped the security scan *and* the fact check outright, so they were
never examined at all.

The boundary was not marginal: 9–17 characters against a threshold of
30. The 32-character near-miss on 2026-09-26 was a coincidence of that
run, not the typical case.

**The long-answer protection also held.** Three episodes had exactly one
unsupported claim with an answer well over the threshold (73, 109 and
178 chars) and all three were `accept` — `ANNOTATE_THRESHOLD = 2` still
prevents a single borderline claim from warning on a longer answer.
Both directions of #1154 are now observed, not just asserted.

Answer-length distribution across all 30 episodes: min 62 / median 148 /
max 369 characters, with the four bare claims below that range.

## 3. Two probe defects, both of which produced a false conclusion

Recorded because the probe was wrong twice before it was right, and both
times it was confident.

### 3.1 A guessed request schema, and a verdict from zero data

The first run sent `{"query": ..., "mode": ...}`. The endpoint takes
`{"question": ..., "api_key": ...}` (`routes/query.py::QueryRequest`),
so all 30 calls returned **HTTP 422** and no episodes were recorded.

The report then printed **"The path did not fire."** — a negative
finding drawn from an empty sample. This is the same failure the
2026-09-24 session hit when a warm-up state with 0 completed queries was
briefly used as counter-evidence.

Fixed twice over: the body now mirrors `scripts/bench.py` (the canonical
caller, rather than a guess), and `render()` refuses to conclude at all
when any call failed or no episode was recorded — it prints
`NO VERDICT` and says an empty sample is not evidence. The runner also
aborts after three consecutive failures instead of repeating a broken
request thirty times.

### 3.2 Measuring the wrong string, and a verdict that contradicted the code

The second run collected all 30 episodes cleanly and still concluded the
path had not fired: **0 of 30 answers at or under 30 chars**.

But four rows read `rec=annotate` with `unsupp=1`, and `_decide` cannot
annotate on a single unsupported claim unless the answer was bare. The
table contradicted the code it was measuring.

Cause: `_format` appends the verification note to the answer, so the
`/query/` audit row holds **answer + note**. A 9-character bare claim
appears there as ~125 characters. The probe was measuring the verifier's
own output as if it were its input.

Fixed by stripping the note before measuring, and — more importantly —
by making that contradiction impossible to overlook: the probe now
flags any `annotate` + 1 unsupported + over-threshold row in red and
tells the reader not to trust the rest of the table.

## 4. What this licenses — and what it does not

**Licensed**

- #1154's bare-claim annotation **fires in production settings** and its
  four firings here were all correct, including the exact "Alex Karp"
  answer that motivated it.
- The long-answer threshold still holds (§2), so the change is not a
  blanket increase in annotation.
- `BARE_CLAIM_ANSWER_CHARS = 30` is comfortable for this shape — the
  bare claims land at 9–17 characters.

**Not licensed**

- ❌ "40% of Q17 answers are hallucinations." 10 samples of one query on
  one corpus. The rate is not the finding; the firing is.
- ❌ "30 is the right threshold." It was not stress-tested — nothing in
  this sample landed between 18 and 61 characters, so the boundary
  region is unmeasured. It remains an inherited number
  (#1154 out-of-scope), and this run only shows it is not *too low* for
  this shape.
- ❌ Anything about verify's echo path, which is unreachable for separate
  structural reasons — `verify-echo-reachability-20260927.md`.
- ❌ Any claim about the other two queries: ids 15 and 18 produced no
  bare answers at all (62–316 chars), so they contributed only the
  long-answer control.

## 5. Follow-ups

1. **The boundary region is unmeasured** (18–61 chars is empty here). If
   the threshold is ever revisited, that is the range to probe.
2. `Dario Amodei` being annotated is worth a thought: it is correct in
   the world and absent from the corpus, and a grounding-first system
   should flag it — but a user reading "not directly supported" about a
   true fact may read it as the system being wrong. That is a UX
   question about the note's wording, not a defect in the rule.
3. The probe's abort-on-failure and the contradiction self-check are
   generic. If a third measurement script appears, they belong in a
   shared module rather than a third copy.
