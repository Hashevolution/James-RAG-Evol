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

**최종 대조 (발송 직전) — 정정 3건**
- Ali README 실측 per-cap 중앙값 = **127.5 / 130.5 / 118.5 / 122.5**,
  README 자체가 **non-monotonic** 이라 명시. 초안의 "downward cap trend
  gone" 은 근거 없는 서술 → 삭제. 1차 범위[118.5–130.5] 안에 신규
  control[124–128.5] 이 **포함**되므로 "두 control 이 어긋난다" 도 과장 →
  "재현 안 된 것은 최저 두 셀" 로 축소.
- 10단어 헤드라인을 "your phrasing" 이라 쓴 것 = 오귀속.
  `launch-tracker.md:109` — 문구는 `v3prime-e-substitution-synthesis-result.md
  §Implications` 의 JAMES-side candidate 였고 Ali 가 **독립 재도출·지지**,
  Ali 고유 기여는 "cost asymmetry in ten words". 3자 수렴으로 재서술.
**핵심 전제 확정 — "48–63" 의 정체**
- item 1 산술 전체가 이 한 단어에 달려 있었음: **범위(max−min)** 이면 SD≈14 →
  차이오차 2.8 → **4.1배(유의)**, **표준편차** 면 SD≈55 → 차이오차 10.9 →
  **1.06배(전혀 유의하지 않음)** — 즉 그가 틀렸는지 옳은지가 뒤집힘.
- Ali README 표의 행 이름이 문자 그대로 **`within-cell range`** (63/48/48/51)
  임을 원문에서 확인. 요약 해석이 아니라 컬럼 헤더 → **범위 확정**, 산술 성립.
- 부수 확인: 왜도(token length 는 우편포) 가 있으면 range/SD 비가 3.735 보다
  커져 SD 는 더 작아짐 → 우리 추정은 **보수적 방향**.

**통계 서술 재점검 (2건 추가 정정)**
- **비교 대상 오류**: "+11.5 는 80콜 중앙값 오차(≈2)의 5배" → +11.5 는 **두
  독립 중앙값의 차이**이므로 차이의 오차(≈2.8, √2 배)와 비교해야 함 → **약 4배**.
  실측 spread 63/48/48/51 평균 52.5 ÷ 3.735 → SD≈14 로 정정. 쌍대(frozen
  payload 동일)라 실제로는 더 유리하나 보수적 기준 채택.
- **분리(disjointness) 과대평가**: 이를 "더 강한 증거"·"효과 없는 원인은 그런
  패턴을 만들지 않는다" 로 단정했으나, 4쌍 부호검정 = **1/16 (0.0625)** 로
  관례적 유의수준 미달. 주 근거는 **크기(≈4σ)**, 분리는 **전 셀 일관성**을
  보이는 보조 근거로 재배치. (상대의 통계를 지적하는 편지에서 같은 유형의
  과장을 저지르지 않도록.)

**최종 다듬기 (발송 직전 4건)**
- **산술 오류 정정**: 2차 대체문이 "9% of that distance" 였음. 11.5 토큰은
  *답변 길이*(127)의 9% 이지 *cap 까지의 거리*(cap400 기준 273, cap4096 기준
  ~3969)의 9% 가 아님 — 후자면 4% / 0.3%. "removing the instruction lengthens
  the reply by about 9%" 로 교체.
- 2번 항목 drop-in 이 bullet 앞부분("…while synthesis never approaches any
  cap")에서 시작해 실제 교체 위치와 어긋났음 → 해당 clause 자리에 정확히
  꽂히도록 재작성.
- 서두 "two sentences" → 실제 대체문 3개(1번 2개 + 2번 1개) → **"two changes"**.
- 전체 압축: 1번 3문단 → 2문단, control 항목 대폭 축약.

- 우리 README 에 "Context" 섹션 없음 (실제: Why SEKOS? / Quick Start /
  Architecture / … / **Papers & Reproducibility**). stitch clause 위치를
  실제 섹션명으로 교체.
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

OK on the record — with two changes first. They sit in one sentence of
the production bullet, plus the boundary-condition paragraph that echoes
it, and they fail differently: the first reaches a conclusion your data
support but justifies it with the wrong test, then overshoots into "no
effect"; the second states as general something your own "does not
claim" section confines to a single measured pair. Neither touches your
result.

**1. The instruction effect is real; the spread test doesn't retire it.**
You write that the 127 → 138.5 shift is "smaller than within-cell spread
— so the binding constraint is neither the cap nor the instruction."
Within-cell spread is the dispersion of individual calls; what a shift
in centres has to clear is the error on the centre, smaller by roughly
√n. Borrowing your 48–63 spread: at n=20 the expected range of a normal
sample is about 3.7 SD, so SD is around 14, the error on an 80-call
median is about 2 tokens, and the error on the difference between two of
them is about 3. The observed +11.5 is close to four times that — and
since both arms ran the same frozen payloads, pairing can only tighten
it.

And it isn't one cell carrying it. Your four control medians span
124–128.5 and your four instruction-removed medians span 133.5–144.5 —
the two sets don't overlap, so every removed cell sits above every
control cell, same day and same frozen payloads, clearing the whole
control range by five tokens. On its own that pattern is only a sign
test on four pairs, which an inert cause reproduces about one time in
sixteen; it is the magnitude above that carries the weight. Together
they say the effect is small, consistent, and not noise. (I can't check
this arm cell by cell — unlike the first sweep's per-cap table, the
deposit gives these medians only as ranges.)

Your conclusion survives all of it: at caps of 400 to 4096, an
instruction worth 11.5 tokens is plainly not what holds the call an
order of magnitude below the ceiling. What doesn't survive is "not what
puts it there," which reads as no effect at all.

Both of my changes land in one sentence of yours, so here is a single
drop-in for it — everything from "per-cap medians" to the end. It
carries the fix in (2) below as well:

> per-cap medians moved 124–128.5 → 133.5–144.5 tokens (pooled 127 →
> 138.5, 1.09×): removing the instruction lengthens the reply by about
> 9% and no more, so the instruction is a contributor but not the
> binding constraint — the order-of-magnitude gap to every cap is
> governed by the model's own natural answer length. Whether the
> absence of a reasoning trace is what places that floor is the
> middleware leg's axis; it was not varied on this stack.

The same phrasing recurs further down, in the paragraph on the boundary
condition, as "…shows the prompt's length instruction is not what puts
it there: the model's visible-answer floor governs". For that one:

> …bounds the prompt's length instruction to about 9% of the reply's
> length: it contributes, but the model's visible-answer floor is what
> holds the call an order of magnitude below the cap.

This reads stronger, not weaker. "The instruction does almost nothing"
invites the one reviewer question you cannot answer from the data; "it
is worth 9%, the floor owns the rest" answers it in advance.

**2. The no-trace explanation is an inference, not your measurement.**
The clause that closes the same sentence — "a hosted model with no
reasoning trace floors near its visible answer" — reads as established,
but the reasoning axis was never varied on your stack: one hosted model,
and every trace-side number in this record comes from e4b, a different
model on a different stack. Your "does not claim" section already says
precisely this; the body should match it. The drop-in above replaces
that clause; dropping it outright works equally well.

**Two things to check rather than change.**

*Robin's third axis.* Your previous draft's Converse bullet carried it —
"synthesis grows markedly more token-efficient with model scale" — and
this version puts the fan-out figure there instead. Her ~9×
token-efficiency finding — the one Issue #448 reads as "Parameter count
appears to buy reasoning efficiency, not just reasoning capacity" — is
now absent, and her leg reads as a replication of substitution
determinism on a larger model. Your first draft tagged that bullet
"[Robin - this is your axis; edit freely.]", so this may simply be her
own rewrite, in which case there is nothing to do. If instead it went out
with the restructuring, she should see that before you submit. (Her 6–9/20 fan-out
does check out against her repo README, so the figure is traceable
through her DOI even though #448 doesn't carry it.)

*How steady the control centre is.* "80 control" means fresh calls
rather than the first sweep re-reported — worth saying in the bullet.
The two are compatible without being identical: your README puts the
first sweep's per-cap medians at 127.5 / 130.5 / 118.5 / 122.5,
non-monotonic across 118.5–130.5, while the same-day control sits at
124–128.5 — inside that span, but never reaching the two lowest cells.
The paired result is untouched, since control and treatment ran the same
day on the same payloads; but the control centre has a few tokens of
play of its own, and that is what a reader will hold the 9% against. One
sentence naming it is enough.

**Two small ones, take or leave.** 10.5281/zenodo.20363998 is deposited
with upload_type `software`, so "the JAMES-leg dataset" may throw anyone
who opens it; "record" or "software archive" is exact. And the ten-word
line — *"Substitution is free. Synthesis costs in proportion to what it
has to invent."* — is the one sentence all three of us hold verbatim: it
came out of the V3′.e result doc, you re-derived it independently on the
PR #440 thread and gave it the "cost asymmetry in ten words" framing,
and Robin locked it. One line in the description would keep it.

**The stitch clause.** Reading it as the sentence each of us drops into
our own forward-pointers on mint day — my README's Papers &
Reproducibility section, Issue #448, your README — one version serves
all three with only the last clause swapped:

> This work is one leg of a three-stack convergence record —
> substitution-vs-synthesis measured independently on a sovereign 26B
> MoE (Converse), the JAMES cognitive middleware (Seo), and a production
> Arabic e-commerce router (Afana) — archived at <DOI>. That record
> states what the three legs jointly establish and what they explicitly
> do not; this repository holds the <sovereign / middleware / production>
> leg's data and drivers.

If you meant the connective sentence inside the deposit instead, say so
and I'll write that one.

Make those two changes and you have my OK on the text as it stands.

— Jiwon Seo
Hashevolution / PROJECT JAMES
ORCID 0009-0002-0007-7860
