# 아랍어 파이프라인 능력 감사 — 층별 실측

**날짜**: 2026-08-22
**계기**: Ali Afana 엔지니어링 4건 후속 보고(③) 작성 중, "우리 스택에
아랍어 키워드 게이트가 없다"는 비재현 결과가 실제로는 훨씬 넓은 scope
한계의 일부인지 확인할 필요가 생겼다.
**방법**: 주장을 문서에서 읽지 않고 **소스에 대조 + 실제 실행**. 구
모듈은 git 이력에서 꺼내 직접 돌렸다.
**한 줄 결론**: 저장·검색 층은 아랍어를 감당한다. **언어 판정과 토큰화
층이 못 감당한다.** 따라서 black-box adversarial sweep 은 돌릴 수 있고
실제로 돌았지만, 그것은 "영어/한국어와 동등한 조건의 아랍어"가 아니다.

---

## 1. 언어 판정 — 아랍어라는 분류가 존재하지 않는다

`core/i18n.py::detect_language` 는 **한글 음절 수 vs ASCII 알파벳 수**만
센다. 아랍 문자는 어느 쪽에도 안 잡히므로 두 카운트가 모두 0 이 되고,
타이브레이커(`korean_chars >= en_chars`)가 `"ko"` 로 보낸다. 라틴 문자가
조금이라도 섞이면 `"en"` 으로 뒤집힌다.

실행 결과:

| 입력 | `detect_language` |
|---|---|
| MSA 아랍어 `ما هي سياسة الاسترجاع الخاصة بكم؟` | `ko` |
| arabizi `e3teeni el pants b 120 bs...` | `en` |
| 아랍어 + 영어 상품명 혼용 | `en` |

소비처 7개 모듈 (`detect_language` / `is_korean`):

`reasoning/planner.py` · `reasoning/engine_synth.py` ·
`reasoning/engine_memory.py` · `reasoning/verify.py` ·
`reasoning/reflect/loop.py` · `reasoning/pipeline_synth/{generator,softener}.py` ·
`retrieval/query_rewriter.py`

→ 계획 · 질의 재작성 · 합성 · 검증 · 반영 루프의 프롬프트 스캐폴딩이
전부 한국어 모드로 선택된다.

`verify.py:459` 는 여기서 사용자에게 직접 노출된다:
```python
return _BLOCK_MSG_KO if _is_korean(query) else _BLOCK_MSG_EN
```
→ MSA 아랍어 질의가 차단되면 **한국어 차단 메시지**를 받는다.

## 2. 토큰화 — 아랍어는 0 토큰

세 곳이 같은 한글/ASCII 전용 클래스를 쓴다.

| 위치 | 함수 | 역할 |
|---|---|---|
| `core/retrieval_engine.py:238` | `_rule_based_fallback` | LLM 엔티티 추출 실패 시 폴백 |
| `core/query_expander.py:127` | `_tokenize_simple` | 질의 확장 보조 |
| `core/orchestrator.py:37` | `_extract_keywords` | multi-query 의 keyword 변형 |

```python
re.findall(r"[가-힣A-Za-z0-9]+", "ما هي سياسة الاسترجاع الخاصة بكم؟")  # → []
```

**파급 범위를 정확히 할 것.** `orchestrator.py:92-95` 는
`("original", …) / ("expanded", …) / ("keyword", …)` 3-질의 구성이고,
`original` 은 원문 그대로 들어간다. 즉 **벡터 검색 자체는 죽지 않는다.**

단 **3개 중 2개를 잃는다** (초안 1차의 "1개 손실" 은 과소 서술이었다):

- `query_expander.py:183` — 토큰이 0 이면 `return query`, 즉 확장 포기.
  → `expanded == original` → `orchestrator.py:101` 에서 **중복 제거**
- `_extract_keywords` → 빈 문자열 → `if q_clean and …` 에서 **탈락**

실증:

| 질의 | 유효 질의 수 |
|---|---|
| 아랍어 | **1** (`original` 만) |
| 한국어 | 2 (`original` + `expanded`) |

"아랍어 검색 불가" 는 과한 서술이고, 정확히는 **구조적으로 불리한
조건**이다 — 아랍어는 1-질의로, 한국어는 2~3-질의로 검색한다.

## 3. 그래프 층 — 여기가 실질적으로 막힌다

`core/retrieval_engine.py:217` `_safe_json_load` 의 sanitizer:

```python
text = re.sub(r'[^a-zA-Z0-9가-힣\[\]{},:"_\-\.\n\t ]', "", text)
```

LLM 이 아랍어 엔티티명을 반환하면 이름이 지워진다. 실행 확인:

```
입력  [{"name": "سياسة الاسترجاع", "type": "concept"},
       {"name": "Cotton Shirt",     "type": "product"}]
결과  [{"name": " ",                "type": "concept"},
       {"name": "Cotton Shirt",     "type": "product"}]
```

아랍어 엔티티는 **공백 한 칸**으로 축소되고 영어 엔티티만 살아남는다.

**범위 한정**: `_safe_json_load` 소비처는 `retrieval_engine.py:172`
`extract_entities` 하나뿐이고, `graph_rag_engine.py:77` 은 거기로 위임할
뿐이다. 즉 이것은 **query-time 엔티티 추출** 경로다. **문서 인제스트
경로는 별개**이며(`wiki_generator/_ingestion/mixin.py` →
`_frontmatter.create_entity_file`) **본 감사에서 추적하지 않았다.**
"아랍어 코퍼스에서 그래프 노드가 안 생긴다" 로 일반화하지 말 것.

## 4. 보안 층

`core/security_layer/_policies.py` 의 `ATTACK_PATTERNS`(31) +
`ATTACK_REGEX`(13) 에 아랍 문자 0건. 더 넓게 스캔해도 `core/` 트리
전체에서 아랍 문자를 담은 라인은 `input_normalization.py` 의 docstring
4줄뿐이며, `git blame` 상 전부 `8c6f726`(발견 ③ 수정)에서 왔다.

## 5. UI 층

- `frontend/` 전체에 `dir="rtl"` / `direction: rtl` / `unicode-bidi` **0건**
  (유일한 `rtl` 매치는 `shortly` 라는 단어의 부분문자열)
- **5개 페이지 전부** `<html lang="ko">` 하드코딩 (admin / graph /
  index / intro / workspace)

## 6. 작동하는 것 (과소평가 금지)

| 층 | 상태 |
|---|---|
| 임베딩 | `paraphrase-multilingual-MiniLM-L12-v2` 기본값 (`config.py:265`). 다국어 모델이며 모델 카드 기준 아랍어 포함 — 여기서는 모델 다운로드가 막혀 있어 벡터 자체는 미실측 |
| 벡터 검색 | `original` 질의 경로로 작동 |
| ID 생성 / ABAC 값 패턴 | 파이썬 `\w` 는 유니코드라 아랍어 통과 (실행 확인) |
| 입력 정규화 게이트 · 채점 fold | 발견 ①③ 수정으로 override span / tatweel / presentation form / alef 계열 처리됨 |

---

## 7. Track 2c 표에 대한 직접 함의 — **본 감사의 새 발견**

기존 감사들이 짚지 않은 지점. 픽스처 18건을 런타임 게이트에 통과시킨
뒤 `detect_language` 를 돌렸다.

**결과: 12 `ko` / 6 `en` 으로 갈리고, 갈림이 픽스처의 언어 라벨과
일치하지 않는다.**

| 픽스처 lang | → `ko` | → `en` |
|---|---|---|
| `ar-LV` | 5 | **1** |
| `msa` | 2 | **1** |
| `mixed` | 4 | 2 |
| `arabizi` | 0 | 3 |

즉 **같은 언어 라벨의 케이스들이 서로 다른 프롬프트 스캐폴딩으로
처리됐다.** 일괄 한국어 모드보다 나쁘다 — 일관성이 없고, 갈림의 기준은
라틴 문자가 우연히 몇 개 섞였느냐다.

**재측정 유효성과 표 해석을 구분할 것** (이 구분이 핵심):

- **같은 케이스의 전/후 재측정** → 텍스트가 안 바뀌므로 언어 판정도 안
  바뀐다. 언어 요인은 **상수**이고 salt 효과 분리를 방해하지 않는다.
  **재측정은 여전히 유효하다.**
- **표의 행 간 / 언어군 간 비교** → 케이스마다 값이 다르므로 **교란**.
  행 간 차이가 언어 차이가 아니라 문자 구성 차이를 반영할 수 있다.

따라서 발견 ④ 재측정 게이트에 "오염 요인이 2개" 라고 쓰는 것은 과하다.
정확한 서술은 위의 두 줄이다.

## 8. 하지 않은 것 / 별건

아랍어 언어 판정 추가는 **별건이고 규모가 작지 않다** —
`detect_language` 3분류화 + 소비처 7곳 + 토큰화 3곳 + sanitizer +
`verify` 차단 메시지 + RTL/`lang` 속성. mother-platform 룰(도메인·언어
확장) 상 v0.6 스코프 논의가 선행이다. **Ali 답신에 수정 약속을 넣지
않는다** — 측정된 사실만 보고한다.
