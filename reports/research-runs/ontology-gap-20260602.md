# Ontology Gap Report

> Generated: 2026-06-02T23:29:41  
> Wiki scanned: `wiki\entity\prod`  
> Total entities: **313**  
> Active entity types: 9  
> Total relation types: 22  

**Status**: read-only advisor (CLAUDE.md rule #3 opt-in). 
No CR opened, no code changed. Reviewer decides per row.

---

## 1. Entity inventory

| Type | Count | Declared since | Status |
|---|---:|---|---|
| `person` | 26 | v0.1 | 🟢 populated |
| `org` | 86 | v0.1 | 🟢 populated |
| `concept` | 135 | v0.1 | 🟢 populated |
| `document` | 63 | v0.1 | 🟢 populated |
| `event` | 3 | v0.4-α-8 | 🟢 populated |
| `date` | 0 | v0.4-α-8 | ⚪ empty slot |
| `location` | 0 | v0.4-α-8 | ⚪ empty slot |
| `quantity` | 0 | v0.4-α-8 | ⚪ empty slot |
| `project` | 0 | v0.4-α-8 | ⚪ empty slot |

## 2. Empty type slots

Types declared in `ENTITY_TYPES` but with zero entities on disk:

- `date` (since `v0.4-α-8`) — 0 entities
- `location` (since `v0.4-α-8`) — 0 entities
- `quantity` (since `v0.4-α-8`) — 0 entities
- `project` (since `v0.4-α-8`) — 0 entities

**Reviewer action**: confirm ingest pipeline emits these types 
when next document arrives, or run a retro-classification 
script on existing `concept` entities (see §3).

## 3. Re-typing candidates (heuristic — reviewer-gated)

Concepts/documents whose name pattern smells like an α-8 
horizontal type. Heuristic only — false positives expected.

### date (5 candidates)

| Current type | Name | Path |
|---|---|---|
| `concept` | 2024년 2분기 실적 | `wiki\entity\prod\concept\2024년_2분기_실적.md` |
| `concept` | 2025년 4분기 | `wiki\entity\prod\concept\2025년_4분기.md` |
| `concept` | 2026년 투자자 서한 | `wiki\entity\prod\concept\2026년_투자자_서한.md` |
| `concept` | Q1 2026 | `wiki\entity\prod\concept\q1_2026.md` |
| `concept` | Q1 2026 실적 | `wiki\entity\prod\concept\q1_2026_실적.md` |

### event (3 candidates)

| Current type | Name | Path |
|---|---|---|
| `document` | 08_13F공시시즌_기관매집공개 | `wiki\entity\prod\document\08_13f공시시즌_기관매집공개.md` |
| `document` | 09_MorganStanley_MSBT출시 | `wiki\entity\prod\document\09_morganstanley_msbt출시.md` |
| `document` | test_events_dominant | `wiki\entity\prod\document\test_events_dominant.md` |

### location (4 candidates)

| Current type | Name | Path |
|---|---|---|
| `concept` | JFK공항 | `wiki\entity\prod\concept\jfk공항.md` |
| `concept` | 데이터센터 | `wiki\entity\prod\concept\데이터센터.md` |
| `document` | web_business_캐빈워시 누구?_1779524333 | `wiki\entity\prod\document\web_business_캐빈워시_누구__1779524333.md` |
| `document` | web_science_Anthropic  본사 어디고 CE_1779083987 | `wiki\entity\prod\document\web_science_anthropic__본사_어디고_ce_1779083987.md` |

### project (1 candidates)

| Current type | Name | Path |
|---|---|---|
| `concept` | Program-of-Thought | `wiki\entity\prod\concept\program_of_thought.md` |

### quantity (1 candidates)

| Current type | Name | Path |
|---|---|---|
| `concept` | Jina Code Embeddings 1.5B | `wiki\entity\prod\concept\jina_code_embeddings_1_5b.md` |


## 4. UNRESOLVED relation targets (high-value ingest candidates)

**Total distinct unresolved targets: 12**  
Top 30 by reference count:

| Target name | Ref count | Referenced by (sample) |
|---|---:|---|
| TESLA | 3 | ARK Invest, BYD, Wolfe Research |
| 블랙록 | 2 | 지정학적 변화, Larry Fink |
| Optimus | 2 | Tesla, Inc. (TSLA), Elon Musk |
| DPAI Arena | 1 | SWE-bench |
| 개체 | 1 | 그래프 알고리즘 |
| 머신러닝 | 1 | 딥러닝 |
| 피지컬 AI | 1 | 에이전트 AI |
| IT | 1 | 인공지능 |
| 벡터 DB | 1 | 코드 임베딩 |
| 테스트 및 기술 분야 | 1 | NI |
| Palantir | 1 | USDA |
| SpaceX | 1 | xAI |

**Reviewer action**: high-ref entities are likely real entities 
the corpus depends on; consider triggering a targeted ingest 
or wiki extraction to create them.

## 5. Relation type usage distribution

**Used relations**: 11 / 22 declared

| Relation | Count | Label |
|---|---:|---|
| `RELATED_TO` | 527 | 관련 |
| `관련` | 254 | — |
| `PRODUCES` | 27 | 생산 |
| `PART_OF` | 17 | 구성 |
| `BELONGS_TO_INDUSTRY` | 16 | 분야 |
| `BELONGS_TO` | 12 | 소속 |
| `IS_A` | 10 | 분류 |
| `FOUNDED_BY` | 7 | 설립됨 |
| `WORKS_AT` | 4 | 근무 |
| `RESEARCHES` | 4 | 연구 |
| `HAS_PART` | 1 | — |

**Declared but unused** (13):

`HAPPENED_ON`, `HAS_CREDENTIAL`, `HAS_SECRET`, `INVOLVES`, `KNOWS_PASSWORD`, `LOCATED_IN`, `MEASURED_AS`, `OCCURRED_AT`, `OPERATES_IN`, `OWNS_PRIVATE`, `STUDIES`, `TEACHES`, `WORKED_ON`

**Reviewer note**: unused relation types are either 
(a) freshly added in this cycle and ingest hasn't surfaced them 
yet, (b) genuinely useless and candidates for deprecation, or 
(c) the heuristic ingest layer doesn't know to emit them. 
Distinguish before deprecating.

## 6. Type/relation mismatches (schema drift signal)

Entities using a relation not in `ALLOWED_RELATIONS` for 
their `entity_type`. Sample of 21:

| Entity | Type | Relation (not allowed) | Target | Path |
|---|---|---|---|---|
| STRC | `concept` | `BELONGS_TO` | NASDAQ | `wiki\entity\prod\concept\strc.md` |
| Archer Aviation | `org` | `BELONGS_TO_INDUSTRY` | eVTOL | `wiki\entity\prod\org\archer_aviation.md` |
| EASA | `org` | `BELONGS_TO_INDUSTRY` | eVTOL | `wiki\entity\prod\org\easa.md` |
| FAA | `org` | `BELONGS_TO_INDUSTRY` | eVTOL | `wiki\entity\prod\org\faa.md` |
| Global Trend & Technology | `org` | `BELONGS_TO_INDUSTRY` | 양자보안 | `wiki\entity\prod\org\global_trend___technology.md` |
| NI | `org` | `BELONGS_TO_INDUSTRY` | 테스트 및 기술 분야 | `wiki\entity\prod\org\ni.md` |
| Palantir Technologies (PLTR) | `org` | `WORKS_AT` | Alex Karp | `wiki\entity\prod\org\palantir_technologies__pltr_.md` |
| PLTR | `org` | `BELONGS_TO_INDUSTRY` | AIP | `wiki\entity\prod\org\pltr.md` |
| Tesla, Inc. (TSLA) | `org` | `BELONGS_TO_INDUSTRY` | 에너지 사업 | `wiki\entity\prod\org\tesla__inc___tsla_.md` |
| (주)파네시아 | `org` | `BELONGS_TO_INDUSTRY` | 생성형 AI | `wiki\entity\prod\org\_주_파네시아.md` |
| 마이크론 테크놀로 | `org` | `BELONGS_TO_INDUSTRY` | AI | `wiki\entity\prod\org\마이크론_테크놀로.md` |
| 마이크론 테크놀로 | `org` | `BELONGS_TO_INDUSTRY` | 데이터센터 | `wiki\entity\prod\org\마이크론_테크놀로.md` |
| 블랙록 IBIT | `org` | `PART_OF` | 미국 스팟 BTC ETF | `wiki\entity\prod\org\블랙록_ibit.md` |
| 피델리티 FBTC | `org` | `PART_OF` | 미국 스팟 BTC ETF | `wiki\entity\prod\org\피델리티_fbtc.md` |
| Elon Musk | `person` | `FOUNDED_BY` | Space Exploration Technologies | `wiki\entity\prod\person\elon_musk.md` |
| Elon Musk | `person` | `FOUNDED_BY` | xAI | `wiki\entity\prod\person\elon_musk.md` |
| Elon Musk | `person` | `FOUNDED_BY` | Neuralink | `wiki\entity\prod\person\elon_musk.md` |
| Larry Fink | `person` | `PRODUCES` | 2026년 투자자 서한 | `wiki\entity\prod\person\larry_fink.md` |
| Marc Tarpenning | `person` | `FOUNDED_BY` | Tesla, Inc. | `wiki\entity\prod\person\marc_tarpenning.md` |
| Martin Eberhard | `person` | `FOUNDED_BY` | Tesla, Inc. | `wiki\entity\prod\person\martin_eberhard.md` |

**Reviewer action**: either widen `ALLOWED_RELATIONS[type]` to 
include the relation (if it's a legitimate pattern) or fix the 
ingest path that emitted the bad triple.

## 7. Summary action list (reviewer's TODO)

1. Verify ingest emits 4 empty types: `date`, `location`, `quantity`, `project`
2. Review 14 re-typing candidates across 5 types
3. Triage 12 UNRESOLVED targets (top 10 high-ref)
4. Decide fate of 13 declared-but-unused relations
5. Resolve 21+ schema drift mismatches

---

*Generated by `scripts/research/ontology_gap_report.py` — read-only advisor. 
Per CLAUDE.md rule #3, no automatic action taken. Reviewer decides every row.*