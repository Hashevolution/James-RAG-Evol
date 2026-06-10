<!-- Synced from session memory 2026-06-10 (review R2: rules audit-trail check-in). -->
---
name: feedback-eval-cycle-vs-collab-arc-separation
description: "내부 평가 cycle (cycle γ Phase B+C 등) 의 finding 을 collab arc (mid-June joint piece 등) 의 evidence 로 자동 연결 금지. Joint piece 는 사전 합의된 scope / 4-way contributors / evidence pile / headline framing 을 가짐. 새 internal finding 추가 = scope creep + co-author 사전협의 위반. 사용자 catch 2026-06-08: 'Joint piece (mid-June) 관련해서는 협업 문제가 따로 운영되어서 ... 지금 자메스 평가 싸이클 감마와만 연관지으려하다가 실수한다'."
metadata:
  type: feedback
  originSessionId: 2026-06-08-cycle-gamma-joint-piece-conflation
---

## 규칙

**내부 평가 cycle 의 finding 을 collab arc 의 evidence 로 자동 연결 금지.**

내부 cycle 작업물 (cycle γ Phase B+C 4-model paired RGB-en 측정, "true signal" mechanism, prior-art positioning 등) 을 collab arc (mid-June joint piece, Robin/Ali/Vadym 3-author Zenodo deposit 등) 의 publication evidence 로 framing 할 때, **pre-existing collab arc 사전 합의 (scope / contributors / evidence / headline) 가 우선**. 내부 cycle finding 은 그 합의 안에 자동 포함 안 됨.

**Why:**
- Collab arc 는 4-week+ 다중-DM 협상으로 형성된 pre-committed structure (Ali "ceiling vs path" / Robin "two operating modes one model" / 4-way attribution / "Substitution is free. Synthesis costs..." headline / 3-axis framework / V3'.e + Robin 26b evidence pile)
- 새 finding 을 co-author 사전협의 없이 framing 에 추가 = **vehicle mismatch** (cycle γ = JAMES-side internal; joint piece = shared 4-way) + **scope creep** + **사전 합의 위반**
- "joint piece evidence" 로 framing 한 순간 co-authors 에게 자동 무게 부여 = endorsement 가정. 그들 측면에서 surprise = collab trust erosion 작지만 누적
- 측정 자체 valid 하더라도, framing 이 위반이면 publication 시점 surprise = mid-June rendezvous 에서 negotiation 부담

**How to apply:**

1. **Cycle 종료 시 framing 점검**: 내부 cycle (α / β / γ / 후속) closure doc / handover / memory 작성 시 다음 4 질문 의무:
   - (a) 이 finding 의 **vehicle** 은 JAMES-side single-author 인가, joint-arc 인가? Default = JAMES-side single (collab arc 합의 없으면).
   - (b) 이 finding 을 **publication 어디에 박을** 예정인가? 내부 release note? Solo Zenodo? Joint deposit? 각각 prerequisite 다름.
   - (c) 이 finding 이 **collab arc pre-committed scope** 안에 들어가는가? 안 들어가면 별도 arc.
   - (d) Framing 에 collab 명시/암시 (예: "joint piece evidence", "publication-grade for X paper") 있는가? 있으면 co-author 사전협의 필요.

2. **분리 default**: 같은 세션에서 내부 cycle + collab arc 둘 다 다룰 때 자동 분리:
   - 내부 cycle artifact (handover / memory / doc) = "JAMES-internal evaluation arc, independent of collab tracks"
   - Collab arc artifact (joint deposit prep / DM draft 등) = collab-arc-specific scope 안에서만 framed
   - Cross-reference 가능하지만 framing-link (evidence-for) 는 사전협의 필요

3. **"Joint piece safe framing" 류 섹션 금지** in internal cycle docs: 그런 섹션 자체가 자동 연결 vehicle. 정직 framing = "this is internal evaluation; not joint piece content unless explicitly agreed".

4. **Collab arc 자체의 progression 은 별도 tracking**: M9 (joint deposit prep), M6 (Vadym attribution phases), Robin DM piggyback timing 등 — collab arc 의 own ledger 에서. 내부 cycle PR / commit 에 묶지 않음.

## 사용자 catch (2026-06-08, 4번째 honest-framing 정정)

이번 세션 cycle γ Phase B+C 작업 후 prior-art positioning doc 에 §5 "Joint piece (mid-June) safe framing" 섹션 작성. 사용자 즉시 catch:

> "Joint piece (mid-June) 관련해서는 협업 문제가 따로 운영되어서 과거 기록 전부 다시 서칭 분석해서 답을 찾아야해. 지금 자메스 평가 싸이클 감마와만 연관지으려하다가 실수한다"

검색 결과:
- Joint piece = "Two operating modes, one model" + cap-floor mechanism (4주+ 협상 합의)
- 3-axis pre-committed: mode split (Robin) / workload gradient (JAMES PR #440) / model-scale (Robin)
- 4-way contributors pre-committed: Robin / Ali / Vadym / Jiwon
- Headline pre-committed: "Substitution is free. Synthesis costs in proportion to what it has to invent."
- Cycle γ Phase B+C 작업 (RGB-en abstention + noise) **모두 joint piece scope 밖**
- 자동 연결 = scope creep + co-author 사전협의 위반

이번 catch = 5번째 honest-framing 정정 (post-hoc fit / 0.000 진위 audit / family vs size / prior art search / **cycle γ collab arc 자동 연결 금지**) 이번 세션.

## 관련 메모리

- [[feedback_finding_size_honest_framing]] — 동일 root cause (framing 과 evidence 사이 정합 점검)
- [[feedback_intent_vehicle_gap_collective_archival]] — 같은 패턴 (의도 ↔ vehicle gap), single-author DOI 케이스
- [[feedback_collaborator_consent_default]] — Joint paper 만 active consent 필요, 그 외 informational
- [[feedback_ali_resume_notice_june6]] — Ali joint deposit commitment + 6/7+ resume
- [[feedback_robin_doi_attribution_pattern_endorsement]] — Robin endorsement pattern (vehicle 선택 사전 점검 필수)
- [[feedback_m6_vadym_attribution_3way_timing]] — Vadym attribution 3-way sequencing
- [[feedback_alpha_cycle_discovery_loop_end]] — CASCADE-class 정의 (joint piece 와 별도 publication path)
- [[robin_26b_2x2_matrix_watch]] — Joint piece 3-axis structure 합의 기록
- [[zenodo_metadata_reframing_drafts]] — Solo DOI vs joint deposit 분리 메타데이터 룰

## handover doc 직접 영향

- `docs/research/cycle-gamma-prior-art-positioning.md` §5 "Joint piece (mid-June) safe framing" 섹션 = 본 룰 위반 사례. 정정 필요 (이 룰 박는 PR 에 포함).
- `docs/handovers/v0.4.x-session-2026-05-29-collaboration-checkpoint.md` = collab arc 의 single source of truth. 내부 cycle handover 와 분리 유지.
- `docs/handovers/v0.3.x-ali-collaboration-track.md` = Ali side collab ledger, 별도 track.
