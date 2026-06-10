# R1.4 — RAB 사전 등록 (Pre-registration)

**Date**: 2026-06-10 (어댑터 구현 + 측정 실행 **전** 커밋 — R5 의무)
**Status**: LOCKED. 이 문서 작성 이후 보고 프로토콜 / 어댑터 계약 / 채점
파라미터 변경 금지. 변경 시 사유를 본 문서에 append 하고 해당 측정은
exploratory 로 강등 (verdict-grade 아님).

**Spec under test**: RAB SPEC v0.1.1 (FROZEN, `eval/rab/SPEC-v0.1.md`)
**Scenario**: S1 lifecycle-small (`eval/rab/scenarios/s1_lifecycle_small.json`)
**Why pre-register**: 이 벤치는 가설이 아니라 **gap structure** 가 산출이다
(SPEC §6 honesty clause #5). 사전 등록은 사후 임계값 fit 을 차단하고,
어느 결과든 정직하게 보고하기 위한 약속이다. R1.0~R1.3 도 같은 규율로
진행했다 (Cycle γ Phase C.2 pre-reg 가 worked example).

---

## 1. 측정할 SUT

| SUT | 어댑터 | 위치 |
|---|---|---|
| Reference | `ReferenceAdapter` | `eval/rab/adapters/reference.py` (기존) |
| **Baseline-0** | `Baseline0Adapter` (vanilla in-memory RAG, default logging) | `eval/rab/adapters/baseline0.py` (R1.4 신규) |
| **JAMES** | `JamesAdapter` | `eval/rab/adapters/james.py` (R1.4 신규) |

- Reference 는 SPEC self-verification 용 (1.0×3 pinned). 본 측정의 비교
  대상이 아님 — 단지 driver+scorer 가 정상 동작함을 재확인한다.
- Baseline-0 = "vanilla quickstart + default logging" 의 in-process
  구현. 외부 LangChain/LlamaIndex 의존을 피하기 위해 최소한의 인-메모리
  RAG (sklearn-free, 토큰 셋 retrieval) + Python `logging` 모듈만 사용한다.
  의도적으로 RAB 캐노니컬 이벤트를 모르고, 결정적 매핑이 어렵다 — 이게
  바로 **bolt-on 으로 칠 수 있는 floor 의 모습**이다. 더 정교한
  Baseline-1 (LangSmith/OTel 매핑) 은 R1.5+ 의 별도 작업.
- JAMES = `core.reasoning.engine.ReasoningEngine` + `core.vector_store` +
  `core.lifecycle.replay_audit/replay_graph` 을 그대로 사용. 격리
  `JAMES_WORKSPACE` 의무.

## 2. 보고 프로토콜 (LOCKED)

R1.4 release artifact = **단 하나의 JSON 결과 파일** per SUT:

```
{
  "spec":           "v0.1.1",
  "scenario":       "S1",
  "scenario_sha":   "<sha256>",
  "sut":            "<reference|baseline0|james>",
  "sut_version":    "<git-sha or tag>",
  "AC":             {"overall": ..., "matched": ..., "total": ..., "per_type": {...}},
  "RF":             {"exact": ..., "graded": ..., "k": ...,
                     "cost_s_per_1k_events": ...,
                     "per_checkpoint": {...}},
  "PC":             {"pc": ..., "traceable": ..., "total_citations": ...,
                     "per_answer": [...]},
  "n_log_events":   ...,
  "log_sha":        "<sha256 of exported log JSONL>",
  "mapping_table_sha": "<sha256 of mapping table JSON>",
  "runner_env":     {"python": ..., "platform": ..., "ts_utc": ...}
}
```

세 SUT 결과를 한 표(**gap table**)에 나란히 배치한다. 이게 release 의
유일한 headline 이다 (SPEC §5).

### 보고 시 의무

1. **Gap table 이 headline**. 단일 SUT 점수를 headline 으로 쓰면
   honesty clause #5 위반. JAMES 점수 자체가 강해도 마찬가지 — 그러기
   위해 만든 벤치다.
2. **Spec version + scenario sha 항상 동반 보고**. SPEC §4.
3. **Re-verification artifact 동반**: 각 SUT 의 export 된 audit log JSONL
   파일 + mapping table JSON 을 commit 또는 release attachment 로 공개.
   제3자가 동일 채점기로 실행 시 numbers 가 bit-for-bit 재현 의무
   (SPEC §4).
4. **"인증 아님" disclaimer**: Art. 10/12/19 operationalisation, 컴플라이언스
   인증 아님 (SPEC §6.3) — 보고 본문에 1줄 명시.
5. **Honest tier 사전 배정**:
   | 결과 | 최대 tier |
   |---|---|
   | gap table 이 audit-native vs bolt-on 의 명확한 격차를 보여줌 | ⭐⭐ (벤치 자기검증 + 외부 비교의 첫 데이터 포인트) |
   | gap 이 보이지만 단일 시나리오만으로 cross-scenario 미확인 | ⭐ (scenario-specific) |
   | 격차가 noise band 안 / 측정 결함 | finding 아님 — 결함 분석 별도 |
6. **mid-June joint piece 자동 연결 금지** (`feedback_eval_cycle_vs_collab_arc_separation`).
   본 측정은 R1 모트 트랙 internal arc 이며, 4-질문 통과 전 collab arc
   evidence 로 사용 금지.

## 3. Cell 유효성 / 무효 조건

- 모든 SUT 가 같은 scenario JSON 을 같은 driver 로 통과해야 한다 —
  driver/scorer 코드는 측정 중 변경 금지.
- Reference 실행이 (AC=1.0, RF-exact=1.0, PC=1.0) 가 아니면 driver/scorer
  결함 — 본 측정 invalid 처리, 결함 수정 PR (Quality delta exempt: fix)
  후 재실행.
- Baseline-0 또는 JAMES 가 scenario 실행 중 예외로 중단되면 그 SUT 의
  numbers 는 "errored" 로만 기록한다 (점수 채우지 않음). 무엇이 끊겼는지
  결과 본문에 명시.
- log_sha / mapping_table_sha 가 빠진 결과는 publishable 아님 (§2 의무 #3).

## 4. 금지 사항 (사전 명시)

1. **측정 후 SPEC 파라미터 변경 금지**: canonicalisation, AC time-window
   매칭 규칙, RF Jaccard 항목 정의, PC chain 정의 — 모두 LOCKED.
   변경이 필요하면 SPEC v0.1.2 로 bump + 변경 사유 changelog + 새 측정
   (현 numbers 는 v0.1.1 결과로 영구 기록).
2. **JAMES 어댑터 측 임시 변경 금지**: 측정 중 unmapped 이벤트를 줄이려고
   mapping table 을 조정하는 등의 "튜닝" 은 post-hoc fit. mapping table 도
   commit 으로 동결.
3. **LLM judge 사용 금지** (SPEC §6.1) — adapter 의 query() 가 LLM 을
   호출하는 것은 SUT 의 정상 동작이며 채점기는 절대 LLM 을 호출하지
   않는다.
4. **Live-state 사용 금지 in RF** (SPEC §6.2) — replay 는 export 된 log
   외 어떤 file/DB 도 읽으면 안 됨. JAMES adapter 의 `replay_at` 는
   `reconstruct_graph_at(t)` + log-only ingest replay 로 구현하며, 그
   외 read 경로는 contract 위반.
5. **JAMES wins framing 금지**: 점수가 어느 방향이든 §2 headline 규칙
   유지. JAMES 가 더 잘 측정될 것을 SPEC §5 가 명시 — 그건 새로운 발견이
   아니라 의도된 설계다.
6. **Baseline-0 부족한 점을 fix 해서 점수 올리려는 시도 금지**: Baseline-0
   = "vanilla quickstart + default logging" 의 정직한 minimum. tracing
   라이브러리 / OTel / 로깅 자체를 추가하면 그건 Baseline-1 이고 별도
   SUT 다 (R1.5 항목).

## 5. 실행 순서 (logical chain)

```
0. 이 사전 등록 commit                       ← P0 (이 단계)
1. JamesAdapter + Baseline0Adapter 구현      ← driver/scorer 변경 금지
2. 단위 테스트 (adapter contract 만족 확인)
3. Reference re-run (self-verification 확인) ← (1.0, 1.0, 1.0) 게이트
4. JAMES adapter S1 실행 → result.json + log + mapping
5. Baseline-0 adapter S1 실행 → result.json + log + mapping
6. gap table 작성 → handover doc + memory update
7. (R1.5) Zenodo 공개 준비 — 별도 작업
```

예상 비용: JAMES 시나리오 1회 실행 ~2-5분 (LLM 호출 20 QUERY), Baseline-0
< 30초 (in-memory). 총 < 10분 측정 + 수십 분 코드/검증.

## 6. 어댑터 계약 사전 명시 (구현 가이드)

SPEC §1 + `driver.py` docstring + `reference.py` 가 정전. R1.4 어댑터들은
다음 7 메서드를 정확히 구현한다:

```
ingest(doc_id, title, text) -> None
update(doc_id, title, text) -> None
supersede(old_doc_id, doc_id, title, text) -> None
delete(doc_id) -> None
query(q) -> {"answer": str, "citations": [str]}
snapshot() -> {"entities": [...], "edges": [...]}   # SPEC §2.4 shape, live
export_log() -> [SPEC §1 row, ...]                  # canonical types,
                                                    # mapping_table 동봉
replay_at(k, ts) -> {"entities": [...], "edges": [...]}  # log-only
```

JAMES adapter 의 mapping table = `core` 의 audit_log/lifecycle event_type
→ RAB canonical type 표를 별도 JSON 으로 commit (channels: INGEST,
UPDATE, SUPERSEDE, DELETE, RETRIEVE, SYNTH, ANSWER 7종 + OTHER 폴백).

---

*이 문서는 어댑터 구현 + 측정 실행 전 커밋된다. Commit hash 가 사전 등록
증거. SPEC v0.1.1, scenario S1 의 sha 동결도 본 commit 에 포함.*
