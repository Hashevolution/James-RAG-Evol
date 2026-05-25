# 2026년 주요 이벤트 기록 — PR-11b verification fixture

> 2026-05-25 verification artifact. 사용 후 archive 보관 — 다음 PR-11b
> regression check 또는 cross-model event-extraction 비교 시 재사용
> 가능. Run 결과: gemma4:e4b 가 5 events 중 3 events 추출 (entity Max
> 6 cap에 의해 마지막 2개 truncate). Production-flow event extraction
> path **확인됨**. 결과 분석은 chat session 기록 참조 (2026-05-25
> session).

이 문서는 PR-11b event entity 추출 path 검증을 위한 일회용 test artifact입니다.
각 항목이 분리된 시간 사건 (event-dominant) 으로, LLM이 event entity type으로
분류하기에 적합한 구조로 작성됐습니다.

## 이벤트 1

2026년 1월 10일, 미국 증권거래위원회(SEC)가 비트코인 spot ETF 11개를 일괄 승인했다.
이는 미국 기관 자금이 비트코인 시장에 합법적으로 진입할 수 있는 첫 채널을 열어준
사건이며, 가상자산 시장의 제도권 편입을 가속화했다.

## 이벤트 2

2026년 3월 21일, 미국 연방준비제도이사회(FRB)가 기준 금리를 0.25%p 인하했다.
당시 인플레이션 둔화와 고용 시장 안정세를 근거로 5.50%에서 5.25%로 조정했으며,
2024년 9월 이후 가장 큰 폭의 금리 인하 결정이었다.

## 이벤트 3

2026년 4월 15일, OpenAI가 GPT-6 모델을 공식 발표했다. 추론 정확도가 기존 모델
대비 35% 향상됐다고 밝혔으며, multi-modal reasoning과 long-context (10M tokens)
기능을 강화했다.

## 이벤트 4

2026년 7월 4일, NASA가 유인 화성 탐사선 "Phoenix"를 발사했다. 4명의 우주비행사가
탑승했으며, 화성 표면 90일 체류와 샘플 회수 임무를 수행할 예정이다. 미국 독립
기념일에 맞춰 진행된 상징적 발사였다.

## 이벤트 5

2026년 11월 5일, 미국 대통령 선거가 진행됐다. 전국 50개 주에서 동시에 투표가
이루어졌으며, 1억 6천만 명 이상의 유권자가 투표에 참여한 것으로 집계됐다.
