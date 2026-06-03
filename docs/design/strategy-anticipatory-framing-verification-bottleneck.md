# Strategy Memo — JAMES 대비(對備) 프레이밍: "검증 병목" 선점

> **Status**: internal draft (positioning memo, not external copy).
> **Genre**: strategy / framing — informs `docs/PLATFORM_READINESS.md`
> 와 `docs/ARCHITECTURE.md §1`의 *동기 서술*. 코드 변경 없음.
> **Trigger**: 2026-06-02 Anthropic "Expanding Project Glasswing"
> 발표문 독해. 그 글의 *대비(anticipatory) 프레이밍* 구조를 JAMES에
> 이식할 수 있는지 검토.
> **Scope guard**: 이 메모는 **내부 사고 정렬용**이다. 외부 공개
> 선언문(Glasswing식 1페이지)으로 승격하려면 별도 PR + honest-framing
> 재검토가 필요하다. 지금은 외부 카피가 **아니다**.
> **작성일**: 2026-06-03

---

## 0. TL;DR

Glasswing 발표문의 설득 구조는 **대비 3단 논법**이다:
*(1) 곧 올 위협 설정 → (2) 위협 도래 전 방어자에게 먼저·통제된 채로
능력 배포 → (3) 발견에서 수정·배포로 무게중심 이동.*

JAMES는 같은 골격을 **"사이버 취약점" 자리에 "출처 없는 지식
(unsourced knowledge)"을 넣어** 그대로 채울 수 있다. JAMES가 이미
스스로를 Agentic RAG와 직교하는 **Replayable RAG**로 포지셔닝한 것이
사실상 이 대비 프레이밍의 씨앗이다.

단, JAMES 버전은 Glasswing보다 **한 단계 더 정직해야** 정체성에
맞는다 — Glasswing 설득력의 상당 부분이 검증 불가능한 규모 주장
("1억 명+", "10,000개+")에서 나오는데, JAMES에는 그것을 금지하는
내부 규율(`memory/feedback_finding_size_honest_framing.md` + PR마다
강제되는 Quality Delta Card)이 이미 있다. 따라서 JAMES의 차별점은
**"우리는 대비 프레이밍을 *측정 가능한 증거와 함께* 짠다"**가 된다.

---

## 1. 왜 이 메모가 존재하나

`docs/PLATFORM_READINESS.md §1`은 mother-hardening의 동기를 **내부
리스크**(섣부른 vertical 출시 = fork tree)로만 서술한다. 그런데
"왜 지금 굳이 auditable·replayable 인프라를 먼저 세우나"라는
**외부 동기**는 명시되어 있지 않다.

Glasswing 발표문은 그 외부 동기를 어떻게 프레이밍하는지에 대한
좋은 참고 사례다(능력이 아니라 *거버넌스·타이밍*을 무대 중앙에
놓는 법). 이 메모는 그 구조만 빌리고, JAMES 정직성 문화에 맞게
재단한 결과물을 남긴다.

---

## 2. 위협 모델 — "검증 병목 교차점"

핵심 명제 (honest-framing 준수형):

> 강력한 생성 AI는 **답 생성 비용**을 한계까지 낮춘다. 그 결과
> 다음 병목은 생성이 아니라 **검증·귀속·정정(verification /
> attribution / correction)** 으로 이동한다. 검증 비용이 생성
> 비용을 초과하는 교차점이 오고, 그 비대칭은 *측정 가능하다*
> (token cost / latency cost axis — QVT 5-axis 중 2축).

Glasswing과의 대칭:

| Glasswing | JAMES |
|---|---|
| 값싸고 빠른 **사이버 공격 AI** 보편화 | 값싸고 빠른 **생성 AI**가 출처·감사·정정 불가 주장으로 지식 공간 범람 |
| 진짜 병목 = 탐지 아닌 **패칭** | 진짜 병목 = 생성 아닌 **검증·귀속·정정** |
| 방어자에게 **먼저·통제된 채로** 배포 | local-first · audit · opt-in self-evolution으로 **신뢰 경계 안에서 먼저** 배포 (CLAUDE.md rule 3) |
| 목표: defender의 **영구적 우위** | 목표: "시점 T에 무엇을 알았고 왜 그렇게 답했나"의 **byte-identical replay** = 사후 검증의 영구적 우위 |

"발견 → 패칭" 이동과 "생성 → 검증" 이동이 정확히 대칭이라는 점이
이 프레이밍의 중심축이다.

---

## 3. JAMES 기존 포지셔닝과의 정합

이 프레이밍은 새 주장을 발명하지 않는다. 기존 자산을 *동기로*
재서술할 뿐이다:

- **ARCHITECTURE §1 (Replayable RAG)** — "what an AI can do"가
  과열되는 동안 JAMES는 "그래서 그게 한 말을 누가 검증·정정하나"라는
  직교 질문을 선점. 대비 프레이밍의 자연스러운 본문.
- **T7 Supersede Chain / T2 Contradiction Arbitration** — old fact를
  덮지 않고 보존 = 정정이 *손실 없이* 일어나는 병목 해소 메커니즘.
- **opt-in self-evolution + approver_username 감사** (CLAUDE.md rule 3)
  = "통제된 채로 먼저 배포"의 JAMES판 안전장치.
- **QVT 5-axis (Path Recall / Graded Answer / Abstention F1 +
  Token/Latency Cost)** = 위협 비대칭을 *측정*하는 도구. 이게
  Glasswing이 못 가진 정직성 레버다.

---

## 4. ⚠️ Honest-framing 가드레일 (이 메모의 핵심 제약)

Glasswing 수사를 그대로 복사하면 JAMES 정체성과 충돌한다.

- ❌ "AI 환각이 곧 세상을 망친다" 식 **미검증 위협 인플레이션**
- ❌ 검증 불가능한 영향 규모("N억 명", "M개 발견") 차용
- ✅ "검증 비용 > 생성 비용 교차점이 온다 — 그 비대칭은 *우리
  하니스로* 측정된다" 식, **증거로 뒷받침되는** 위협 설정
- ✅ 모든 공개 가능 주장은 `feedback_finding_size_honest_framing.md`
  통과 + bench/Quality Delta Card 동반

규칙: **이 프레이밍을 외부로 내보내는 모든 문장은, JAMES 내부에서
재현 가능한 측정으로 뒷받침될 수 있을 때만 쓴다.** 그렇지 못한
문장은 "비전(aspiration)"으로 명시 라벨링한다.

---

## 5. 한 줄 프레이밍 (내부 합의용 초안)

> "강력한 생성 AI는 답을 무한히 싸게 만든다. 그래서 다음 병목은
> 생성이 아니라 검증·귀속·정정이다. JAMES는 그 병목이 닥치기 전에,
> 모든 주장에 출처가 있고 모든 추론이 재생 가능하며 모든 오류가
> 보존·정정되는 지식 인프라를 먼저 세운다."

---

## 6. 어디에 반영하나 (후속, 별도 PR)

이 메모 자체는 코드/계약을 바꾸지 않는다. 합의되면 다음 위치에
*동기 서술*로 주입한다 (각각 별도 PR, 해당 라벨):

1. `docs/PLATFORM_READINESS.md §1` — 내부 리스크 옆에 **외부 동기
   (검증 병목)** 한 단락 추가. (`docs` 라벨)
2. `docs/ARCHITECTURE.md §1 Mission` — Replayable RAG를 "곧 올 검증
   병목에 대한 대비"로 1문장 명시. (`architecture` 라벨 — §1 변경이므로)
3. v0.5 도메인 선정 근거 — "기업 내부지식 ontology" 후보를 이 대비
   논리(audit/ownership/correction moat)로 정당화. (v0.5 게이트 후)
4. (선택) 외부 공개용 1페이지 positioning — **별도 결정 필요**.
   honest-framing 재검토 필수. 현 단계 범위 밖.

---

## 7. Open questions (다음 세션 판단)

- 이 프레이밍을 v0.4 closure 서술에 넣을지, v0.5 진입 동기로 미룰지?
- §6-2(ARCHITECTURE §1 변경)는 trust boundary가 아니라 mission
  서술이지만, §1 변경은 관례상 `architecture` 라벨 + PR 필요 —
  분리 PR로 갈지 이 메모와 묶을지?
- "검증 병목" 명제를 실제 측정으로 뒷받침하는 작은 실험
  (생성 vs 검증 token-cost 비대칭 마이크로벤치)을 만들지? — 만들면
  honest-framing 레버가 데이터로 확정된다.
