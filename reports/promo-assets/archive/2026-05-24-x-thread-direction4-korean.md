# X (Twitter) 스레드 — Direction 4 결과 (한국어, 7-tweet)

> Draft 2026-05-24. Korean LinkedIn publish 직후 운영자 발행 예정.
>
> 한국 readership 대상. 각 tweet 280자 제한 안에서 작성. 영어
> hashtag 일부 mix. Tag form: text mention ("Robin Converse + Ali
> Afana 협업") — X handles 미확정이라 @ 멘션 대신 텍스트.

---

## Tweet 1/7 (hook · fold)

```
🔬 노트북 작은 모델(Gemma 4 e4b)과 협업자가 운영하는 큰 모델 서버(Gemma 4 26B MoE)에 같은 질문 20번씩.

"외우기"와 "생각하기"는 완전히 다른 일이었습니다.

스레드 ↓
```

## Tweet 2/7 (외우기)

```
(A) 외우기: "환불 정책 그대로 알려주세요"

작은 모델이든 큰 모델이든 → 20번 모두 글자 하나 안 다른 같은 답.
T=0.2 sampling 노이즈도 무시. 영어 290자 정확히 똑같이.

→ Gemma 4 family의 구조적 성질 — sampling layer 자체를 건너뜁니다.
```

## Tweet 3/7 (생각하기)

```
(B) 생각하기: "이 상황에 환불 가능한가요?"

• 작은 모델(e4b) → 20번 모두 다 다른 답
• 큰 모델(26B) → 6개만 다르고 나머진 같은 답으로 모임

같은 정답에 도달하지만, 작은 건 길을 부채처럼 펼치고 큰 건 한 점에 모입니다.

(Robin Converse — "fanning out vs clustering")
```

## Tweet 4/7 (의미)

```
의미: 큰 모델은 "용량"이 큰 게 아니라 "길을 더 잘 압니다".

파라미터 수가 늘면 routing precision이 정확해진다.
단순 capacity 증가가 아닙니다.

Ali Afana의 표현 — "같은 답까지 가는 길이 짧아진다(shortening the path)" — 가 여기 정확히 맞습니다.
```

## Tweet 5/7 (3-author lock)

```
3-Author Lock — 세 연구실 따로 확인한 3개 축이 하나의 architectural property로:

• 모드 분리 — Robin Converse
• 작업-무게 그라데이션 — JAMES
• 모델-스케일 효율 — Robin/Ali

헤드라인:
"외우는 답은 공짜. 만드는 답은 무게가 든다 — 파라미터 수에 반비례해서."
```

## Tweet 6/7 (한국 readership 의미)

```
sovereign-AI / 온프레미스 운영자에게 실무 의미:

같은 워크플로에서 작은 모델로 "외우기" + 큰 모델로 "생각하기" 분리 = 토큰 비용 9배 감소 (26B 49토큰 vs e4b 400-450토큰, 같은 정답).

자메스 다음 cycle의 "Adaptive Budgeting + Auto-Routing" 설계 기반.
```

## Tweet 7/7 (링크 + tag + hashtag)

```
🔗 PR #453: github.com/Hashevolution/James-RAG-Evol/pull/453
🔗 Robin 26B repo: github.com/triavalabs/gemma4-26b-mode-split
🔗 Issue #448: github.com/Hashevolution/James-RAG-Evol/issues/448

Robin Converse + Ali Afana 협업.

#SovereignAI #LocalLLM #Gemma4 #자메스 #온프레미스AI
```

---

## 메모

- X tag (@) form은 미사용. Robin / Ali의 X handle 미확정 — text mention으로 안전 처리.
- Hashtag 5개 (LinkedIn 한국어판의 10개에서 줄임). X는 hashtag 많으면 noise.
- Tweet 7 URL은 LinkedIn `lnkd.in/*` shortener 대신 raw GitHub URL — X의 t.co가 자동 변환. 영구 링크가 raw form일 때 더 안정적.
- 운영자 발행 시점: Korean LinkedIn publish 직후 또는 한국 X readership peak (KST 19-22시 / 07-09시) 권장.
- 발행 후 launch-tracker.md row를 ✅ 상태로 업데이트 (현재 🟡 draft).
