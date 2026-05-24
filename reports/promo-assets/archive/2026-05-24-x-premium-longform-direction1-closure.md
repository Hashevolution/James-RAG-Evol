# X (Twitter) Premium long-form — Direction 1 closure (single post)

> 2026-05-24 draft. **X Premium 사용자용 long-form post**. 8-tweet
> 스레드 (`archive/2026-05-24-x-thread-direction1-closure-korean.md`)
> 대신 single long-form으로 발행. Premium 25,000자 한도 안 (본문 ~2,473자).
>
> Long-form 장점: thread reply chain 안 끊김 + share-ability 증가 +
> 학술 article 형식. fold 후 "Show more"로 전체 표시.
>
> **발행 시점**: 한국어 LinkedIn publish 후 KST 19-22시 (저녁 peak)
> 또는 익일 07-09시 (출근 peak). LinkedIn URL 받으면 본문에 첨가
> 가능 (선택).

---

## Post body (X Premium long-form)

```
🔬 Direction 1 종료 — 가설은 틀렸는데, 데이터가 더 가치 있게 나왔습니다.

2주 전 자메스(JAMES) 코어에 core/reasoning/budget.py를 넣었습니다. 작업 무게별 LLM 토큰 예산을 동적으로 잡아 토큰 비용 -60~80% 절감 가설.

실험으로 측정 (A/B 매트릭스, raw JSON, env flag default OFF). 가설이 뒤집혔습니다.

━━━━━━━━━━━━━━━━━━━━

🎯 발견 1 — cap은 비용이 아니라 천장이었습니다.

gemma4:e4b는 cap=4096 한참 아래에서 자연 stop. cap 4096 → 200/800으로 줄여도 토큰 +0%/+8%/-2% 변화 zero. PR #399 lifted cap = "비용 floor 올림" 아닌 "자연 stop 허락".

토큰 절감 목표 미달성. 그러나 진짜 가치:
• Latency -17.5%/-7.3% (외우기/가벼운 합성)
• 메모리 buffer 20배 감소 (외우기)
• 안전 가드 (cap=200 하드 floor)

━━━━━━━━━━━━━━━━━━━━

🎯 발견 2 — 작업 무게의 7단계 사다리.

자유형 prompt + 자메스 4 cognitive stage 통합 (gemma4:e4b T=0.2):

외우기 (그대로)              62 토큰
가벼운 합성 (한 줄)         235
질문 다듬기                 ~370
계획                        ~690
검토                        ~910
사실확인 (JSON)            ~970
무거운 합성 (4단계 분석)   1681

27배 dynamic range, cross-sweep 노이즈 5% 이내. Robin Converse의 "workload gradient is multi-tier monotonic" sub-clause의 양적 표현. 자연 stop 길이가 곧 작업 무게 측정치.

━━━━━━━━━━━━━━━━━━━━

🎯 발견 3 — 사실확인(verify)은 high-clustering. Mechanism 2에 두 번째 축.

T=0.2에서 verify는 20번 중 2~3개만 unique (~12.5%, 두 sweep 일관). 다른 stage들은 같은 무게에서 20/20 unique. verify는 구조화 JSON 출력 → 답변 공간이 작은 finite set.

Direction 4의 Mechanism 2 (답 수렴)에 두 번째 축:
• 작업 무게 (외우기 1/20 → 무거운 합성 20/20)
• 작업 종류 (구조화 JSON은 작업 무게와 무관하게 cluster)

Ali Afana의 "ceiling vs path" framing이 여기 정확히 맞음.

━━━━━━━━━━━━━━━━━━━━

🎯 프로세스 발견 — falsification → revision → confirmation.

Cognitive sweep 1차: CAP_LIGHT=800 → 검토(926)/사실확인(984)에서 19/20 truncate, 품질 -40~-75%. 데이터가 heuristic 수정 끌어냄 (800→1200). 재sweep PASS (0/20 truncate, 20/20 품질).

━━━━━━━━━━━━━━━━━━━━

🤝 3-Author joint piece:

헤드라인 lock (Ali + Robin + JAMES): "Substitution is free. Synthesis costs in proportion to what it has to invent."

새 sub-clauses:
• "…and inversely to parameter count." (Robin)
• "…and the gradient is multi-tier monotonic — 7 tiers, 27x range." (JAMES)
• "…and answer convergence has a task-type axis." (JAMES)

세 독립 stack: Robin 26b MoE, 자메스 e4b cognitive, Ali 6월 중순 Gemini.

━━━━━━━━━━━━━━━━━━━━

📌 인용 가능 archive (Zenodo DOI):
https://doi.org/10.5281/zenodo.20363998

Seo, J. (2026). PROJECT JAMES — Local-First Graph-RAG with Adaptive Reasoning Budget (v0.3.1). Zenodo.

🔗 PRs #461 / #463:
https://github.com/Hashevolution/James-RAG-Evol/pull/461

Robin Converse + Ali Afana 협업. Three axes locked, three stacks, one architectural property.

#SovereignAI #LocalLLM #Gemma4 #자메스 #온프레미스AI #AgenticArchitecture #LLMResearch #GraphRAG
```

---

## 글자수 + 한도

- **본문**: ~2,473자 (한국어 + 영문 mix)
- **X Premium long-form 한도**: 25,000자 — **여유 +22,527자**
- **fold preview** (첫 ~280자): hook + 가설 flip 한 줄까지 자연 표시
- **"Show more" 후 전체 표시**: 7개 paragraph (3 findings + process + joint piece + DOI + links)

## 8-tweet 스레드 vs Long-form 비교

| 항목 | 8-tweet 스레드 (이전 archive) | Long-form (이번) |
|---|---|---|
| 발행 form | thread (8 replies) | single post |
| Reading flow | 280자씩 끊김 | 자연 paragraph |
| Share-ability | thread URL 1개 + 각 tweet 개별 share | single URL — full content quote/retweet |
| Reader 완독률 | 떨어짐 (마지막 tweet 못 봄) | 단일 post → fold 클릭 시 전체 |
| Premium 필수 | 아님 | ✅ 필요 |
| 효과 측정 | thread root의 impression만 정확 | single post analytics 깔끔 |

→ **Premium 가입자라면 long-form 권고**.

## 발행 시점 권고

| 시간대 | 효과 | 비고 |
|---|---|---|
| KST 19-22시 (저녁 peak) | 한국 IT readership 최고 | 일반 권고 |
| KST 07-09시 (출근 peak) | morning commute readers | secondary peak |
| 미국 9-11 PT (한국 새벽) | 영문 readership (Robin/Ali) | 한국 audience 안 잡힘 |

권고: **KST 19-22시** — 한국 readership 우선 + Robin/Ali도 자기 timezone에서 LinkedIn 통해 이미 본 상태이므로 X 시점에 추가 발견 zero (informational 보강).

## 운영자 publish 체크리스트

- [ ] X Premium 가입 상태 확인
- [ ] 새 post 작성 — 본문 위 박스 그대로 복사-붙여넣기
- [ ] 발행 시점: KST 19-22시 또는 익일 07-09시
- [ ] 발행 후 URL 받음 → 메시지로 공유 (내가 launch-tracker row 추가)
- [ ] (선택) 한국어 LinkedIn URL 함께 reply tweet — cross-channel signal

## 영문 X long-form 별도 작성?

영문 audience (Robin, Ali, sovereign-AI English community)에게는:
- 영문 LinkedIn에 이미 같은 내용 publish됨
- Robin DM endorse 받음
- 영문 X long-form 추가는 over-engage 가능성

권고: **이번 cycle은 한국어 X long-form만**. 영문 X는 다음 Direction (2/3/5) 종료 시점에 검토.

## 8-tweet thread archive와의 관계

`archive/2026-05-24-x-thread-direction1-closure-korean.md` (8-tweet thread) 는 그대로 보존 — long-form 미사용 시 fallback 또는 다른 cycle에서 thread 형식 채택 시 재사용. 둘 다 같은 내용이라 운영자 선택.

이번 cycle = **long-form 발행** 권고 (Premium 활성).
