# [임시명세서 초안] STAGE 3 — Security 2-stage + Cross-stage ABAC

> 본 문서는 STAGE 3 (점수 2/5) 임시명세서 작성을 위한 skeleton입니다.
> 특허로(patent.go.kr) 전자출원 시 본 문서를 기반으로 PDF·hwp로 전환하여 첨부하십시오.
> 작성 시 [TODO] 마커를 모두 제거·채워주세요.
>
> **참고 자료**: `core/security_layer.py:169-389` (구현 완료).
>
> ⚠️ "graph traversal per-hop role gating"은 미구현이므로 청구 제외 (포함 시 무효 위험).

---

## 발명의 명칭
**역할 기반 LLM 응답 시스템에서 입력·출력 2단계 검증과 cross-stage ABAC 일관성 검증을 통한 보안 방법**
(영문: Two-stage Security with Cross-stage ABAC Verification for Role-based LLM Response Systems)

## 출원인
[TODO: 성명 / 주소 / 주민번호 또는 외국인등록번호]

## 발명자
[TODO: 성명 / 주소]

## 공지예외 주장
- 공개일자: 2026-05-05
- 공개매체: GitHub public repository (https://github.com/Hashevolution/James-RAG-Evol)
- 공개주체: 발명자 본인
- 공지예외 만료일: **2027-05-04**
- 증빙: `docs/patent/disclosure_log.txt`

---

## 1. 기술 분야

본 발명은 LLM 기반 응답 생성 시스템의 보안에 관한 것으로, 보다 구체적으로는 사용자 역할에 따라 입력 단계의 prompt injection 검출과 출력 단계의 PII/엔티티 마스킹을 수행하면서, 입력→검색→출력의 3단계에서 동일 ABAC 정책이 일관되게 적용됐는지 사후 검증하는 방법에 관한 것이다.

## 2. 배경 기술

### 2.1 기존 LLM 보안의 한계

기존 LLM 시스템의 보안은 다음 한계를 가진다:
- **입력 단계 부재**: prompt injection이 무방비로 LLM에 전달되어 system prompt 탈취 위험
- **출력 단계 부재 또는 단순**: PII가 응답에 포함되어 데이터 누출
- **단계 간 일관성 부재**: Vector 검색 단계에서 권한 통과한 결과가 Graph 단계에서 다시 검사 안 됨 → policy drift
- **역할별 차별화 부재**: external/employee/manager/admin 역할이 동일 처리 받음

### 2.2 RBAC vs ABAC

기존 RBAC(Role-Based Access Control)는 역할별 정적 권한 매핑이지만, ABAC(Attribute-Based Access Control)는 동적 attribute 기반 판정이 가능. 그러나 LLM 응답 파이프라인의 다단계(Vector → Graph → Output) 흐름에서 ABAC 정책의 cross-stage 일관성을 보장하는 메커니즘은 부재.

## 3. 해결하고자 하는 과제

1. 입력 단계에서 prompt injection 실시간 검출 + 무력화
2. 출력 단계에서 역할별로 PII와 person entity 이름을 마스킹
3. Vector 단계 → Graph 단계 → Output 단계의 ABAC 일관성 사후 검증
4. 역할 admin도 차단 가능한 정책 — admin 권한 탈취 시도까지 방어

## 4. 과제의 해결 수단

### 4.1 Stage 1 — 입력 Pre-check (`core/security_layer.py:323-362`)

```python
class SecurityLayer:
    def pre_check(self, query: str, user_role: str) -> dict:
        # 1. 입력 유효성
        ok, reason = validate_input(query)
        if not ok: return {"allowed": False, "reason": "..."}

        # 2. 공격 탐지 — admin도 차단
        if detect_attack(query):
            log_attack(query, user_role)
            return {"allowed": False, "reason": "보안 정책에 의해 차단"}

        # 3. Instruction Isolation
        safe_query, was_modified = extract_data_only(query)

        # 4. query 정제
        safe_query = self._sanitize_query(safe_query)
        return {"allowed": True, "query": safe_query}

    def _sanitize_query(self, text: str) -> str:
        """ATTACK_PATTERNS + ATTACK_REGEX 둘 다 치환"""
        for pattern in ATTACK_PATTERNS:
            text = re.sub(re.escape(pattern), "[BLOCKED]", text, flags=re.IGNORECASE)
        for pattern in ATTACK_REGEX:
            text = re.sub(pattern, "[BLOCKED]", text, flags=re.IGNORECASE)
        return text[:500]
```

### 4.2 Stage 2 — 출력 Post-check (`core/security_layer.py:253-316`)

10개 PII 정규식 + 역할별 차단 키워드 + person entity 마스킹:

```python
SENSITIVE_PATTERNS = [
    (r"\b\d{6}-\d{7}\b", "주민번호"),
    (r"\b\d{3}-\d{4}-\d{4}\b", "전화번호"),
    (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", "이메일"),
    (r"password\s*[:=]\s*\S+", "비밀번호"),
    (r"비밀번호\s*[:=]\s*\S+", "비밀번호"),
    (r"api[_\-]?key\s*[:=]\s*[\w\-]+", "API키"),
    (r"secret\s*[:=]\s*[\w\-]+", "시크릿"),
    (r"token\s*[:=]\s*[\w\.\-]+", "토큰"),
    (r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b", "카드번호"),
    (r"계좌[번호\s]*[:\s]*[\d\-]+", "계좌번호"),
    (r"\b[A-Z]{2,5}-\d{4,8}\b", "내부코드"),
]

BLOCKED_KEYWORDS_BY_ROLE = {
    "external": ["급여", "연봉", "salary", "개인정보", "주민", "비밀",
                 "confidential", "기밀", "내부망", "DB 구조", "스키마"],
    "employee": ["급여", "salary", "주민등록번호", "비밀번호", "secret"],
}

SENSITIVE_ENTITY_TYPES_BY_ROLE = {
    "external": {"person"}, "employee": set(),
    "manager":  set(), "admin": set(),
}
```

`mask_sensitive()` 는 키워드 + 뒤따르는 값까지 함께 마스킹 (예: "급여: 5000만원" → "[REDACTED]"), `filter_answer_by_role()` 는 graph context의 person entity 이름 + wiki person names 를 모두 마스킹.

### 4.3 Cross-stage ABAC 일관성 검증 (`core/security_layer.py:169-224`)

```python
def cross_stage_abac_verify(
    user_role: str, vector_docs: list, graph_entities: list, final_answer: str
) -> Dict:
    violations, stage_results = [], {}

    # Stage 1: Vector
    for doc in vector_docs:
        meta = doc.get("metadata", {"sensitivity": "public"})
        if not check_access(user_role, meta):
            violations.append(f"Vector 우회: role={user_role} sens={meta.get('sensitivity')}")

    # Stage 2: Graph
    for entity in graph_entities:
        if not check_access(user_role, entity):
            violations.append(f"Graph 우회: entity={entity.get('name')} sens={entity.get('sensitivity')}")

    # Stage 3: Output 키워드 누출 (external 한정)
    if user_role == "external" and final_answer:
        for kw in ["비밀", "confidential", "기밀", "salary", "급여", "주민번호", "secret"]:
            if kw.lower() in final_answer.lower():
                violations.append(f"Output 누출: 민감 키워드 '{kw}' → external 노출")

    consistent = len(violations) == 0
    if not consistent:
        log_system_event("abac_violation", f"role={user_role} violations={violations}")
    return {"consistent": consistent, "violations": violations,
            "stage_results": stage_results, "role": user_role}
```

세 단계 모두에서 동일 사용자 역할로 일관된 정책이 적용됐는지 사후 확인하고, 위반 시 audit log + 운영자 알림.

### 4.4 4-Tier 역할 계층

```python
ROLE_LEVEL = {"external": 0, "employee": 1, "manager": 2, "admin": 3}
SENSITIVITY_LEVEL = {"public": 0, "internal": 1, "confidential": 2, "secret": 3}

def check_access(user_role: str, entity: dict) -> bool:
    return ROLE_LEVEL.get(user_role, 0) >= SENSITIVITY_LEVEL.get(entity.get("sensitivity", "public"), 0)
```

## 5. 효과

1. **입력 prompt injection 차단** — admin 권한이라도 차단되어 권한 탈취 방어
2. **출력 PII 다층 마스킹** — 정규식 10종 + 역할별 키워드 + entity 이름 모두 적용
3. **단계 간 정책 drift 탐지** — Vector·Graph·Output 어느 한 단계만 약화돼도 ABAC verify에서 위반 검출
4. **External 추가 보호** — external 역할은 person entity 이름까지 마스킹, 인물 정보 누설 방지
5. **Audit 가능** — 모든 위반·차단이 log에 기록되어 사후 책임 추적

## 6. 청구범위

### 청구항 1 (방법)

LLM 기반 응답 생성 시스템의 보안 방법으로서,
(a) 사용자 query 수신 시 입력 단계에서 사전 정의된 prompt injection 패턴 (정규식 사전) 을 검출하여 매칭 시 query를 차단하거나 매칭 부분을 무력화 토큰으로 치환하는 단계;
(b) 응답 생성 후 출력 단계에서 (i) PII 정규식 10종으로 마스킹, (ii) 사용자 역할별 차단 키워드 사전으로 마스킹, (iii) graph context와 wiki에서 추출된 person entity 이름을 마스킹하는 단계;
(c) Vector 검색 결과·Graph traversal 결과·최종 응답 모두에 대해 동일 사용자 역할로 ABAC 정책이 일관되게 적용됐는지 사후 검증하고 위반 발견 시 audit log에 기록하는 단계
를 포함하는 것을 특징으로 하는, 2단계 + cross-stage ABAC 보안 방법.

### 청구항 2 (시스템)

LLM 기반 응답 시스템으로서,
- (1) 입력 단계 pre-check 모듈,
- (2) 출력 단계 post-check 모듈,
- (3) Vector·Graph·Output 3단계 ABAC 일관성 검증 모듈,
- (4) 4-tier 역할 계층(`external`, `employee`, `manager`, `admin`) 과 4-tier 민감도(`public`, `internal`, `confidential`, `secret`),
- (5) 위반 audit log
를 포함하는 것을 특징으로 하는 시스템.

### 청구항 3 (종속 — 입력 prompt injection 패턴)

청구항 1에 있어서, 입력 단계의 prompt injection 패턴은 ATTACK_PATTERNS 정확 매칭 사전과 ATTACK_REGEX 정규식 사전 두 개로 분리되며, 둘 다에 대해 치환을 수행하는 것을 특징으로 하는 방법.

### 청구항 4 (종속 — 키워드+값 마스킹)

청구항 1에 있어서, 출력 단계의 키워드 마스킹은 키워드 단독이 아닌 키워드와 그 뒤를 따르는 값까지 함께 `[REDACTED]`로 치환하는 것을 특징으로 하는 방법 (예: "급여: 5000만원" 전체 치환).

### 청구항 5 (종속 — Person entity 마스킹)

청구항 1에 있어서, 사용자 역할이 external인 경우 graph context의 entity_type=="person" 인 모든 entity의 name과, wiki에서 추출된 person 이름 목록 양쪽 모두를 응답에서 `[인물명 REDACTED]`로 치환하는 방법.

### 청구항 6 (종속 — Cross-stage 검증)

청구항 1에 있어서, cross-stage 검증은 (i) Vector docs의 metadata.sensitivity, (ii) Graph entities의 sensitivity, (iii) 최종 응답의 민감 키워드 — 세 곳 모두를 동일 user_role로 검사하고 한 곳이라도 위반이 발견되면 inconsistent로 판정하는 방법.

### 청구항 7 (종속 — Admin 차단)

청구항 1에 있어서, prompt injection 검출은 사용자 역할 admin에 대해서도 동등하게 적용되어, admin 권한 탈취 시도를 방어하는 방법.

### 청구항 8 (종속 — 역할 계층)

청구항 2에 있어서, ROLE_LEVEL과 SENSITIVITY_LEVEL은 4-tier (0~3) 정수로 정의되며, 사용자 역할 레벨이 entity 민감도 레벨 이상일 때만 접근 허용되는 시스템.

### 청구항 9 (종속 — Instruction Isolation)

청구항 1에 있어서, 입력 단계는 prompt injection 검출 외에 추가로 instruction isolation (사용자 발화 중 시스템 instruction 형태의 부분을 데이터 영역으로 격리) 을 적용하는 방법.

### 청구항 10 (종속 — Audit log)

청구항 1에 있어서, 모든 차단·마스킹·위반 이벤트는 timestamp, user_role, 매칭 패턴, 차단 사유와 함께 audit log에 기록되어 사후 책임 추적이 가능한 방법.

## 7. 도면 (작성 필요)

- **도면 1**: 입력 pre-check 흐름 — validate → detect_attack → extract_data_only → sanitize
- **도면 2**: 출력 post-check 흐름 — graph_context masking → wiki_person masking → PII regex → role keyword masking
- **도면 3**: Cross-stage ABAC verify 구조 — Vector / Graph / Output 3단계 검사 + 위반 누적
- **도면 4**: Role × Sensitivity 4×4 매트릭스 — 접근 허용/거부 판정

## 8. 실시예 (Working Example)

`core/security_layer.py:169-389` 전체 — 본 명세서에 부속서로 첨부.

특히 다음 함수들이 핵심:
- `pre_check()` (라인 323-362)
- `mask_sensitive()` (라인 253-275)
- `filter_answer_by_role()` (라인 277-316)
- `cross_stage_abac_verify()` (라인 169-224)
- `SecurityLayer` 클래스 (라인 320-394)

## 9. 산업상 이용 가능성

본 발명은 기업 내부 챗봇, 정부·공공기관 LLM 시스템, 의료·법률 상담 봇, 다중 사용자 SaaS 챗봇 등 사용자 역할별 데이터 접근 제어가 필요한 모든 환경에 산업상 이용 가능하다.

---

## 10. 출원 시 체크리스트

- [ ] 발명자/출원인 정보 기재
- [ ] 도면 1~4 작성 (`assets/patent/stage3-figs/` 권장)
- [ ] §6 청구항 한국어 법률 용어 검수
- [ ] ⚠️ "graph traversal per-hop role gating"은 미구현이므로 청구·실시예에서 절대 언급 금지
- [ ] 공지예외 적용 신청서 별도 첨부
- [ ] 출원료 6만원 (개인 감면 시 1.8만원) 납부

---

**End of skeleton.**
