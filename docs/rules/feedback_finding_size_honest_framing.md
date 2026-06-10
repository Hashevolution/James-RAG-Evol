<!-- Synced from session memory 2026-06-10 (review R2: rules audit-trail check-in). -->
---
name: feedback-finding-size-honest-framing
description: "발견의 크기에 맞게 framing 해야 함. 트리비얼한 것을 \"publishable narrative\" 로 인플레이션 시키지 말 것. 모델-설계 의존적 결과를 \"JAMES 가 발견\" 으로 포장하면 self-deception. 진짜 비-trivial 부분만 강하게 부각."
metadata:
  node_type: memory
  type: feedback
  originSessionId: c47eaf4c-729a-45b2-a903-1825b34fc205
---

# 발견 크기에 맞게 솔직히 framing (2026-06-01)

α-6 Phase 3a 1b 분석 doc 작성 시 사용자가 catch — "capability
amplifier", "inverted-U capability floor" 같은 표현이 실은
**모델 설계상 학습된 능력 차원** 의 재포장이라 트리비얼.

**Why (사용자 지적)**: 모델이 abstention 학습 받았으면 가능, 안
받았으면 불가능 — 이건 SFT/RLHF 문헌 수십 번 말한 트리비얼 관찰.
"JAMES 가 capability floor 를 발견했다" 같은 framing 은 자기 발견의
무게를 부풀리는 self-deception. 실은 Google 의 학습 설계 결과를
관찰한 것에 가깝다.

**Why this trap is dangerous**:
1. publishable narrative 만들고 싶은 욕망이 framing 을 부풀림
2. 트리비얼 부분이 강조되면 진짜 비-trivial 부분 (예: S4 citation
   tier-invariant) 의 신뢰도가 함께 떨어짐 (전체가 over-claimed 느낌)
3. 협업자 / 외부 시청자가 곧 catch 하면 reputation 손상

**How to apply (every analysis / closure doc)**:

1. **Tier 매기기 의무**: 발견 후보마다 ⭐ ~⭐⭐⭐ 등급 + **trivial /
   partial / genuinely novel** 라벨.
   - trivial = 이미 문헌에 있거나 모델 설계 차원 재포장
   - partial = JAMES-specific 측면 있으나 일반적 패턴의 사례
   - genuinely novel = JAMES architectural 주장 (모델 가족 / 크기
     무관)

2. **"capability amplifier" 류 표현 금지** — 모델이 학습된 능력에
   의존하는 layer 의 효과를 "JAMES 가 발견한 mechanism" 처럼 포장
   금지. 대신 "operational routing rule" / "deployment cost data" 로
   직설.

3. **S4 citation 류는 강하게 부각 가능** — 27× 모델 크기 차에서
   tier-invariant path Δ 는 진짜 architectural 주장. 외부 graph
   pipeline 이 모델 학습 무관하게 effect 만드는 결과.

4. **"disruption mode" 류는 partial 격** — JAMES 가 약-capability 를
   깨뜨림은 JAMES-specific failure mode 지만, "약 신호 + amplifier
   = 노이즈 증폭" 의 일반 패턴 사례. 운영 규칙으로 정리.

5. **closure doc 톤 가라앉히기** — "큰 발견" / "publishable
   surprise" 보다 **"운영 규칙 데이터 수집 + 1 universal-law
   candidate"** 로 정렬. Phase 2 의 "REVERSES tier-gated hypothesis"
   톤도 사실은 over-claim 일 수 있음.

**Pattern this fits**: [[feedback_jameses_positioning_replayable_rag]]
정정 2026-05-31 ("Replayable RAG 단일 framing 금지") + [[feedback_intent_vehicle_gap_collective_archival]] (vehicle vs claim 정합) +
[[feedback_build_dont_broadcast]] 의 연속선. 사용자가 일관되게
**framing 정확도 > 마케팅 임팩트** 를 우선시. self-broadcast 톤이
한 줄이라도 들어가면 catch.

**즉시 적용 (α-6 Phase 3a)**:
- 이미 commit 된 1b 분석 doc (`alpha-6-phase-3a-gemma3-1b-analysis-20260601.md`) 의 §4/§5/§7 어휘 정정 필요 (closure 시점)
- 12b/27b 분석 doc 은 처음부터 솔직 tier 매기기로 쓰기
- recovery curve doc 은 "trivial / partial / novel" 등급 표 포함
- closure PR description 의 publishable narrative 는 S4 universal 만
  강조 + S5/S6 는 "routing rule data" 로 분류

**Don't apply where**: 측정 결과 자체의 데이터 정확성 (숫자, 통계
유의성, 측정 가설 검증). 솔직 framing 은 **결과의 해석 / 톤** 에
적용; 결과의 사실 자체는 변함없음.
