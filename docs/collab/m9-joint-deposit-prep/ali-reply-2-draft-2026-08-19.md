# Ali 2차 답장 초안 — 2026-08-19 (joint deposit 최종본 승인)

**상태**: DRAFT. 발송 전 운영자 확인.
**성격**: 조건부 OK. 그가 요청한 것 = ① 이 텍스트 그대로에 대한 OK ② stitch clause.

**원자료 대조 (2026-08-19 재점검)**
- Ali 가 인용한 우리 축 수치 전부 원자료 일치 — 62→1681 / 27× / tier당 3–5% /
  5 of 7 tiers 82–98% trace / substitution 2% / reflect 61%·visible 580 /
  PR #461·#463·#440 / Issue #448 / DOI 20363998·20372649·20374227.
- Converse 축의 "6–9/20 unique" 는 Issue #448 본문에 **없으나**
  `triavalabs/gemma4-26b-mode-split` README 에 cap400=6 / cap4096=9 로 존재.
  그녀의 DOI 20570701 이 그 저장소의 아카이브이므로 추적 가능 → 지적 대상 아님.
- Issue #448 원문 표현은 *"Parameter count appears to buy reasoning
  efficiency, not just reasoning capacity."* (LinkedIn 변형과 다름 — 편지는
  이슈 원문을 인용).
- 통계 논증은 SE 추정이 아니라 **control 4셀(124–128.5)과 제거 4셀
  (133.5–144.5)의 완전 분리**를 1차 근거로 삼음. 분포 가정 불필요.
  SE 는 보조: n=20 range 48–63 → SD≈15 → 80콜 중앙값 오차 ≈2 토큰.
**전제**: 1차 답장 발송 완료. 저장소 정정(#1077)·lint 복구(#1078) main 반영 완료.

## 이 답장이 하는 일

1. **OK를 준다** — 단, 문장 2개 교체 조건. 둘 다 그가 스스로 세운
   "does not claim" 기준을 본문이 넘어선 자리라, 넘기면 리뷰어가 먼저 찌른다.
2. **확인 질문 2개** — Robin model-scale 축 소멸 / control arm 출처.
3. **stitch clause 초안 제공** — 왕복 1회 절약.
4. 선택 2건(“dataset” 표기, 10단어 헤드라인)은 한 줄씩만.

## 넣지 않은 것

- Vadym: 최종본에 "each variant has its own tax"가 없으므로 **이 기록에는
  귀속 결함이 없다**. Phase 2 통지는 이 기록과 분리해 별도 처리.
- 엔지니어링 4건 진행 상황: 측정 결과 나온 뒤 별도 메시지(1차 답장에서 이미 예고).

---

Ali,

OK on the record — with two sentences I'd change first, both in the
production bullet, and both because the body currently claims more than
your own "does not claim" section allows. Neither touches your result.

**1. The instruction effect is real; the spread test doesn't retire it.**
You write that the 127 → 138.5 shift is "smaller than within-cell
spread — so the binding constraint is neither the cap nor the
instruction." Within-cell spread is the dispersion of individual
samples; what a shift in centres has to clear is the error on that
centre, which is smaller by roughly √n.

The cleanest evidence is in the numbers you already report, and it needs
no distributional assumption at all: your four control medians span
124–128.5 and your four instruction-removed medians span 133.5–144.5.
Those two sets are **disjoint** — every removed cell sits above every
control cell, in a same-day paired arm on frozen payloads. A cause that
does nothing does not move all four cells in the same direction and
clear the whole control range by five tokens.

The arithmetic agrees. Borrowing your 48–63 within-cell spread: at
n=20 the expected range of a normal sample is about 3.7 SD, so SD is on
the order of 15, and the error on an 80-call arm's median is about 2
tokens (≈1.25 × 15/√80). The observed +11.5 is roughly five times that.
Per-cell it still clears — median error ≈4 tokens against shifts of
+9 to +16.

That is a small effect, not an absent one. Suggested replacement:

> per-cap medians moved 124–128.5 → 133.5–144.5 tokens (pooled 127 →
> 138.5, 1.09×): the instruction accounts for roughly 9% of the reply
> length and no more, leaving the order-of-magnitude gap to every cap
> governed by the model's own natural answer length. The instruction is
> a contributor, not the binding constraint.

and, in the paragraph below it:

> the instruction-removed arm bounds the prompt's length instruction to
> roughly 9% of that distance: the model's own answer floor, not the
> instruction, is what keeps the call an order of magnitude below the
> cap.

This is stronger for you, not weaker. "The instruction does almost
nothing" invites one reviewer question you cannot answer from the data;
"the instruction is worth 9% and the floor owns the rest" answers it in
advance.

**2. The no-trace explanation is an inference, not your measurement.**
"a hosted model with no reasoning trace floors near its visible answer"
reads as established, but the reasoning axis was never varied on your
stack — you ran one hosted model, and every trace-side number in this
record comes from e4b, a different model on a different stack. Your
"does not claim" section already says exactly this; the body should
match it. Cut the clause from the bullet, or land it as:

> whether the absence of a reasoning trace is what places that floor is
> the middleware leg's axis, and was not varied here.

**Two things to check rather than change.**

*Robin's third axis.* Earlier drafts carried three axes with model-scale
efficiency as its own — her ~9× synthesis-efficiency finding, which
Issue #448 states as "Parameter count appears to buy reasoning
efficiency, not just reasoning capacity." In this version her leg is a
replication of substitution determinism on a larger model and the 9× is
gone. If that is her call, fine; if it is a casualty of restructuring to
three legs, she should see it before submission. (Her 6–9/20 synthesis
uniqueness checks out against her repo README, so that figure is
traceable through her DOI even though #448 doesn't carry it.)

*Run-to-run drift.* You say "80 control", so the control arm is fresh
calls rather than the original sweep re-reported — worth making explicit
in the bullet, because the two controls do not line up. The first sweep
put the medians at 127.5–130.5 for 400–800 and 118.5–122.5 for
1600–4096; the same-day control reads 124–128.5 across all four, with
the downward cap trend flattened. At matched caps that is roughly a
six-token move between runs of the same nominal condition. It does not
threaten the paired result — the disjointness above is within one
same-day arm — but it does bound how precisely the 9% can be quoted, and
one sentence naming it would pre-empt the question.

**Two small ones, take or leave.** 10.5281/zenodo.20363998 is deposited
with upload_type `software`, so "the JAMES-leg dataset" may confuse
anyone who opens it — "record" or "software archive" is exact. And the
ten-word line — *"Substitution is free. Synthesis costs in proportion to
what it has to invent."* — is your phrasing, Robin endorsed it, and it
is the one sentence all three of us have agreed on verbatim; it would
cost one line in the description to keep it.

**The stitch clause.** Taking it as the sentence each of us drops into
our own forward-pointers on mint day — my README Context section, Issue
#448, your README — here is a version that works in all three with only
the last clause swapped:

> This work is one leg of a three-stack convergence record —
> substitution-vs-synthesis measured independently on a sovereign 26B
> MoE (Converse), the JAMES cognitive middleware (Seo), and a production
> Arabic e-commerce router (Afana) — archived at <DOI>. That record
> states what the three legs jointly establish and what they explicitly
> do not; this repository holds the <sovereign / middleware / production>
> leg's data and drivers.

If you meant the connective sentence inside the deposit instead, say so
and I'll write that one.

Change those two sentences and you have my OK on the text as it stands.

— Jiwon Seo
Hashevolution / PROJECT JAMES
ORCID 0009-0002-0007-7860
