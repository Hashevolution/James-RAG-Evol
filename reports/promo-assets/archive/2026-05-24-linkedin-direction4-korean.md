# LinkedIn 한국어판 — Direction 4 결과 (publish 본문)

> 발행 2026-05-24, [URL](https://www.linkedin.com/posts/jiwon-seo-8b8649237_researchgemma4-26b-moe-cross-model-data-activity-7464152765888602113-q7KF/)
>
> 한국 readership 대상 / 일반인도 이해 쉬운 스토리 구성. 영문판
> (activity-7463978849412857856) 과 의도적 차이 4건 (narrative hook /
> 협업자 vocab 직접 인용 attribution / 한국 sovereign-AI 가치 단락 /
> 자메스 next-cycle 예고).

---

🔬 노트북에서 돌리는 작은 모델(Gemma 4 e4b)과, 협업자가 자체 운영하는 큰 모델 서버(Gemma 4 26B MoE).
같은 질문을 20번씩 던졌습니다. 결과가 흥미로워서 공유합니다.

질문을 두 종류로 나눠 봤습니다.
• (A) 외워서 답하기 — "환불 정책 그대로 알려주세요"
• (B) 생각해서 답하기 — "이 상황에 환불 가능한지 추천해주세요"

▌(A) 외우기 — 작은 모델이든 큰 모델이든 20번 모두 글자 하나 안 다른 같은 답.
T=0.2 sampling 노이즈가 있어도 무시. 영어 290자 한 글자도 안 틀리고 똑같이.
→ 이건 측정 우연이 아니라 Gemma 4 family의 구조적 성질입니다.
   sampling layer 자체를 건너뛰고 외운 답이 그대로 흘러나옵니다.

▌(B) 생각하기 — 두 모델이 갈립니다.
• 작은 모델(e4b) — 20번 모두 다 다른 답 (다 정답이지만 매번 표현이 다름)
• 큰 모델(26B) — 20번 중 6개만 다르고 나머진 같은 답으로 모임

같은 정답에 도달하는데, 작은 모델은 길을 부채처럼 펼치고, 큰 모델은 한 점에 모입니다.
(Robin Converse가 만든 표현 — "fanning out vs clustering")

▌의미 — 큰 모델은 "용량"이 큰 게 아니라 "어느 길로 갈지 더 잘 압니다"

지금까지 우리는 AI 파라미터 수가 늘면 단순히 "더 많이 외운다 / 더 똑똑하다"고
가정해왔습니다. 이번 데이터가 보여준 건 조금 다릅니다.

  파라미터 수가 늘면 어느 길로 갈지에 대한 라우팅이 정확해진다.
  단순한 capacity 증가가 아닙니다.

Ali Afana가 먼저 던진 표현 — "같은 답에 도달하는 길이 짧아진다(shortening the path)"
— 가 여기 깔끔하게 맞습니다. 큰 모델은 "정답까지 어느 길로 가야 할지" 더 잘 압니다.

▌3-Author Lock — joint paper publishable 수준

세 곳의 독립 연구실이 따로 확인한 세 개의 축이, 하나의 architectural property로 묶입니다.

• 모드 분리 (외우기 vs 생각하기) — Robin Converse
• 작업-무게 그라데이션 (무거움/가벼움/없음) — JAMES
• 모델-스케일 효율 (토큰 + 답의 수렴) — Robin / Ali

헤드라인 한 줄:
"외우는 답은 공짜다. 만드는 답은 무게가 든다 — 그것도 파라미터 수에 반비례해서."

▌한국 sovereign-AI / 온프레미스 운영자에게 의미

이건 학술 결과만이 아닙니다. 같은 워크플로 안에서 어느 모델을 어디 배치할지 —
작은 모델로 "외우기" 작업 처리, 큰 모델은 "생각하기"에 모아쓰는 — 게 토큰 비용을
9배까지 줄입니다 (26B 49토큰 vs e4b 400-450토큰, 같은 정답).

자메스 다음 cycle의 "Adaptive Budgeting + Auto-Routing" 설계의 데이터 기반입니다.
local-first 운영 환경에서 모델 선택이 단순 "큰 게 좋다"가 아니라 "작업 무게에
맞춰 라우팅"으로 바뀝니다.

🔗 PR #453 (전체 결과 + driver patch + raw JSON):
   https://lnkd.in/gJSsWP63
🔗 Robin의 26B 자매 repo (MIT, 80-call raw + sweep.py):
   https://lnkd.in/gSFDymSx
🔗 Issue #448 — 크로스-스택 분석 스레드:
   https://lnkd.in/gxMmMggF

@Robin Converse @Ali Afana — 3-axis로 정리해주신 덕에 publishable로 올라옵니다.

#자메스 #로컬LLM #온프레미스AI #그래프RAG #자율운영AI
#SovereignAI #LLM #Gemma4 #LocalLLM #AgenticArchitecture

---

## 영문판과의 의도적 차이

| 영문판 (activity-7463978849412857856) | 한국어판 (activity-7464152765888602113) |
|---|---|
| 후크 = 데이터 라인 1줄 | 후크 = "외우기 vs 생각하기" 비유 + 데이터 라인 |
| Robin "fanning out vs clustering" vocab 사용 | 본문에 명시 인용 + attribution |
| Ali "shortening the path" framing 적용 | 본문에 명시 인용 + attribution |
| Robin/Ali tag (영문 handle) | Robin/Ali tag (동일) |
| 8 hashtag (영문) | 10 hashtag (5 KR + 5 EN mix) |
| 학술 결과 중심 | 한국 sovereign-AI / 온프레미스 운영자 실무 가치 단락 추가 |
| Direction 1+5 announce 없음 | 자메스 next-cycle ("Adaptive Budgeting + Auto-Routing") 예고 추가 |

## 운영자 publish 결정

- 2026-05-24 KST publish
- 운영자가 작성된 본문 그대로 publish (수정 없음)
- 이 archive는 다음 promo cycle (k-channel publish 시점) reference + audit trail
