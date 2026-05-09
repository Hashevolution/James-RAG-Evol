# [임시명세서 초안] STAGE 2 — Feedback Shadow Accumulation

> 본 문서는 STAGE 2 (점수 2/5) 임시명세서 작성을 위한 skeleton입니다.
> 특허로(patent.go.kr) 전자출원 시 본 문서를 기반으로 PDF·hwp로 전환하여 첨부하십시오.
> 작성 시 [TODO] 마커를 모두 제거·채워주세요.
>
> **참고 자료**: `core/feedback_engine.py:35-151, 241-250` (구현 완료).

---

## 발명의 명칭
**다중 신호 누적 임계 기반 대화형 인공지능 적응 방법 및 시스템**
(영문: Multi-Signal Accumulation and Threshold-Based Adaptation Method for Conversational AI)

## 출원인
[TODO: 성명 / 주소 / 주민번호 또는 외국인등록번호]

## 발명자
[TODO: 성명 / 주소]

## 공지예외 주장
- 공개일자: 2026-05-05 (GitHub public 첫 commit)
- 공개매체: GitHub public repository (https://github.com/Hashevolution/James-RAG-Evol)
- 공개주체: 발명자 본인
- 공지예외 만료일: **2027-05-04**
- 증빙: `docs/patent/disclosure_log.txt`

---

## 1. 기술 분야

본 발명은 대화형 인공지능 시스템의 사용자 피드백 학습에 관한 것으로, 보다 구체적으로는 명시적·암시적 피드백 신호를 7가지 유형으로 분류하여 decay 인자와 임계값으로 누적하고, 임계값 초과 시 응답 경향을 강화 또는 약화하는 방법 및 시스템에 관한 것이다.

## 2. 배경 기술

### 2.1 기존 RLHF의 한계

OpenAI ChatGPT, Anthropic Claude, Google Gemini 등은 RLHF(Reinforcement Learning from Human Feedback)로 학습되지만 다음 한계를 가진다:
- (i) RLHF는 모델 학습 단계에 한 번 적용 — 운영 단계에서 사용자 개별 피드백이 즉시 반영되지 않음
- (ii) 명시 피드백(👍/👎) 외 암시 피드백(추가 질문, 대화 단절) 활용 부재
- (iii) 단일 피드백으로 응답 경향이 변하면 noise·악의적 피드백에 오염되기 쉬움
- (iv) 운영 단계 학습은 catastrophic forgetting 위험

### 2.2 기존 즉시 학습 시스템의 한계

LangChain memory, ChatGPT Custom Instructions 등은 사용자 발화를 그대로 저장하지만:
- 한 번 발화로 시스템 경향이 변함 → 누적 검증 부재
- 피드백 유형 분류 부재
- 시간 감쇠 부재 → 오래된 피드백이 영원히 영향

## 3. 해결하고자 하는 과제

1. 명시·암시 피드백을 다양한 유형으로 분류해 가중치 부여
2. 단일 피드백으로 시스템 경향이 변하지 않고 누적 임계값 초과 시에만 변경
3. 시간 감쇠로 오래된 피드백 영향 자연 약화
4. 응답 방향(direction)별로 별도 누적해 무관 주제 간 누설 방지

## 4. 과제의 해결 수단

### 4.1 7-Type 피드백 신호 분류

본 발명은 사용자 발화를 다음 7개 유형으로 분류한다 (`core/feedback_engine.py:35-43`):

| 유형 | 가중치 | 검출 패턴 |
|------|--------|----------|
| explicit_positive | +1.0 | 👍 버튼 클릭 또는 "좋아", "잘했어", "맞아", "훌륭", "정확", "고마워" |
| flow_continue | +0.3 | 자연스러운 대화 지속 (negative/correction 패턴 부재) |
| implicit_positive | +0.2 | 직전 응답 후 추가 질문 + 길이 5자 이상 + "?" 포함 |
| explicit_negative | -1.0 | 👎 버튼 또는 "싫어", "틀렸", "잘못", "별로" |
| correction | -0.8 | "그게 아니라", "수정해", "고쳐", "다시 해줘" |
| strong_objection | -0.6 | "완전히 틀렸", "말도 안돼", "이해 못했" |
| implicit_negative | -0.3 | 대화 단절 또는 주제 급전환 |

### 4.2 Direction-Scoped Shadow Accumulator

각 (mode, query_topic_hash) 조합을 conversational direction으로 식별하고, direction별로 별도 score를 누적:

```python
# core/feedback_engine.py:107-151
def accumulate(self, direction_id: str, signal: str, query: str = "") -> Dict:
    delta     = FEEDBACK_SIGNALS.get(signal, 0.0)
    old_score = self._shadow[direction_id]
    new_score = (old_score + delta) * DECAY        # decay 0.9

    self._shadow[direction_id] = new_score

    # 임계값 판단
    action = "none"
    if new_score >= REINFORCE_TH:                  # +2.0
        action = "reinforce"
        self._apply_reinforce(direction_id, new_score)
        self._shadow[direction_id] = 0.0           # 리셋
    elif new_score <= WEAKEN_TH:                   # -2.0
        action = "weaken"
        self._apply_weaken(direction_id, new_score)
        self._shadow[direction_id] = 0.0
    return {"signal": signal, "score": new_score, "action": action}
```

### 4.3 Decay 인자

각 신규 신호 가산 후 `× 0.9` decay가 적용되어:
- 오래된 신호의 영향이 자연 감소
- 누적이 무한히 증가하지 않음 (수렴 ≤ delta / (1 - decay) = 10 × delta)
- 단일 강한 신호로 임계 도달 불가능 (+1.0 신호 단독 → max 0.9, < 2.0)

### 4.4 강화/약화 액션

- **Reinforce** (`new_score ≥ +2.0`): 해당 direction의 응답 패턴을 preferences DB에 저장 → 차후 동일 direction의 query에 우선 적용
- **Weaken** (`new_score ≤ -2.0`): 해당 direction의 응답 패턴 재검토 제안 → 운영자 검토 큐에 추가
- 임계 도달 후 score는 0으로 리셋되어 재누적 시작

## 5. 효과

1. **단일 피드백 오염 방지** — 누적 임계 ≥2.0 도달 필요, 약 3~5회 일관된 신호 필요
2. **암시 피드백 활용** — 명시 버튼 외 자연 발화에서도 학습
3. **시간 감쇠** — 오래된 피드백이 자연 약화, catastrophic forgetting 회피
4. **Direction 격리** — 한 주제 피드백이 다른 주제로 누설되지 않음
5. **Audit 가능** — 모든 누적·액션이 history에 기록

## 6. 청구범위

### 청구항 1 (방법)

대화형 인공지능 시스템의 사용자 피드백 적응 방법으로서,
(a) 사용자 발화로부터 N개 사전 정의된 피드백 유형 (각 [-1.0, +1.0] 범위의 가중치를 가짐) 중 하나를 패턴 매칭으로 검출하는 단계;
(b) (mode, query_topic_hash) 합성 키로 식별되는 conversational direction별로 shadow accumulator를 유지하는 단계;
(c) 신규 피드백 가중치를 직전 누적값에 더한 후 사전 정의된 decay 인자를 곱하여 새 누적값을 산출하는 단계;
(d) 새 누적값이 양의 임계값 이상이면 reinforce 액션, 음의 임계값 이하이면 weaken 액션을 트리거하고 누적값을 0으로 리셋하는 단계
를 포함하는 것을 특징으로 하는, 다중 신호 누적 적응 방법.

### 청구항 2 (시스템)

대화형 인공지능 시스템으로서,
- (1) N개 피드백 유형 가중치 사전,
- (2) 발화로부터 유형을 검출하는 detector,
- (3) direction별 shadow accumulator,
- (4) decay 인자와 임계값으로 reinforce/weaken을 결정하는 decision module,
- (5) 액션 결과를 preferences DB 또는 검토 큐에 적용하는 applier
를 포함하는 것을 특징으로 하는, 누적 기반 적응 시스템.

### 청구항 3 (종속 — 7 유형)

청구항 1에 있어서, 상기 N=7이며 다음 유형을 포함하는 것을 특징으로 하는 방법: explicit_positive (+1.0), flow_continue (+0.3), implicit_positive (+0.2), explicit_negative (-1.0), correction (-0.8), strong_objection (-0.6), implicit_negative (-0.3).

### 청구항 4 (종속 — Decay 0.9)

청구항 1에 있어서, decay 인자는 0.9이며 신규 신호 가산 후 적용되는 것을 특징으로 하는 방법.

### 청구항 5 (종속 — 임계값 ±2.0)

청구항 1에 있어서, 양의 임계값은 +2.0, 음의 임계값은 -2.0인 것을 특징으로 하는 방법.

### 청구항 6 (종속 — Direction 식별)

청구항 1에 있어서, conversational direction은 시스템의 응답 모드와 query topic hash의 합성 키로 식별되어 무관 주제 간 피드백 누설을 방지하는 것을 특징으로 하는 방법.

### 청구항 7 (종속 — 암시 피드백)

청구항 3에 있어서, implicit_positive는 직전 응답 후 사용자가 추가 질문(길이 임계 이상 + "?" 포함)을 보낸 경우 검출되는 것을 특징으로 하는 방법.

### 청구항 8 (종속 — 패턴 매칭)

청구항 3에 있어서, explicit_positive와 explicit_negative는 한국어/영어 키워드 사전 매칭으로 검출되며, correction과 strong_objection은 별도 패턴 사전으로 분리 검출되어 동일 발화에서 가장 강한 부정 신호 우선 채택되는 방법.

### 청구항 9 (종속 — Reinforce 적용)

청구항 1에 있어서, reinforce 액션은 해당 direction의 응답 패턴을 preferences DB에 영구 저장하여 동일 direction의 차후 query에 우선 적용되는 방법.

### 청구항 10 (종속 — Audit)

청구항 1에 있어서, 모든 신규 신호·누적값·액션은 jsonl history에 timestamp와 함께 기록되어 사후 검증 가능한 방법.

## 7. 도면 (작성 필요)

- **도면 1**: 7-type signal 검출 흐름 — 발화 → 우선순위 매칭 → 가중치 산출
- **도면 2**: Direction-scoped accumulator 구조 — (mode, topic_hash) → score map
- **도면 3**: Decay + threshold dynamics — score over time, 강화/약화 트리거 시점
- **도면 4**: Reinforce/Weaken 액션 적용 흐름 — preferences DB 저장 / 검토 큐 추가

## 8. 실시예 (Working Example)

`core/feedback_engine.py:35-151` 핵심 발췌:

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

class FeedbackEngine:
    def detect(self, query, prev_answer="", explicit=None):
        if explicit == "positive": return "explicit_positive"
        if explicit == "negative": return "explicit_negative"
        q = query.lower().strip()
        if any(k in q for k in _OBJ_KO):  return "strong_objection"
        if any(k in q for k in _COR_KO):  return "correction"
        if any(k in q for k in _NEG_KO + _NEG_EN): return "explicit_negative"
        if any(k in q for k in _POS_KO + _POS_EN): return "explicit_positive"
        if prev_answer and len(query) > 5 and "?" in query:
            return "implicit_positive"
        return "flow_continue"

    def accumulate(self, direction_id, signal, query=""):
        delta = FEEDBACK_SIGNALS.get(signal, 0.0)
        new_score = (self._shadow[direction_id] + delta) * DECAY
        self._shadow[direction_id] = new_score
        if new_score >= REINFORCE_TH:
            self._apply_reinforce(...); self._shadow[direction_id] = 0.0
        elif new_score <= WEAKEN_TH:
            self._apply_weaken(...);    self._shadow[direction_id] = 0.0
```

## 9. 산업상 이용 가능성

본 발명은 LLM 챗봇, 추천 시스템, 콘텐츠 큐레이션, 고객 지원 봇 등 사용자 피드백을 운영 단계에서 점진적으로 반영해야 하는 모든 대화형 시스템에 산업상 이용 가능하다.

---

## 10. 출원 시 체크리스트

- [ ] 발명자/출원인 정보 기재
- [ ] 도면 1~4 작성 (`assets/patent/stage2-figs/` 권장)
- [ ] §6 청구항 한국어 법률 용어 검수
- [ ] 공지예외 적용 신청서 별도 첨부
- [ ] 출원료 6만원 (개인 감면 시 1.8만원) 납부

---

**End of skeleton.**
