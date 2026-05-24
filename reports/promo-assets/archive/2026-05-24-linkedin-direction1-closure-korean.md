# LinkedIn 한국어 — Direction 1 closure (draft)

> 2026-05-24 draft. 영문판 (activity TBD) 발행 후 6-12시간 뒤 publish.
> 영문판과 의도적 차이 4건: narrative hook 강화 / 협업자 vocab 직접
> 인용 + attribution / 한국 sovereign-AI / 온프레미스 운영자 가치
> 단락 / KR-EN hashtag mix. 이전 Direction 4 한국어 글 (activity-
> 7464152765888602113) 패턴 따라.

---

🔬 **Direction 1 종료 — 가설은 틀렸는데, 데이터가 더 가치 있게 나왔습니다.**

2주 전 자메스(JAMES) 코어에 `core/reasoning/budget.py`를 넣었습니다. 작업 무게에 따라 LLM 토큰 예산(`num_predict`)을 다르게 잡으면 토큰 비용 -60~80% 절감 가능하다는 가설로요.

라이브 검증으로 끝낼 일이 아니라 **실험으로 측정하자** 결정. A/B 매트릭스, raw JSON 보존, pre-registered decision tree, env flag로 default OFF 게이트. 운영 영향 zero 상태에서 데이터만 측정.

결과가 도착했고, **가설이 뒤집혔습니다**.

🎯 **발견 1 — 트렁크(cap)는 비용이 아니라 천장이었습니다.**

`gemma4:e4b`는 cap=4096 한참 아래에서 알아서 멈춥니다 (`done_reason=stop`). cap을 4096 → 200 / 800으로 줄여도 **토큰 사용량 +0% / +8% / -2%** — 변화 zero. PR #399가 한 일은 "비용 floor 올림"이 아니라 "모델이 자연 stop할 수 있게 허락한 것"이었습니다.

토큰 절감 목표는 안 달성. 그러나 데이터가 보여준 진짜 가치:

• 외우기 / 가벼운 합성에서 latency **-17.5% / -7.3%** (Ollama KV-cache 버퍼 크기 효과)
• 외우기 호출에서 메모리 buffer **20배 감소**
• 안전 가드 (cap=200은 폭주 방지 하드 floor)

구현은 그대로 tree에 유지. `JAMES_ADAPTIVE_BUDGET=1` env flag 뒤에 (default OFF). 운영자가 메모리 / latency / 안전 측면에서 opt-in 가능.

🎯 **발견 2 — 작업 무게의 7단계 사다리.**

첫 sweep은 외우기 / 가벼운 합성 / 무거운 합성 3단계. 후속 sweep은 자메스의 4개 cognitive stage (질문 다듬기 / 계획 / 검토 / 사실확인). 둘이 합쳐서 **7단계 monotonic 자연-stop gradient**:

```
1. 외우기 (그대로 보여)        62 토큰
2. 가벼운 합성 (한 줄 답)     235
3. 질문 다듬기                ~370
4. 계획                       ~690
5. 검토                       ~910
6. 사실확인 (JSON)           ~970
7. 무거운 합성 (4단계 분석) 1681
```

**27배 dynamic range, cross-sweep 노이즈 5% 이내.** 이게 Robin Converse와 합의해온 sub-clause — *"작업 그라디언트는 단일 모델에서 multi-tier monotonic"* — 의 **양적 표현**입니다. **자연 stop 길이가 곧 작업 무게의 측정치**.

🎯 **발견 3 — 사실확인(verify)은 high-clustering 작업. Mechanism 2에 두 번째 축.**

T=0.2에서 verify는 **20번 호출 중 2~3개만 unique 답** (~12.5%, 두 sweep 모두 일관). 다른 cognitive stage들은 같은 작업 무게에서 20/20 unique. 차이는: verify가 구조화된 JSON (`{"grounded": ..., "unsupported": [...]}`) 출력 → 답변 공간이 작은 finite set.

Direction 4의 Mechanism 2 (답 수렴)에 **두 번째 축** 추가:
• 작업 무게 (외우기 1/20 → 무거운 합성 20/20)
• **작업 종류** (구조화 JSON 출력은 작업 무게와 무관하게 cluster)

Ali Afana가 26b cross-stack 데이터에 던진 *"shortening the path"* (같은 답까지 더 짧은 경로) framing이 여기 정확히 맞습니다. 구조화 출력은 도착지 집합이 작아서 무거운 작업에서도 짧은 경로로 모입니다.

🎯 **그리고 프로세스 발견 — falsification → revision → confirmation.**

Cognitive sweep 첫 실행은 CAP_LIGHT=800. 검토 (자연 stop 926) + 사실확인 (984)에서 19/20번 truncation, 답 품질 -40~-75% 폭락 → calibration 오류 노출.

데이터가 heuristic 수정을 끌어냄 (CAP_LIGHT 800 → 1200). 재sweep PASS: truncation 0/20, 품질 20/20 회복.

Robin이 26b mode-split sweep에서 보여준 empirical discipline과 같은 패턴. Joint paper protocol에 대한 신뢰 누적.

🤝 **3-Author Joint Piece 진행 상태**:

3-author lock된 헤드라인 (변동 없음): *"외우는 답은 공짜다. 만드는 답은 만들어야 할 무게만큼 든다."*

새 sub-clause 초안:
• *"…그리고 파라미터 수에 반비례한다."* (Robin axis-3, evidence layer 2개)
• *"…그리고 그라디언트는 multi-tier monotonic — 27배 dynamic range의 7단계 측정."* (JAMES Direction 1)
• *"…그리고 답 수렴은 작업 종류 축도 있다 — 구조화 JSON은 작업 무게와 무관하게 cluster."* (JAMES Direction 1, 양 sweep 검증)

2026-05-24 Robin endorsement로 활성화된 joint piece outline trigger가 이제 **세 독립 stack 위에 load-bearing**: Robin의 26b MoE, 자메스의 e4b cognitive stack, 그리고 Ali의 6월 중순 Gemini backend.

🇰🇷 **한국 sovereign-AI / 온프레미스 운영자에게 의미**:

이 데이터는 학술적 결과만이 아닙니다. **`gemma4:e4b`로 LLM 워크로드를 운영하는 한국 팀**이라면 다음 항목이 즉시 적용 가능:

• Adaptive Budgeting의 token 절감 목표는 e4b에서 안 됨 — 다만 **latency 7-17% 작은 자동차일수록 빠른 출발** + **safety 가드** 이점은 실측 확인됨
• 7단계 자연 stop 표는 **워크로드 사이징 reference**로 직접 사용 가능: 어느 stage가 어느 cap에 들어가는지 미리 알 수 있음
• `JAMES_ADAPTIVE_BUDGET=1` env flag 켜면 production opt-in 즉시 가능 (PR #461 + #463 main 안착)

자메스 다음 cycle (Direction 2 — task-weight 측정 metric 공식화)이 이 7단계 데이터를 ground truth로 소비. **단일 metric으로 작업 무게 자동 예측**이 가능해지면 cap heuristic 자체가 measured signal로 교체됩니다.

📌 **인용 가능 archive (Zenodo DOI)**: https://doi.org/10.5281/zenodo.20363998
Seo, J. (2026). PROJECT JAMES — Local-First Graph-RAG with Adaptive Reasoning Budget (v0.3.1). Zenodo.

🔗 PR #461 (D1.A 모듈 + D1.B wiring + 3-prompt 실험 + 4단계 확장): https://github.com/Hashevolution/James-RAG-Evol/pull/461
🔗 PR #463 (heuristic v2 + closure result docs + 7-tier gradient): https://github.com/Hashevolution/James-RAG-Evol/pull/463
🔗 Cognitive stages result doc: https://github.com/Hashevolution/James-RAG-Evol/blob/main/reports/promo-assets/v3prime-direction1-cognitive-stages-result.md

@Robin Converse @Ali Afana — three axes locked, three independent stacks, one architectural property. 7-tier gradient + verify task-type clustering은 joint-paper §axis-2 input.

#자메스 #로컬LLM #온프레미스AI #그래프RAG #자율운영AI
#SovereignAI #LLM #Gemma4 #LocalLLM #AgenticArchitecture

---

## 영문판과의 의도적 차이

| 영문판 (this draft sibling, English) | 한국어판 |
|---|---|
| 가설 / 결과 / 발견 학술 voice | 같은 voice + 비유 (트렁크, 자동차, 사다리) 가벼운 강화 |
| Robin "fanning out vs clustering" vocab 인용 | Ali "shortening the path" 한국어 + 영문 병기로 attribution |
| sovereign-AI 운영자 단락 (영문판은 implicit) | 한국 sovereign-AI / 온프레미스 운영자 명시 단락 (실무 의미 3개) |
| Direction 2 언급 없음 | 자메스 다음 cycle (Direction 2 task-weight metric) 예고 |
| 8 영문 hashtag | 10 (5 KR + 5 EN mix) |

## 운영자 publish 체크리스트

- [ ] 영문판 publish 후 6-12시간 뒤 publish (이전 Direction 4 cycle 패턴)
- [ ] @Robin Converse + @Ali Afana 자동완성 tag (영문판과 동일 person)
- [ ] 발행 후 URL을 `launch-tracker.md`에 row 추가 + PR #461 + PR #463 description 양방향 cross-link (4-way audit trail closure: 영문 LinkedIn ↔ 한국어 LinkedIn ↔ PR ↔ result doc)
- [ ] X 7-tweet thread는 한국어 publish 후 KST 19-22 또는 익일 07-09 peak에

## What this post deliberately does NOT do

- 가설 PASS이라고 위장 — 명시적으로 fail 인정 + 데이터 가치 reframe
- env flag default ON flip 약속 — 안 함, OFF 유지
- Joint paper publish 시점 약속 — Ali Gemini backend 6월 중순 land 후 outline 작성이 자연 trigger
- Robin/Ali에게 공개 답변 요청 — tag로 informational 알림만
