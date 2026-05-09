# [임시명세서 초안] STAGE 4 — Trait Pair Auto-rebalance + Threshold Prompt Directive

> 본 문서는 STAGE 4 (점수 2/5) 임시명세서 작성을 위한 skeleton입니다.
> 특허로(patent.go.kr) 전자출원 시 본 문서를 기반으로 PDF·hwp로 전환하여 첨부하십시오.
> 작성 시 [TODO] 마커를 모두 제거·채워주세요.
>
> **참고 자료**: `core/character_profile.py:17-66, 68-97` (구현 완료).

---

## 발명의 명칭
**쌍 합 보존 invariant 자동 재조정과 threshold prompt directive 주입을 결합한 대화형 에이전트 캐릭터 프로파일링 방법**
(영문: Character Profiling Method for Conversational Agents via Sum-Invariant Pair Rebalancing and Threshold-Based Prompt Directive Injection)

## 출원인
[TODO: 성명 / 주소 / 주민번호 또는 외국인등록번호]

## 발명자
[TODO: 성명 / 주소]

## 공지예외 주장
- 공개일자: 2026-05-05
- 공개매체: GitHub public repository (https://github.com/Hashevolution/James-RAG-Evol)
- 공개주체: 발명자 본인
- 공지예외 만료일: **2027-05-04**
- 증빙: `docs/patent/disclosure_log.txt`

---

## 1. 기술 분야

본 발명은 대화형 에이전트(챗봇)의 캐릭터 성향(trait) 프로파일링에 관한 것으로, 보다 구체적으로는 N개의 trait 쌍에 대해 각 쌍의 합이 1.0이 되는 invariant을 유지하면서 자동 재조정하고, trait 값을 임계값으로 분류해 prompt directive로 변환·주입하는 방법에 관한 것이다.

## 2. 배경 기술

### 2.1 기존 캐릭터 프로파일링 한계

ChatGPT Custom Instructions, Character.AI, ChatBot persona 시스템 등은 다음 한계를 가진다:
- (i) Trait이 독립 변수로 다뤄짐 — "탐구심 0.9 + 집중력 0.9" 같은 모순 조합이 가능
- (ii) Trait → prompt 변환이 정성적 — 설계자가 매 trait마다 instruction을 직접 작성
- (iii) 조정 시 다른 trait의 일관성이 깨짐
- (iv) Trait 개수가 늘어나면 운영자 부담 기하급수 증가

### 2.2 본 발명이 다루는 시나리오

운영자가 챗봇의 성향을 조정한다. "탐구심"을 0.9로 높이면, 본 발명에서 "집중력"이 자동으로 0.1로 조정되어 두 trait의 균형이 보존된다. Trait 값이 0.7 초과면 강한 directive가 prompt에 자동 주입되고, 0.3 미만이면 반대 방향 directive가 주입된다. 운영자는 N개 trait를 일일이 instruction으로 변환할 필요 없이 숫자 슬라이더만 조작하면 된다.

## 3. 해결하고자 하는 과제

1. Trait 쌍의 합 invariant을 유지하면서 한 trait 변경 시 다른 trait 자동 재조정
2. 독립 trait (쌍 제약 없음) 와 쌍 trait를 동일 시스템 내에서 분리 관리
3. Trait 값을 임계값으로 분류해 prompt directive로 자동 변환
4. 운영자가 직접 instruction을 쓰지 않아도 되는 추상화

## 4. 과제의 해결 수단

### 4.1 Trait Pair Sum-Invariant

각 쌍에 대해 합이 1.0이 되는 invariant을 정의 (`core/character_profile.py:17-29`):

| 그룹 | Trait 1 | Trait 2 | 기본값 | Invariant |
|------|---------|---------|--------|-----------|
| A | curiosity (탐구심) | focus (집중력) | 0.5 / 0.5 | sum = 1.0 |
| B | caution (신중함) | boldness (과감함) | 0.7 / 0.3 | sum = 1.0 |
| C | analytical (분석력) | intuitive (직관력) | 0.6 / 0.4 | sum = 1.0 |
| D | independent (독립성) | collaborative (협력성) | 0.5 / 0.5 | sum = 1.0 |

### 4.2 독립 Trait (E 그룹)

쌍 invariant이 없는 독립 trait — 다른 trait와 무관하게 조정 가능 (`core/character_profile.py:26-28`):

| 그룹 | Trait | 기본값 |
|------|-------|--------|
| E | security (보안의식) | 0.9 |
| E | creativity (창의성) | 0.5 |
| E | empathy (공감능력) | 0.5 |

총 11개 trait = 4 쌍 (8개) + 3 독립.

### 4.3 자동 재조정 (`core/character_profile.py:55-66`)

```python
_OPPONENTS = {
    "curiosity": "focus",     "focus": "curiosity",
    "caution": "boldness",    "boldness": "caution",
    "analytical": "intuitive","intuitive": "analytical",
    "independent": "collaborative", "collaborative": "independent",
}
# E 그룹 (security, creativity, empathy) 은 _OPPONENTS에 부재 → 재조정 없음

def set_trait(self, trait_id: str, value: float) -> Dict:
    if trait_id not in TRAITS:
        return {"error": f"알 수 없는 성향: {trait_id}"}
    value = max(0.0, min(1.0, round(value, 3)))
    self._values[trait_id] = value
    opp = _OPPONENTS.get(trait_id)
    if opp:                                   # 쌍 trait인 경우
        self._values[opp] = round(1.0 - value, 3)
    self._save()
    return {"trait_id": trait_id, "value": value, "opponent": opp}
```

### 4.4 Threshold Prompt Directive 주입 (`core/character_profile.py:68-97`)

Trait 값에 따라 자동으로 prompt directive 생성:

```python
def get_prompt_modifiers(self) -> str:
    p = self._values
    lines = []

    # 0.7 이상 → 강한 directive 주입
    if p.get("caution", 0.5) > 0.7:
        lines.append("확실한 정보만 포함하고 불확실한 부분은 명시하라.")
    if p.get("curiosity", 0.5) > 0.7:
        lines.append("관련된 흥미로운 주제도 함께 제시하라.")
    if p.get("analytical", 0.5) > 0.7:
        lines.append("논리적 근거와 데이터를 중심으로 분석하라.")
    if p.get("empathy", 0.5) > 0.7:
        lines.append("사용자의 감정과 맥락을 고려해서 답변하라.")
    if p.get("creativity", 0.5) > 0.7:
        lines.append("창의적이고 다양한 관점에서 접근하라.")
    if p.get("security", 0.5) > 0.7:
        lines.append("보안 위험성과 잠재적 취약점을 항상 함께 언급하라.")

    # 0.3 이하 → 반대 방향 directive
    if p.get("caution", 0.5) < 0.3:
        lines.append("다양한 가능성을 열어두고 과감하게 제안하라.")

    return " ".join(lines)
```

운영자는 trait 슬라이더만 조작하고, prompt directive는 자동 생성·주입.

## 5. 효과

1. **모순 조합 자동 방지** — pair invariant이 운영자의 비현실적 조합 입력을 차단
2. **운영자 부담 감소** — 11개 trait를 instruction 11개로 작성할 필요 없음
3. **독립/쌍 분리 관리** — 보안의식 같은 절대 가치는 독립 유지, 성향 균형은 쌍으로 관리
4. **Threshold 추상화** — 0.7/0.3 경계로 binary directive on/off, 비전문 운영자도 직관적 조작 가능
5. **재현성** — 동일 trait 값 → 동일 prompt directive, 응답 행동 예측 가능

## 6. 청구범위

### 청구항 1 (방법)

대화형 에이전트의 캐릭터 프로파일링 방법으로서,
(a) N개 trait 쌍과 M개 독립 trait를 정의하는 단계 (각 쌍은 두 trait의 합이 1.0인 invariant을 가짐);
(b) 운영자가 쌍 내 한 trait를 X 값으로 설정 시, 같은 쌍의 opposing trait를 (1.0 − X)로 자동 재조정하는 단계;
(c) 독립 trait는 다른 trait와 무관하게 0~1 범위에서 자유 설정되는 단계;
(d) 모든 trait 값을 두 임계값 (예: 0.7과 0.3) 으로 분류하여, 임계 초과 trait에 대해 강한 directive 문장을, 임계 미만 trait에 대해 반대 방향 directive 문장을 prompt에 자동 주입하는 단계
를 포함하는 것을 특징으로 하는, 캐릭터 프로파일링 방법.

### 청구항 2 (시스템)

대화형 에이전트로서,
- (1) N개 trait 쌍과 M개 독립 trait의 정의 사전,
- (2) 한 trait 변경 시 opposing trait를 자동 재조정하는 set_trait 모듈,
- (3) trait 값을 prompt directive로 변환하는 modifier 생성 모듈,
- (4) LLM 호출 직전에 modifier를 system prompt에 주입하는 prompt builder
를 포함하는 것을 특징으로 하는 시스템.

### 청구항 3 (종속 — 4 쌍 + 3 독립)

청구항 1에 있어서, N=4이고 M=3이며, 4 쌍은 (curiosity ↔ focus), (caution ↔ boldness), (analytical ↔ intuitive), (independent ↔ collaborative) 이고, 3 독립 trait는 (security, creativity, empathy) 인 것을 특징으로 하는 방법.

### 청구항 4 (종속 — Sum-Invariant 강제)

청구항 1에 있어서, set_trait 모듈은 한 trait를 X로 설정한 후 항상 opposing trait를 (1.0 − X)로 round-to-3-decimal 정밀도로 강제 설정하여, 운영자가 두 trait를 독립적으로 설정해 invariant을 깨뜨릴 수 없는 방법.

### 청구항 5 (종속 — Threshold)

청구항 1에 있어서, 두 임계값은 0.7 과 0.3 이며, 0.7 초과 trait는 해당 방향의 강한 directive를, 0.3 미만 trait는 반대 방향의 directive를 주입하고, 0.3~0.7 범위의 trait는 directive를 주입하지 않는 것을 특징으로 하는 방법.

### 청구항 6 (종속 — Directive 사전)

청구항 1에 있어서, 각 trait는 강한 directive 문장과 반대 방향 directive 문장의 두 가지가 사전에 매핑되어, 동일 trait 값은 동일 directive 문장을 생성하는 방법.

### 청구항 7 (종속 — 0~1 클램프)

청구항 1에 있어서, set_trait 모듈은 입력 값을 max(0.0, min(1.0, value))로 클램프하고 round-to-3 정밀도로 정규화하여 보존하는 방법.

### 청구항 8 (종속 — Audit/저장)

청구항 2에 있어서, set_trait 모듈은 매 변경마다 trait 값 dictionary를 디스크에 영속화하여 시스템 재시작 후에도 trait 상태가 보존되는 시스템.

### 청구항 9 (종속 — UI)

청구항 2에 있어서, 운영자에게 노출되는 UI는 11개 trait 각각에 0~1 슬라이더를 제공하고, 쌍 trait의 한쪽 슬라이더 조작 시 opposing trait의 슬라이더가 동시에 1−X 값으로 자동 이동하는 시스템.

### 청구항 10 (종속 — 그룹 표시)

청구항 1에 있어서, 각 trait는 그룹 식별자(A/B/C/D 쌍 또는 E 독립)와 한국어/영어 label, icon을 메타데이터로 가지며, UI는 그룹 단위로 trait를 묶어 표시하는 방법.

## 7. 도면 (작성 필요)

- **도면 1**: 11개 trait 구성도 — 4 쌍 (A/B/C/D) + 3 독립 (E)
- **도면 2**: set_trait 자동 재조정 — 슬라이더 조작 → opposing trait 동시 이동
- **도면 3**: Threshold → directive 매핑 — 0~1 축에 0.3 / 0.7 경계, 각 영역에서의 directive 종류
- **도면 4**: prompt builder 흐름 — trait 값 dict → modifier 문자열 → system prompt 주입

## 8. 실시예 (Working Example)

`core/character_profile.py:17-97` 전체. 핵심:

```python
TRAITS = {
    "curiosity":     {"label":"Curiosity",    "label_ko":"탐구심",   "group":"A","default":0.5},
    "focus":         {"label":"Focus",         "label_ko":"집중력",   "group":"A","default":0.5},
    "caution":       {"label":"Caution",       "label_ko":"신중함",   "group":"B","default":0.7},
    "boldness":      {"label":"Boldness",       "label_ko":"과감함",   "group":"B","default":0.3},
    "analytical":    {"label":"Analytical",    "label_ko":"분석력",   "group":"C","default":0.6},
    "intuitive":     {"label":"Intuitive",     "label_ko":"직관력",   "group":"C","default":0.4},
    "independent":   {"label":"Independent",   "label_ko":"독립성",   "group":"D","default":0.5},
    "collaborative": {"label":"Collaborative", "label_ko":"협력성",   "group":"D","default":0.5},
    "security":      {"label":"Security",      "label_ko":"보안의식", "group":"E","default":0.9},
    "creativity":    {"label":"Creativity",    "label_ko":"창의성",   "group":"E","default":0.5},
    "empathy":       {"label":"Empathy",       "label_ko":"공감능력", "group":"E","default":0.5},
}

_OPPONENTS = {
    "curiosity":"focus", "focus":"curiosity",
    "caution":"boldness", "boldness":"caution",
    "analytical":"intuitive", "intuitive":"analytical",
    "independent":"collaborative", "collaborative":"independent",
}

def set_trait(self, trait_id: str, value: float) -> Dict:
    value = max(0.0, min(1.0, round(value, 3)))
    self._values[trait_id] = value
    opp = _OPPONENTS.get(trait_id)
    if opp: self._values[opp] = round(1.0 - value, 3)
    self._save()
    return {"trait_id": trait_id, "value": value, "opponent": opp}
```

## 9. 산업상 이용 가능성

본 발명은 챗봇 페르소나 설정, 게임 NPC 성향, 가상 비서 캐릭터, AI 컴패니언 앱 등 다양한 대화형 AI 환경에서 운영자가 직관적으로 캐릭터 성향을 조정하는 데 산업상 이용 가능하다.

---

## 10. 출원 시 체크리스트

- [ ] 발명자/출원인 정보 기재
- [ ] 도면 1~4 작성 (`assets/patent/stage4-figs/` 권장)
- [ ] §6 청구항 한국어 법률 용어 검수
- [ ] 공지예외 적용 신청서 별도 첨부
- [ ] 출원료 6만원 (개인 감면 시 1.8만원) 납부

---

**End of skeleton.**
