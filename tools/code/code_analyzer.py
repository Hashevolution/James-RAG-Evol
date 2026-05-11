"""
PROJECT JAMES - Code Analyzer (Phase 5.5)

역할: JAMES Core Engine을 통한 코드 분석.
Sandbox 검증 + Code Reader 통과 후 분석 수행.

절대 제약:
  ❌ Core Engine 수정 금지 (호출만 허용)
  ❌ 결과를 Memory에 미검증 저장 금지
  ✅ RAGEngine.query()를 통해서만 분석
  ✅ 분석 결과 감사 로그 기록
  ✅ tool_used 필드로 tool 추적
"""

import json
import time
from datetime import datetime
from typing import Dict, Optional, Tuple

from tools.code.sandbox import policy_validate_path, log_security_event
from tools.code.code_reader import CodeReader

AUDIT_LOG_PATH = "james_audit_tool.jsonl"

# 분석 타입별 프롬프트 템플릿
ANALYSIS_TEMPLATES = {
    "review":   "다음 코드를 리뷰하고 개선점을 찾아줘:\n\n{code}",
    "explain":  "다음 코드의 동작을 단계별로 설명해줘:\n\n{code}",
    "bug":      "다음 코드에서 버그나 잠재적 문제를 찾아줘:\n\n{code}",
    "security": "다음 코드에서 보안 취약점을 분석해줘:\n\n{code}",
    "summary":  "다음 코드를 간략하게 요약해줘 (목적, 입력, 출력):\n\n{code}",
}


def _log_analysis(path: str, analysis_type: str, elapsed: float, success: bool):
    entry = {
        "time":          datetime.now().isoformat(),
        "event":         "CODE_ANALYSIS",
        "tool_used":     "code_analyzer",
        "path":          path,
        "analysis_type": analysis_type,
        "elapsed_sec":   elapsed,
        "success":       success,
        "layer":         "tool",
    }
    try:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # Phase 1: mirror to SQLite (see core/audit_bridge.py).
    try:
        from core.audit_bridge import mirror_to_audit_db
        mirror_to_audit_db(entry)
    except Exception:
        pass


class CodeAnalyzer:
    """
    JAMES Core Engine 호출을 통한 코드 분석 도구.
    Core Engine은 수정하지 않고 쿼리만 전달.
    """

    def __init__(self, user_role: str = "admin"):
        self.user_role = user_role
        self.reader    = CodeReader(user_role=user_role)
        self._engine   = None   # lazy init

    def _get_engine(self):
        """RAGEngine lazy init — import는 분석 시점에만"""
        if self._engine is None:
            try:
                from core.graph_rag_engine import RAGEngine
                self._engine = RAGEngine(default_role=self.user_role)
            except ImportError as e:
                print(f"[ANALYZER] ⚠️ RAGEngine 로드 실패: {e}")
        return self._engine

    def analyze_file(
        self,
        path:          str,
        analysis_type: str = "review",
        start_line:    int = 1,
        end_line:      Optional[int] = None,
    ) -> Tuple[bool, str, Dict]:
        """
        파일을 읽어 JAMES Core로 분석.

        Args:
            path:          분석할 파일 (workspace 내)
            analysis_type: review / explain / bug / security / summary
            start_line:    분석 시작 라인
            end_line:      분석 끝 라인

        Returns:
            (success, analysis_result, metadata)
        """
        t_start = time.time()

        # 1. PolicyEngine + sandbox 경로 검증 (#44 phase 3-3)
        path_ok, reason = policy_validate_path(path, self.user_role, "fs.read")
        if not path_ok:
            log_security_event("PATH_VIOLATION", f"analyze:{path}")
            return False, f"경로 차단: {reason}", {}

        # 2. 파일 읽기
        read_ok, content, meta = self.reader.read_file(path, start_line, end_line)
        if not read_ok:
            return False, f"읽기 실패: {content}", {}

        # 3. 분석 타입 검증
        if analysis_type not in ANALYSIS_TEMPLATES:
            analysis_type = "review"

        # 4. 프롬프트 구성 (코드 앞부분만 사용, 500자 제한)
        code_snippet = content[:2000]
        template     = ANALYSIS_TEMPLATES[analysis_type]
        query        = template.format(code=code_snippet)

        # 5. JAMES Core Engine 호출 (수정 없이 query만)
        engine = self._get_engine()
        if engine is None:
            # fallback: 코드 직접 출력
            result_text = f"[JAMES Core 없음] 코드 내용:\n{code_snippet[:500]}"
            elapsed     = round(time.time() - t_start, 2)
            _log_analysis(path, analysis_type, elapsed, False)
            return True, result_text, meta

        try:
            result = engine.query(query, user_role=self.user_role)
            answer = result.get("answer", "분석 결과 없음")
        except Exception as e:
            log_security_event("ANALYSIS_ERROR", str(e), blocked=False)
            answer  = f"분석 오류: {e}"

        elapsed = round(time.time() - t_start, 2)

        meta.update({
            "analysis_type": analysis_type,
            "elapsed_sec":   elapsed,
            "tool_used":     "code_analyzer",
        })

        _log_analysis(path, analysis_type, elapsed, True)
        print(f"[ANALYZER] ✅ {path} ({analysis_type}) {elapsed}s")
        return True, answer, meta

    def analyze_snippet(
        self,
        code:          str,
        analysis_type: str = "review",
        filename:      str = "snippet",
    ) -> Tuple[bool, str, Dict]:
        """
        코드 스니펫 직접 분석 (파일 없이).
        Sandbox injection 방지를 위해 코드 내용 sanitize.
        """
        # injection 패턴 차단
        from core.security_layer import sanitize_document_content
        safe_code = sanitize_document_content(code, source=filename)

        if analysis_type not in ANALYSIS_TEMPLATES:
            analysis_type = "review"

        template = ANALYSIS_TEMPLATES[analysis_type]
        query    = template.format(code=safe_code[:2000])

        engine = self._get_engine()
        if engine is None:
            return True, f"[JAMES Core 없음] 스니펫 수신: {len(safe_code)}자", {}

        t_start = time.time()
        try:
            result = engine.query(query, user_role=self.user_role)
            answer = result.get("answer", "")
        except Exception as e:
            answer = f"분석 오류: {e}"

        elapsed = round(time.time() - t_start, 2)
        _log_analysis(filename, analysis_type, elapsed, True)
        return True, answer, {"filename": filename, "elapsed_sec": elapsed}

    def collect_attack_surface(self, path: str) -> Dict:
        """
        [Phase 5.5 데이터 수집] 분석 중 공격 surface 탐지 및 기록.
        Phase 6 보안 설계를 위한 실제 데이터 수집.
        """
        read_ok, content, meta = self.reader.read_file(path)
        if not read_ok:
            return {}

        surface = {
            "path":              path,
            "timestamp":         datetime.now().isoformat(),
            "has_imports":       "import" in content,
            "has_exec":          "exec(" in content or "eval(" in content,
            "has_file_access":   "open(" in content,
            "has_network":       any(k in content for k in ["requests", "urllib", "socket", "http"]),
            "has_subprocess":    "subprocess" in content or "os.system" in content,
            "has_env_access":    "os.environ" in content,
            "injection_risk":    any(k in content for k in ["input(", "sys.argv", "os.system"]),
            "lines":             meta.get("total_lines", 0),
            "risk_score":        0,
        }

        # 위험도 점수
        risk_factors = [
            surface["has_exec"], surface["has_network"],
            surface["has_subprocess"], surface["injection_risk"]
        ]
        surface["risk_score"] = sum(risk_factors)

        # 감사 기록
        entry = {
            "time":    datetime.now().isoformat(),
            "event":   "ATTACK_SURFACE_SCAN",
            "path":    path,
            "surface": surface,
            "layer":   "code_analyzer",
        }
        try:
            with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

        print(f"[ANALYZER] 공격 surface 스캔: {path} | risk={surface['risk_score']}")
        return surface


if __name__ == "__main__":
    import os
    os.makedirs("./workspace", exist_ok=True)

    # 테스트 파일 생성
    with open("./workspace/sample.py", "w", encoding="utf-8") as f:
        f.write("""
import os
import requests

def get_data(user_input):
    # 사용자 입력 처리
    result = os.system(f"echo {user_input}")  # 위험!
    return requests.get("http://example.com").text

def safe_func(x):
    return x * 2
""")

    print("=== Code Analyzer 자가 테스트 ===\n")
    analyzer = CodeAnalyzer(user_role="admin")

    # 공격 surface 스캔 (JAMES Core 없어도 동작)
    surface = analyzer.collect_attack_surface("./workspace/sample.py")
    ok = surface.get("risk_score", 0) >= 2  # exec + subprocess + network 탐지
    print(f"  {'✅' if ok else '❌'} 공격 surface 탐지: risk_score={surface.get('risk_score')} (기대≥2)")
    print(f"     has_network={surface.get('has_network')}")
    print(f"     has_subprocess={surface.get('has_subprocess')}")
    print(f"     injection_risk={surface.get('injection_risk')}")

    # 경로 탈출 차단
    ok2, msg, _ = analyzer.analyze_file("../secret.py")
    print(f"\n  {'✅' if not ok2 else '❌'} 경로 탈출 차단: {not ok2}")
