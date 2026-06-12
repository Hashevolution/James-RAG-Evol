# RAB · LRB 공개 — LinkedIn / X 프리미엄 포스트 초안 (2026-06-12)

> 모든 수치는 `papers/rab-preprint/main.tex` (2026-06-11) 및
> `papers/lrb-preprint/main.tex` (2026-06-12) 프리프린트와
> `docs/handovers/v0.4-next-session-entry-2026-06-12-pm.md`에서 직접 검증.
> 두 프리프린트의 honesty clause (H3 "certify 아님" / H5 "JAMES 점수는
> headline 아님" / no-JAMES-wins-framing prereg 금지조항)을 포스트
> 차원에서도 준수하도록 작성됨.

---

## 1. LinkedIn 포스트 (한국어)

EU AI Act의 고위험 시스템 의무가 2026년 8월 2일 발효됩니다. 그날 이후
이 질문에 답해야 합니다:

**"당신의 RAG/에이전트 시스템은, 내보낸 로그만 가지고 무엇을 색인하고,
무엇을 검색하고, 무엇을 답변했는지 재구성할 수 있습니까?"**

지난 두 달간 솔로 프로젝트 JAMES에서 이 질문을 측정하는 벤치마크 두 개를
만들어 공개했습니다.

🔹 **RAB (Replayable-Audit Benchmark) v0.1.1**
EU AI Act 10·12·19조의 기록 의무를 3개의 결정론적 지표로 조작화했습니다
— AC(감사 완전성), RF(로그만으로 상태 재현), PC(인용→원천 출처 체인).
채점 어디에도 LLM judge가 없습니다. 우리가 아는 한, 임의의 RAG/에이전트
시스템이 **내보낸 감사 로그 아티팩트 자체**를 AI Act 기록 조항에 대해
채점하는 첫 벤치마크입니다.

4개 시스템을 측정한 갭 테이블이 헤드라인입니다 (특정 시스템 점수가
아니라):
- 감사-네이티브 런타임: AC/RF/PC = 1.000 / 1.000 / 1.000
- 볼트온 OpenTelemetry GenAI 트레이싱: 0.500 / 0 / 0
- 기본 로깅(quickstart): 0.275 / 0 / 0

가장 흥미로운 발견 두 가지:
1. 기본 로깅과 볼트온 트레이싱은 **서로 다른 곳에서** 실패합니다.
   기본 로깅은 INGEST는 잡지만 ANSWER를 놓치고, OTel 트레이싱은
   ANSWER는 잡지만 INGEST 어휘 자체가 없습니다. 둘 다 RF와 PC는 0.
2. 볼트온 트레이싱은 **인용을 49건 방출했지만 추적 가능한 건 0건**
   — 인용 체인이 도착할 INGEST 이벤트가 로그에 없기 때문입니다.

40개 연산 시나리오에서 400개 연산 시나리오(10배)로 키워도 갭 테이블의
모든 셀이 소수점 셋째 자리까지 동일하게 재현됐습니다.

🔹 **LRB (Lifecycle Retrieval Benchmark) v0.2**
기존 RAG 벤치마크(MuSiQue, 2WikiMultiHop, ALCE …)는 **얼어붙은
코퍼스**를 씁니다. 그러나 실제 기업 문서는 계속 바뀝니다 — 정책 개정,
이사 교체, 계약 갱신. LRB는 각 질의에 (query_time, valid_time) 쌍을
부여해 "현재 상태 검색"과 "타임트래블 검색"을 같은 픽스처에서
측정합니다.

결과 (S2 타임트래블, R@1): append-only 0.225 < supersede-제거 0.538 <
validity-window 0.713. 이 V < N < J 순서는
- 4개 모델 패밀리(4B/12B/47B/클라우드)에서 4/4 보존되고,
- 문서 1,000개·이벤트 5,620개의 12.5배 스케일 점프에서도 4개 스케일
  지점 전부에서 보존되며, validity-window의 기여(J−N 갭)는 모든
  지점에서 +0.10 이상이었습니다.

그리고 정직한 negative도 같이 공개합니다: 라이프사이클 축이 없는
MuSiQue에서는 세 시스템이 사실상 동일했습니다. 갭은 시간 축에만
존재합니다 — 이게 측정이 진짜라는 증거입니다.

🔹 **이 프로젝트의 방법론이 사실 진짜 차별점입니다**
- 측정 전에 사전등록(pre-registration) 커밋 — RAB 2건, LRB 6건,
  결정 규칙까지 잠금
- 사전등록한 RF-cost 가설은 기준 미달 → **주장 자체를 보류** (룰대로)
- 측정 아티팩트 발견 시 자기 정정 후 공개 (S3 계약서 어휘 붕괴 →
  수치 재측정 → 정직한 재프레이밍)
- 벤치마크 저자의 시스템이 잘 나오는 건 헤드라인이 아니라는 조항을
  스펙에 명문화

두 벤치마크 모두 스펙, 시나리오, 채점기, 어댑터, 80+ 측정 아티팩트가
결정론적으로 재현 가능하게 공개되어 있습니다.
- RAB: Zenodo DOI 10.5281/zenodo.20625533
- LRB: Zenodo DOI 10.5281/zenodo.20652679
- GitHub: github.com/Hashevolution/James-RAG-Evol

감사-네이티브 런타임을 만들고 계시다면 (ActiveGraph 포함) — 어댑터
컨트랙트가 열려 있습니다. 외부 재현과 SUT 제출을 정식으로 초대합니다.

(주의: RAB는 AI Act 개념을 '측정'하는 것이지 컴플라이언스를 '인증'하지
않습니다. 스펙 honesty clause H3.)

#EUAIAct #RAG #AIGovernance #Benchmark #AuditLog #LLM #TemporalRAG
#Reproducibility

---

## 2. LinkedIn 포스트 (영문 — 국제 도달용)

The EU AI Act's high-risk obligations enter into force on **2 August
2026**. From that day, operators of RAG and agent systems face a
measurable question:

**"Given only your exported log, can you reconstruct what was indexed,
retrieved, and answered?"**

I've just released two pre-registered, deterministic benchmarks that
measure exactly this, built solo on PROJECT JAMES:

🔹 **RAB v0.1.1 — Replayable-Audit Benchmark.** Three metrics anchored
verbatim to EU AI Act Articles 10/12/19 — Audit Completeness, Replay
Fidelity (log-only), Provenance Coverage — with **no LLM judge anywhere
in scoring**. To our knowledge, the first benchmark that scores the
exported audit-log artifact of arbitrary RAG/agent systems against the
Act's record-keeping articles.

The headline is the gap table, not any single system's score:
audit-native 1.000/1.000/1.000 · bolt-on OpenTelemetry GenAI tracing
0.500/0/0 · default logging 0.275/0/0. Two findings stand out:
default logging and bolt-on tracing fail at **different** canonical
categories (INGEST vs ANSWER), and the bolt-on tier **emitted 49
citations of which 0 were traceable** — there's no INGEST event in the
log for the provenance chain to terminate at. Every cell replicated to
the third decimal place on a 10× larger scenario.

🔹 **LRB v0.2 — Lifecycle Retrieval Benchmark.** Frozen-corpus RAG
benchmarks can't measure whether you retrieve the *time-valid* version
of a document. LRB gives every query a (query_time, valid_time) pair.
Result (R@1, time-travel): append-only 0.225 < remove-on-supersede
0.538 < validity-window 0.713 — an ordering preserved across **four
model families** (4B → 12B → 47B → cloud) and across a **12.5× scale
jump** to 1,000 docs / 5,620 lifecycle events, with the
validity-window contribution above +0.10 at every point. And the
honest negative: on MuSiQue, which has no lifecycle axis, all three
systems are equivalent — the gap is real and task-specific.

Both benchmarks ship with locked pre-registrations (8 total), frozen
honesty clauses, and 80+ deterministic measurement artifacts. One
pre-registered hypothesis (RF-cost super-linearity) missed its locked
threshold — so the claim is withheld, per the rule as written.

- RAB: Zenodo DOI 10.5281/zenodo.20625533
- LRB: Zenodo DOI 10.5281/zenodo.20652679
- Code: github.com/Hashevolution/James-RAG-Evol

If you build an audit-native runtime, the adapter contract is open —
external replication and SUT submissions are formally invited.

(RAB operationalises AI Act concepts; it does not certify compliance.)

#EUAIAct #RAG #AIGovernance #Benchmark #AuditLog #Reproducibility

---

## 3. X 프리미엄 (한국어, 롱폼 1포스트)

당신의 RAG 시스템 로그, EU AI Act가 발효되는 8월 2일에 살아남을까요?

직접 측정해봤습니다. 결과가 꽤 잔인합니다.

벤치마크 두 개를 만들어 공개했습니다 — 솔로 프로젝트 JAMES에서, 측정
전에 전부 사전등록하고.

**① RAB — 감사 로그 벤치마크 (EU AI Act 10·12·19조)**

질문은 하나: "내보낸 로그만으로 시스템이 한 일을 재구성할 수 있는가?"
LLM judge 없이 결정론적 지표 3개(완전성 AC / 로그-only 재현 RF / 출처
추적 PC)로 채점합니다.

4개 시스템 갭 테이블:
- 감사-네이티브: 1.000 / 1.000 / 1.000
- OTel GenAI 볼트온 트레이싱: 0.500 / 0 / 0
- 기본 로깅: 0.275 / 0 / 0

제일 아픈 발견: 볼트온 트레이싱이 인용을 49건 방출했는데 **추적 가능한
건 0건**. 인용 체인이 도달할 INGEST 이벤트가 로그에 아예 없어서입니다.
그리고 기본 로깅과 볼트온은 서로 반대 위치에서 실패합니다 — 하나는
색인은 잡고 답변을 놓치고, 하나는 답변은 잡고 색인 어휘가 없습니다.
규모를 10배(40→400 연산) 키워도 모든 셀이 소수점 셋째 자리까지 재현.

**② LRB — 시간 유효성 검색 벤치마크**

MuSiQue 같은 기존 벤치는 얼어붙은 코퍼스를 씁니다. 현실의 문서는
바뀝니다. "계약 체결 당시 정책이 뭐였지?"에 답하려면 시간 축이
필요합니다.

타임트래블 질의 R@1: append-only 0.225 < supersede-제거 0.538 <
validity-window 0.713. 이 순서는 4개 모델(4B→클라우드)에서 4/4,
문서 1,000개로 12.5배 키운 스케일 사다리 4지점 전부에서 보존.
갭은 모든 지점에서 +0.10 이상.

그리고 정직하게: 시간 축이 없는 MuSiQue에선 세 시스템이 동일합니다.
갭은 시간 축에만 존재 — 그래서 진짜입니다.

**③ 어쩌면 제일 중요한 부분**

사전등록 8건을 측정 전에 커밋했고, 그중 한 가설(RF-cost 초선형)은
잠가둔 기준에 미달해서 **주장을 통째로 보류**했습니다. 측정 아티팩트를
발견했을 땐 수치를 철회하고 재측정해서 다시 공개했습니다. 벤치마크
저자의 시스템이 잘 나오는 건 헤드라인이 아니라고 스펙에 박아뒀습니다.

전부 재현 가능: 스펙+시나리오+채점기+80+ 측정 아티팩트.
RAB: doi.org/10.5281/zenodo.20625533
LRB: doi.org/10.5281/zenodo.20652679
github.com/Hashevolution/James-RAG-Evol

감사-네이티브 런타임 만드시는 분들 — 어댑터 컨트랙트 열려 있습니다.
재현해보시고, 깨보세요.

---

## 4. X 프리미엄 (영문, 롱폼 1포스트)

Will your RAG system's logs survive August 2, 2026?

That's when the EU AI Act's record-keeping obligations (Articles
10/12/19) enter into force. I built two benchmarks to measure it —
pre-registered before any measurement, solo, on PROJECT JAMES.

**① RAB — scores the exported audit log itself.** Three deterministic
metrics (Audit Completeness / log-only Replay Fidelity / Provenance
Coverage), zero LLM judges. The 4-system gap table:

audit-native 1.000/1.000/1.000
OTel GenAI bolt-on tracing 0.500/0/0
default logging 0.275/0/0

The brutal finding: bolt-on tracing emitted **49 citations, 0
traceable** — there is no INGEST event in the log for the provenance
chain to terminate at. Default logging and bolt-on tracing fail at
*opposite* categories (one catches indexing but misses answers, the
other the reverse). Every cell replicated to the 3rd decimal place at
10× scenario scale.

**② LRB — temporal validity of retrieval.** Frozen-corpus benchmarks
can't tell you whether you retrieve the *time-valid* version of a
document. With (query_time, valid_time) pairs: R@1 goes append-only
0.225 < remove-on-supersede 0.538 < validity-window 0.713 — an
ordering preserved across 4 model families (4B → cloud) and a 12.5×
scale jump to 1,000 docs / 5,620 lifecycle events, gap > +0.10 at
every point. Honest negative included: on MuSiQue (no lifecycle axis)
all three systems are identical. The gap is task-specific — that's how
you know it's real.

**③ The discipline is the product.** 8 pre-registrations locked before
measurement. One hypothesis missed its locked threshold → claim
withheld, per the rule as written. One measurement artifact found →
numbers retracted, re-measured, re-published with honest framing. "The
benchmark author's system scoring well is not the headline" is frozen
into the spec.

Everything reproducible bit-for-bit:
RAB doi.org/10.5281/zenodo.20625533
LRB doi.org/10.5281/zenodo.20652679
github.com/Hashevolution/James-RAG-Evol

Building an audit-native runtime? The adapter contract is open. Come
replicate — or break it.

---

## 5. 게시 시 주의사항 (포스트에는 포함하지 않음)

1. **arXiv 언급 금지 (아직)**: 두 프리프린트 모두 arXiv 제출 전
   (operator pre-flight 6건 미완). "공개된 프리프린트/Zenodo DOI"까지만
   사실. arXiv 제출 완료 후 링크 추가 권장.
2. **"첫 벤치마크" 주장에는 항상 "우리가 아는 한(to our knowledge)"
   단서** — 프리프린트 본문과 동일한 수위 유지.
3. **JAMES-wins 프레이밍 금지** (R1.4 prereg 금지조항): 갭 테이블이
   헤드라인. JAMES 1.000은 honesty clause H5상 "expected"로만.
4. **컴플라이언스 인증 아님** (H3): RAB는 조작화 도구. 포스트에 명시함.
5. LRB 절대 수치는 시나리오-민감 (⭐⭐): 포스트는 패턴+갭(⭐⭐⭐)만
   주장하도록 작성됨. 절대값 인용 시 "S2 기준" 명시 유지.
6. RF-cost(O(N²)) 주장 금지 — 사전등록 기준 미달로 보류 상태.
