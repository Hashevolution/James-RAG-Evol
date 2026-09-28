# Relaxing the fact-check cost 5 of 6 catches to save 1 false alarm — rejected (2026-09-28)

> **Hypothesis**: verify's fact-check flags correct core answers as
> unsupported ("BTC와 비트코인은 같은 디지털 자산", "Anthropic develops
> Claude" — 5 times in 3 runs, `annotation-axis-20260928.md` §4) because
> its prompt sets a literal bar ("직접 지지되는지" / "directly
> supported") and gives only a trivial common-knowledge example.
>
> **Change tested** (`6eac521`, branch `fix/v0.6.2-factcheck-inference`,
> **not merged**): paraphrase, translation and conclusions that follow
> directly from the data count as support; definitions and abbreviations
> pass as general knowledge. Two limits against letting "Alex Karp"
> through: inference only about the same subject, and a specific
> entity's attributes (CEO, dates, figures, who issues what) never pass
> as general knowledge.
>
> **Design**: 6 captures interleaved BASE (`main` `787aaec`) ↔ FIX
> (`6eac521`), arms separated by commit, plus the bare-claim sample
> (Q15/17/18 ×10) on each. Same session, ~1 h 33 min. All runs 18/18
> healthy. **Both arms run with reflect off** — the operator `.env`
> change made earlier the same day (`reflect-off-n3-20260928.md`), so
> this measures the new production configuration.

## 1. Verdict: rejected

The change's own axis — the annotation axis, since the fact-check's only
output is annotations:

| arm | annotations | true alarms | misses | strict recall | graded false alarms |
|---|---:|---:|---:|---:|---:|
| BASE | 22 | **6** | 5 | **0.55** | 9 |
| FIX | 12 | **1** | 7 | **0.13** | 8 |

The false alarms the change was written to remove barely moved
(**9 → 8**). The true alarms it was built to protect collapsed
(**6 → 1**).

Controlled for which answers were wrong — the two queries that
hallucinated in **both** arms:

| query (truth = absent) | BASE caught | FIX caught |
|---|---:|---:|
| Q7 "RAG와 Graph RAG의 차이는?" | 3 / 3 | 1 / 3 |
| Q10 "OpenAI의 최신 모델 전략은?" | 2 / 3 | 0 / 3 |

**5 of 6 → 1 of 6** on the same wrong answers. Not a sampling artifact.

The bare-claim sample could not test the "Alex Karp" limit: with reflect
off, **0 of 30** answers in either arm landed at or under 30 characters.
The path was not exercised. (The probe reported exactly that rather than
"did not fire" — the #1157 guard doing its job.)

## 2. Mechanism

The relaxed checker stopped *listing* hallucinated claims at all:

| arm | clean accept | annotate |
|---|---:|---:|
| BASE | 26 | 22 |
| FIX | **34** | **12** |

Q10, FIX r2 — an answer built on interpretive claims about OpenAI's
strategy that the evidence does not carry — got
`{"grounded": true, "unsupported": []}`. The rule *"a conclusion that
follows directly from the data counts as support"* gave the model a
licence to treat an interpretation as a conclusion. The same-subject
limit did not help, because the subject was right; the claims were just
not in the data.

The lesson generalises past this prompt: **"inference counts" is not a
rule a small model applies narrowly.** reflect's critique (#1151) failed
in the other direction — too literal, rejecting the Q19 inference — and
the obvious correction overshoots.

## 3. The 5-axis deltas are not the change's

| axis | BASE | FIX | Δ |
|---|---:|---:|---:|
| Graded Answer | 0.6667 | 0.7667 | +0.1000 |
| Abstention F1 | 0.6667 | 0.5714 | −0.0953 |
| Latency | 39.65 s | 39.63 s | −0.02 |

The graded rise is driven by Q19: BASE synth answered *"insufficient
information"* in 3 of 3 runs, FIX synth answered correctly in 3 of 3.
**The fact-check cannot cause that** — it runs after synth and only
appends notes; the notes were checked and stripping them changes
nothing; retrieval was identical across all six runs (same expansion,
same top document at the same rerank score); no memory carried over
(every episode `gate4_dedup`).

A 3–0 / 0–3 split on *some* query among 20 is roughly a coin flip by
chance alone (~3% per query under p = 0.5, 1 − 0.97²⁰ ≈ 46%). This is
the multiple-comparisons trap, and it would have made a rejected change
look like a graded improvement. Latency confirms reflect off in
practice: ~39.6 s in every run, matching the NOREFLECT arm.

## 4. A pre-existing verify defect, found on the way

While tracing §2 a self-contradictory verdict turned up —
`{"grounded": true, "unsupported": [5 claims]}` → `rec=accept`. It is
**not** caused by this change. Counted from the untruncated
`rec=… unsupp=N` rows, an *accept* with 2 or more listed unsupported
claims — which `_decide` can only produce when the boolean contradicts
the list — occurs in every arm measured today:

| arm | accepted despite 2+ listed unsupported claims |
|---|---:|
| BASE | 2 / 54 |
| FIX | 2 / 54 |
| reflect ON | 3 / 54 |
| reflect OFF | 5 / 54 |

`Verifier._decide` gates on `not is_grounded` before it looks at the
list, so when the model contradicts itself the boolean wins and the
listed claims are discarded. (An earlier draft of this analysis blamed
the relaxed prompt for these; the per-arm count shows they are equally
common without it.)

Deriving groundedness from the list would close it — but the list is
also where the false alarms come from, so the effect on precision is
unknown. It needs its own measurement on the annotation axis.

## 5. What this licenses — and what it does not

**Licensed**

- This relaxation must not ship: −5 true alarms for −1 false alarm, on a
  like-for-like comparison.
- verify's `_decide` discards listed unsupported claims whenever the
  model's boolean says grounded, at 2–5 per 54 answers in every
  configuration (§4).

**Not licensed**

- ❌ "The false alarms are unfixable." One wording was tested.
- ❌ Any 5-axis reading (§3).
- ❌ Anything about the "Alex Karp" limit — the path was not exercised.

## 6. What next, if the false alarms are revisited

1. **Narrow, not broad.** The false alarms were all definitional
   (BTC ≡ Bitcoin, a ticker) or the answer's own central, fixture-graded
   claim. A clause admitting *only* definitions and abbreviations —
   with no inference rule at all — is the next hypothesis. Measure it
   exactly like this: annotation axis, like-for-like on the queries
   that hallucinate in both arms.
2. **§4 separately**, with the same measurement. Keep the two changes
   apart; together their effects on precision would be indistinguishable.
