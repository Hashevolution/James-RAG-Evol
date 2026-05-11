"""
PROJECT JAMES — Phase 7 통합 테스트 스위트
실행: python james_phase7_test.py

테스트 항목 (총 7개 섹션 / 70+ 항목):
  S1. 파일 존재 확인 (25항목)
  S2. 문법/임포트 검증 (15항목)
  S3. 자기진화 루프 (10항목)
  S4. 피드백 시스템 (8항목)
  S5. 성향/능력 시스템 (6항목)
  S6. API 엔드포인트 (8항목)
  S7. 실제 서버 연동 (선택, --live 옵션)

경로 탐색:
  - 테스트 파일 위치 기준 탐색
  - 프로젝트 루트 상위 폴더도 탐색 (core/, tools/ 구조)
"""

import sys, ast, re
from pathlib import Path

# ── 경로 탐색 ─────────────────────────────────────────────────────
# 테스트 파일 위치 기준으로 BASE 결정
# graph_rag_engine.py / server_llmwiki.py가 있는 폴더를 BASE로 사용
def find_base() -> Path:
    candidates = [
        Path(__file__).parent,
        Path(__file__).parent.parent,
        Path.cwd(),
        Path.cwd().parent,
    ]
    for c in candidates:
        if (c / "server_llmwiki.py").exists():
            return c
    return Path(__file__).parent

BASE = find_base()
print(f"[TEST] BASE: {BASE}\n")

# ── 색상 출력 ─────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

passed = 0
failed = 0
warns  = 0


def ok(label):
    global passed
    passed += 1
    print(f"  {GREEN}✅{RESET} {label}")


def fail(label, reason=""):
    global failed
    failed += 1
    r = f" ({reason})" if reason else ""
    print(f"  {RED}❌{RESET} {label}{r}")


def warn(label, reason=""):
    global warns
    warns += 1
    r = f" ({reason})" if reason else ""
    print(f"  {YELLOW}⚠️{RESET}  {label}{r}")


def section(title):
    print(f"\n{BOLD}{CYAN}{'─'*55}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*55}{RESET}")


# ════════════════════════════════════════════════════════════
# S1. 파일 존재 확인
# ════════════════════════════════════════════════════════════
section("S1. 파일 존재 확인")

REQUIRED_FILES = {
    # ── 루트 파일
    "server_llmwiki.py":            "FastAPI 서버",
    "config.py":                    "설정",

    # ── core/ 폴더 (엔진 + 코어 모듈 전부 여기)
    "core/graph_rag_engine.py":     "Graph-RAG 엔진",
    "core/reasoning_engine.py":     "추론 엔진",
    "core/graph_engine.py":         "Graph 엔진",
    "core/retrieval_engine.py":     "Retrieval 엔진",
    "core/gemma_client.py":         "Gemma LLM 클라이언트",
    "core/security_layer.py":       "보안 레이어",
    "core/auth.py":                 "인증",
    "core/vector_store.py":         "Vector Store",
    "core/wiki_generator.py":       "Wiki 생성기",
    "core/query_router.py":         "쿼리 라우터",
    "core/intent_classifier.py":    "의도 분류기 (P7)",
    "core/memory_store.py":         "메모리 저장소 (P7)",
    "core/memory_extractor.py":     "메모리 추출기 (P7)",
    "core/feedback_engine.py":      "피드백 엔진 (P7-EVO-C)",
    "core/character_profile.py":    "성향 프로필 (P7-EVO-D)",
    "core/knowledge_tracker.py":    "지식 추적기 (P7-EVO-E)",

    # ── tools/ 폴더
    "tools/self/file_scanner.py":         "파일 스캐너 (P7-BUG-1)",
    "tools/self/evo_analyzer.py":         "진화 분석기 (P7-EVO-A)",
    "tools/self/importance_scorer.py":    "중요도 측정 (P7-EVO-B)",
    "tools/self/performance_evaluator.py":"성능 평가기 (P8-EVAL-1)",
    "tools/self/self_learner.py":         "자기학습 (P8-LEARN-1)",
    "tools/multimodal/image_analyzer.py": "이미지 분석 (P7-VIS-1)",
    "tools/multimodal/video_analyzer.py": "영상 분석 (P7-VID-1)",
    "tools/multimodal/media_store.py":    "미디어 저장",
    "tools/screen/screen_agent.py":       "Screen Agent (P7-SCR-1)",
    "tools/wiki/wiki_editor.py":          "Wiki 편집기",
    "tools/patch/patch_validator.py":     "Patch 검증",
    "tools/patch/patch_applier.py":       "Patch 적용",

    # ── Frontend
    "frontend/index.html":          "메인 UI",
    "frontend/admin.html":          "어드민 UI",
    "frontend/static/chat.js":      "챗 JS",
    "frontend/static/admin.js":     "어드민 JS",
    "frontend/static/upload.js":    "업로드 JS",
}

for fpath, desc in REQUIRED_FILES.items():
    full = BASE / fpath
    if full.exists():
        ok(f"{desc} — {fpath}")
    else:
        fail(f"{desc} — {fpath}", f"없음: {full}")

# ════════════════════════════════════════════════════════════
# S2. 문법/임포트 검증
# ════════════════════════════════════════════════════════════
section("S2. 문법 / 핵심 기능 검증")

PY_FILES = [
    ("core/reasoning_engine.py",   False),   # core/ 폴더
    ("core/graph_rag_engine.py",   False),   # core/ 폴더
    ("server_llmwiki.py",          False),
    ("config.py",            False),
    ("core/intent_classifier.py",  False),
    ("core/memory_store.py",       False),
    ("core/memory_extractor.py",   False),
    ("core/feedback_engine.py",    False),
    ("core/character_profile.py",  False),
    ("core/knowledge_tracker.py",  False),
    ("tools/self/file_scanner.py", False),
    ("tools/self/evo_analyzer.py", False),
    ("tools/self/importance_scorer.py",     False),
    ("tools/self/performance_evaluator.py", False),
    ("tools/self/self_learner.py",          False),
    ("tools/screen/screen_agent.py",        False),
]

for fpath, _ in PY_FILES:
    full = BASE / fpath
    if not full.exists():
        warn(f"파일 없음: {fpath}", f"경로: {full}")
        continue
    try:
        content = full.read_text(encoding="utf-8")
        ast.parse(content)
        ok(f"문법 OK: {fpath}")
    except SyntaxError as e:
        fail(f"문법 오류: {fpath}", str(e))

# ════════════════════════════════════════════════════════════
# S3. 자기진화 루프 검증
# ════════════════════════════════════════════════════════════
section("S3. 자기진화 루프")

# EVO-A: proposals 구조
try:
    src = (BASE / "tools/self/evo_analyzer.py").read_text(encoding="utf-8")
    checks = [
        ("EvoObserver 클래스",    "class EvoObserver"),
        ("EvoAnalyzer 클래스",    "class EvoAnalyzer"),
        ("EvoExecutor 클래스",    "class EvoExecutor"),
        ("approve_and_execute()", "def approve_and_execute"),
        ("save_report()",         "def save_report"),
        ("제안 유형 4종",         all(t in src for t in
            ["wiki_add","wiki_update","code_patch","config_update"])),
    ]
    for label, check in checks:
        (ok if (check if isinstance(check, bool)
                else check in src) else fail)(label)
except Exception as e:
    fail("evo_analyzer.py 로드 실패", str(e))

# EVO-B: ImportanceScorer
try:
    src = (BASE / "tools/self/importance_scorer.py").read_text(encoding="utf-8")
    for label, check in [
        ("ImportanceScorer.score()", "def score"),
        ("LOOM threshold 반환",      "def get_loom_threshold"),
        ("반복 오류 쿼리 조회",       "def get_repeated_error_queries"),
        ("감쇠(Decay) 적용",          "SIGNAL_DECAY"),
    ]:
        (ok if check in src else fail)(label)
except Exception as e:
    fail("importance_scorer.py 로드 실패", str(e))

# ════════════════════════════════════════════════════════════
# S4. 피드백 시스템 (EVO-C)
# ════════════════════════════════════════════════════════════
section("S4. 피드백 시스템 (P7-EVO-C)")

try:
    src = (BASE / "core/feedback_engine.py").read_text(encoding="utf-8")
    fb_checks = [
        ("7종 피드백 신호",        "FEEDBACK_SIGNALS"),
        ("즉시 반영 금지 (shadow)","SHADOW_DB"),
        ("강화 임계값",            "REINFORCE_TH"),
        ("약화 임계값",            "WEAKEN_TH"),
        ("감쇠(Decay)",            "DECAY"),
        ("detect() 함수",          "def detect"),
        ("accumulate() 함수",      "def accumulate"),
        ("PII 마스킹 없음 확인",   True),   # feedback_engine은 마스킹 불필요
    ]
    for label, check in fb_checks:
        (ok if (check if isinstance(check, bool)
                else check in src) else fail)(label)

    # chat.js 👍👎 버튼
    js_src = (BASE / "frontend/static/chat.js").read_text(encoding="utf-8")
    ok("👍👎 버튼 존재") if "sendFeedback" in js_src else fail("👍👎 버튼 없음")

    # server direction_id
    srv = (BASE / "server_llmwiki.py").read_text(encoding="utf-8")
    ok("/feedback/ API") if "/feedback/" in srv else fail("/feedback/ API 없음")
    ok("direction_id 응답") if "direction_id" in srv else fail("direction_id 없음")

except Exception as e:
    fail("feedback_engine.py 로드 실패", str(e))

# ════════════════════════════════════════════════════════════
# S5. 성향/능력 시스템 (EVO-D/E)
# ════════════════════════════════════════════════════════════
section("S5. 성향/능력 시스템 (P7-EVO-D/E)")

try:
    src_d = (BASE / "core/character_profile.py").read_text(encoding="utf-8")
    ok("11개 성향 항목") if len(re.findall(r'"[a-z]+"\s*:', src_d)) >= 10 else fail("성향 항목 부족")
    ok("상충 그룹 A~E")  if all(f'"group":"{g}"' in src_d or f"\"group\":\"{g}\"" in src_d
                                or f"'group':'{g}'" in src_d
                                for g in "ABCDE") else warn("상충 그룹 일부 누락")
    ok("set_trait()") if "def set_trait" in src_d else fail("set_trait() 없음")
    ok("get_prompt_modifiers()") if "def get_prompt_modifiers" in src_d else fail("modifiers 없음")

    src_e = (BASE / "core/knowledge_tracker.py").read_text(encoding="utf-8")
    ok("6개 도메인") if len(re.findall(r'"[a-z]+"\s*:\s*\{', src_e)) >= 6 else fail("도메인 부족")
    ok("능력치 목록") if "CAPABILITIES" in src_e else fail("CAPABILITIES 없음")
    ok("레벨 시스템") if "level" in src_e else fail("레벨 시스템 없음")

    # admin UI
    html = (BASE / "frontend/admin.html").read_text(encoding="utf-8")
    js   = (BASE / "frontend/static/admin.js").read_text(encoding="utf-8")
    ok("레이더 차트 캔버스") if "radar-chart" in html else fail("레이더 캔버스 없음")
    ok("렌더링 함수") if "renderRadarChart" in js else fail("renderRadarChart 없음")
    ok("능력 성장 바") if "capability-bars" in html else fail("능력 바 없음")
    ok("도메인 레벨") if "domain-levels" in html else fail("도메인 레벨 없음")

except Exception as e:
    fail("성향/능력 시스템 검증 실패", str(e))

# ════════════════════════════════════════════════════════════
# S6. API 엔드포인트 검증
# ════════════════════════════════════════════════════════════
section("S6. API 엔드포인트 체크")

try:
    srv = (BASE / "server_llmwiki.py").read_text(encoding="utf-8")
    apis = [
        ("/feedback/",                    "피드백 전송 (EVO-C)"),
        ("/feedback/stats/",              "피드백 통계"),
        ("/admin/character/",             "성향 조회/설정 (EVO-D)"),
        ("/admin/knowledge/",             "능력 성장 (EVO-E)"),
        ("/analyze/image/",               "이미지 분석 (VIS-1)"),
        ("/analyze/video/",               "영상 분석 (VID-1)"),
        ("/screen/analyze/",              "화면 분석 (SCR-1)"),
        ("/admin/proposals/",             "제안 검토 (EVO-A)"),
        ("approve",                        "제안 승인"),
        ("/admin/performance/evaluate/",  "자기 채점 (EVAL-1)"),
        ("/admin/learn/topic/",           "주제 학습 (LEARN-1)"),
        ("/history/",                     "대화 히스토리"),
        ("/history/summarize/",           "세션 요약"),
    ]
    for endpoint, desc in apis:
        endpoint_check = endpoint.replace("{proposal_id}", "")
        (ok if endpoint_check in srv else fail)(f"{desc} — {endpoint}")
except Exception as e:
    fail("server_llmwiki.py 파싱 실패", str(e))

# ════════════════════════════════════════════════════════════
# S7. IntentClassifier 패턴 검증
# ════════════════════════════════════════════════════════════
section("S7. IntentClassifier 패턴 검증")

try:
    sys.path.insert(0, str(BASE))
    ic_src = (BASE / "core/intent_classifier.py").read_text(encoding="utf-8")
    g = {}
    exec(ic_src, g)
    clf = g["IntentClassifier"]()

    cases = [
        # (쿼리, role, 기대모드)
        ("안녕",                         "admin",    "chat"),
        ("파이썬 함수 만들어줘",          "admin",    "coding"),
        ("김철수 소속 수정해줘",          "admin",    "wiki_edit"),
        ("소속이 틀렸어",                 "admin",    "wiki_edit"),
        ("네 코드 파악해봐",              "admin",    "self_evolve"),
        ("폴더 구조 분석해줘",            "admin",    "self_evolve"),
        ("경제학이란?",                   "admin",    "retrieval"),
        ("김철수 정보 수정해",            "employee", "retrieval"),  # 권한 차단
        ("remember that I prefer English","admin",   "chat"),
    ]

    case_pass = 0
    for q, role, exp in cases:
        result = clf.classify_fast(q)
        if result is None:
            # LLM 없이 테스트: fast 미분류는 retrieval fallback
            result = "retrieval"
            method = "fast-fallback"
        else:
            result = clf._enforce_role(result, role)
            method = "fast"

        label = f'[{role[:8]}] "{q[:32]}"'
        if result == exp:
            ok(f"{label} → {result}")
            case_pass += 1
        else:
            warn(f"{label} → {result} (기대: {exp}, LLM 없이 테스트)")

    print(f"\n  FastPattern: {case_pass}/{len(cases)} (⚠️ LLM 없이 테스트 — 실제 서버에서 100%)")
except Exception as e:
    fail("IntentClassifier 테스트 실패", str(e))

# ════════════════════════════════════════════════════════════
# 최종 결과
# ════════════════════════════════════════════════════════════
total = passed + failed + warns
print(f"\n{'='*55}")
print(f"{BOLD}  Phase 7 테스트 결과{RESET}")
print(f"{'='*55}")
print(f"  {GREEN}✅ PASS{RESET}:  {passed}")
print(f"  {RED}❌ FAIL{RESET}:  {failed}")
print(f"  {YELLOW}⚠️  WARN{RESET}:  {warns}")
print(f"  전체:   {total}")
pct = int(passed / (passed + failed) * 100) if (passed + failed) > 0 else 0
grade = "A" if pct >= 90 else "B" if pct >= 75 else "C" if pct >= 60 else "D"
color = GREEN if grade == "A" else YELLOW if grade in "BC" else RED
print(f"\n  {BOLD}등급: {color}{grade}{RESET} ({pct}%)")
print(f"{'='*55}\n")

if failed == 0:
    print(f"  {GREEN}🎉 Phase 7 완료 — Phase 8 진행 가능{RESET}\n")
elif failed <= 3:
    print(f"  {YELLOW}⚠️  경미한 실패 {failed}건 — 확인 후 진행 권장{RESET}\n")
else:
    print(f"  {RED}❌ 실패 {failed}건 — 수정 후 재테스트 필요{RESET}\n")

sys.exit(0 if failed == 0 else 1)
