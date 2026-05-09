# [임시명세서 초안] Umbrella System + Memory Loom 결합 출원

> 본 문서는 STAGE 1(가장 우선) 임시명세서 작성을 위한 skeleton입니다.
> KIPRIS 전자출원 시 본 문서를 기반으로 PDF·hwp로 전환하여 첨부하십시오.
> 작성 시 [TODO] 마커를 모두 제거·채워주세요.

---

## 발명의 명칭
**로컬 환경에서 안전한 지식 기반 추론 시스템 및 메모리 오염 방지 방법**
(영문: System for Locally-Secure Knowledge-Based Inference with Multi-Gate Memory Validation)

## 출원인
[TODO: 성명 / 주소 / 주민번호 또는 외국인등록번호]

## 발명자
[TODO: 성명 / 주소]

## 공지예외 주장
- 공개일자: 2026-05-05
- 공개매체: GitHub public repository (https://github.com/hashevolution/james-rag-evol)
- 공개주체: 발명자 본인
- 증빙: `docs/patent/disclosure_log.txt`

---

## 1. 기술 분야

본 발명은 인공지능 기반 자연어 질의응답 시스템에 관한 것으로, 보다 구체적으로는 외부 LLM 서비스 호출을 최소화하면서 지식 그래프와 메모리 검증 로직을 결합하여 로컬 환경에서 안전하게 동작하는 추론 시스템 및 그 방법에 관한 것이다.

## 2. 배경 기술

### 2.1 기존 RAG 시스템의 한계
- 단순 벡터 검색만으로는 다중-홉 추론이 어려움
- LLM이 무비판적으로 사실을 메모리에 기록하여 환각·오염이 누적됨
- 클라우드 LLM 호출이 응답 시간·비용·프라이버시 문제를 야기함

### 2.2 그래프 기반 RAG의 한계
- Microsoft GraphRAG 등은 그래프 구축 시 LLM 호출이 과다 (비용 高)
- 메모리에 대한 검증 게이트가 단순(confidence threshold만 적용)
- 입력·검색·출력 단계 간 권한 일관성 검증 부재

## 3. 해결하고자 하는 과제

1. LLM 호출 없이도 키워드를 정확히 확장하여 검색 품질을 유지하는 방법
2. 그래프 메모리에 사실을 기록할 때 다단계 게이트로 오염을 방지하는 방법
3. 사용자 역할에 따라 입력·출력 단계 모두에서 권한 일관성을 검증하는 방법
4. 위 모든 모듈이 협력하는 단일 통합 추론 시스템

## 4. 과제의 해결 수단

### 4.1 시스템 구성 (도면 1 참조)

본 시스템은 다음 7개 모듈을 포함한다:

```
[사용자 질의]
   ↓
(1) 엔티티 추출 모듈 (JEPA-Lite)
    - 사전 + 토큰화 기반 키워드 확장
    - LLM 호출 금지
    - 50 토큰 hard cap
    - 3 초 timeout
   ↓
(2) Hybrid 검색 모듈
    - Vector 60% + BM25 20% + Keyword 20%
   ↓
(3) Ontology 가중 그래프 traversal 모듈
    - DFS 최대 깊이 4
    - score = ontology_weight × confidence
   ↓
(4) Memory Loom 검증 모듈 (도면 2 상세)
    - 5개 순차 게이트
   ↓
(5) Feedback Shadow 적응 모듈
    - 7-type signal × decay 0.9 × threshold ±2.0
   ↓
(6) 2-stage 보안 모듈
    - 입력 prompt-injection 검출
    - 출력 PII / entity 마스킹
    - cross-stage ABAC 검증
   ↓
(7) Character Profile 모듈
    - trait pair sum-invariant rebalance
   ↓
[로컬 LLM 응답 생성]
```

### 4.2 Memory Loom 5-gate 상세 (도면 2 참조)

후보 fact `(head, relation, tail, confidence, ontology_valid)` 가 입력되면:

| Gate | 조건 | 거부 시 사유 코드 |
|------|------|--------------------|
| 1 | `confidence ≥ 0.75` | `low_confidence` |
| 2 | `ontology_valid == True` | `ontology_violation` |
| 3 | `session_write_count ≤ 3` | `rate_limited` |
| 4 | `triple_key NOT IN window(100)` | `duplicate` |
| 5 | `same(head, relation) → tail_diff OR confidence_diff > 0.3 → reject` | `conflict` |

5개 게이트를 모두 통과한 사실만 그래프에 기록되며, 각 거부는 audit log로 보존된다.

상세 구현: [TODO: `core/memory_loom.py:80-149` 인용 코드 첨부]

### 4.3 데이터 흐름 예시

[TODO: 구체적 입력/출력 example 1~2개 작성. 예: "삼성전자가 LG와 합병한다는 fact가 입력되면 Gate 5에서 confidence=0.42로 기존 fact(confidence=0.91)와 충돌하여 거부된다."]

---

## 5. 청구항

### 청구항 1 (Independent — 시스템)
로컬 환경에서 안전하게 동작하는 지식 기반 추론 시스템으로서,
- (a) 사전과 토큰화 기반으로 LLM 호출 없이 사용자 질의로부터 키워드를 확장하되, 50 토큰 이하의 hard cap 및 3 초 이내 timeout을 적용하는 엔티티 추출 모듈;
- (b) 벡터 유사도 60%, BM25 20%, 키워드 매칭 20%의 가중치로 hybrid score를 산출하는 검색 모듈;
- (c) entity-relation 그래프에서 ontology weight × confidence를 곱한 score로 최대 깊이 4의 DFS 확장을 수행하는 그래프 traversal 모듈;
- (d) 후보 사실에 대해 (i) confidence ≥ 0.75, (ii) ontology 일관성, (iii) 세션당 쓰기 ≤ 3, (iv) 직전 100건 중복 검사, (v) 동일 head·relation 쌍에서 tail 차이 또는 confidence 차이 > 0.3 거부 — 의 5개 게이트를 순차 적용하여 통과한 사실만 그래프에 기록하는 메모리 검증 모듈;
- (e) N개 사전 정의된 피드백 유형을 0.9 decay 및 ±2.0 threshold로 누적하는 적응 모듈;
- (f) 입력 prompt-injection 검출, 출력 PII / 엔티티 마스킹, 입력→검색→출력 cross-stage ABAC 검증을 수행하는 2-stage 보안 모듈;
- (g) trait pair 합 = 1.0 invariant을 유지하며 한 trait 변경 시 opposing trait를 자동 재조정하는 캐릭터 프로파일 모듈;
을 포함하는 시스템.

### 청구항 2 (Independent — 방법)
청구항 1의 시스템을 이용한 추론 방법으로서,
1. 사용자 질의를 수신하는 단계;
2. 모듈 (a)로 키워드를 확장하는 단계;
3. 모듈 (b)로 후보 문서를 검색하는 단계;
4. 모듈 (c)로 그래프를 확장하여 컨텍스트를 수집하는 단계;
5. 모듈 (d)로 신규 메모리 후보를 검증·기록하는 단계;
6. 모듈 (f)로 출력 응답을 마스킹·검증하는 단계;
7. 로컬 LLM으로 최종 응답을 생성하는 단계;
를 포함하는 방법.

### 청구항 3~10 (Dependent — Memory Loom 세부)
- 청구항 3: Gate 1의 confidence threshold가 0.75인 청구항 1의 시스템.
- 청구항 4: Gate 3의 세션당 쓰기 한도가 3회인 청구항 1의 시스템.
- 청구항 5: Gate 4의 중복 윈도우가 100인 청구항 1의 시스템.
- 청구항 6: Gate 5의 confidence 차이 threshold가 0.3인 청구항 1의 시스템.
- 청구항 7: 게이트별 거부 사유를 audit log에 기록하는 청구항 1의 시스템.
- 청구항 8: triple_key가 (normalize(head), normalize(relation), normalize(tail))의 hash인 청구항 1의 시스템.
- 청구항 9: ontology weight가 [TODO: 가중치 매핑 표 첨부] 인 청구항 1의 시스템.
- 청구항 10: feedback 유형 N=7이며 각 유형이 [-1.0, +1.0] 가중치를 갖는 청구항 1의 시스템.

[TODO: 종속항을 더 추가하여 보호 범위를 두텁게 해도 좋습니다. 임시명세서는 청구항 형식 강제 없으므로 자유 서술도 가능.]

---

## 6. 도면

### 도면 1 — 시스템 전체 아키텍처
[TODO: 박스+화살표 다이어그램. draw.io / excalidraw / mermaid 모두 가능. PDF 변환 필수.]

### 도면 2 — Memory Loom 5게이트 흐름도
[TODO: 게이트 1~5 순차 + 거부 분기 + accept 분기]

---

## 7. 도면의 간단한 설명

- 도면 1: 본 발명에 따른 추론 시스템의 전체 구성도
- 도면 2: Memory Loom 5게이트 검증 흐름도

## 8. 부호의 설명

[TODO: 도면에 사용된 부호와 명칭 매핑. 예: 100 - 엔티티 추출 모듈, 110 - 사전 저장소, ...]

---

## 9. 발명을 실시하기 위한 구체적인 내용

### 9.1 모듈 (a) — JEPA-Lite 엔티티 추출
[TODO: `core/jepa_adapter.py` 핵심 코드 인용. 50 token hard cap 부분, 3초 timeout 부분 명시.]

### 9.2 모듈 (d) — Memory Loom
[TODO: `core/memory_loom.py:80-149` 핵심 코드 인용. 5개 게이트 각 구현부 명시.]

### 9.3 그 외 모듈
[TODO: (b)(c)(e)(f)(g) 각각 코드 인용 또는 의사코드.]

---

## 10. 산업상 이용 가능성

본 발명은 기업·공공기관 내부의 폐쇄망 챗봇, 의료·법률 상담, 군용 정보 시스템 등 외부 LLM 호출이 제한되거나 데이터 유출 위험이 큰 환경에서 안전한 지식 기반 추론을 제공하는 데에 산업상 이용 가능하다.

---

## 11. 명세서 작성 체크리스트

- [ ] 모든 [TODO] 제거
- [ ] 도면 2매 PDF 첨부
- [ ] 출원인 정보 기재
- [ ] 공지예외 주장서 첨부
- [ ] disclosure_log.txt 첨부
- [ ] KIPRIS 전자출원 → 출원번호 수령
- [ ] 출원확인서 PDF 보관 → `docs/patent/stage1-receipt.pdf`
