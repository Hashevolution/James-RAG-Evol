# STAGE 1 (Memory Loom 5-gate) 선행 특허 검색 결과 — 2026-05-21

> 본 문서는 STAGE 1 (Memory Loom — 5 단계 게이트 기반 메모리 저장 검증) 추가 prior art 검색 결과.
> 검색 일자: 2026-05-21
> 검색 도구: Claude 자동 Agent

---

## 1. 검색 타깃 (STAGE 1 의 5 요소)

| 요소 | 설명 |
|---|---|
| ① | 5 게이트의 specific 순차 적용 (Gate1~5 순서 고정) |
| ② | 결정론적 수치 캡 (0.75 conf / 3 writes / 100 window / 0.3 diff) |
| ③ | (entity_id, relation_type) base-key 충돌 + confidence diff 트리거 |
| ④ | collections.deque(maxlen=100) 기반 dedup |
| ⑤ | per-gate distinct audit log step (gate1_fail ~ gate5_conf_conflict) |

---

## 2. 검색 결과 요약

### 위험 등급 분포

| 등급 | 건수 | 사례 |
|---|---|---|
| 🔴 거의 동일 | **0건** | — |
| 🟠 상당 겹침 | **~7건** ⚠️ | Mem0, A-MAC, Zep, ContextGuard, Cognee, Claude Dreams |
| 🟡 일부 겹침 | ~10건 | LangChain, mem0 docs, SSGM 등 |
| 🟢 무관 | ~4건 | LangChain BaseMemory, OpenAI Memory FAQ |

### 가장 가까운 후보들

#### 🟠 Mem0 (arXiv 2504.19413, 2025-04)
- 특징: 2-phase pipeline — extraction → conflict detection → graph update
- LLM-driven Delete/NOOP decisions
- 차별점: **LLM judgment vs deterministic rules** (STAGE 1 은 결정론적)
- 위험: 매우 가까움. STAGE 1 의 conflict detection 과 패턴 유사.

#### 🟠 A-MAC (arXiv 2603.04549, 2026-03 추정)
- 제목: Adaptive Memory Admission Control for LLM Agents
- 특징: 5 factors (future utility, factual confidence, semantic novelty, temporal recency, content type)
- 차별점: **learned weighting vs deterministic ordering** (STAGE 1 은 고정 5 게이트 순서)
- 위험: "5 factors" terminology 유사. mechanism 명확 다름.

#### 🟠 ContextGuard / "RAG's Next Frontier" (Medium, 2026-02)
- 특징: Compiler-style pipeline + "Gate" component + reason codes
- 차별점: hard admission control with reason codes (~= STAGE 1 의 audit log step)
- 위험: gating + reason codes 패턴 유사

#### 🟠 Cognee (AI Memory with Ontologies)
- 특징: Entity recognition + SHACL/OWL validation (ontology validity)
- 차별점: Gate 2 (ontology_valid) 의 직접 prior art
- 위험: ontology validation gate 단독은 prior art 명확

#### 🟠 Claude Auto Dream/Memory (Anthropic, 2026-02~05)
- 특징: Background "dreaming" merges duplicates + replaces stale entries
- 차별점: offline batch vs online rule-based (STAGE 1 은 실시간)
- 위험: dedup + conflict resolution 개념 유사

---

## 3. 신규성 결론

**STAGE 1 의 개별 게이트 5개는 모두 prior art 존재**. 그러나 **조합 + 결정론적 수치 캡 + per-gate audit naming** 은 prior art 부재.

### Novelty 살아 있는 요소

1. **5 게이트의 specific 고정 순서** (confidence → ontology → write rate → dedup → conflict) — 정확한 순서 prior art 0건
2. **결정론적 수치 캡** (0.75 / 3 / 100 / 0.3) — A-MAC 은 learned, Mem0 는 LLM 판단 → 결정론적 캡 0건
3. **`MAX_WRITES_PER_SESSION = 3` 의 hard cap** — 어디서도 prior art 없음
4. **collections.deque(maxlen=100) 기반 dedup** — 자료구조 specific
5. **per-gate distinct step names** (gate1_fail ~ gate5_conf_conflict) — Springdrift 도 trace 만, 게이트별 별도 step naming 0건

---

## 4. 권고

⚠️ **narrow 청구 후 출원 진행** — 단, STAGE 1A 보다 narrow 폭이 좁아짐

### 청구항 narrowing 전략

청구항 1 의 핵심: **전체 5 게이트 시퀀스 + 정확한 수치 + 결정론적 (no LLM)** 모두 통합 청구.

```
청구항 1 (narrow):
"대화형 인공지능 시스템에서 LLM 추출 결과를 장기 기억에 저장할지 결정하는 방법으로서,
 LLM 추론을 호출하지 않는 결정론적 규칙으로 다음 5 게이트를 정확한 순서로 적용:
 (a) Gate 1 — confidence ≥ 임계값 (default 0.75, [0,1] 범위);
 (b) Gate 2 — ontology_valid == True;
 (c) Gate 3 — 현재 세션의 저장 횟수 < 한도 (default 3, 정수);
 (d) Gate 4 — (entity_id, relation_type, tail_id) 트리플 키가 최근 N (default 100)
     개의 저장 이력 deque 에 존재 안 함;
 (e) Gate 5 — (entity_id, relation_type) 키의 기존 항목 중 tail 불일치 또는
     |confidence 차이| > 임계값 (default 0.3) 이면 거부;
 각 게이트 거부는 distinct step 명 (gate1_fail, gate2_fail, gate3_limit,
 gate4_dedup, gate5_conflict, gate5_conf_conflict) 으로 audit log 기록"
```

→ 모든 specific 디테일 + 결정론적 (anti-Mem0) 명시.

### 강조할 차별점 (vs Mem0)

| 항목 | STAGE 1 | Mem0 (2025-04) |
|---|---|---|
| 의사결정 주체 | 결정론적 규칙 | LLM (Delete/NOOP) |
| 게이트 수 | 5 (고정 순서) | 2 (extraction → conflict) |
| 수치 캡 | 하드 (0.75/3/100/0.3) | 학습/LLM 동적 |
| 세션 쓰기율 | 하드 cap 3 | 없음 (또는 per-round) |
| Dedup 메커니즘 | deque(100) | 임베딩 유사도 |
| Audit log | per-gate distinct steps | 일반 trace |
| Latency | 매우 낮음 (no LLM) | LLM call 필요 |
| Reproducibility | 완전 | LLM 비결정성 |

### 강조할 차별점 (vs Claude Memory / ChatGPT Memory)

- ChatGPT/Claude memory: 폐쇄적 (public spec 없음), background batch processing
- STAGE 1: open spec, online rule-based, MIT 라이선스

---

## 5. 배경기술 인용 권장

| 인용 | 차별 표현 |
|---|---|
| US20180060733A1 (Google, 2018) | "단일 confidence threshold 와 달리, 본 발명은 5 게이트 순차..." |
| US12387050 (2025-08) | "multi-threshold LLM 과 달리, 본 발명은 결정론적 5 게이트..." |
| arXiv 2504.19413 Mem0 (2025-04) | "LLM-driven Delete/NOOP 과 달리, 본 발명은 결정론적 룰..." |
| arXiv 2603.04549 A-MAC (2026-03) | "learned 5 factors 와 달리, 본 발명은 hardcoded specific caps..." |
| arXiv 2603.15994 Selective Memory (2026-03) | "단일 학습 임계값과 달리, 본 발명은 5 결정론적 게이트..." |
| Cognee ontology memory | "ontology validation 단독 게이트와 달리, 본 발명은 ontology 를 5 게이트 중 1 단계..." |

---

## 6. 등록 가능성 추정

- Narrow claim (위 안): **45~55%**
- Broad concept claim (without numerical caps): 25~35% (Mem0 anticipation 위험)
- Defensive publication 효과: ⭐⭐⭐ (이미 MIT + GitHub 로 확보)

---

## 7. STAGE 1 vs STAGE 1A 비교

| 항목 | STAGE 1 | STAGE 1A |
|---|---|---|
| 🟠 prior art | 7건 ⚠️ | 1건 ✅ |
| 결정 영역 활성도 | 매우 활발 (Mem0, Letta, Zep 등) | 비교적 niche |
| Specific 메커니즘 새로움 | 5 게이트 순서 + 결정론적 | stem matching + asymmetric |
| Narrow claim 등록 가능성 | 45~55% | 55~65% |
| 출원 가치 / 비용 효율 | 보통 | **우수** |

---

## 8. 출원 결정

| 시나리오 | 결정 |
|---|---|
| **시나리오 1: STAGE 1A 만 추가 출원** | ⭐⭐⭐ 권장 (1A 가 prior art 깨끗) |
| 시나리오 2: STAGE 1 + 1A 모두 | 가능 (사업화 IP 자산 강화 시) |
| 시나리오 3: STAGE 1 만 추가 | 비추 (1A 가 더 클리어한데 굳이) |
| 시나리오 4: STAGE 1B 만 (현 상태) | 비용 절약 최우선 시 |

### 권고: 시나리오 1 (STAGE 1A 추가)

이유:
1. STAGE 1A 가 prior art 환경 명확히 깨끗 (7건 vs 1건)
2. STAGE 1 의 Mem0 와의 거리 좁음 → 정식 전환 시 거절 위험 ↑
3. 비용 절약 ₩13,800
4. STAGE 1 의 결정론적 메커니즘은 MIT + GitHub 공개로 이미 defensive

---

**End of prior-art-1.md**
