# Hada / GeekNews 투고 (velog 공유용)

> 사이트: https://news.hada.io
> 형식: 외부 링크 + 짧은 본문 (마크다운)
> **상태**: 작성 완료, velog 발행 후 외부 링크 URL만 채워 투고

---

## 외부 링크 URL (velog 발행 후 채워서 투고)

```
<velog 글 URL — 발행 후 채울 자리>
```

대체 후보 (velog 글 외부 페이지가 너무 안 열리는 환경 대비):
```
https://github.com/Hashevolution/James-RAG-Evol/blob/main/reports/promo-assets/velog-openssf-silver-6weeks.md
```

## 제목 (택1)

- (A) **솔로 메인테이너가 OpenSSF 실버에 도전한 6주 — 정직한 UNMET으로 통과한 1인 OSS의 기록** ← 추천
- (B) OpenSSF Best Practices 실버 티어 136% 도달기 (1인 운영, alpha) — 어슈어런스 케이스 작성기
- (C) 1인 메인테이너도 OpenSSF 실버를 받을 수 있다 — 6주, 9개 항목, 6개 PR의 기록

**추천: (A)** — "정직한 UNMET"이 글의 실제 핵심이고 이 표현이 클릭을
유도하면서도 과장이 아님. (B)는 "136%"가 미끼처럼 보일 위험, (C)는
"받을 수 있다"가 광고체로 읽힐 위험.

## 본문 (마크다운, 복붙용)

````markdown
## 한 줄 요약
1인 운영 오픈소스가 OpenSSF Best Practices **passing(111%)**에서
**실버 티어 136%**까지 6주에 어떻게 올라갔는지의 회고.

요지: 80여 개 silver-tier MUST/SHOULD 항목 중 1인 메인테이너가
구조적으로 만족시킬 수 없어 보이는 항목들 (`bus_factor`,
`access_continuity` 등) 을 **거짓 없이 UNMET으로 표기하고, 그 위에
OpenSSF가 명시적으로 인정하는 정당화 패턴 (lockbox + legal heir,
SHOULD criterion justification) 을 얹는 방식** 으로 통과시킴.

## 글의 핵심 (3줄)

1. **UNMET을 정직하게 표기하는 게 통과의 핵심.** "다 만족시켰다"가
   아니라 "못 만족시키는 항목을 거짓 없이 공개하되 회복 경로를
   문서화" — `access_continuity` (MUST) 와 `bus_factor` (SHOULD)
   둘 다 이 방식으로 통과.
2. **Assurance case 작성이 가장 무거웠고 가장 보람있었다.** 26 KB
   문서, 47개 file:line 인용, 부수효과로 race condition 1건 + 권한
   체크 누락 1건 발견.
3. **Documentation currency는 자동화 없이 정책만으로 통과 가능.**
   stale 버전 참조 4건을 grep으로 잡고 CONTRIBUTING.md에 정책 신설.

## 6주 PR 타임라인

| 주차 | 항목 | PR |
|---|---|---|
| Week 1 | `dco` (CLA로 대체) | #340 |
| Week 2 | `code_of_conduct` · `governance` · `roles_responsibilities` | #353 |
| Week 3 | `static_analysis_common_vulnerabilities` | #356 |
| Week 4 | `assurance_case` | #360 |
| Week 5 | `access_continuity` · `bus_factor` | #362 |
| Week 6 | `documentation_current` (+ stale 4건 fix) | #363 |

## 무엇을 안 했는지

- bus factor를 실제로 2로 올리는 일 — 1인 BDFL 모드는 v1.0까지의
  의도된 트레이드오프
- 자동 doc-lint — 다음 cycle
- 도메인 분화 — 모체 강화가 v1.0까지 유일한 우선순위

## 링크

- 본문 (velog): <velog URL — 발행 후 채울 자리>
- GitHub: https://github.com/Hashevolution/James-RAG-Evol
- OpenSSF 페이지: https://www.bestpractices.dev/projects/12806
- 핵심 PR: #340 / #353 / #356 / #360 / #362 / #363

> *MIT 라이선스, alpha (v0.3.0 — Platform Skeleton). 1인 메인테이너 운영.*
````

---

## 투고 시 체크

- [ ] velog 글이 먼저 발행되었고 URL이 유효한지 확인
- [ ] 외부 링크 URL을 velog URL로 교체 (위 placeholder 자리)
- [ ] 본문 안의 `<velog URL — 발행 후 채울 자리>` 도 교체
- [ ] 댓글 응대 가능한 시간대에 투고 (한국 시간 오전 9~10시 권장 — 점심
      전 첫 페이지 노출)
- [ ] 투고 후 30분 내 첫 댓글 들어오면 즉시 응대 (Hada는 첫 30분
      코멘트 활성도가 점수 가중)
- [ ] 발행 직후 `launch-tracker.md` 에 게시 ID + URL 기록

## 톤 가이드 (댓글 응대 시)

- 자랑조 X, "1인 운영이라 부족할 수 있지만 정직하게 공개했다" 톤 유지
- 도메인 (legal/food/retail) 질문은 "v1.0 이후 계획, 현재는 모체
  강화만" 으로 정리
- "이거 LangChain/LlamaIndex 와 뭐가 다른가" 질문엔 *감사 가능성·trust
  zone·assurance case 작성* 의 차별점만 강조 (벤더 비교 X)
- 비판은 GitHub Issue 로 유도, 인신공격성 댓글은 무시
