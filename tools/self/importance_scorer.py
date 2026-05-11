"""
PROJECT JAMES — Importance Scorer (Phase 7, P7-EVO-B)

대화에서 중요도를 측정해서 메모리 강화 + 지식 보강 제안을 생성.

중요도 측정 기준:
  1. 반복성 (Repetition)   : 동일/유사 질문 반복 → 핵심 관심사
  2. 강조성 (Emphasis)     : "꼭", "반드시", "중요", "핵심" 등
  3. 지시성 (Instruction)  : "기억해", "앞으로", "항상" 등 명시 지시
  4. 밀도성 (Density)      : 짧은 시간에 집중적으로 언급
  5. 오류성 (Error)        : 낮은 score → 지식 부족 → 보강 필요

연동:
  - LOOM Gate: 중요도 높으면 confidence threshold 낮춰 저장 허용
  - EvoAnalyzer: 반복 오류 쿼리 → wiki_add 제안 자동 생성
"""

import re
import json
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path

try:
    from config import BASE_DIR
except ImportError:
    BASE_DIR = "."

SCORE_LOG = Path(BASE_DIR) / "workspace" / "importance_log.jsonl"
SCORE_LOG.parent.mkdir(parents=True, exist_ok=True)

# 중요도 점수 기준
IMPORTANCE_TH_HIGH   = 0.75   # 매우 중요 → 즉시 메모리 강화
IMPORTANCE_TH_MEDIUM = 0.45   # 중간 → 축적 후 강화
SIGNAL_DECAY         = 0.9    # Decay — 오래된 신호 감쇠

# 패턴 가중치
WEIGHT_REPEAT    = 0.35   # 반복
WEIGHT_EMPHASIS  = 0.25   # 강조
WEIGHT_INSTRUCT  = 0.25   # 지시
WEIGHT_ERROR     = 0.15   # 오류 기반 보강

# 강조 패턴
EMPHASIS_KO = [
    "꼭", "반드시", "중요", "핵심", "절대", "필수",
    "강조", "특히", "무조건", "정확히", "명확히",
]
EMPHASIS_EN = [
    "must", "always", "critical", "important", "key",
    "essential", "never forget", "make sure", "crucial",
]

# 지시 패턴
INSTRUCT_KO = [
    "기억해", "기억해줘", "앞으로", "항상", "매번",
    "잊지 마", "메모해", "저장해줘",
]
INSTRUCT_EN = [
    "remember", "keep in mind", "from now on",
    "always", "make sure to", "don't forget",
]


class ImportanceScorer:
    """
    대화 중요도 실시간 측정기.
    서버 전체에서 싱글턴으로 운용.
    """

    def __init__(self, window_sec: int = 3600):
        self._window_sec   = window_sec          # 분석 창 (기본 1시간)
        self._query_hist   = deque(maxlen=500)    # (timestamp, query, score)
        self._repeat_count = defaultdict(int)     # 쿼리 패턴 → 반복 횟수
        self._error_hist   = deque(maxlen=200)    # 낮은 score 기록

    # ─── 핵심: 중요도 점수 계산 ────────────────────────────────

    def score(self, query: str, unified_score: float = 1.0,
              answer: str = "") -> Dict:
        """
        단일 쿼리 중요도 점수 계산.

        Returns:
            {
              "importance":    0.0~1.0,
              "level":        "high"|"medium"|"low",
              "reasons":      [이유 목록],
              "enhance":      bool  (메모리 강화 필요 여부),
              "propose_wiki": bool  (wiki 보강 제안 필요)
            }
        """
        q_norm  = self._normalize(query)
        reasons = []
        scores  = []

        # 1. 반복성 점수
        repeat_score = self._calc_repeat(q_norm)
        if repeat_score > 0:
            scores.append(repeat_score * WEIGHT_REPEAT)
            reasons.append(f"반복 질문 ({self._repeat_count[q_norm[:30]]}회)")

        # 2. 강조성 점수
        emphasis_score = self._calc_emphasis(query)
        if emphasis_score > 0:
            scores.append(emphasis_score * WEIGHT_EMPHASIS)
            reasons.append("강조 표현 감지")

        # 3. 지시성 점수
        instruct_score = self._calc_instruction(query)
        if instruct_score > 0:
            scores.append(instruct_score * WEIGHT_INSTRUCT)
            reasons.append("명시적 지시")

        # 4. 오류 기반 점수 (낮은 unified_score)
        error_score = self._calc_error(unified_score, answer)
        if error_score > 0:
            scores.append(error_score * WEIGHT_ERROR)
            reasons.append(f"지식 부족 (score={unified_score:.2f})")

        # 종합 중요도
        importance = min(sum(scores), 1.0)
        level = ("high" if importance >= IMPORTANCE_TH_HIGH
                 else "medium" if importance >= IMPORTANCE_TH_MEDIUM
                 else "low")

        # 히스토리 업데이트
        now = time.time()
        self._query_hist.append((now, q_norm, importance))
        self._repeat_count[q_norm[:30]] += 1
        if unified_score < 0.30:
            self._error_hist.append({
                "query":   query,
                "score":   unified_score,
                "time":    datetime.now().isoformat(),
            })

        result = {
            "query":       query,
            "importance":  round(importance, 3),
            "level":       level,
            "reasons":     reasons,
            "enhance":     importance >= IMPORTANCE_TH_MEDIUM,
            "propose_wiki":unified_score < 0.30 and self._repeat_count[q_norm[:30]] >= 2,
        }

        # 로그 기록
        if importance >= IMPORTANCE_TH_MEDIUM:
            self._log(result)
            print(f"[IMPORTANCE] {level.upper()}: '{query[:40]}' "
                  f"score={importance:.3f} | {', '.join(reasons)}")

        return result

    # ─── LOOM Gate 연동 ────────────────────────────────────────

    def get_loom_threshold(self, query: str) -> float:
        """
        중요도에 따른 LOOM Gate1 confidence 임계값 반환.
        중요할수록 낮은 threshold → 저장 가능성 높임.
        """
        q_norm = self._normalize(query)
        repeat = self._repeat_count.get(q_norm[:30], 0)

        if repeat >= 5:
            return 0.40   # 5회 이상 반복 → threshold 낮춤
        elif repeat >= 3:
            return 0.55
        elif repeat >= 2:
            return 0.65
        return 0.75       # 기본값 (변경 없음)

    # ─── 반복 오류 쿼리 조회 ───────────────────────────────────

    def get_repeated_error_queries(self, min_count: int = 2) -> List[Dict]:
        """
        반복적으로 낮은 score가 나온 쿼리 목록.
        → wiki 보강 제안 대상.
        """
        counts = defaultdict(list)
        for e in self._error_hist:
            counts[e["query"][:50]].append(e)

        result = []
        for q_key, entries in counts.items():
            if len(entries) >= min_count:
                result.append({
                    "query":   entries[0]["query"],
                    "count":   len(entries),
                    "avg_score": sum(e["score"] for e in entries) / len(entries),
                    "last":    entries[-1]["time"],
                })
        return sorted(result, key=lambda x: x["count"], reverse=True)

    # ─── 내부 헬퍼 ────────────────────────────────────────────

    def _normalize(self, q: str) -> str:
        q = q.lower().strip()
        q = re.sub(r'[?？!！.,。、]+', '', q)
        q = re.sub(r'\s+', ' ', q)
        return q[:50]

    def _calc_repeat(self, q_norm: str) -> float:
        count = self._repeat_count.get(q_norm[:30], 0)
        if count >= 5: return 1.0
        if count >= 3: return 0.7
        if count >= 2: return 0.4
        return 0.0

    def _calc_emphasis(self, query: str) -> float:
        q = query.lower()
        all_emphasis = EMPHASIS_KO + EMPHASIS_EN
        hits = sum(1 for kw in all_emphasis if kw in q)
        return min(hits * 0.5, 1.0)

    def _calc_instruction(self, query: str) -> float:
        q = query.lower()
        all_instruct = INSTRUCT_KO + INSTRUCT_EN
        hits = sum(1 for kw in all_instruct if kw in q)
        return min(hits * 0.6, 1.0)

    def _calc_error(self, unified_score: float, answer: str) -> float:
        if unified_score < 0.15: return 1.0
        if unified_score < 0.25: return 0.7
        if unified_score < 0.30: return 0.4
        return 0.0

    def _log(self, result: Dict):
        try:
            with open(SCORE_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    **result, "logged_at": datetime.now().isoformat()
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def get_stats(self) -> Dict:
        """현재 통계."""
        high_count = sum(1 for _, _, s in self._query_hist if s >= IMPORTANCE_TH_HIGH)
        return {
            "total_queries":   len(self._query_hist),
            "high_importance": high_count,
            "error_queries":   len(self._error_hist),
            "repeated_errors": len(self.get_repeated_error_queries()),
        }


# ─── 싱글턴 ─────────────────────────────────────────────────────

_scorer: Optional[ImportanceScorer] = None

def get_scorer() -> ImportanceScorer:
    global _scorer
    if _scorer is None:
        _scorer = ImportanceScorer()
    return _scorer

def score_query(query: str, unified_score: float = 1.0,
                answer: str = "") -> Dict:
    """외부 진입점."""
    return get_scorer().score(query, unified_score, answer)

def get_loom_threshold(query: str) -> float:
    """LOOM Gate1 동적 임계값."""
    return get_scorer().get_loom_threshold(query)

def get_repeated_errors(min_count: int = 2) -> List[Dict]:
    """반복 오류 쿼리 목록."""
    return get_scorer().get_repeated_error_queries(min_count)

def get_scorer_stats() -> Dict:
    """통계."""
    return get_scorer().get_stats()
