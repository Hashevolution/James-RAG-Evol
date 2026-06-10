<!-- Synced from session memory 2026-06-10 (review R2: rules audit-trail check-in). -->
---
name: feedback-n1-verdict-inflation-n3-caught
description: "α-8 cycle 2026-06-02→03 — n=1 single-shot 결과 (graded Δ +0.037, abst_f1 Δ +0.137) 가 ⭐⭐ adopt 임계 통과한 듯 보였으나 n=3 paired confirm (4.7h compute) 가 noise band 0.060 / 0.418 안 으로 collapse 시킴. n=3 paired rule 이 정확히 over-claim 막는 process. honest framing rule 의 실증 1차 사례."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 2ccdb644-a11f-400f-ba26-5fabce1c65bd
---

# n=1 verdict inflation → n=3 paired catch (α-8, 2026-06-02→03)

n=1 single-shot 결과가 verdict threshold 통과한 듯 보일 때, n=3 paired
confirm 이 정확히 over-claim 을 잡아냄. α-8 cycle 이 첫 실증 사례.

## Why

α-8 Phase C 진행 순서:
1. **n=1 multihop_rag** (3.6h): graded Δ +0.037 (= ⭐⭐ 임계 통과), abst_f1
   Δ +0.137 (FN 16→11 = 31% reduction), R1 audit 으로 5개 absence-language
   answer 확인. Verdict = ⭐⭐ adopt 결론 도출.
2. **n=3 paired confirm** (4.7h): same fixture, same model, same code.
   결과:
   - graded median Δ +0.007 (noise band ±0.060) → ⭐ operational only
   - abst_f1 median Δ +0.058 (noise band ±0.418, **1/7 수준**)
   - 양쪽 cell 의 individual runs spread 가 거대: graph 의 abst_f1 단일
     runs 0.216/0.455/0.634, range 0.418
3. n=1 보였던 "+0.137 = strong" 은 1 run 의 운 좋은 outlier 였음.

### Per-run variance 가 왜 이렇게 큰가
- multihop_rag fixture 100 queries 중 25 만 null_query (abst 측정 모수)
- LLM (gemma4:e4b) 의 default temperature → null query 답변에 stochastic
  refusal/hallucination 분기 (run 마다 4-21 hallucinations)
- abst_f1 = TP / (TP + 0.5(FP+FN)) = 25 query 분모로 noise sensitive

### Aggregate level 에서는 direction 일치
n=3 paired 의 confusion matrix 합산 (300 queries):
- graph: FN=48, TP=27
- ontology: FN=42, TP=33
- ΔFN=−6 (12.5% reduction), ΔTP=+6, ΔFP=−9, ΔTN=+9
- 4 축 모두 design intent 일치하나 per-run noise 가 매우 큼 → median Δ 가
  noise 안

즉 **direction 은 진짜, magnitude 측정은 n=3 도 부족**. 더 큰 N (n=5+) 또는
순수 null fixture 가 필요.

## How to apply

**룰**: n=1 결과가 verdict threshold 근접/통과 시, **n=3 paired confirm
완료 전까지 ⭐⭐ adopt claim 잠정으로만 사용. memory / closure doc /
ARCHITECTURE 등재 / 협업자 share 모두 n=3 이후로 보류.**

- 본 케이스에서 n=1 직후 작성된 memory `project_alpha_8_closure_state` 가
  ⭐⭐ 톤으로 lock-in 됨 → n=3 후 downgrade rewrite 필요했음 (작업 1h+
  추가)
- 본 케이스에서 n=1 직후 Robin DM 답장 옵션 C (α-8 추가 share) 권장 →
  사용자 catch 로 보류됨. n=3 downgrade 후 retrospectively 옳음
  ([[feedback_dm_collab_response_eagerness_trap]] 강화 evidence)
- 본 케이스에서 n=1 직후 ARCHITECTURE.md §5.7.12 draft 작성 → n=3 후
  defer 결정. draft 폐기 안 함, "future retry base" 로 보존

**Process correctness 측면**: n=3 paired rule 자체가 정확히 작동.
[[feedback_finding_size_honest_framing]] 룰 의 실증. n=1 → ⭐⭐ →
n=3 → ⭐ downgrade 가 보여주는 건 **honest measurement infrastructure
가 wrong-overclaim 을 system-level 에서 막음**.

### 운영 체크리스트 (n=1 → n=3 transition 시점에)

1. ✅ n=1 결과 보고 시 "잠정 (n=1)" 명시
2. ✅ memory 작성은 n=3 후로 미루거나 frontmatter description 에 "n=1
   provisional" 명시
3. ✅ 협업자 share / DM 은 n=3 후 (혹은 n=1 매우 크면 디자인 메모 §4.1
   tree 의 noise band 보다 훨씬 위일 때만)
4. ✅ ARCHITECTURE.md 등 정식 doc 등재는 n=3 confirm 후
5. ✅ "5 hallucinations averted = 31% reduction" 같은 % 클레임은
   aggregate (n=3) 기준만 사용

## n=1 over-claim 의 signature 신호

n=1 결과 평가 시 다음 중 ≥2 충족 시 "over-claim 위험" 빨간불:
- graded Δ 가 임계 ± 절반 안 (e.g., +0.020 ~ +0.040 = ±0.010 from +0.030)
- abst_f1 Δ 가 fixture 의 historic noise band 보다 1/4 작음 (multihop
  abst_f1 historic noise = 0.1+ 였으므로 Δ +0.137 가 noise 비대비 1.4×
  = 마진 작음)
- TP/FP/FN/TN 의 단일 cell sum 이 ≤50 (multihop = 25 null × 1 run = 25
  TP+FN, FP+TN ~ 75) — 작은 분모 = noise 민감
- 다른 측정 axis 들이 동시에 noise-band 안

## 관련

- [[project_alpha_8_closure_state]] — 본 사례의 verdict downgrade
- [[feedback_finding_size_honest_framing]] — 발견 크기 honest framing
  primary rule, 본 메모는 그것의 measurement-side 운영 룰
- [[feedback_dm_collab_response_eagerness_trap]] — n=1 직후 share 본능
  trap 의 자매 룰
- [[alpha_5_multihop_rag_reset]] — n=1 vs n=3 paired design 결정 origin
- [[feedback_alpha6_findings_mostly_known_to_literature]] — α-6 finding
  tier 평가 룰
- design memo §4.1 verdict tree — `graded Δ ≥ +0.030` 임계 정의
