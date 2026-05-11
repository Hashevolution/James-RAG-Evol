"""
PROJECT JAMES — Evolution Analyzer (Phase 7, Self-Evolution)

자메스가 스스로 개선점을 발견하고 제안을 생성 → admin 수락 시 자동 실행 → 결과 보고.

흐름:
  관찰(Observe) → 분석(Analyze) → 제안(Propose) → 실행(Execute) → 보고(Report)

제안 유형:
  wiki_add    : 지식 부족 → 새 entity 추가
  wiki_update : 잘못된 지식 → 기존 entity 수정
  code_patch  : 코드 버그/개선 → Patch 생성
  config_update: 설정 최적화 → persona/config 변경
"""

import os
import json
import time
import uuid
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple

try:
    from config import BASE_DIR
except ImportError:
    BASE_DIR = "."

PROPOSALS_DIR = Path(BASE_DIR) / "workspace" / "proposals"
REPORTS_DIR   = Path(BASE_DIR) / "workspace" / "evo_reports"
AUDIT_FILE    = Path(BASE_DIR) / "james_evo_log.jsonl"

PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# 위험도 정의
RISK_LEVELS = {
    "wiki_add":            "low",    # 새 지식 추가 — 낮음
    "wiki_update":         "low",    # 지식 수정 — 낮음
    "config_update":       "medium", # 설정 변경 — 중간
    "code_patch":          "high",   # 코드 변경 — 높음
    # [#A6-3] 웹 검색 결과 → wiki entity 장기 저장 admin confirm.
    # 외부 출처(low-trust)가 wiki에 들어가 retrieval 결과로 회수되므로
    # operator가 한 번 검토해야 한다. risk=medium으로 다른 자동 작업과
    # 같은 우선순위로 표시.
    "web_longterm_save":   "medium",
}

# 관찰 기준
LOW_SCORE_TH   = 0.30   # unified_score 이하 → 지식 부족
REPEAT_TH      = 3      # 동일 패턴 N회 반복 → 중요 패턴


# ─────────────────────────────────────────────
# 관찰 — 대화/추론 결과에서 개선점 감지
# ─────────────────────────────────────────────

class EvoObserver:
    """대화 결과를 관찰해서 개선 신호 수집."""

    def __init__(self):
        self._signals: List[Dict] = []

    def observe(self, query: str, result: dict) -> Optional[Dict]:
        """
        쿼리 + 추론 결과 관찰.
        개선 신호 발견 시 signal dict 반환, 없으면 None.
        """
        signal = None
        score  = result.get("unified_score", 1.0)
        answer = result.get("answer", "")
        mode   = result.get("mode", "")

        # 신호 1: 지식 부족 (낮은 score + "자료 없음")
        if score < LOW_SCORE_TH and "자료" in answer:
            signal = {
                "type":    "knowledge_gap",
                "query":   query,
                "score":   score,
                "detail":  f"unified_score={score:.3f}, 자료 없음 응답",
                "suggest": "wiki_add",
            }

        # 신호 2: LLM 실패
        elif any(p in answer for p in ["오류가 발생", "생성에 실패", "연결 오류"]):
            signal = {
                "type":    "llm_error",
                "query":   query,
                "score":   score,
                "detail":  f"LLM 실패 응답: {answer[:80]}",
                "suggest": "code_patch",
            }

        # 신호 3: 낮은 score지만 fallback 성공 → wiki 보강 필요
        elif score < LOW_SCORE_TH and mode == "retrieval":
            signal = {
                "type":    "weak_retrieval",
                "query":   query,
                "score":   score,
                "detail":  f"retrieval score 낮음: {score:.3f}",
                "suggest": "wiki_add",
            }

        if signal:
            signal["observed_at"] = datetime.now().isoformat()
            self._signals.append(signal)

        return signal

    def get_signals(self) -> List[Dict]:
        return self._signals

    def clear(self):
        self._signals.clear()


# ─────────────────────────────────────────────
# 분석 — 신호 패턴 분석 + 제안 초안 생성
# ─────────────────────────────────────────────

class EvoAnalyzer:
    """신호들을 분석해서 구체적인 제안을 생성."""

    def analyze_signals(self, signals: List[Dict], llm) -> List[Dict]:
        """
        신호 목록 → 제안 목록 생성.
        LLM으로 원인 분석 + 해결방안 도출.
        """
        if not signals:
            return []

        proposals = []

        # 지식 부족 신호 그룹화
        knowledge_gaps = [s for s in signals if s["type"] in
                          ("knowledge_gap", "weak_retrieval")]
        if knowledge_gaps:
            for gap in knowledge_gaps[:3]:   # 최대 3개
                proposal = self._make_wiki_proposal(gap, llm)
                if proposal:
                    proposals.append(proposal)

        # LLM 오류 신호
        llm_errors = [s for s in signals if s["type"] == "llm_error"]
        if llm_errors:
            proposal = self._make_code_proposal(llm_errors, llm)
            if proposal:
                proposals.append(proposal)

        return proposals

    def _make_wiki_proposal(self, signal: Dict, llm) -> Optional[Dict]:
        """지식 부족 → wiki 추가 제안 생성."""
        query = signal.get("query", "")
        if not query:
            return None

        # LLM으로 wiki 내용 초안 생성
        prompt = (
            f"다음 주제에 대한 간결한 wiki entity 내용을 작성해줘.\n"
            f"주제: {query}\n\n"
            f"형식:\n"
            f"# {{주제}}\n\n{{핵심 설명 3~5줄}}\n\n"
            f"## 주요 특징\n- {{특징1}}\n- {{특징2}}\n\n"
            f"wiki 내용:"
        )
        try:
            draft = llm.call_gemma(prompt, timeout=60, use_cache=False)
        except Exception:
            draft = f"# {query}\n\n{query}에 대한 정보입니다."

        # entity 이름 추출
        entity_name = query.split("은")[-1].split("는")[-1].split("이")[-1].strip()
        entity_name = re.sub(r'[?？!！]', '', entity_name).strip() or query[:20]

        return _make_proposal(
            prop_type   = "wiki_add",
            title       = f"[지식 추가] {entity_name}",
            description = f"'{query}' 질문에 자료 없음 — wiki 추가 필요",
            content     = draft or "",
            metadata    = {
                "entity_name":  entity_name,
                "entity_type":  "concept",
                "source_query": query,
                "signal":       signal,
            }
        )

    def _make_code_proposal(self, errors: List[Dict], llm) -> Optional[Dict]:
        """LLM 오류 패턴 → 코드 개선 제안."""
        details = "\n".join([e["detail"] for e in errors[:3]])
        prompt = (
            f"PROJECT JAMES에서 다음 오류들이 반복 발생하고 있습니다:\n{details}\n\n"
            f"원인과 개선 방안을 간결하게 제안해주세요:\n"
            f"1. 원인:\n2. 개선 방안:\n3. 수정 파일:"
        )
        try:
            analysis = llm.call_gemma(prompt, timeout=60, use_cache=False)
        except Exception:
            analysis = "LLM 분석 실패"

        return _make_proposal(
            prop_type   = "code_patch",
            title       = f"[코드 개선] LLM 오류 패턴 ({len(errors)}회 발생)",
            description = f"반복 LLM 오류 감지 — 코드 개선 필요",
            content     = analysis or "",
            metadata    = {"errors": errors, "count": len(errors)}
        )


# ─────────────────────────────────────────────
# 제안 관리
# ─────────────────────────────────────────────

def _make_proposal(prop_type: str, title: str, description: str,
                   content: str, metadata: dict = None) -> Dict:
    """제안 객체 생성."""
    proposal_id = f"evo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    return {
        "proposal_id": proposal_id,
        "type":        prop_type,
        "risk":        RISK_LEVELS.get(prop_type, "medium"),
        "title":       title,
        "description": description,
        "content":     content,
        "metadata":    metadata or {},
        "status":      "pending",
        "created_at":  datetime.now().isoformat(),
        "reviewed_at": None,
        "executed_at": None,
        "result":      None,
    }


def save_proposal(proposal: Dict) -> Path:
    """제안 파일 저장."""
    path = PROPOSALS_DIR / f"{proposal['proposal_id']}.json"
    path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[EVO] 제안 저장: {proposal['title']}")
    return path


def load_proposal(proposal_id: str) -> Optional[Dict]:
    """제안 로드."""
    path = PROPOSALS_DIR / f"{proposal_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_proposals(status: str = "all") -> List[Dict]:
    """제안 목록 조회."""
    proposals = []
    for f in sorted(PROPOSALS_DIR.glob("evo_*.json"), reverse=True):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
            if status == "all" or p.get("status") == status:
                proposals.append(p)
        except Exception:
            pass
    return proposals[:50]


# ─────────────────────────────────────────────
# 실행 — admin 수락 시 자동 적용
# ─────────────────────────────────────────────

class EvoExecutor:
    """admin 승인된 제안을 자동 실행."""

    def execute(self, proposal: Dict) -> Dict:
        """
        제안 유형에 따라 자동 실행.
        Returns: result dict
        """
        prop_type = proposal.get("type", "")
        t_start   = time.time()
        result    = {"success": False, "message": "", "details": {}}

        try:
            if prop_type == "wiki_add":
                result = self._execute_wiki_add(proposal)
            elif prop_type == "wiki_update":
                result = self._execute_wiki_update(proposal)
            elif prop_type == "code_patch":
                result = self._execute_code_patch(proposal)
            elif prop_type == "config_update":
                result = self._execute_config_update(proposal)
            elif prop_type == "web_longterm_save":
                # [#A6-3] admin이 confirm한 웹 검색 결과를 wiki entity로 저장.
                result = self._execute_web_longterm_save(proposal)
            else:
                result["message"] = f"알 수 없는 제안 유형: {prop_type}"

        except Exception as e:
            result["success"] = False
            result["message"] = f"실행 오류: {e}"

        result["elapsed_sec"] = round(time.time() - t_start, 2)
        return result

    def _execute_web_longterm_save(self, proposal: Dict) -> Dict:
        """[#A6-3] admin이 confirm한 웹 검색 결과를 wiki entity로 저장.

        Pipeline은 이전엔 should_promote_to_longterm 조건 만족 시
        save_as_longterm을 즉시 호출했다 — operator 모르는 사이 wiki에
        외부 출처가 추가됨. 이제는 proposal로 큐잉, admin이 admin 페이지
        Proposals에서 검토 후 Approve.

        Metadata expected (pipeline.py가 채움):
          query:        원본 사용자 쿼리
          summary:      LLM 200자 요약 (이미 생성)
          web_results:  search_web 결과 list (URL/title/snippet/body)
          user_role:    원 호출자 role (audit용)
        """
        from tools.web.web_searcher import save_as_longterm, update_knowledge_level
        meta = proposal.get("metadata", {}) or {}
        query        = meta.get("query", "")
        summary      = meta.get("summary", "")
        web_results  = meta.get("web_results", [])
        original_role = meta.get("user_role", "admin")
        if not (query and summary and web_results):
            return {
                "success": False,
                "message": "metadata 누락 (query/summary/web_results 필요)",
                "details": {"missing": [
                    k for k in ("query", "summary", "web_results")
                    if not meta.get(k)
                ]},
            }
        try:
            path = save_as_longterm(query, web_results, summary, original_role)
            if not path:
                return {"success": False,
                        "message": "save_as_longterm가 None 반환 (저장 실패)",
                        "details": {}}
            # admin 승인 후 저장 완료 → KnowledgeTracker 장기 +5점
            update_knowledge_level(query, is_longterm=True)
            return {
                "success": True,
                "message": f"wiki entity 저장 완료: {path}",
                "details": {"path": str(path), "topic": query[:30]},
            }
        except Exception as e:
            return {"success": False,
                    "message": f"저장 실패: {type(e).__name__}: {e}",
                    "details": {}}

    def _execute_wiki_add(self, proposal: Dict) -> Dict:
        """wiki 새 entity 추가."""
        from tools.wiki.wiki_editor import create_entity
        meta        = proposal.get("metadata", {})
        entity_name = meta.get("entity_name", "unknown")
        content     = proposal.get("content", "")
        entity_type = meta.get("entity_type", "concept")

        ok, msg = create_entity(
            name        = entity_name,
            entity_type = entity_type,
            description = content[:500],
            user_role   = "admin",
        )
        return {"success": ok, "message": msg,
                "details": {"entity": entity_name}}

    def _execute_wiki_update(self, proposal: Dict) -> Dict:
        """wiki entity 수정."""
        from tools.wiki.wiki_editor import update_entity
        meta    = proposal.get("metadata", {})
        name    = meta.get("entity_name", "")
        content = proposal.get("content", "")

        ok, msg = update_entity(name, content, user_role="admin")
        return {"success": ok, "message": msg,
                "details": {"entity": name}}

    def _execute_code_patch(self, proposal: Dict) -> Dict:
        """코드 패치 적용 (Patch Pipeline 사용)."""
        content = proposal.get("content", "")

        # 코드 블록 추출
        code_blocks = re.findall(r'```(?:python)?\n(.*?)```', content, re.DOTALL)
        if not code_blocks:
            return {"success": False,
                    "message": "적용할 코드 블록 없음 — 수동 검토 필요",
                    "details": {"content_preview": content[:200]}}

        # Patch 객체 생성 후 Pipeline 통과
        from tools.patch.patch_generator import PatchGenerator
        from tools.patch.patch_validator import PatchValidator
        from tools.patch.patch_applier   import apply as patch_apply

        gen = PatchGenerator()
        patch = gen.generate(
            code    = code_blocks[0],
            context = proposal.get("description", ""),
            source  = "self_evolve",
        )

        validator = PatchValidator()
        passed, failures = validator.validate(patch)
        if not passed:
            return {"success": False,
                    "message": f"Patch 검증 실패: {failures}",
                    "details": {"failures": failures}}

        ok, msg = patch_apply(patch, validated=True)
        return {"success": ok, "message": msg,
                "details": {"patch_id": patch.get("patch_id", "")}}

    def _execute_config_update(self, proposal: Dict) -> Dict:
        """설정 변경 (persona/memory 업데이트)."""
        meta    = proposal.get("metadata", {})
        changes = meta.get("changes", {})

        from core.memory import MemoryStore
        store = MemoryStore()
        applied = []
        for key, value in changes.items():
            if store.set_persona(key, str(value)):
                applied.append(f"{key}={value}")

        return {"success": bool(applied),
                "message": f"설정 적용: {', '.join(applied)}",
                "details": {"applied": applied}}


# ─────────────────────────────────────────────
# 보고 — 실행 결과 기록 + 알림
# ─────────────────────────────────────────────

def save_report(proposal: Dict, result: Dict) -> Dict:
    """실행 결과 보고서 저장."""
    report = {
        "report_id":   f"report_{uuid.uuid4().hex[:8]}",
        "proposal_id": proposal["proposal_id"],
        "type":        proposal["type"],
        "title":       proposal["title"],
        "executed_at": datetime.now().isoformat(),
        "success":     result.get("success", False),
        "message":     result.get("message", ""),
        "details":     result.get("details", {}),
        "elapsed_sec": result.get("elapsed_sec", 0),
    }

    # 파일 저장
    path = REPORTS_DIR / f"{report['report_id']}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 감사 로그
    with open(AUDIT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False) + "\n")

    status = "✅ 성공" if report["success"] else "❌ 실패"
    print(f"[EVO] 실행 보고: {report['title']} → {status}")
    return report


def list_reports(limit: int = 20) -> List[Dict]:
    """실행 보고서 목록 조회."""
    reports = []
    for f in sorted(REPORTS_DIR.glob("report_*.json"), reverse=True)[:limit]:
        try:
            reports.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return reports


# ─────────────────────────────────────────────
# 메인 진입점
# ─────────────────────────────────────────────

# 싱글턴 옵저버 (서버 전체에서 공유)
_observer = EvoObserver()
_analyzer = EvoAnalyzer()
_executor = EvoExecutor()


def observe_and_signal(query: str, result: dict) -> Optional[Dict]:
    """대화 결과 관찰 → 신호 반환."""
    return _observer.observe(query, result)


def generate_proposals_from_signals(llm) -> List[Dict]:
    """현재까지 쌓인 신호로 제안 생성 + 저장."""
    signals  = _observer.get_signals()
    proposals = _analyzer.analyze_signals(signals, llm)
    saved = []
    for p in proposals:
        save_proposal(p)
        saved.append(p)
    if saved:
        _observer.clear()   # 처리된 신호 초기화
    return saved


def approve_and_execute(proposal_id: str) -> Dict:
    """
    admin 승인 → 즉시 실행 → 보고.
    Returns: report dict
    """
    proposal = load_proposal(proposal_id)
    if not proposal:
        return {"success": False, "message": f"제안 없음: {proposal_id}"}

    if proposal.get("status") not in ("pending", "approved"):
        return {"success": False,
                "message": f"실행 불가 상태: {proposal['status']}"}

    # 상태 → approved
    proposal["status"]      = "approved"
    proposal["reviewed_at"] = datetime.now().isoformat()
    save_proposal(proposal)

    # 실행
    print(f"[EVO] 실행 시작: {proposal['title']}")
    result = _executor.execute(proposal)

    # 상태 업데이트
    proposal["status"]      = "completed" if result["success"] else "failed"
    proposal["executed_at"] = datetime.now().isoformat()
    proposal["result"]      = result
    save_proposal(proposal)

    # 보고서 저장
    report = save_report(proposal, result)
    return report


def reject_proposal(proposal_id: str, reason: str = "") -> bool:
    """제안 거부."""
    proposal = load_proposal(proposal_id)
    if not proposal:
        return False
    proposal["status"]      = "rejected"
    proposal["reviewed_at"] = datetime.now().isoformat()
    proposal["result"]      = {"message": f"거부됨: {reason}"}
    save_proposal(proposal)
    print(f"[EVO] 제안 거부: {proposal['title']}")
    return True
