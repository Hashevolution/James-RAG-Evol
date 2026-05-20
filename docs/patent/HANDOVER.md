# 특허 출원 작업 핸드오버 문서

> 본 문서는 James-RAG-Evol의 한국 특허 출원 작업에 대한 전체 진행 상황 핸드오버입니다.
> 새 대화 세션에서 본 파일 한 개만 읽으면 작업을 이어갈 수 있도록 설계되었습니다.
>
> **작성일**: 2026-05-09 (초판) / 2026-05-10 (2차 보강) / 2026-05-10 (skeleton 완성) / 2026-05-09 (메인 정합 정정) / 2026-05-19 (PAUSE 결정) / **2026-05-20 (Pause 조건 1/3 해결 — noisy-OR 핫픽스)**
> **마지막 업데이트**: Hotfix PR #349 (`b89c099`) 로 공식 ↔ 구현 일치 회복 + 7 invariant lock-in. Pause 유지 (남은 조건 2/3).

---

## ⏸️ 0. PAUSE 상태 (2026-05-19, 업데이트 2026-05-20)

### 현재 결정
**출원 작업 일시 중단 유지**. 핫픽스 1 + 2 + postmortem (PR #349/350/351/352) 로 Knowledge Cascade 안정화는 달성했으나, 사용자 우선순위 (§8) 가 출원이 아닌 제품 강화 (Phase 2 Planner / Episodic Memory / Phase 2 Default ON) 임이 명시됨. **시점적 트리거 발동 시까지 PAUSE 유지**.

### Postmortem (PR #352, `fcc79cc`, 2026-05-20) 흡수 — 출원 framing 원칙

**`docs/postmortems/2026-05-20-knowledge-cascade-defects.md` §0 + §4.4**:

> **제품 동작을 먼저 만들고, 그 결과를 특허로 정리한다.**
> - ❌ "디자인 메모가 청구한 것을 코드로 backing"
> - ✅ "제품이 이렇게 동작하므로 그 동작을 청구"
> - 방향은 **코드 → 청구**. 디자인 메모는 historical artifact 이며 청구의 ground truth 아님.

**§10 Ground Truth**: 청구 reference 는 항상 **현재 코드 + 테스트**:
- `core/relations_schema.py` (현재 commit)
- `tests/test_relations_schema.py` (현재 commit) — 7 invariant
- `core/wiki_generator.py` (현재 commit)
- `tests/test_phase_b_ingestion_sources.py::CrossDocSourceAggregationTests` (현재 commit) — 5 invariant
- `CHANGELOG.md` (현재 commit)

→ STAGE 1B skeleton + 디자인 메모는 historical. 출원 시점에 새로 코드·테스트 기반으로 청구 작성.

### Postmortem §8 사용자 우선순위 (출원 ≠ 우선)

| 우선 | 항목 | 출원 영향 |
|---|---|---|
| 🔴 | **Phase 2 PR-7 Planner** — multi-step task decomposition + Tool Router wiring | STAGE 6 안정화 대기 |
| 🟠 | Phase 3 PR-9 Episodic Memory | STAGE 8 안정화 대기 |
| 🟠 | Phase 2 Default ON 검토 (Reflection / Verification) | STAGE 6 안정화 대기 |
| 🟡 | PR-O6b Graph Node Editor frontend | STAGE 1B Phase E UX 확장 |
| 🟡 | 0.6 confidence 임계값 재튜닝 (multi-source 누적 후) | STAGE 1B Tier 3 검증 자동 누적 |

→ 출원은 명시 우선순위 0순위. **자연 누적 + 시점적 트리거로만 트리거**.

### 핫픽스 1 + 2 결합 효과 (안정화 달성)
- **PR #349 (`b89c099`, 09:07 KST)**: `compute_confidence_from_sources` → noisy-OR `1 − Π(1 − w_i)` + 7 invariant
- **PR #350 (`1009cca`, 11:06 KST)**: `process_document_for_entities` cross-doc aggregation + `_merge_relations_into_existing_entity` + 5 invariant
- **PR #351 (`5517743`, 13:32 KST)**: CHANGELOG reframe — product impact lead, design memo demoted to historical reference
- **PR #352 (`fcc79cc`, 13:47 KST)**: Postmortem 403줄, 4-layer silent alignment failure 분석 + §8 우선순위 명시

**12 invariant 테스트 lock-in** (`tests/test_relations_schema.py` 7 + `tests/test_phase_b_ingestion_sources.py` 5):
- 공식 정합 (7)
- State 생성 정합 (5)
- 결합 contract (`test_confidence_uses_noisy_or_after_two_sources` — 0.91 assertion)

Production wiki: 278 files, **0 multi-source relations** — defect dormant, caught pre-manifestation. 다음 ingest 부터 자연 누적.

### 재개 조건 (ALL of) — 업데이트
1. ✅ ~~공식 확정~~ ← PR #349 (2026-05-20)
2. ✅ ~~Cross-doc state 생성 정합~~ ← PR #350 (2026-05-20)
3. ⏳ 사용자 시점적 트리거 (예: Show HN 임팩트, 경쟁사 출원, 투자 협상, 사용자 명시 결정)
4. ⏳ (선택) Tier 2 synthetic A/B 또는 Tier 3 실 multi-source 누적 — 정식 전환 시점에 보강

### 출원 가능 후보 매트릭스 (2026-05-20 재평가)

상세 분석: `docs/patent/filability-2026-05-20.md`

| Stage | 점수 | 코드 안정성 | 안정적 출원 가능 |
|---|---|---|---|
| **1 (Memory Loom)** | 4/5 ⭐ | ⭐⭐⭐ v0.1 부터 안정 | ✅ **HIGH — 즉시 가능** |
| **1A (Doc-source gate)** | 3/5 ⭐ | ⭐⭐⭐ 단일 PR 머지, 무변동 | ✅ **HIGH — 즉시 가능** |
| **1B (Cascade)** | 4/5 ⭐⭐ | ⭐⭐⭐ **12 invariant lock (최다)** + 명세↔구현↔테스트 3자 정합 | ✅ **HIGH — 즉시 가능** (재분류 2026-05-20) |
| 2 (Feedback Shadow) | 2/5 | ⭐⭐⭐ 안정 | ✅ MID — 출원 가능 (약한 신규성) |
| 3 (Security 2-stage) | 2/5 | ⭐⭐ PR #322 catalog_context 추가 | ✅ MID — 가능 (#322 종속항) |
| 4 (Trait Pair) | 2/5 | ⭐⭐⭐ 안정 | ✅ LOW — 약한 신규성 |
| 4A (Self-Evolution) | 3/5 ⭐ | ⚠️ PR #78/79 머지 확인 필요 | ⚠️ 확인 후 |
| 4B (Trace Correlation) | 2/5 | ⭐⭐⭐ 안정 + STAGE 10 흡수 가능 | ✅ MID |
| 5 (Reasoning Backend) | 4/5? | ❌ Plugin API 설계 진행 중 (#343/344) | ❌ WAIT — 1~2개월 |
| 6 (Cognitive Middleware) | 3/5? | ❌ Phase 2 Default ON 미결 | ❌ WAIT — Phase 2 종결 후 |
| 7 (Change Request) | 2/5? | ⭐⭐ 안정 | ✅ LOW — 약한 신규성 |
| 8 (Episodic Memory) | 2/5? | ❌ §8 next priority — 미완 | ❌ WAIT |
| 9 (Catalog Context) | 2/5? | ⭐⭐⭐ 안정 | ✅ STAGE 3 종속항으로 흡수 |
| 10 (Replay Trace) | 3/5? | ⭐⭐⭐ 안정 | ✅ STAGE 4B 종속항 또는 별건 |

**즉시 안정적 출원 가능 (Tier 1)**: STAGE 1, 1A, **1B** (3건, 약 5.4만 원)
**조건부 출원 가능 (Tier 2)**: STAGE 2, 3, 4, 4B, 7, 9, 10 (7건, 약 12.6만 원)
**대기 필요 (Tier 5)**: STAGE 0, 4A (확인 필요), 5, 6, 8

> **재분류 사유 (2026-05-20)**: STAGE 1B 를 처음에는 "사용자 §8 우선순위 미포함"
> 이유로 Tier 3 분류했으나, §8 은 **엔지니어링 우선순위** 이지 출원 가능성 아님.
> 12 invariant lock (가장 많음) + 핫픽스 1+2 후 3자 정합 + 회귀 차단 견고 →
> 기술적으로는 Tier 1 분류가 정합. 사용자 지적 후 정정.

### 재개 시 첫 메시지 (복사용)
```
James-RAG-Evol 특허 출원 작업 재개합니다.

다음 파일 확인 후 작업 진행 해주세요:
- docs/patent/HANDOVER.md (pause 결정 + 재개 조건 §0)
- docs/patent/filability-2026-05-20.md (안정적 출원 가능 후보 매트릭스)
- docs/patent/REVIEW-NOTES.md (선행기술 분석)
- docs/patent/prior-art-1B.md (Google Patents 검색 결과)
- docs/patent/stage1b-invariant-claims-mapping.md (12 invariant → 청구항 매핑)
- docs/postmortems/2026-05-20-knowledge-cascade-defects.md (framing 원칙)

핵심 원칙: "코드 → 청구" — 디자인 메모 X, 현재 코드 + 테스트가 청구 ground truth.

작업 브랜치: claude/security-audit-LRxjo

[구체 요청 — 예: "STAGE 1 + 1A 즉시 출원 진행" / "STAGE 1B 출원 트리거 발동"]
```

### Pause 중 보존 자산
| 파일 | 상태 |
|---|---|
| `strategy.md` | ✅ 유효 (단, 안정성 매트릭스는 `filability-2026-05-20.md` 우선) |
| `REVIEW-NOTES.md` | ✅ 유효 |
| `prior-art-1B.md` | ✅ Google Patents 검색 (🔴=0, 🟠=2, 🟡=4, 🟢=8) |
| `stage1b-invariant-claims-mapping.md` | ✅ 12 invariant 매핑 (7+5) |
| `filability-2026-05-20.md` | ✅ **NEW** — 14 후보 안정성 평가 |
| 8개 stage skeleton | ⚠️ historical. 출원 시 현재 코드·테스트 기반 재작성 (postmortem §10 원칙) |
| `disclosure_log.txt` | ✅ PR #266~#352 commit 추가 완료 |

### Grace Period 시계 (오늘 2026-05-20 기준)
| 후보 | Grace 만료 | 남은 일수 |
|---|---|---|
| STAGE 4A | 2027-05-03 | **348일** ⚠️ 가장 빠름 |
| STAGE 1·2·3·4 | 2027-05-04 | 349일 |
| STAGE 1A·1B (디자인) | 2027-05-08 | 353일 |
| STAGE 1B (Phase D 구현) | 2027-05-13 | 358일 |
| STAGE 1B (Hotfix 1 noisy-OR) | 2027-05-20 | 365일 |
| STAGE 1B (Hotfix 2 cross-doc) | 2027-05-20 | 365일 |
| STAGE 5 (Reasoning Backend) | 2027-05-17 | 362일 |

> ⚠️ **2026년 12월 ~ 2027년 1월** 까지 재개 결정 필수.

### 신규 발견 (재개 시 평가 대상)
v0.3 platform skeleton 진행 중 새로 등장한 특허 후보 6건 (skeleton 없음):
- STAGE 5 — Reasoning Backend Plugin (PR #283/284/285/324/325/326)
- STAGE 6 — Cognitive Middleware Layer (PR #275/289/290/295/297)
- STAGE 7 — Change Request Workflow (PR #237/239/240/243)
- STAGE 8 — Episodic Memory Store (PR #338)
- STAGE 9 — Schema v1.1 Catalog Context (PR #322)
- STAGE 10 — Replay-able Audit Trace (PR #284/285)

### 전략 재평가 (Postmortem 반영)
- **MIT + GitHub 공개**가 이미 defensive publication 80% 커버
- 권장 시나리오 (Postmortem 정합): 사용자 시점적 트리거에만 출원, 자연 누적 + grace 활용
- **즉시 가능한 minimal 출원** (트리거 발동 시): STAGE 1 + STAGE 1A 2건 = 약 3.6만 원
- 청구 reference 는 **현재 코드 + 테스트** (skeleton X, 디자인 메모 X)
- 정식 전환은 multi-source 자연 누적 (1~3개월) 후 D+330일 시점에 선별

---



---

## 🎯 한 줄 요약

James-RAG-Evol(MIT, GitHub Public)의 핵심 기술 8건에 대해 한국 특허청 임시명세서를 발명자 직접(DIY) 출원하여 우선일을 확보하는 작업. 8개 skeleton 작성 완료, 출원인 정보 기재·도면 PDF 변환·특허로 전자출원이 남아있음.

---

## 1. 핵심 배경

| 항목 | 값 |
|------|-----|
| 프로젝트 | James-RAG-Evol (Hashevolution organization, MIT 라이선스) |
| GitHub | https://github.com/Hashevolution/James-RAG-Evol |
| 첫 공개 | 2026-05-05 (`d15bf66` 첫 commit) |
| 작업 브랜치 | `claude/security-audit-LRxjo` (모든 특허 작업 commit이 여기에 있음) |
| 출원 방식 | DIY (변리사 미사용, 발명자 직접 임시명세서) |
| 출원 사이트 | **특허로 (patent.go.kr)** — 회원가입 + 전자출원 |
| 검색 사이트 | KIPRIS (kipris.or.kr) — 선행기술 검색 전용 (출원 불가, 자주 혼동되는 부분) |

**한국 공지예외 (특허법 30조)**: 발명자가 직접 공개한 발명에 대해 12개월 grace period 내 출원 시 신규성 인정. 후보별 grace 만료일이 다름 (아래 §3 표 참조).

---

## 2. 사용자 결정 사항

| 결정 | 내용 | 시점 |
|------|------|------|
| 시나리오 | **C — 전부 8건 출원** (1/1A/1B/2/3/4/4A/4B) | 2026-05-10 |
| 비용 | 약 14~48만원 (개인 감면 70% 적용 시) | — |
| Stage 1 구조 | Memory Loom **단독** → **Umbrella + Memory Loom 결합 출원**으로 격상 | 2026-05-10 |
| 머지 정책 | `docs/patent-additional-candidates` 브랜치를 `claude/security-audit-LRxjo`에 fast-forward 머지 (충돌 없음) | 2026-05-10 |
| Hybrid RAG (#5) | 별건 출원 비추천, #0/#1/#3 종속항으로 흡수 | 2026-05-10 |
| 사이트 정정 | 모든 docs에서 "KIPRIS 출원" 표현을 "특허로 출원"으로 정정 | 2026-05-10 |

---

## 3. 출원 후보 10개 (8 stage)

| # | 후보 | 점수 | Stage | Grace 만료 | 우선순위 |
|---|-----|------|-------|-----------|---------|
| 0 | Umbrella Architecture | 3/5 (조건부) | STAGE 1 흡수 | 2027-05-04 | 2 (1과 동시) |
| 1 | **Memory Loom 5-gate** | **4/5 ⭐** | STAGE 1 본체 | 2027-05-04 | **2** |
| 2 | Feedback Shadow | 2/5 | STAGE 2 | 2027-05-04 | 6 |
| 3 | 2-stage Security + ABAC | 2/5 | STAGE 3 | 2027-05-04 | 7 |
| 4 | Trait Pair Auto-rebalance | 2/5 | STAGE 4 | 2027-05-04 | 8 |
| 5 | Hybrid RAG paradigm | 1/5 | ❌ 별건 안 함 | — | — |
| **A** | Doc-source 출처 게이트 그래프 탐색 | 3/5 ⭐ | STAGE 1A | 2027-05-08 | 3 |
| **B** | **Provenance Cascade + Log-sum** | **4/5 ⭐⭐** | STAGE 1B | 2027-05-08 | **1 (최우선)** |
| **C** | Bench-gated Self-Evolution + Rollback | 3/5 ⭐ | STAGE 4A | 2027-05-03 | 4 |
| **D** | Trace Correlation via ContextVar | 2/5 | STAGE 4B | 일자 확인 필요 | 5 |

### 우선순위 권고 사유

- **1순위 STAGE 1B (Cascade)**: 디자인 메모만 PR #145로 공개됨 (현재 상태 "outline / feasibility study"). 본 구현은 v0.3에서 예정 → 자연 누설 위험으로 가장 빠르게 출원해 우선일 확보. 디자인 메모 자체가 공개 disclosure이므로 grace 만료 2027-05-08 카운트다운 시작.
- **2순위 STAGE 1**: 가장 강한 단위 발명 + 시스템 청구
- **3순위 STAGE 1A**: STAGE 1과 동시 진행 가능
- **4순위 STAGE 4A**: Grace 가장 빠른 만료 (2027-05-03) — 일정 여유 있되 잊지 말 것

### 미니멀 시나리오 (예산 압박 시)

STAGE 1 + STAGE 1B 두 건만 출원 = **약 4~12만원, 92% 가치 확보**.

---

## 4. 작성된 모든 산출물 (`docs/patent/` 디렉토리)

### 전략·증빙 문서

| 파일 | 줄 수 | 용도 | 상태 |
|------|------|------|------|
| `strategy.md` | 281 | DIY 출원 전체 전략, 후보 평가, stage 일정, 비용 | ✅ 완성 (사이트명 정정 완료) |
| `disclosure_log.txt` | — | 공지예외 증빙 (git log 덤프 + A/B PR commit hash) | ⚠️ C/D commit hash TODO 남음 |
| `HANDOVER.md` | (본 파일) | 핸드오버 문서 (절차·일정·인벤토리) | — |
| `REVIEW-NOTES.md` | ~280 | 검색·검토 결과 (선행기술·법규·청구 분석) | ✅ 완성 |

### 8개 임시명세서 skeleton

| Stage | 파일 | 줄 수 | 점수 | 주요 인용 코드 |
|-------|------|------|------|---------------|
| 1 | `stage1-spec-skeleton.md` | 446 | 4/5 ⭐ | `core/memory/loom.py:80-149` (구 `core/memory_loom.py`), `core/query_expander.py` (구 `core/jepa_adapter.py`), graph_engine, ontology |
| 1A | `stage1a-docsource-gate-spec-skeleton.md` | 173 | 3/5 ⭐ | `core/graph_engine.py:_doc_outgoing_hop_valid` (**PR #139, 머지 완료** `371838c`) |
| 1B | `stage1b-cascade-spec-skeleton.md` | 327 | 4/5 ⭐⭐ | `docs/design/v0.3-knowledge-cascade.md` (~430줄, 미구현) |
| 2 | `stage2-feedback-shadow-spec-skeleton.md` | 213 | 2/5 | `core/feedback_engine.py:35-151` (구현 완료) |
| 3 | `stage3-security-spec-skeleton.md` | 245 | 2/5 | `core/security_layer.py` (구현 완료, 본 분기 169-389 / **메인 라인 시프트** ≈ 249-450) |
| 4 | `stage4-trait-pair-spec-skeleton.md` | 268 | 2/5 | `core/character_profile.py:17-97` (구현 완료) |
| 4A | `stage4a-self-evolution-spec-skeleton.md` | 269 | 3/5 ⭐ | `tools/patch/patch_validator.py` (구현 완료), PR #69/77/78/79 |
| 4B | `stage4b-trace-correlation-spec-skeleton.md` | 305 | 2/5 | `core/observability.py` (**Phase 1 구현 완료**, PR #67/97/138 머지) |

각 skeleton 공통 구성:
- 발명의 명칭 (한·영)
- 출원인 / 발명자 [TODO]
- 공지예외 주장 (날짜·만료일 별도)
- §1 기술분야 ~ §10 출원 체크리스트
- 청구범위 10개 (독립 1~3 + 종속 4~10)
- §8 실시예에 실제 코드 인용 또는 의사코드
- 도면 4매 outline (mermaid 소스 또는 설명문)

---

## 5. Git 브랜치 상태

### 메인 작업 브랜치: `claude/security-audit-LRxjo`

```
88af169 docs(patent): add 6 remaining 임시명세서 skeletons (1A/2/3/4/4A/4B)
ba46eba docs(patent): augment with 4 new candidates (A/B/C/D) — 2026-05-10
eb8a625 docs(patent): correct site — 출원은 특허로(patent.go.kr), KIPRIS는 검색 전용
5d99301 docs(patent): fill technical [TODO]s in STAGE 1 spec skeleton
6160fe1 docs(patent): add DIY filing strategy + STAGE 1 spec skeleton + disclosure log
[기존 v0.1.0-alpha 코드 commit들...]
```

### 잔존 브랜치: `docs/patent-additional-candidates`

이미 fast-forward 머지로 위 브랜치에 흡수됨. GitHub에서 삭제하거나 무시해도 됨.

```bash
# 정리하려면:
git push origin --delete docs/patent-additional-candidates
```

---

## 6. 사용자 작업 체크리스트 (남은 일)

### STAGE 0 — 사전 준비 (특허로 가입)

- [ ] **특허로 (patent.go.kr)** 회원가입
- [ ] 본인인증 (휴대폰 또는 공동/금융 인증서)
- [ ] **출원인 코드** 부여 신청 (개인은 자동 발급, 약 30분)
- [ ] **KEAPS** (통합전자출원 SW) 설치 — Windows 권장, macOS 지원 제한적
- [ ] 공동인증서 또는 금융인증서 등록
- [ ] 공지예외 적용 주장 신청서 양식 다운로드 (특허로 → 민원서식)

### 명세서 마무리

- [ ] 8개 skeleton의 **`[TODO: 출원인 / 발명자]`** 섹션 채움 (공통 정보)
- [ ] 8건 × 4매 = **32매 도면** 작성 (mermaid 소스는 skeleton에 있음, PDF 변환 필요)
- [ ] 도면 변환 도구: draw.io / excalidraw / mermaid.live
- [ ] 도면 저장 경로 권장: `assets/patent/stage{N}-figs/figure-{1-4}.pdf`

### Disclosure log 보강

- [ ] `disclosure_log.txt` 의 **C/D 후보 commit hash** 확인하여 기재
  - C: PR #69 (opt-in flag), #77 (eval gate), #78 (rollback), #79 (audit endpoint)
  - D: PR #67 (ContextVar 인프라), #97 (real reasoning stream)

### 출원 (8건 순차)

- [ ] 1순위: **STAGE 1B** (Cascade) — `stage1b-cascade-spec-skeleton.md`
- [ ] 2순위: STAGE 1 (Memory Loom + Umbrella)
- [ ] 3순위: STAGE 1A (Doc-source gate)
- [ ] 4순위: STAGE 4A (Self-Evolution)
- [ ] 5순위: STAGE 4B (Trace Correlation)
- [ ] 6순위: STAGE 2 (Feedback Shadow)
- [ ] 7순위: STAGE 3 (Security 2-stage)
- [ ] 8순위: STAGE 4 (Trait Pair)

각 출원: 6만원 (개인 감면 시 1.8만원), 출원번호 발급 후 출원확인서 PDF 보관 → `docs/patent/stage{N}-receipt.pdf`

### 1년 모니터링 (D+30일~D+360일)

- [ ] 분기별 KIPRIS(`kipris.or.kr`) 재검색 — 경쟁사 신규 출원 추적
- [ ] 신규 차별점 발생 시 추가 임시 출원

### 정식 전환 결정 (D+330일~D+360일, 마감 2027-04월경)

- [ ] 사업화/투자 진척에 따라 결정
- [ ] 정식 전환 시 변리사 자문 권장 (건당 200만원 + 변리사 자문 20~50만원)
- [ ] 미전환 시 자동 취하 → 우선일 효력 소멸 (회수 불가)

---

## 7. 출원인/발명자 정보 채우는 방법

각 skeleton 상단:

```markdown
## 출원인
[TODO: 성명 / 주소 / 주민번호 또는 외국인등록번호]

## 발명자
[TODO: 성명 / 주소]
```

### 표준 양식 (특허로)

```markdown
## 출원인
- 명칭: 홍길동
- 출원인코드: 4-2026-012345-6  (특허로 가입 후 발급)
- 우편번호: 06000
- 주소: 서울특별시 강남구 테헤란로 123, 101호

## 발명자
- 성명: 홍길동
- 주민등록번호: 800101-1234567
- 우편번호: 06000
- 주소: 서울특별시 강남구 테헤란로 123, 101호
```

### 4가지 시나리오

| 시나리오 | 출원인 | 발명자 |
|---|---|---|
| A. 혼자 개인 출원 | 본인 (개인 감면 70%) | 본인 |
| B. 회사 명의 + 본인이 발명자 | 회사 (법인) | 본인 (직무발명) |
| C. 공동 발명 | 본인 또는 회사 | 본인 + 공동 발명자들 |
| D. 외국인 | 본인 | 본인 (외국인등록번호) |

### ⚠️ 주의: PII 보호

- 주민등록번호는 **git에 commit 금지** (매우 민감 PII)
- 권장 방법: skeleton의 [TODO]는 그대로 두고, 출원인 정보는 별도 비공개 파일 (예: `~/private/patent-applicant-info.md`) 로 보관
- 특허로 KEAPS 전자출원 시 양식에 직접 입력 → 자동으로 명세서에 삽입

---

## 8. 핵심 기술 참조 (코드 인용 사실 검증용)

### Memory Loom 5-gate (메인 기준 `core/memory/loom.py:80-149`, 본 분기 시점에는 `core/memory_loom.py`)

```python
MAX_WRITES_PER_SESSION   = 3       # Gate 3 한도
MEMORY_CONFIDENCE_TH     = 0.75    # Gate 1 임계값
MEMORY_DEDUP_WINDOW      = 100     # Gate 4 윈도우
CONFLICT_CONFIDENCE_DIFF = 0.3     # Gate 5 confidence 차이 임계값
```

게이트 순서: confidence → ontology_valid → write_rate → dedup → conflict.

### 키워드 동의어 기반 질의 확장기 (메인 기준 `core/query_expander.py`, 구 `core/jepa_adapter.py`)

> ⚠️ **명칭 정정 (2026-05-09)**: 본 모듈은 v0.2 정합성 정정에서 `jepa_adapter` → `query_expander`로 리네임됨. 사유는 LeCun JEPA(Joint-Embedding Predictive Architecture)와 무관한 순수 키워드 동의어 사전 lookup + 한국어 stopword 필터 구현이기 때문. **특허 명세서에 "JEPA"라는 용어 절대 사용 금지** — 청구·실시예 모두 "키워드 동의어 사전 기반 질의 확장"으로 한정 기재.

```python
TOKEN_HARD_LIMIT = 50     # 확장 후 token 최대 (구 JEPA_TOKEN_HARD_LIMIT 별칭은 v0.2까지 호환)
TIMEOUT_SEC      = 3.0    # 이 안에 못 끝내면 bypass (구 JEPA_TIMEOUT_SEC 별칭 동일)
```

LLM 호출 0회, 임베딩 미사용, 그래프 미접근. `_SYNONYM_MAP` 17개 표제어, `_STOPWORDS` 한국어 조사 사전.

### Graph DFS (`core/graph_engine.py:220-307`)

```python
CONFIDENCE_THRESHOLD = 0.6
MAX_DEPTH            = 4
DFS_SCORE_THRESHOLD  = 0.05
DEPTH_DECAY          = 0.7
```

ACT halting + ontology weighted scoring (`compute_graph_score = Σ(weight × confidence) / depth`).

### Feedback Engine (`core/feedback_engine.py:35-151`)

```python
FEEDBACK_SIGNALS = {
    "explicit_positive":  +1.0, "flow_continue":    +0.3,
    "implicit_positive":  +0.2, "explicit_negative":-1.0,
    "correction":         -0.8, "strong_objection": -0.6,
    "implicit_negative":  -0.3,
}
REINFORCE_TH = +2.0
WEAKEN_TH    = -2.0
DECAY        = 0.9
```

### Security Layer (`core/security_layer.py`)

라인 시프트 매핑 (본 분기 → 메인):

- `pre_check()`: validate → detect_attack → extract_data_only → sanitize (본 분기 323-362 / **메인 ≈ 409**)
- `mask_sensitive()`: 10개 PII 정규식 (본 분기 253-275 / **메인 ≈ 339**)
- `filter_answer_by_role()`: graph + wiki person entity 마스킹 (본 분기 277-316 / **메인 ≈ 363**)
- `cross_stage_abac_verify()`: Vector / Graph / Output 3단계 일관성 (본 분기 169-224 / **메인 ≈ 249**)

### Character Profile (`core/character_profile.py:17-97`)

11개 trait = 4 쌍 (A/B/C/D, sum-invariant) + 3 독립 (E)
Threshold prompt directive: > 0.7 강한 directive, < 0.3 반대 방향

### Patch Validator (`tools/patch/patch_validator.py`)

4 게이트: Static Check / PROTECTED_FILES / 회귀 테스트 / Security Bypass
- `FORBIDDEN_PATTERNS`: 11개 (eval, exec, subprocess, os.system, rm -rf 등)
- `SECURITY_BYPASS_PATTERNS`: 7개 (pre_check=lambda...True 등)

---

## 9. 비용 시나리오 (1년 차, 개인 감면 70%)

| 시나리오 | 출원 건수 | 합계 (감면 후) |
|---------|----------|---------------|
| 미니멀 (STAGE 1 + 1B) | 2건 | 약 4~12만원 |
| 핵심+신규 (1/1A/1B/4A) | 4건 | 약 14~48만원 |
| ✅ **전부 (1/1A/1B/2/3/4/4A/4B)** | **8건** | **약 14~48만원** |
| (선택) 정식 전환 1건 | — | 약 200만원 |

---

## 10. 리스크 / 주의 사항

1. **청구항 작성 미숙** — DIY 임시명세서는 보호 범위가 좁아질 수 있음. 정식 전환 시 변리사 도움 권장.
2. **명세서 부실 거절** — "통상의 기술자가 재현 가능한 수준" 기재요건 미달 시 거절. 코드 인용·도면 충실히.
3. **Grace period 카운트다운** — 후보별 마감일 다름. 가장 빠른 건 2027-05-03 (STAGE 4A).
4. **Umbrella claim 거절 리스크** — STAGE 1 broad 청구가 신규성 거절돼도 Memory Loom 종속항은 거의 확실히 살아남음.
5. **B (Cascade) 자연 누설 리스크** — v0.3 구현이 GitHub에서 더 상세히 진행 중. 빨리 출원해 우선일 확보 필수.
6. **번역 부담** — 미국·PCT 진출 시 건당 100~200만원 추가.
7. **PII 보호** — 주민등록번호를 git에 commit 금지.
8. **사이트 혼동 주의** — 출원은 특허로(patent.go.kr), KIPRIS는 검색 전용.

---

## 11. 새 세션에서 작업 이어가는 방법

### 새 세션 시작 시 첫 메시지로 사용할 프롬프트 (복사용)

```
James-RAG-Evol 한국 특허 출원 작업을 이어 진행합니다.

이전 세션에서 진행된 모든 내용은 다음 파일에 정리되어 있습니다:
docs/patent/HANDOVER.md

이 파일을 먼저 읽고, 다음 작업을 진행해주세요:
[여기에 구체 요청 작성 — 예: "도면 32매 mermaid 소스 모두 작성", "STAGE 0 가이드 상세화", 등]

작업 브랜치: claude/security-audit-LRxjo
```

### 새 세션이 알아야 할 핵심 사실 (HANDOVER.md를 안 읽어도 즉시 파악)

- 작업 브랜치: `claude/security-audit-LRxjo`
- 8개 skeleton 모두 작성 완료
- 사용자 결정: 시나리오 C (전부 8건 출원)
- 사이트: 특허로(patent.go.kr) — KIPRIS 아님
- 사용자가 다음 할 일: 출원인 정보 + 도면 PDF + 특허로 가입 + 전자출원
- Claude가 다음 도울 수 있는 일: 도면 mermaid 작성, STAGE 0 가이드, commit hash 조사 (C/D 후보), timeline 분해

---

## 12. 관련 외부 링크

- 특허로 (출원·심사·등록): https://www.patent.go.kr/
- KIPRIS (선행기술 검색): https://www.kipris.or.kr/
- 특허법 30조 (공지예외): https://www.law.go.kr/법령/특허법/제30조
- KIPO 인공지능 발명 심사 가이드라인 (2021): 특허청 홈페이지 → 심사기준 → AI 발명
- KEAPS 다운로드: 특허로 → 자료실 → SW 다운로드

---

## 13. 작업 이력 (Commit log)

```
88af169 docs(patent): add 6 remaining 임시명세서 skeletons (1A/2/3/4/4A/4B)
ba46eba docs(patent): augment with 4 new candidates (A/B/C/D) — 2026-05-10
eb8a625 docs(patent): correct site — 출원은 특허로(patent.go.kr), KIPRIS는 검색 전용
5d99301 docs(patent): fill technical [TODO]s in STAGE 1 spec skeleton
6160fe1 docs(patent): add DIY filing strategy + STAGE 1 spec skeleton + disclosure log
```

---

**End of Handover.**

핸드오버를 받은 새 세션은 본 파일과 `docs/patent/strategy.md`를 차례로 읽으면 전체 맥락을 파악할 수 있습니다.
