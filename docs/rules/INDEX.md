# docs/rules/ — 측정·framing 룰 audit-trail

> **Origin**: 2026-06-09 외부 project-direction review 권고 R2.
> CLAUDE.md 가 지정한 의무-reading 룰들이 session memory 에만 존재
> (repo 부재 = bus factor 1 + auditability 자기모순) → repo 에
> selective sync. **Source of truth = session memory** (운영자 로컬);
> 이 디렉토리는 repo-side audit trail 사본이다. 룰이 갱신되면 sync
> 날짜를 파일 상단 주석에 업데이트.

## 9 user catches (honest-framing 정정 시리즈)

| # | 파일 | 한 줄 |
|---|---|---|
| 5th | [feedback_eval_cycle_vs_collab_arc_separation.md](feedback_eval_cycle_vs_collab_arc_separation.md) | 내부 평가 cycle finding 을 collab arc evidence 로 자동 연결 금지 (4-질문 점검) |
| 6th | [feedback_single_axis_ablation_misframing.md](feedback_single_axis_ablation_misframing.md) | 단일-axis ablation → "structural defect" framing 금지, multi-axis Pareto prerequisite |
| 7th | [feedback_path_d_james_not_specialty_verifier.md](feedback_path_d_james_not_specialty_verifier.md) | JAMES ≠ HALT-RAG specialty verifier — evidence 없는 단일 axis 추격 거부 (9th 로 conditional 화) |
| 8th | [feedback_d2_v2_softener_bilingual_regression.md](feedback_d2_v2_softener_bilingual_regression.md) | JAMES ≠ Korean-only — softener 영어 확장은 별도 design 필요 (V2 negative evidence) |
| 9th | [feedback_james_identity_measurement_driven.md](feedback_james_identity_measurement_driven.md) | JAMES 정체성 = measurement-driven discovery (1-8 의 mirror correction, framing equilibrium) |

(1st–4th catches — post-hoc fit / 0.000 진위 / family vs size / prior art — 는
`docs/research/cycle-gamma-prior-art-positioning.md` 및
`docs/handovers/v0.4-cycle-gamma-phase-c-4model-true-signal-2026-06-08.md` 에 기록.)

## 측정 방법론 core rules

| 적용 시점 | 파일 | 한 줄 |
|---|---|---|
| Plan 짜기 전 | [feedback_methodological_chain_before_plan.md](feedback_methodological_chain_before_plan.md) | 4-질문 의무 (verdict Q / diagnostic Q / fixture role 라벨링 / logical 순서) |
| Verdict 해석 전 | [feedback_fixture_fitness_before_verdict.md](feedback_fixture_fitness_before_verdict.md) | fixture 가 verdict-grade 인가 먼저 확인 (n=1 over-read 금지) |
| 비교 분석 전 | [feedback_evidence_grounded_validity_check.md](feedback_evidence_grounded_validity_check.md) | evidence 전달 동등성 + 학습-지식-leak 분리 의무 |
| n=1 → n=3 전 | [feedback_n1_verdict_inflation_n3_caught.md](feedback_n1_verdict_inflation_n3_caught.md) | n=3 paired 전 ⭐⭐ claim / memory / share 보류 |
| 결과 받기 직전 | [feedback_oracle_phrase_artifacts.md](feedback_oracle_phrase_artifacts.md) | 4-step rule + 4-bucket 진단 (oracle matcher / wiring / layer-intent) |
| Cell verdict 시 | [mechanism_layer_intent_axis_alignment.md](mechanism_layer_intent_axis_alignment.md) | per-layer design-intent axis 매칭 (uniform 5-axis 금지) + 측정 prerequisite |
| 새 oracle/측정 진입 시 | [feedback_self_evaluation_trap.md](feedback_self_evaluation_trap.md) | 자기 fixture + 자기 채점 = ⭐ trivial — 외부 표준 벤치 path 우선 |
| Closure framing 시 | [feedback_finding_size_honest_framing.md](feedback_finding_size_honest_framing.md) | 발견마다 trivial / partial / novel tier 매기기 의무 |
| 새 fix 평가 시 | [feedback_mother_platform_6_principles.md](feedback_mother_platform_6_principles.md) | Default vs Option 분리 + multi-axis Default 평가 (5-질문) |

## 사용법

- 새 measurement cycle 진입 시: **측정 방법론 core rules 전부 의무 reading.**
- "JAMES 부족 / defect / default 변경" framing 시작 전: 6th + 7th + 9th catch reading.
- Pre-registration (R5): `docs/research/cycle-gamma-phase-c2-preregistration-2026-06-10.md` 가 worked example.
