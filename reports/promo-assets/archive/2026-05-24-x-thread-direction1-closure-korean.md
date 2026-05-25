# X (Twitter) 스레드 — Direction 1 closure (한국어, 8-tweet)

> Draft 2026-05-24. 한국어 LinkedIn publish 직후 발행 예정.
>
> 한국 readership 대상. 각 tweet 280자 안. 영어 hashtag 일부 mix.
> Tag form: text mention ("Robin Converse / Ali Afana 협업") — X handle
> 미확정이라 @ 멘션 대신 텍스트. 이전 Direction 4 X 스레드 (2026-
> 05-24, `archive/2026-05-24-x-thread-direction4-korean.md`) 패턴 따라.

---

## Tweet 1/7 (hook · fold)

```
🔬 자메스에 "동적 토큰 예산" 모듈을 넣어봤습니다 (Direction 1).

가설: 작업 무게별 cap 조절로 토큰 -60~80% 절감 가능.

결과: 가설은 틀렸는데, 데이터가 더 가치 있게 나왔어요.

스레드 ↓
```

## Tweet 2/7 (가설 flip)

```
gemma4:e4b는 cap=4096 한참 아래에서 알아서 멈춥니다.

cap을 4096 → 200/800으로 줄여도:
• 토큰 변화 zero
• done_reason=stop 모든 cell
• 품질 회귀 0

→ cap은 비용이 아니라 천장이었음.
PR #399가 한 일 = "비용 floor 올림" 아니라 "자연 stop 허락".
```

## Tweet 3/7 (3 진짜 wins)

```
가설은 틀렸지만 데이터가 보여준 3 win:

• Latency -17.5% / -7.3% (외우기 / 가벼운 합성)
  Ollama KV-cache 버퍼 사이즈 효과
• 메모리 buffer 20× 감소 (외우기)
• 안전 가드 (cap=200 = 폭주 방지 하드 floor)

production opt-in path 유지.
```

## Tweet 4/7 (7-tier gradient)

```
7단계 monotonic 자연-stop 사다리 (gemma4:e4b T=0.2):

외우기            62 토큰
가벼운 합성       235
질문 다듬기      ~370
계획             ~690
검토             ~910
사실확인         ~970
무거운 합성     1681

27× dynamic range. cross-sweep 노이즈 5% 이내.
자연 stop 길이 = 작업 무게 측정치.
```

## Tweet 5/7 (verify clustering 발견)

```
새 발견: verify (사실확인)는 high-clustering 작업.

20번 호출 중 2~3개만 unique (~12.5%, 두 sweep 일관).
다른 stage들은 20/20 unique.

차이: verify는 구조화 JSON 출력 → 답변 공간이 작은 finite set.

Mechanism 2 (답 수렴)에 두 번째 축 — 작업 무게 + 작업 종류.
```

## Tweet 6/7 (process win + heuristic v2)

```
프로세스 발견 — falsification → revision → confirmation.

cognitive sweep 1차: CAP_LIGHT=800 → 검토/사실확인 19/20 truncate, 품질 -40~-75%.

데이터가 heuristic 수정 끌어냄: CAP_LIGHT 800 → 1200.

재sweep: truncation 0/20, 품질 20/20 회복.

empirical discipline 정합.
```

## Tweet 7/8 (citable archive — Zenodo DOI)

```
📌 인용 가능 archive (Zenodo DOI):
doi.org/10.5281/zenodo.20363998

Seo, J. (2026). PROJECT JAMES — Local-First Graph-RAG with Adaptive Reasoning Budget (v0.3.1). Zenodo.

데이터 / 코드 / result docs 모두 영구 archive.
```

## Tweet 8/8 (links + tag + hashtag)

```
🔗 PR #461: github.com/Hashevolution/James-RAG-Evol/pull/461
🔗 PR #463: github.com/Hashevolution/James-RAG-Evol/pull/463
🔗 Result doc: github.com/Hashevolution/James-RAG-Evol/blob/main/reports/promo-assets/v3prime-direction1-cognitive-stages-result.md

Robin Converse + Ali Afana 협업. Three axes locked.

#SovereignAI #LocalLLM #Gemma4 #자메스 #온프레미스AI
```

---

## 메모

- 각 tweet 280자 안 (한국어). LinkedIn 글의 압축 버전.
- Tag form: text mention (이전 Direction 4 X 스레드 패턴 그대로 — X handle 미확정).
- Tweet 7 URL: raw GitHub URL (t.co 자동 변환).
- 발행 시점: 한국어 LinkedIn publish 후 KST 19-22 (저녁 peak) 또는 익일 07-09 (출근 peak).

## 운영자 publish 체크리스트

- [ ] 한국어 LinkedIn publish 완료 확인
- [ ] X publish — Tweet 1을 thread root, 2~7을 reply로 순차
- [ ] 발행 후 root URL을 `launch-tracker.md`에 row 추가
- [ ] X handle (X reply) 등 inbound 모니터링 — 이전 Direction 4 X 스레드와 같은 dynamic

## 영문 X 스레드 별도 작성 여부

- 영문 X account 활동이 한국어보다 활발하면 영문 버전도 별도 작성 검토 (이번엔 한국어 우선)
- 영문 LinkedIn 본문이 충분히 detailed라서 X 영문 미작성도 OK
- 결정은 운영자
