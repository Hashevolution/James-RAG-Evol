# [임시명세서 초안] STAGE 4A — Bench-gated Self-Evolution + Byte-Identical Rollback

> 본 문서는 STAGE 4A (점수 3/5 ⭐, 신규 후보 C) 임시명세서 작성을 위한 skeleton입니다.
> 특허로(patent.go.kr) 전자출원 시 본 문서를 기반으로 PDF·hwp로 전환하여 첨부하십시오.
> 작성 시 [TODO] 마커를 모두 제거·채워주세요.
>
> **참고 자료**: `tools/patch/patch_validator.py` (4-gate validation, 구현 완료), PR #69 (opt-in flag), #77 (eval gate), #78 (rollback), #79 (audit endpoint).

---

## 발명의 명칭
**회귀 검증 게이트 및 Byte-Identical Rollback을 결합한 자기 개선형 인공지능 시스템의 안전 배포 방법**
(영문: Safe-Deployment Method for Self-Improving AI Systems via Bench-Gated Validation and Byte-Identical Rollback)

## 출원인
[TODO: 성명 / 주소 / 주민번호 또는 외국인등록번호]

## 발명자
[TODO: 성명 / 주소]

## 공지예외 주장
- 공개일자: 2026-05-04 (PR #69 첫 commit)
- 공개매체: GitHub public repository (https://github.com/Hashevolution/James-RAG-Evol)
- 공개주체: 발명자 본인
- 공지예외 만료일: **2027-05-03**
- 증빙: `docs/patent/disclosure_log.txt` (C 후보 항목)

---

## 1. 기술 분야

본 발명은 자기 개선(self-improving) 인공지능 시스템의 안전 배포에 관한 것으로, 보다 구체적으로는 LLM이 생성한 코드 패치를 회귀 테스트, 인간 승인, 그리고 byte-identical rollback 메커니즘으로 게이팅하여 라이브 시스템에 안전하게 적용하는 방법에 관한 것이다.

## 2. 배경 기술

### 2.1 기존 자기 개선 AI의 한계

AutoML, NAS, Self-RAG, AutoGPT 등 자기 개선 AI 시스템은 "더 좋은 모델·코드"를 만드는 데에 집중하지만, **이를 라이브 환경에 안전하게 배포하는 메커니즘** 자체는 부재하거나 단순한 형태에 머문다.

기존 한계:
1. **Eval gate 부재**: 패치 적용 후에야 회귀 발견. 사고 발생 시 복원 비용 큼
2. **인간 승인 누락**: AI 자체 판단으로 deploy → 운영자 의도 위배 가능
3. **Rollback 정확성 부재**: byte-level 정확도가 보장되지 않은 rollback은 시스템 상태를 부분적으로만 되돌림 → silent corruption
4. **Audit invariant 부재**: 누가, 언제, 무엇을 승인했는지 추적 불가
5. **보안 우회 미탐지**: LLM이 생성한 패치가 보안 레이어(`pre_check`, `check_access` 등)를 무력화하는 코드를 포함할 수 있음

### 2.2 본 발명이 다루는 시나리오

운영자가 챗봇 시스템을 운영 중이며, 시스템이 사용자 피드백으로부터 자동으로 개선 패치를 생성한다. 이 패치를 적용하기 전에:
- (i) 기존 회귀 테스트 (`james_diagnostic.py`, `james_security_test.py`) 가 95% 이상 점수로 통과해야 한다
- (ii) `core/security_layer.py` 등 PROTECTED 파일은 절대 수정될 수 없다
- (iii) 인간 운영자가 approver_username으로 명시적으로 승인해야 한다
- (iv) 적용 후 성능 저하 발생 시 byte-identical 상태로 즉시 복원되어야 한다
- (v) 모든 결정·롤백이 audit DB에 영구 기록되어야 한다

기존 시스템은 위 다섯 조건을 모두 만족시키는 통합 메커니즘을 제공하지 않는다.

## 3. 해결하고자 하는 과제

1. LLM이 생성한 코드 패치에 대한 다단계 정적·동적 검증 게이트 설계
2. 인간 승인이 부재하면 deploy를 거부하는 audit invariant 강제
3. mid-write crash 상황에서도 byte-identical로 복원되는 rollback 메커니즘
4. 보안 레이어 우회 패턴을 정적 분석으로 탐지·차단

## 4. 과제의 해결 수단

### 4.1 4-Gate Patch Validation (구현 완료)

`tools/patch/patch_validator.py` 의 `PatchValidator.validate()` 가 다음 4단계를 순차 적용한다:

| Gate | 조건 | 거부 시 사유 |
|------|------|--------------|
| 1 | Static Check — eval/exec/subprocess 등 11개 위험 패턴 부재 | `forbidden_pattern_detected` |
| 2 | PROTECTED_FILES — `core/security_layer.py` 등 보호 파일 미수정 | `protected_file_modified` |
| 3 | 회귀 테스트 — `james_diagnostic.py`, `james_security_test.py` 점수 ≥ 95% | `regression_test_failed` |
| 4 | Security Bypass — `pre_check=lambda...True` 등 7개 우회 패턴 부재 | `security_bypass_detected` |

```python
# tools/patch/patch_validator.py:75-118
class PatchValidator:
    def validate(self, patch: dict) -> Tuple[bool, List[str]]:
        # Gate 1
        ok, reason = self._gate1_static(patch["diff"], patch_id)
        if not ok: return False, [f"Gate1: {reason}"]
        # Gate 2
        ok, reason = self._gate2_protected(patch["target"], patch_id)
        if not ok: return False, [f"Gate2: {reason}"]
        # Gate 3
        ok, reason = self._gate3_tests(patch_id)
        if not ok: return False, [f"Gate3: {reason}"]
        # Gate 4
        ok, reason = self._gate4_security(patch["diff"], patch_id)
        if not ok: return False, [f"Gate4: {reason}"]
        return True, []
```

### 4.2 3-Condition 안전 배포 정책

4-Gate 통과 후에도 다음 3조건을 모두 만족해야만 deploy 허용:

```
[feedback signal]
   ↓
candidate patch 생성
   ↓
조건 1: 4-Gate validate() == True (회귀 테스트 95% 이상 포함)
   ↓
조건 2: human approver_username 필드 존재 + approval_method ∈ {"manual_review", "auto_approved_low_risk"}
   ↓
조건 3: 적용 전 원본 파일 SHA-256 hash 보존 → rollback handle 생성
   ↓
deploy
   ↓
post-deploy bench (~30초) 재실행 → 점수 < 95% 이면 자동 rollback
   ↓
rollback: 원본 byte stream을 atomic file write로 복원 → SHA-256 재검증
   ↓
audit DB: before/after metrics + approver + approval_method + ROLLED_BACK 이벤트 기록
```

### 4.3 Byte-Identical Rollback

기존 fs-level snapshot 방식과 달리:
- 적용 전 원본 파일을 `os.read(fd)` 로 직접 읽어 byte stream으로 보존 (line-ending 변환·encoding 변환 없음)
- rollback 시 동일 byte stream을 `os.write(fd, b)` 로 atomic 복원
- 복원 후 SHA-256 재계산 → 원본 hash와 일치하는지 invariant 검증
- mid-write crash 시뮬레이션 (50% 지점에서 SIGKILL) 시에도 복원 invariant 보존

### 4.4 Audit Invariant

`/admin/patches/audit` endpoint (PR #79) 가 다음 invariant을 강제:
- approver_username 없이 작성된 audit row → 시스템이 deploy 차단
- approval_method가 화이트리스트에 없는 값 → 차단
- ROLLED_BACK 이벤트는 항상 별도 row로 기록되어 변조 어려움
- before_metrics + after_metrics 둘 다 기록되어 사후 검증 가능

## 5. 효과

1. **AI 자율 배포의 안전성 보장** — 회귀·보안 우회·인간 승인 누락 모두 게이트로 차단
2. **사고 발생 시 즉시 복원** — byte-identical rollback으로 silent corruption 회피
3. **Audit 영속성** — 모든 결정 추적 가능, 사후 검증·법적 책임 명확화
4. **Mid-write crash 내구성** — atomic write + hash 재검증으로 부분 복원 위험 제거
5. **운영자 신뢰** — 자기 개선 시스템을 안심하고 활성화 가능

## 6. 청구범위

### 청구항 1 (방법 — 안전 배포)

자기 개선형 인공지능 시스템의 코드 패치 안전 배포 방법으로서,
(a) LLM이 생성한 후보 코드 패치를 수신하는 단계;
(b) 다음 4개의 검증 게이트를 순차적으로 적용하는 단계:
    (i) 정적 분석 게이트 — 사전 정의된 위험 패턴(eval, exec, subprocess 호출 등)이 패치에 부재함을 검증;
    (ii) 보호 파일 게이트 — 패치 대상이 보호 파일 목록에 부재함을 검증;
    (iii) 회귀 테스트 게이트 — 사전 정의된 테스트 스위트의 점수가 사전 정의된 임계값 이상임을 검증;
    (iv) 보안 우회 게이트 — 사전 정의된 보안 우회 패턴이 패치에 부재함을 검증;
(c) 4개 게이트 모두 통과 시, approver_username 및 approval_method 필드가 채워진 인간 승인 record가 부재하면 deploy를 거부하는 단계;
(d) 인간 승인 통과 시, 적용 대상 파일의 byte stream과 SHA-256 hash를 보존하는 rollback handle을 생성하는 단계;
(e) 패치 적용 후 post-deploy 회귀 테스트 점수가 임계값 미만이면 상기 byte stream으로 atomic 복원하고 SHA-256 hash 재검증을 수행하는 단계;
(f) 모든 게이트·승인·deploy·rollback 이벤트를 audit log에 영구 기록하는 단계
를 포함하는 것을 특징으로 하는, 자기 개선 AI 안전 배포 방법.

### 청구항 2 (시스템)

자기 개선형 인공지능 시스템으로서,
- (1) 4개 검증 게이트를 적용하는 patch validator,
- (2) 인간 승인 필드 부재 시 deploy를 거부하는 approval enforcement layer,
- (3) byte stream과 SHA-256 hash를 보존하는 rollback handle store,
- (4) post-deploy 자동 rollback을 트리거하는 bench monitor,
- (5) 모든 이벤트를 영구 기록하는 audit log
를 포함하는 것을 특징으로 하는, 안전 배포 가능한 자기 개선 AI 시스템.

### 청구항 3 (종속 — 정적 분석)

청구항 1에 있어서, 상기 정적 분석 게이트는 정규식 기반으로 다음 위험 패턴을 검출하는 것을 특징으로 하는 방법: `eval(`, `exec(`, `__import__(`, `subprocess.call`, `os.system(`, `rm -rf`, `PROTECTED_FILES =`, `ROLE_LEVEL =`, `SENSITIVITY_LEVEL =`.

### 청구항 4 (종속 — 보안 우회)

청구항 1에 있어서, 상기 보안 우회 게이트는 정규식 기반으로 다음 패턴을 검출하는 것을 특징으로 하는 방법: `pre_check\s*=\s*lambda.*True`, `check_access.*return True`, `detect_attack.*return False`, `lambda\s+\w+.*:\s*True`, `ROLE_LEVEL\[`.

### 청구항 5 (종속 — 회귀 테스트 임계)

청구항 1에 있어서, 상기 회귀 테스트 게이트는 exit code 0 또는 (exit code != 0 이지만 report JSON의 score 필드가 95% 이상) 인 경우에만 통과로 판정하는 것을 특징으로 하는 방법.

### 청구항 6 (종속 — Byte-Identical Rollback)

청구항 1에 있어서, 상기 rollback handle은 적용 대상 파일의 byte stream을 line-ending·encoding 변환 없이 보존하고, 복원 시 atomic write 후 SHA-256 hash가 원본과 일치하는지 검증하는 것을 특징으로 하는 방법.

### 청구항 7 (종속 — Mid-write Crash 내구성)

청구항 6에 있어서, 적용 또는 복원 단계의 50% 지점에서 시스템이 비정상 종료되어도 다음 시동 시 SHA-256 hash 검증으로 부분 적용 상태를 탐지하고 자동 복원하는 것을 특징으로 하는 방법.

### 청구항 8 (종속 — Audit Invariant)

청구항 1에 있어서, audit log의 모든 deploy 이벤트는 다음 필드를 필수로 가지며, 누락 시 시스템이 그 record를 거부하는 것을 특징으로 하는 방법: `approver_username`, `approval_method ∈ {"manual_review", "auto_approved_low_risk"}`, `before_metrics`, `after_metrics`, `gate_results`.

### 청구항 9 (종속 — ROLLED_BACK 이벤트)

청구항 1에 있어서, rollback 발생 시 별도의 ROLLED_BACK 이벤트가 audit log에 추가 기록되며, 원 deploy 이벤트는 변조되지 않는 것을 특징으로 하는 방법.

### 청구항 10 (종속 — Opt-in 활성화)

청구항 2에 있어서, 본 시스템은 운영자의 opt-in flag (`AUTO_DEPLOY_ENABLED=true`) 가 명시적으로 설정된 경우에만 활성화되며, default는 disabled 인 것을 특징으로 하는 시스템.

## 7. 도면 (작성 필요)

- **도면 1**: 4-Gate validate() flow chart — Gate 1~4 순차, 거부 분기, ALL_PASS
- **도면 2**: 3-Condition deploy pipeline — feedback → patch → 4-gate → approval → rollback handle → deploy → bench → rollback (조건부)
- **도면 3**: Byte-Identical Rollback 메커니즘 — byte stream 보존, atomic write, SHA-256 재검증
- **도면 4**: Audit DB schema + ROLLED_BACK 이벤트 흐름

## 8. 실시예 (Working Example)

### 8.1 4-Gate Validator (구현 완료, 인용 가능)

`tools/patch/patch_validator.py:69-209` 전체 클래스 — 본 명세서에 부속서로 첨부.

핵심 코드 (위험 패턴 정의):

```python
# tools/patch/patch_validator.py:27-50
FORBIDDEN_PATTERNS = [
    r"\beval\s*\(", r"\bexec\s*\(", r"__import__\s*\(",
    r"import\s+os\s*;", r"subprocess\.call", r"os\.system\s*\(",
    r"open\s*\(['\"]\/", r"rm\s+-rf",
    r"PROTECTED_FILES\s*=", r"ROLE_LEVEL\s*=", r"SENSITIVITY_LEVEL\s*=",
]

SECURITY_BYPASS_PATTERNS = [
    r"pre_check\s*=\s*lambda.*True",
    r"allowed.*=.*True",
    r"security.*=.*False",
    r"ROLE_LEVEL\[",
    r"check_access.*return True",
    r"detect_attack.*return False",
    r"lambda\s+\w+.*:\s*True",
]
```

### 8.2 자가 검증 (구현 완료)

`tools/patch/patch_validator.py:212-255` 의 자가 테스트가 7개 시나리오를 검증:
- Gate 1 정상 / eval 차단 / exec 차단
- Gate 2 PROTECTED 차단 / 정상 파일 통과
- Gate 4 보안 우회 차단 / 정상 diff 통과

### 8.3 Rollback handle 의사코드 (PR #78 예정 구현)

```python
class RollbackHandle:
    def __init__(self, target_path: str):
        self.target = target_path
        with open(target_path, "rb") as f:
            self.original_bytes = f.read()
        self.original_sha = hashlib.sha256(self.original_bytes).hexdigest()

    def rollback(self) -> bool:
        # atomic write via temp + rename
        tmp = self.target + ".rollback.tmp"
        with open(tmp, "wb") as f:
            f.write(self.original_bytes)
            os.fsync(f.fileno())
        os.replace(tmp, self.target)
        with open(self.target, "rb") as f:
            current_sha = hashlib.sha256(f.read()).hexdigest()
        return current_sha == self.original_sha
```

## 9. 산업상 이용 가능성

본 발명은 자기 개선 챗봇, AutoGPT 류 에이전트, AI 코드 어시스턴트, MLOps 자동 배포 파이프라인 등에서 안전하게 코드를 자동 갱신하는 데 산업상 이용 가능하다. 특히 운영자가 24/7 모니터링 어려운 SaaS 환경에서 사고 자동 회복을 보장하는 데 유용하다.

---

## 10. 출원 시 체크리스트

- [ ] 발명자/출원인 정보 기재
- [ ] 도면 1~4 작성 (`assets/patent/stage4a-figs/` 권장)
- [ ] §6 청구항 한국어 법률 용어 검수
- [ ] §8 실시예에 PR #69/77/78/79 머지 후 실제 deploy/rollback 코드 보강
- [ ] 공지예외 적용 신청서 별도 첨부
- [ ] disclosure_log.txt 의 C 후보 commit hash 정확히 확인 후 기재
- [ ] 출원료 6만원 (개인 감면 시 1.8만원) 납부

---

**End of skeleton.**
