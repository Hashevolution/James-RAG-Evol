# STAGE 1B 선행 특허 검색 결과

> 본 문서는 `stage1b-cascade-spec-skeleton.md` 출원 전 선행 특허 검색 결과를 기록한다.
> 작성일: 2026-05-11
> 검색 대상: Provenance Cascade + Log-sum Confidence (B 후보)

---

## 1. 검색 타깃 (요소 분해)

STAGE 1B의 결합 발명:

| 요소 | 설명 |
|---|---|
| ① | Knowledge graph relation이 **여러 source**를 갖는 구조 (sources array) |
| ② | Confidence를 **확률 OR / log-sum (`1 − Π(1−w)`)** 으로 도출 |
| ③ | 출처 문서 삭제 시 **automatic cascade** (source drop → recompute → orphan sweep) |
| ④ | **Manual 편집의 cascade 면역** (role 필드, doc_id=null) |
| ⑤ | 문서 수정 시 **(s, p, o) triple 단위 diff cascade** |
| ⑥ | **audit log + monotonicity 수학 보장** |

⚠️ 개별 요소는 선행기술이 있을 수 있음. **5~6요소 결합** 발명임을 보이는 게 핵심.

---

## 2. 검색 사이트 및 키워드

### 2.1 KIPRIS (한국, https://www.kipris.or.kr/)

#### 키워드 셋 A — 핵심 결합

```
1.  지식그래프 출처 cascade
2.  지식그래프 신뢰도 다중출처
3.  관계 출처 가중치 결합
4.  knowledge graph provenance
5.  graph 출처 추적 신뢰도
```

#### 키워드 셋 B — 수학 공식

```
6.  확률 OR 신뢰도
7.  log-sum 신뢰도 그래프
8.  monotone cascade 그래프
```

#### 키워드 셋 C — 도메인

```
9.  RAG 지식그래프 출처
10. LLM 지식그래프 cascade
```

#### 추가 필터
- 출원공개일: 2010-01-01 ~ 2026-05-11
- IPC: G06F16/36, G06N5/02

### 2.2 Google Patents (전 세계, https://patents.google.com/)

#### 검색식 1 — 핵심 결합
```
("knowledge graph" OR "graph database") AND ("provenance" OR "source attribution") AND ("cascade" OR "propagation")
```

#### 검색식 2 — 수학 공식
```
"knowledge graph" AND ("probabilistic OR" OR "noisy-OR" OR "log-sum") AND "confidence"
```

#### 검색식 3 — 삭제 cascade
```
"knowledge graph" AND ("source deletion" OR "document removal") AND ("relation" OR "edge") AND "confidence"
```

#### 검색식 4 — Manual 면역
```
"knowledge graph" AND ("manual edit" OR "human curation") AND ("preserve" OR "immune" OR "protect")
```

#### 검색식 5 — Triple diff
```
"knowledge graph" AND ("triple" OR "RDF") AND ("diff" OR "delta" OR "incremental update")
```

#### 검색식 6~10 보조
```
6.  "RAG" AND "knowledge graph" AND "maintenance"
7.  "fact extraction" AND "confidence" AND "multiple sources"
8.  "ontology" AND "source weight" AND "evidence accumulation"
9.  "Wikidata" AND "confidence" AND "cascade"
10. "GraphRAG" AND "provenance"
```

#### Google Patents 필터
- After: 2010
- Status: Granted + Active
- Country: KR, US, EP, WO, CN, JP
- CPC: G06F16/36, G06F16/2455, G06N5/022, G06N5/04

---

## 3. 발견된 의심 특허

### 3.1 KIPRIS 결과

> 사용자가 직접 검색 후 의심 건 여기에 추가.

#### 후보 K-1: [특허번호, 제목]
- 출원인:
- 출원일:
- 핵심 청구항 요약:
- STAGE 1B와의 차이:
- 위험 등급: 🟢/🟡/🟠/🔴

### 3.2 Google Patents 결과 (Claude 자동 검색, 2026-05-11 완료)

#### 🟠 후보 G-1: US20180060733A1
- 출원인: IBM (추정)
- 출원일: 2016-08-31 / 공개: 2018-03-01
- 제목: Techniques for assigning confidence scores to relationship entries in a knowledge graph
- 핵심 청구항 요약: 지식그래프 n-튜플 관계에 초기 confidence 할당 + feature vector·학습된 weight로 후속 confidence 산출
- STAGE 1B와의 차이:
  - 겹침: 요소 ① (다중 소스 가능) + 요소 ② (가중치 기반 신뢰도)
  - 차이: **학습 기반 weight** (feature vector + ML) — 우리는 **폐쇄식 `c=1−Π(1−w_i)`**. 삭제 cascade·manual 면역·triple diff 청구 없음.
- 위험 등급: 🟠 (상당 겹침, 요소 1·2 부분)
- Mitigation: 청구항 1을 "각 관계가 `{doc_id, weight, role, timestamp}` 튜플 배열을 보유하고, 신뢰도가 `c=1−Π(1−w_i)`로 산출되며, 소스 문서 삭제 시 cascade하는 단계"로 한정. **학습 기반이 아닌 폐쇄식 결합** 명시 필수.

#### 🟠 후보 G-2: US8682913B1
- 출원인: Google
- 출원일: 2005-03-31 / 등록: 2014-03-25
- 제목: Corroborating facts extracted from multiple sources
- 핵심 청구항 요약: 동일 subject의 attribute-value 쌍을 여러 소스에서 추출해 corroborate. "소스 수·importance 메트릭" 기반 confidence
- STAGE 1B와의 차이:
  - 겹침: 요소 ① + 일부 ②
  - 차이: **확률 OR 폐쇄식 명시 없음**, **삭제 cascade 없음**, **manual 면역 없음**, **triple diff 없음**
- 위험 등급: 🟠 (상당 겹침, 요소 1·일부 2)
- Mitigation: 청구항에 "noisy-OR closed-form `c=1−Π(1−w_i)`" + "doc_id 기반 삭제 cascade (sources 배열에서 doc_id 제거 → confidence 재계산 → orphan drop → 고립 엔티티 삭제)" + "`role='manual' & doc_id=null` cascade 면역" 종속항 추가.

#### 🟡 후보 G-3~G-6 (일부 겹침)
- G-3: US8825471B2 — Unsupervised extraction of facts (Google, 2014-09-02)
- G-4: US9424524B2 — Extracting facts from unstructured text (2016-08-23)
- G-5: WO2017058584A1 — Extracting facts from unstructured information (2017-04-06)
- G-6: US20040249871A1 — Auto-removal of documents from knowledge repository (2004-12-09)
  - 시간 기반 deletion이며 KG cascade 아님. 도메인 다름.

#### 🟢 후보 G-7~G-14 (무관)
- US20160239500A1, US20110022598A1, US20180144252A1, US20220147835A1, US20240086732,
  US11409698/US11216456 (Oxford Semantic), US9547823B2, US11645095B2

#### 학술 선행자료 (특허는 아니나 진보성 평가 영향)
- 🟠 Efthymiou et al., ScienceDirect 2023 — Online maintenance of evolving KG with why-provenance, RDFS saturation, **삭제 처리 명시**. 단 noisy-OR/manual 면역 없음.
- 🟡 arXiv 2108.07758 (2021) — Provenance of query result probabilities in uncertain KGs
- 🟡 HUKA (Gaur et al., CIKM 2020) — How-provenance under updates to KGs
- 🟡 Knowledge Vault (Dong et al., 2014) — Probabilistic knowledge fusion (다중 추출기, noisy-OR 가능성 있음)

### 3.3 Google Patents 결과 (사용자 직접 검색)

> 사용자가 직접 검색 후 의심 건 여기에 추가.

### 3.4 Claude 검색의 한계 (보완 필수)

1. **patents.google.com 직접 접근 HTTP 403 차단** — 청구항 원문 미확인. 위 분석은 검색엔진 요약 + Justia·SEObytheSea 등 서드파티 설명 기반.
2. **KIPRIS·CNIPA·J-PlatPat 미검색** — Google Patents가 일부 KR/CN 패밀리를 포함하나 별도 확인 권장.
3. **IBM·Google의 KR/EP/CN 패밀리** 미확인 — 동일 발명의 한국 출원 여부 확인 필수.

추가 검색 권장:
1. KIPRIS: "지식그래프 신뢰도 캐스케이드", "노이지-OR 지식그래프", "출처 가중치 트리플"
2. CNIPA: "知识图谱 置信度 级联 删除"
3. EPO Espacenet: US20180060733A1, US8682913B1 패밀리 트리
4. Lens.org: IPC `G06N5/02` + "provenance" + "cascade"

---

## 4. 위험 등급 매핑 가이드

| 등급 | 의미 | 조치 |
|---|---|---|
| 🟢 무관 | 도메인 다름·요소 일부만 일치 | 무시. 출원 진행 |
| 🟡 일부 겹침 | 1~2개 요소 일치 | 청구항을 결합 발명으로 좁힘. 종속항 차별점 명시 |
| 🟠 상당 겹침 | 3~4개 요소 일치 | 출원 전 청구항 대폭 수정 |
| 🔴 거의 동일 | 5개 이상 + 동일 도메인 | 출원 보류 + 변리사 자문 |

---

## 5. 최종 결론 (Claude 검색 단독, KIPRIS 보완 대기)

- 위험 등급 🟠 이상: **2건** (US20180060733A1, US8682913B1)
- 위험 등급 🔴: **0건**
- **출원 진행 가부**:
  - [ ] ✅ 진행 (위험 없음)
  - [x] ⚠️ **청구항 수정 후 진행** ← **현재 권고**
  - [ ] ❌ 보류 (변리사 자문 필요)

### 청구항 수정 권고 (Mitigation)

기존 skeleton §6 청구항 1을 다음 한정으로 강화:

```
청구항 1 (수정안):
지식 그래프 시스템에서 관계의 신뢰도를 도출하는 방법으로서,
(a) 상기 관계에 대해 출처 가중치 집합 sources = {(doc_id_i, w_i, role_i, ts_i)
    : i = 1..n} 을 유지하는 단계 — 여기서 각 항목은 학습 가중치가 아닌
    추출 시점의 LLM 출력 score 또는 정책 기반 weight를 그대로 사용함;
(b) 상기 관계의 신뢰도 confidence를 폐쇄식 (closed-form)
    confidence = 1 - Π(1 - w_i) for i in sources 에 의해 도출하는 단계
    — 학습 모델 추론을 거치지 않음;
(c) 상기 도출된 신뢰도를 retrieval, scoring, 또는 reasoning 단계에서
    사용하는 단계
를 포함하는, 신뢰도 도출 방법.
```

추가 강화 종속항:

```
청구항 4 (수정안 — manual 면역, 가장 강한 신규성):
청구항 2에 있어서, 상기 sources 배열의 각 항목은 role 필드와 doc_id 필드를
가지며, role 값이 "manual"이고 doc_id 값이 null인 항목은 (b)~(e) 단계의
어떤 cascade 동작에서도 제거되지 않고 보존되는 것을 특징으로 하는 방법.

청구항 5 (수정안 — triple diff):
청구항 2에 있어서, 출처 문서가 수정될 때:
(a) 직전 추출 결과를 (subject, predicate, object) 트리플 집합으로
    보존하는 단계 — 청구항 1의 sources 배열과 별도로 sidecar 파일로 저장;
(b) 새 내용에서 동일 트리플 집합을 LLM으로 추출하는 단계;
(c) 두 집합의 차집합 removed = old - new, added = new - old,
    교집합 kept = old ∩ new를 산출하는 단계;
(d) removed에 대해서만 청구항 2의 (b)~(e)를 수행하고, added에 대해서만
    source 추가를 수행하며, kept에 대해서는 source의 timestamp·weight·role
    필드를 유지하는 단계
를 추가로 포함하는 방법.
```

### 우리의 강한 신규성 (검색 결과 0건)

1. ✅ 폐쇄식 `c = 1 − Π(1 − w_i)` (학습 기반 fusion과 명확 구분)
2. ✅ `role='manual' & doc_id=null` cascade 면역 — **가장 강한 신규성**
3. ✅ (s, p, o) 트리플 단위 diff cascade — 학술·특허 0건
4. ✅ 단조성 수학적 보장 청구

**비고**:
- KIPRIS 사용자 직접 검색 완료 후 §3.1 추가 → 최종 결론 재확정 필요.
- IBM US20180060733A1의 KR 패밀리 존재 여부는 KIPRIS에서 출원인 "International Business Machines" 또는 "IBM" 검색으로 별도 확인 권장.

---

**작성자**: 발명자 본인 (DIY) + Claude (자동 보조 검색)
**작업 브랜치**: claude/security-audit-LRxjo
