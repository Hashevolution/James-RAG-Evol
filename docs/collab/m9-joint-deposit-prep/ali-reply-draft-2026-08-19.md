# Ali Afana 답장 초안 — 2026-08-19

**상태**: DRAFT. 발송 전 운영자 확인 필요.
**채널**: Ali가 보낸 경로(이메일) 그대로 회신. LinkedIn 중복 발송 불필요 — 본인이 "동일 메시지"라고 명시했음.
**선행 조건**: 없음. Phase 0(DOI 확정) 종결, Phase 1(저장소 정정) 커밋 완료 상태에서 작성됨.

## 발송 전 확인 항목

1. **v0.3.3 DOI `10.5281/zenodo.20374227`** — GitHub 증거로 확정(PR #520 `isNewVersionOf` + alpha.3 notes). Zenodo Versions 탭 육안 확인 1회 하면 완전무결. 안 해도 발송 가능 판단.
2. **concept DOI** — 우리가 한 번도 기록한 적 없음. 아래 편지는 "확인해 줄 수 없고, 어차피 쓰면 안 된다"로 답함.
3. **Vadym 통지** — 이 편지가 `feedback_m6_vadym_attribution_3way_timing` Phase 2(JAMES→Ali) 이행분. Robin Phase 1은 여전히 미완이며, 단독 DM 금지 규칙 유지.
4. **저장소 정정 커밋** — 편지가 참조하는 커밋이 브랜치에 있는지 확인. main 병합 전이면 문장에서 "on a branch"로 조정하거나 병합 후 발송.
5. **약속한 것** — bidi span 제거 / session salting 재측정 / 아랍어 정규화 / 그의 replay 드라이버 실행. 발송 = 이행 의무 발생. Phase 3 착수 계획과 함께 보낼 것.

---

Ali,

Two months is your call to make, not a debt. You said what the reason
was; that is enough said about it. Thank you for the deposit and for
the four findings — the second half of this reply is worth more to me
than the first.

You asked to be read as a submission before being asked for a
signature. That is how I read it, and this is the report.

## The record itself

The numbers hold together and they reconcile with the repository. Four
caps x N=20 x two call shapes gives the 160, the 80 routing calls at
one distinct output and 49 completion tokens flat, and the synthesis
medians moving 130.5 -> 118.5 across a 10x cap range are the same 12
tokens your letter quotes. `finish_reason` "stop" on 160/160 with zero
truncations is the right thing to report, and reporting the cost
($0.03) is the sort of detail that makes a record replayable rather
than merely readable.

The scope section does the work you built it to do. Stating that the
production leg pinned T=0.2 while the deployed app runs at default
temperature — and that what is expected to survive temperature is the
token count, not byte equality — is the declaration a reviewer would
otherwise have to extract from you. Same for refusing to claim that
three stacks make a universal. I would not soften any of it.

**One methodological point, and it is the one I would raise as a
reviewer.** Your conclusion is that the shipped prompt's "2-4
sentences" instruction, not the cap, is the binding constraint. I
believe the observation, but as measured, two causes are confounded:
the prompt is length-instructed *and* gpt-4o-mini emits no reasoning
trace. On our side those are separable, and the separation matters —
see the next section, where five of our seven tiers turn out to be
82-98% hidden reasoning trace. A model that has no such trace is
already floored near its visible-answer length before any instruction
is applied.

Separating them costs one added cell: length instruction on/off x
reasoning mode on/off, same fixture, same caps. If the length
instruction is doing the work, dropping it should lift the medians
substantially at the high caps. If it is not, the medians barely move
and the binding constraint is the model's own stopping behaviour. Either
result strengthens the record; the current one states a mechanism that
the design cannot yet distinguish from its alternative. I would put
"the instruction, not the cap, appears to be binding" in the record and
name the missing cell, rather than drop the finding.

## Corrections you should make to the metadata — and they are ours, not yours

The Seo bullet cites the seven-tier gradient as "V3-prime Direction 1;
PR #440, Issue #448". Three things are wrong there, and all three trace
back to my prep folder rather than to your reading.

- **PR #440** is V3'.e, merged 2026-05-23. It measures *three* workload
  levels — heavy 0/10, light 14/20, none 20/20 at cap=400. The phrase
  "7-tier" does not appear in it, and it predates Direction 1.
- **The seven-tier result is PR #461 + #463**, merged 2026-05-24. #463
  carries the tier table (62 / 235 / ~370 / ~690 / ~910 / ~970 / 1681)
  and the 27x figure. It is archived as v0.3.1, DOI
  10.5281/zenodo.20363998 — and that Zenodo record's own
  `related_identifiers` cite #461, #463 and #457, never #440.
- **Issue #448 is Robin's** 26b cross-stack data. Cited under my bullet
  it reads as her leg supporting mine, which is exactly the collapse
  the three-axis split exists to prevent.

The cause: my joint-deposit prep folder labelled this axis "workload
gradient ... (PR #440)", which was correct when the axis *was* the
three-level split, and I never updated the pointer after v0.3.1
upgraded the axis to seven tiers. You took "seven-tier" from the DOI
description, which was right, and "#440" from my folder, which was
stale. Fixed on my side now, along with a second defect the same audit
turned up: one of my release notes had assigned v0.3.3's DOI to a
release that never existed. Both corrections are in the repository with
the evidence written next to them, so the next person to read those
files does not repeat either.

## The axis in my words, for verbatim use

> **Workload gradient (Seo):** inside retrieval middleware on
> gemma4:e4b, completion length at natural stop rises monotonically
> across a seven-tier task ladder — 62 -> 1681 tokens, 27x dynamic
> range, per-tier cross-sweep variation within 3-5% (V3-prime
> **Direction 1 closure, PRs #461/#463**, archived as
> 10.5281/zenodo.20363998; the earlier two-mode / three-workload split
> is **PR #440**, and Converse's cross-stack numbers are **Issue
> #448**). The measured quantity is total completion tokens
> (`eval_count`), which on this model includes a hidden reasoning
> trace: a follow-up decomposition found 5 of the 7 tiers are 82-98%
> trace, so the gradient's magnitude is part task workload and part
> reasoning-mode cost. The substitution baseline (2% trace) and the
> `reflect` tier (61%, 580 visible tokens) are the tiers carrying
> unambiguous workload signal.

The decomposition behind that caveat: verify is 1164 eval_count against
23 visible tokens; query_rewrite 534 against 38; planner 685 against
92; reflect 1492 against 580. Disabling reasoning reclaims 83-98% of
five tiers with the visible answer unchanged. The 27x span survives,
but per-tier magnitudes collapse. I would rather that sit in the joint
record from the start than be found by a reviewer, and it is also the
fact that makes your boundary condition worth measuring properly rather
than assuming.

**One factual mismatch to reconcile while we are here.** The
forward-pointer in the v0.3.1 and v0.3.3 Zenodo notes — the one your
record resolves — describes your leg as "Provia, mid-June
managed-Gemini cross-stack". You delivered a hosted gpt-4o-mini
production router. Those records are minted and not editable, so the
joint deposit should say in one sentence that the third leg was
measured on a different backend than the one anticipated. Better to
state it than to leave a pointer resolving to a stack nobody used.

## Your four questions

1. **Alphabetical authorship as drafted — yes.** No reservation.
2. **Publication -> report, CC-BY-4.0 — yes.** My own draft already
   defaulted to CC-BY-4.0 for the joint record with the solo records
   staying MIT, so we converged independently. "Report" also keeps the
   path to arXiv clean.
3. **DOIs — cite all three individually, and do not use the concept
   DOI.**
   - v0.3.1 — `10.5281/zenodo.20363998`
   - v0.3.2 — `10.5281/zenodo.20372649`
   - v0.3.3 — `10.5281/zenodo.20374227`

   I cannot confirm `20363997` as the concept DOI — I have never
   recorded one, which is itself a hygiene failure on my side. More to
   the point, a Zenodo concept DOI resolves to the *latest* version of
   the record chain, which today is v0.4.4
   (`10.5281/zenodo.20652679`). As a fallback for a v0.3.x citation it
   would silently point at the wrong artifact.
4. **A suggestion, not a request:** Robin's solo record has a DOI —
   `10.5281/zenodo.20570701`, from 2026-06-08 — and the metadata cites
   only the GitHub URL. Her call whether to add it.

**Two things I owe you rather than answer.**

*Vadym Arnaut.* My contribution catalog credits him as the source of
"each variant has its own tax", the phrasing you later used, flagged to
me by Robin. Your draft is three-author, which may simply mean you
weren't told he was in the catalog — so, telling you now. Whether the
record is three-author or four is for you and Robin to settle; I have
no position beyond wanting the provenance to be accurate either way.

*The headline.* "Substitution is free. Synthesis costs in proportion to
what it has to invent." is your line, Robin endorsed it, and it is the
only phrase all three of us have agreed on verbatim. Your new title is
better as a title, but I would keep that sentence somewhere in the
description rather than lose it.

## Your four findings, checked here

**1. Bidi — you were right, and it is our code.** Our input gate strips
the control characters and keeps the concealed text: exactly the
operation you walked back. The recommendation came from your report,
but shipping the weaker version was my choice, not yours. Moving to
span removal, keeping the discipline that the adversarial fixtures
stay un-normalised so the fixture-to-server boundary is still what is
under test.

**2. `\d` — does not reproduce in our scorer, but the class does.**
Python's `re` is Unicode-aware by default, so our price extractor
handles Arabic-Indic digits: `re.findall(r"\b\d+\b", "السعر ٣٥٠ شيكل")`
returns `['٣٥٠']` and `int()` gives 350. Under `re.ASCII` it returns
`[]`, which is what your stack does by default. So the finding is real
and it is a language difference, not a difference in care. Where it
does land on us is the browser: our answer renderer parses citation and
step markers out of model output with JavaScript `\d`, which *is*
ASCII-only. An Arabic-numeral enumeration would silently fail to
render. Found because you asked the question; fixing it.

**3. Arabic keyword gates — applies.** Our runtime gate applies NFC,
which leaves both tatweel and Arabic presentation forms untouched
(`ﻛﺘﺎﺏ` is unchanged under NFC and only folds under NFKC), and our
adversarial scorer matches substrings with a plain lowercase
comparison. Both are the false-negative-on-benign-traffic story you
describe. Moving to NFKC plus tatweel and alef-maqsura folding, with
the same fixture-boundary carve-out as (1).

**4. Run identity — applies, and I can scope the blast radius
exactly.** Our query endpoint defaults `session_id` to the literal
string `"default"`, the engine injects that session's last five turns
into the prompt, and every successful call writes a turn back. Our
adversarial sweep posts only the question, so all 18 cases ran under
`"default"` — very likely as turns 1 through 18 of a single
conversation. There is a verdict in our cross-stack comparison that I
wrote off as single-run noise, and it may instead be order
contamination. Re-running salted, and I will send you the corrected
table either way.

The part that matters for the joint record: the V3-prime and Direction
1 drivers do not go through that endpoint. They call Ollama's
`/api/generate` directly, one process, no session, no history. The
seven-tier numbers are not exposed to this. I would rather tell you the
boundary than let you discover it.

## What I'd like next

I'll take you up on the invitation literally. Your replay driver needs
only fetch and an OpenAI-compatible endpoint, which a local Ollama
satisfies, so I will run it here and report what comes back — including,
and especially, if it does not reproduce.

On sequencing: I have no objection to the joint deposit going to arXiv
as the first paper out of this chain, and I would rather my corrections
be in it than appended to it — which is what this letter is trying to
make possible. The second study you mention touching JAMES directly: I
would rather see it proposed on its own terms, with its scope and its
evidence stated up front, than fold it into this thread. Open it when
it's ready and I will read it the way you read this one.

Thank you for the four findings. Three of them are live defects here, and
the fourth found a real one somewhere I wasn't looking.

— Jiwon Seo
Hashevolution / PROJECT JAMES
github.com/Hashevolution/James-RAG-Evol
ORCID 0009-0002-0007-7860
