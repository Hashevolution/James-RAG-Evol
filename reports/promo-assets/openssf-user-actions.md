# OpenSSF Best Practices Badge — 신청 직전 사용자 작업

> 본 가이드는 `../session-2026-05-09-promotion-readiness.md` Phase 4의 보충 문서입니다.
> 코드/문서 변경은 자동으로 반영했지만, 다음 두 항목은 **GitHub UI에서 사용자만 할 수 있습니다.**

---

## 작업 1. GitHub Private Vulnerability Reporting 활성화 ✅ 완료

> 2026-05-11: 사용자가 GitHub 리포 Settings → Code security and analysis에서 활성화 확인.
> SECURITY.md의 1순위 링크가 동작합니다.

SECURITY.md에 안내한 1순위 채널이 실제로 동작하려면 리포 설정에서 한 번 켜야 합니다.

### 단계별

1. 브라우저로 `https://github.com/Hashevolution/James-RAG-Evol` 접속.
2. 상단 메뉴에서 **Settings** 클릭. (관리자 권한 필요)
3. 왼쪽 사이드바 **"Code security and analysis"** (또는 "Security" → "Code security") 클릭.
4. 페이지 안에서 **"Private vulnerability reporting"** 섹션을 찾습니다.
5. 우측의 **Enable** 버튼 클릭.
6. (선택) "Permission setup" 같은 추가 안내가 나오면 따라 진행. 보통 추가 권한 없이 즉시 활성화.
7. 활성화 확인:
   - `https://github.com/Hashevolution/James-RAG-Evol/security/advisories/new` 가 200으로 열리면 성공.
   - 닫혀 있으면 "Not enabled" 메시지가 보입니다.

### 검증

- SECURITY.md의 1순위 링크 클릭 → 신고 폼이 떠야 합니다.
- 안 뜨면 사이드바에서 "Reports" 또는 "Advisories" 권한이 비활성화 상태일 수 있습니다.

---

## 작업 2. 백업 이메일 채워 넣기 ✅ 완료

> 2026-05-11: `karu-7@hanmail.net` 으로 확정. SECURITY.md에 반영.

GitHub PVR 장애·외부인 신고 시 이메일이 백업 채널 역할을 합니다.
스팸 부담이 생기면 (b) GitHub 메일 또는 (c) 도메인 메일로 추후 교체 가능.

---

## 작업 3. (선택) CI 뱃지 추가

GitHub Actions 워크플로가 1개 이상 있다면 README 상단에 뱃지를 붙이는 것이 OpenSSF "automated tests" 항목 증빙으로 강력합니다.

확인 방법:

```bash
ls -la .github/workflows/ 2>/dev/null
```

워크플로 파일이 보이면 그 파일명을 알려주세요. README 상단 뱃지 라인에 다음 형태로 추가합니다:

```markdown
[![CI](https://github.com/Hashevolution/James-RAG-Evol/actions/workflows/<file>.yml/badge.svg)](https://github.com/Hashevolution/James-RAG-Evol/actions)
```

워크플로가 없으면 OpenSSF 신청에서 "automated tests"를 "Met"으로 처리하되 증빙은 `james_*_test.py` 파일 링크로 대체.

---

## 작업 4. OpenSSF Badge 페이지에서 자가 평가 시작

위 작업 1~2가 끝나면 본 메인 가이드의 Phase 4-2 ~ 4-4를 그대로 따라가면 됩니다.

요약:
- `https://www.bestpractices.dev/` → Sign in (GitHub OAuth)
- "+ Add" → Project URL = `https://github.com/Hashevolution/James-RAG-Evol`
- 항목별 Met / Unmet / N/A 체크. 각 Met 옆에 GitHub 영구 링크(파일/커밋 hash) 첨부
- 100% 도달 시 자동 발급 → 발급된 마크다운 스니펫을 README 뱃지 라인에 추가
