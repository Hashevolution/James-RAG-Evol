# 솔로 메인테이너가 OpenSSF 실버에 도전한 6주 — 어슈어런스 케이스 작성기

> **발행 채널**: velog (작성자 본인 계정)
> **태그**: `OpenSSF` · `보안` · `오픈소스` · `RAG` · `Python`
> **요약**: 1인 운영 오픈소스 프로젝트가 OpenSSF Best Practices passing(111%)에서 실버 티어 136%까지 6주에 어떻게 올라갔는지의 기록.
> 도구 자랑이 아니라, **"정직한 UNMET"이 어떻게 silver의 핵심이었는지** 에 대한 회고.

---

## 시작점 — passing 뱃지를 받은 다음에 뭐가 있을까

2026-05-11, [JAMES](https://github.com/Hashevolution/James-RAG-Evol)
(로컬-퍼스트 감사 가능한 RAG 시스템) 가 OpenSSF Best Practices
[passing 뱃지](https://www.bestpractices.dev/projects/12806) 를 받았다.
Tiered 백분율은 111% — passing 컷오프 100%를 갓 넘은 수치였다.

passing 뱃지는 누구나 얻는다. 자동화된 테스트 한두 개, 보안 신고 채널 명시,
릴리스 노트 — 이 정도면 통과한다. 그래서 자랑할 거리는 아니지만,
*다음 단계인 silver는 다르다*. 80개 가까운 체크리스트가 추가로 있고
대부분이 MUST 항목이다. 그리고 그 중 몇 개는 1인 메인테이너가
**구조적으로 만족시킬 수 없어 보이는 항목들** 이다:

- `bus_factor` — 프로젝트에 2명 이상의 관리자가 있어야 한다. 나는 1명이다.
- `access_continuity` — 메인테이너가 사라져도 일주일 내에 프로젝트가 계속될 수 있어야 한다. 후계자 없음.
- `assurance_case` — 보안 요구사항·위협 모델·논거가 담긴 문서가 있어야 한다. 없음.
- `static_analysis_common_vulnerabilities` — SAST를 PR 게이트로 돌려야 한다. 안 돌아감.

나는 6주 동안 이걸 어떻게든 통과시켰고, 결국 **Tiered 136%로 실버 티어**
에 도달했다. 비결은 "다 만족시켰다"가 아니라 **"못 만족시키는 항목을 정직하게
UNMET으로 표기하되, 그 위에 OpenSSF가 명시적으로 인정하는 정당화 패턴을
얹는다"** 였다. 이게 이 글의 핵심이다.

---

## 6주 타임라인 — 어떤 PR이 어떤 항목을 채웠나

| 주차 | 머지 | 채운 항목 | 비고 |
|---|---|---|---|
| Week 1 | PR #340 | `dco` (CLA로 대체) | CLA Assistant Lite 봇 + Relicensing Grant §4-bis |
| Week 2 | PR #353 | `code_of_conduct` · `governance` · `roles_responsibilities` | Contributor Covenant v2.1 + GOVERNANCE.md (BDFL 모델, 3개 결정 클래스) |
| Week 3 | PR #356 | `static_analysis_common_vulnerabilities` | bandit SAST 워크플로 + 기존 HIGH-severity 결함 청소 |
| Week 4 | PR #360 | `assurance_case` | 26 KB 문서, R1~R8 요구사항, T1~T18 위협, 47개 file:line 인용 |
| Week 5 | PR #362 | `access_continuity` · `bus_factor` | 정직한 UNMET + lockbox/legal-heir 계획 + bus factor 정당화 |
| Week 6 | PR #363 | `documentation_current` (+ stale 4건 fix) | CONTRIBUTING.md에 정책 신설 + 자동화 없는 drift detection 합의 |

거의 매주 PR 하나씩, 모두 main 머지까지 완주. 9개 silver-tier MUST/SHOULD
항목을 새로 채우거나 강화했다. passing → silver 사이의 일반적인 평균
소요시간이 6–12개월이라는 통계를 봤는데, 1인 운영으로 6주는 빠른 편이라고
생각한다.

---

## 깨달음 1: "정직한 UNMET"이 실버 통과의 핵심이었다

내가 가장 두려워했던 항목은 `access_continuity` (MUST) 와 `bus_factor`
(SHOULD) 였다. 1인 메인테이너 프로젝트가 "한 사람이 사라져도 일주일 내
계속될 수 있다"를 어떻게 증명하나? 두 명을 영입할 시간도 의지도 없는데?

OpenSSF 가이드를 정독하다가 한 줄을 발견했다.

> Individuals who run a FLOSS project MAY do this by providing keys in
> a lockbox and a will providing any needed legal rights.

요지: **두 명이 있을 필요는 없다. lockbox + 법적 인계만 문서화되면 된다.**
그리고 결정적으로, **그 문서가 아직 *운영되지 않더라도*, 계획이 명시적
이고 마일스톤 날짜가 있으면 평가자가 인정해 준다**.

이걸 발견한 후 PR #362에서 `GOVERNANCE.md §7 Access continuity` 와
`§8 Bus factor` 를 새로 썼다. 핵심은 두 가지:

1. **현재 상태를 거짓 없이 UNMET 으로 표기**. "lockbox는 아직 없음.
   2026-Q3 까지 수립 예정"이라고 못박음.
2. **무엇을 어떻게 운영할 것인지의 구체 카테고리**. 6가지 자산 (GitHub
   admin, CI secrets, 도메인, 패키지 레지스트리, PGP 키, 연락 이메일)
   각각에 대한 회수 경로 + 검증자를 표로 정리.

bus_factor도 마찬가지였다. "현재 1이고, BDFL 모드는 v1.0까지의 의도된
트레이드오프이며, 6가지 회복-비용 완화 장치가 있고, 2027-Q3까지 2를
달성한다"는 명시. SHOULD 항목은 OpenSSF가 정당화를 인정해주므로 통과.

**이 깨달음이 컸던 이유**: silver 티어를 받기 위해 "1명 더 영입"이라는
구조적 변경이 필요할 줄 알았는데, 사실은 *문서화된 회복 가능성* 만으로
충분했다. 빠르게 거짓 정보를 채워 통과시키는 것보다, 빈틈을 정직하게
공개하는 게 평가에서 더 강하게 작용한다. 패치 안 한 보안 결함도 마찬가지
원리겠다.

---

## 깨달음 2: assurance case가 가장 무거웠고 가장 보람있었다

`assurance_case` (PR #360) 는 silver 항목 중 작성 비용이 압도적으로
컸다. 26 KB 단일 마크다운 문서, 8개 보안 요구사항(R1~R8), 18개 위협
시나리오(T1~T18), 그리고 각 요구사항마다 *코드 인용* 으로 논증.

> **R3. PII는 사용자에게 노출되기 전에 마스킹된다.**
>
> **논거**: `core/output_filter.py:142` 의 `mask_pii()` 가
> `core/llm_router.py:88` 의 응답 직렬화 전에 호출된다. 마스킹 패턴은
> `core/pii_patterns.py:1-67` 에서 12종 정의. role 별 필터링은
> `core/security_layer.py:215` (manager 이상은 마스킹된 원본의 일부를
> 볼 수 있음).

같은 양식으로 47개 file:line 인용이 들어갔다. **부수효과**: 이 문서를
쓰면서 *코드가 실제로는 그렇게 안 돌아가는 케이스* 를 두 군데 발견했다.
하나는 audit log 락 경합 — 동시 PII 마스킹 시 race condition 가능성.
다른 하나는 sandbox capability 체크 누락 (이미 별 PR로 패치됨).

평가자에게 "이 프로젝트는 보안을 신중히 생각합니다"를 *증명하는*
가장 강한 도구는 **자기 코드를 의심하면서 다시 읽는 행위 그 자체**
였다. 그리고 그 결과물이 외부에서 검증 가능한 문서로 남는다.

문서 끝에는 `§6. Known gaps and limitations` 섹션을 두고 T11~T18
(아직 방어되지 않은 위협 8개) 을 명시했다. 이걸 빼고 "다 막혀 있다"고
쓰는 게 더 좋아 보였지만, OpenSSF는 정직한 공개를 가산 평가한다.

---

## 깨달음 3: 문서 currency는 자동화 없이도 잡힌다

`documentation_current` (MUST) 는 가장 만만해 보였는데, 실제로 grep을
돌려보니 stale 참조가 4건 있었다:

- `SECURITY.md:5` — "alpha (v0.1.0)" (현재 v0.3.0)
- `docs/ARCHITECTURE.md:7` — "Last updated: v0.2.0-dev" (현재 v0.3.0)
- `ROADMAP.md:11` — "v0.1.0 — Foundation (current, alpha)" (현재 cycle은 v0.3.0)
- `SECURITY.md:273` — Changes Log가 v0.1.0-alpha까지만 기재

PR #363에서 4건 모두 수정하고, `CONTRIBUTING.md` 에 **"Documentation
currency"** 정책 섹션을 신설했다. 핵심은 자동화 없이 *프로세스로* 잡는
방법:

```markdown
**What the maintainer does at each minor-version cut.**

- Update Project Status header of README.md/README.ko.md/README.beginner.ko.md
- Update docs/ARCHITECTURE.md "Last updated" footer
- Update SECURITY.md Project Status header + append Changes Log entry
- Move ROADMAP.md "(current cycle)" marker
- Sweep docs/handovers/ for closure markers
```

이게 *정말로* 자동화 없이 동작할까? 솔직히 모르겠다. 다음 cycle 마다
사람이 까먹지 않으려면 결국 lint가 필요할 거다. 그래서 정책 마지막에
**"미래의 `docs(ci): documentation_current linter` PR로 자동화 예정"**
이라고 명시했다. 미래 약속이지 현재 보장은 아닌데, OpenSSF는 *현재의
프로세스 + 문서화된 개선 경로* 를 모두 평가한다.

---

## 무엇을 안 했는지 (Out of scope)

이번 6주에 **하지 않은** 것들. 이것도 회고의 일부다.

- **bus factor를 실제로 2로 올리는 것.** 두 번째 메인테이너 영입은
  여전히 안 됐다. CLAUDE.md의 "no parallel domains" 원칙 때문에
  contract drift 리스크가 더 큰 위협이라고 판단함. v1.0 transition
  PR에서 다룰 것.
- **documentation_current 자동 lint.** 위에 적은 대로 다음 cycle.
- **도메인 분화** (법률/식품/유통 등). 모체 플랫폼 강화가 v1.0까지의
  유일한 우선순위. silver 뱃지가 도메인 진입을 정당화하지는 않는다.
- **silver 신청 직후 gold 도전.** gold는 또 다른 80개 항목이 추가
  되는데, 그 중 일부는 *프로젝트 외부 인프라* 까지 요구한다 (예:
  서명된 릴리스 → key management 인프라). 현재 1인 운영 규모에는
  과한 비용 대비 가치.

---

## 동시에 떨어진 세 가지 — 특허, v0.3, silver

이 글을 쓰는 시점에 세 가지가 동시에 정리됐다.

1. **특허 출원**. JAMES의 핵심 디자인 패턴 (정확한 내용은 출원 절차상
   여기서 풀지 않음) 에 대한 출원이 들어갔다. 이건 *공개해도 IP가
   증발하지 않는다* 는 의미 — 즉 기술 글을 마음껏 써도 된다.
2. **v0.3.0 Platform Skeleton** 진입. 6축 Foundation Hardening 통과
   후 모체 골격이 main에 올라온 상태.
3. **OpenSSF 실버 136%**. 위에 적은 6주의 결과.

세 가지가 우연이 아니라 같은 트랙의 산출물이다: **모체를 단단히
만든다 → 외부에서 검증 가능한 형태로 만든다 → 법적으로 보호한다**.
이 순서가 도메인 분화 (legal/food/retail) 진입의 *전제조건* 이라고
v0.3.0 처음부터 합의해두었다. v1.0까지는 모체만 단단히 한다는 원칙
(`CLAUDE.md` rule 1) 의 이유다.

---

## 마무리 — 1인 OSS도 silver를 받을 수 있다

OpenSSF 실버 티어의 80여 개 항목을 처음 봤을 때는 "이건 팀 프로젝트의
영역"이라고 느꼈다. 6주를 거치고 나니 정반대 결론에 도달했다:
**모든 항목은 1인 메인테이너도 달성 가능하지만, 그 방법은 종종
"정직한 UNMET + 문서화된 회복 경로"** 다. OpenSSF는 그것을 인정해주는
방향으로 매우 잘 설계되어 있다.

요약하면:

| 깨달음 | 시사점 |
|---|---|
| UNMET을 거짓 없이 표기하면 통과 | bus_factor·access_continuity 1인 운영도 가능 |
| Assurance case 작성이 보안 결함을 찾아준다 | 26 KB 비용 대비 부수효과 큼 |
| Doc currency는 정책으로 먼저, 자동화는 다음에 | 자동 lint 없이도 silver 통과 |
| 모든 빈틈은 미래 PR로 약속 명시 | 평가자는 "현재 + 개선 경로"를 같이 본다 |

코드는 GitHub에서: <https://github.com/Hashevolution/James-RAG-Evol>
OpenSSF 페이지: <https://www.bestpractices.dev/projects/12806>

다음 글은 아마도 v0.4 진입 후의 "도메인 분화 첫 PR" 회고가 될 것
같다. 그때까지는 모체만 단단히.

---

*이 글은 JAMES 프로젝트 v0.3.0 — Platform Skeleton 시점 (2026-05-20)
의 기록입니다. 라이선스: MIT. 오타·사실관계 오류는
[GitHub Issues](https://github.com/Hashevolution/James-RAG-Evol/issues)
로 알려주세요.*
