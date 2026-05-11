"""
PROJECT JAMES — Performance Evaluator (Phase 8, P8-EVAL-1)

자메스가 스스로 성능을 평가하고 채점하여 개선 제안을 자동 생성.

평가 항목:
  1. 응답 품질   (unified_score 분포)
  2. 응답 속도   (timing_sec 분포)
  3. 오류율      (blocked + LLM 실패 비율)
  4. 지식 커버리지 (자료 없음 비율)
  5. 메모리 효율  (cache hit rate)

채점 결과:
  A (90~): 우수, 제안 없음
  B (75~): 양호, 최적화 제안
  C (60~): 보통, 지식 보강 제안
  D (~60): 미흡, 코드 개선 제안 + 지식 보강
"""

import json
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from config import BASE_DIR
except ImportError:
    BASE_DIR = "."

EVAL_LOG  = Path(BASE_DIR) / "workspace" / "eval_log.jsonl"
EVAL_LOG.parent.mkdir(parents=True, exist_ok=True)

# 평가 기준
SCORE_GOOD     = 0.50   # unified_score 이 이상이면 양호
SPEED_GOOD_SEC = 15.0   # 15초 이내면 양호
EVAL_WINDOW    = 50     # 최근 N회 대화 기준 평가


class PerformanceEvaluator:
    """
    실시간 성능 지표 수집 + 주기적 자기 채점.
    """

    def __init__(self):
        self._records    = deque(maxlen=EVAL_WINDOW * 2)
        self._last_eval  = None
        self._eval_count = 0

    # ─── 지표 수집 ─────────────────────────────────────────────

    def record(self, query: str, result: Dict, elapsed: float):
        """매 쿼리 결과를 기록."""
        self._records.append({
            "query":    query[:80],
            "score":    result.get("unified_score", 0.5),
            "elapsed":  elapsed,
            "mode":     result.get("mode", ""),
            "blocked":  result.get("blocked", False),
            "answer":   result.get("answer", "")[:50],
            "time":     datetime.now().isoformat(),
        })

        # 50회마다 자동 평가
        if len(self._records) % EVAL_WINDOW == 0:
            self.evaluate()

    # ─── 자기 채점 ─────────────────────────────────────────────

    def evaluate(self) -> Dict:
        """
        최근 기록 기반 자기 채점.
        Returns: 평가 결과 dict
        """
        if not self._records:
            return {"grade": "N/A", "message": "데이터 없음"}

        records   = list(self._records)[-EVAL_WINDOW:]
        total     = len(records)
        now       = datetime.now().isoformat()

        # 지표 계산
        scores   = [r["score"]   for r in records]
        speeds   = [r["elapsed"] for r in records]
        blocked  = [r for r in records if r["blocked"]]
        no_data  = [r for r in records
                    if "자료에 없음" in r["answer"] or "No relevant" in r["answer"]]
        errors   = [r for r in records
                    if "오류" in r["answer"] or "error" in r["answer"].lower()]

        avg_score    = sum(scores) / total if total else 0
        avg_speed    = sum(speeds) / total if total else 0
        block_rate   = len(blocked) / total if total else 0
        nodata_rate  = len(no_data) / total if total else 0
        error_rate   = len(errors) / total if total else 0

        # 점수 계산 (100점)
        score_pt = min(avg_score / SCORE_GOOD, 1.0) * 35       # 35점
        speed_pt = max(0, 1 - avg_speed / SPEED_GOOD_SEC) * 25  # 25점
        block_pt = (1 - block_rate) * 15                         # 15점
        nodata_pt= (1 - nodata_rate) * 15                        # 15점
        error_pt = (1 - error_rate) * 10                         # 10점
        total_pt = score_pt + speed_pt + block_pt + nodata_pt + error_pt

        # 등급
        grade = ("A" if total_pt >= 90 else
                 "B" if total_pt >= 75 else
                 "C" if total_pt >= 60 else "D")

        # 문제점 도출
        issues = []
        proposals_needed = []

        if avg_score < SCORE_GOOD:
            issues.append(f"평균 검색 정확도 낮음 ({avg_score:.2f})")
            proposals_needed.append("wiki_add")

        if avg_speed > SPEED_GOOD_SEC:
            issues.append(f"평균 응답 속도 느림 ({avg_speed:.1f}초)")
            proposals_needed.append("code_patch")

        if nodata_rate > 0.30:
            issues.append(f"자료 없음 비율 높음 ({nodata_rate*100:.0f}%)")
            proposals_needed.append("wiki_add")

        if error_rate > 0.10:
            issues.append(f"오류 비율 높음 ({error_rate*100:.0f}%)")
            proposals_needed.append("code_patch")

        eval_result = {
            "eval_id":      f"eval_{self._eval_count:04d}",
            "grade":        grade,
            "total_score":  round(total_pt, 1),
            "evaluated_at": now,
            "sample_count": total,
            "metrics": {
                "avg_retrieval_score": round(avg_score, 3),
                "avg_response_sec":    round(avg_speed, 2),
                "block_rate":          round(block_rate, 3),
                "nodata_rate":         round(nodata_rate, 3),
                "error_rate":          round(error_rate, 3),
            },
            "score_breakdown": {
                "retrieval":  round(score_pt, 1),
                "speed":      round(speed_pt, 1),
                "security":   round(block_pt, 1),
                "coverage":   round(nodata_pt, 1),
                "stability":  round(error_pt, 1),
            },
            "issues":            issues,
            "proposals_needed":  list(set(proposals_needed)),
        }

        self._eval_count += 1
        self._last_eval  = eval_result
        self._log(eval_result)

        print(f"[EVAL] 자기 채점: {grade}등급 ({total_pt:.1f}/100) "
              f"| 문제: {len(issues)}개")

        # 문제 있으면 자동 제안 생성
        if issues and proposals_needed:
            self._auto_propose(eval_result)

        return eval_result

    # ─── 자동 제안 생성 ────────────────────────────────────────

    def _auto_propose(self, eval_result: Dict):
        """평가 결과 기반 제안 자동 생성."""
        try:
            from tools.self.evo_analyzer import _make_proposal, save_proposal
            from tools.self.importance_scorer import get_repeated_errors

            grade   = eval_result["grade"]
            issues  = eval_result["issues"]
            metrics = eval_result["metrics"]

            # 지식 부족 제안
            if "wiki_add" in eval_result["proposals_needed"]:
                repeated = get_repeated_errors(min_count=2)
                if repeated:
                    top_q = repeated[0]
                    p = _make_proposal(
                        prop_type   = "wiki_add",
                        title       = f"[자동평가-{grade}] 지식 보강: {top_q['query'][:30]}",
                        description = (
                            f"평가 등급 {grade} — "
                            f"자료 없음 비율 {metrics['nodata_rate']*100:.0f}%\n"
                            f"반복 오류 쿼리: '{top_q['query']}' ({top_q['count']}회)"
                        ),
                        content     = f"# {top_q['query']}\n\n[자메스 자동 생성 — 내용 검토 필요]",
                        metadata    = {
                            "entity_name":  top_q["query"][:30],
                            "entity_type":  "concept",
                            "source_query": top_q["query"],
                            "auto_eval":    True,
                            "grade":        grade,
                        }
                    )
                    save_proposal(p)

            # 속도/코드 개선 제안
            if "code_patch" in eval_result["proposals_needed"]:
                p = _make_proposal(
                    prop_type   = "code_patch",
                    title       = f"[자동평가-{grade}] 성능 최적화 필요",
                    description = (
                        f"평가 등급 {grade} ({eval_result['total_score']}/100)\n"
                        f"문제: {'; '.join(issues)}"
                    ),
                    content     = (
                        f"## 성능 평가 보고\n\n"
                        f"등급: {grade} ({eval_result['total_score']}/100)\n\n"
                        f"### 문제점\n" +
                        "\n".join(f"- {i}" for i in issues) +
                        "\n\n### 권장 조치\n"
                        "- 응답 속도 개선: 캐시 전략 검토\n"
                        "- 지식 베이스 보강 권장"
                    ),
                    metadata    = {
                        "auto_eval": True,
                        "grade":     grade,
                        "metrics":   metrics,
                    }
                )
                save_proposal(p)

        except Exception as e:
            print(f"[EVAL] 자동 제안 실패: {e}")

    # ─── 통계 + 보고서 ─────────────────────────────────────────

    def get_last_eval(self) -> Optional[Dict]:
        return self._last_eval

    def get_metrics(self) -> Dict:
        """현재 실시간 지표."""
        if not self._records:
            return {}
        records = list(self._records)
        total   = len(records)
        return {
            "sample_count":        total,
            "avg_retrieval_score": round(
                sum(r["score"] for r in records) / total, 3),
            "avg_response_sec":    round(
                sum(r["elapsed"] for r in records) / total, 2),
            "nodata_rate":         round(
                sum(1 for r in records if "자료에 없음" in r["answer"]) / total, 3),
            "error_rate":          round(
                sum(1 for r in records if "오류" in r["answer"]) / total, 3),
            "eval_count":          self._eval_count,
        }

    def _log(self, result: Dict):
        try:
            with open(EVAL_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def load_eval_history(self, limit: int = 20) -> List[Dict]:
        """과거 평가 기록 조회."""
        records = []
        try:
            if EVAL_LOG.exists():
                lines = EVAL_LOG.read_text(encoding="utf-8").strip().split("\n")
                for line in reversed(lines[-limit:]):
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
        except Exception:
            pass
        return records


# ─── 싱글턴 ─────────────────────────────────────────────────────

_evaluator: Optional[PerformanceEvaluator] = None

def get_evaluator() -> PerformanceEvaluator:
    global _evaluator
    if _evaluator is None:
        _evaluator = PerformanceEvaluator()
    return _evaluator

def record_query(query: str, result: Dict, elapsed: float):
    """매 쿼리 기록."""
    get_evaluator().record(query, result, elapsed)

def run_evaluation() -> Dict:
    """수동 평가 실행."""
    return get_evaluator().evaluate()

def get_current_metrics() -> Dict:
    """현재 지표 조회."""
    return get_evaluator().get_metrics()

def get_eval_history(limit: int = 20) -> List[Dict]:
    """과거 평가 기록."""
    return get_evaluator().load_eval_history(limit)
