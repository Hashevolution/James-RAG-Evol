"""
PROJECT JAMES — Feedback Engine (P7-EVO-C)

설계 원칙:
  즉시 반영 금지 → shadow DB 누적 → 임계값 초과 → 검증 후 반영
  한 번 피드백으로 변하지 않음 — 오염 방지

피드백 분류:
  explicit_positive (+1.0): "좋아", "잘했어", 👍
  flow_continue     (+0.3): 자연스러운 대화 지속
  implicit_positive (+0.2): 추가 질문 (관심 표현)
  explicit_negative (-1.0): "싫어", "틀렸어", 👎
  correction        (-0.8): "아니야", "그게 아니라"
  strong_objection  (-0.6): 강한 이의 제기
  implicit_negative (-0.3): 대화 단절 / 주제 급전환
"""

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

try:
    from config import BASE_DIR
except ImportError:
    BASE_DIR = "."

SHADOW_DB  = Path(BASE_DIR) / "workspace" / "feedback_shadow.jsonl"
APPLY_LOG  = Path(BASE_DIR) / "workspace" / "feedback_applied.jsonl"
SHADOW_DB.parent.mkdir(parents=True, exist_ok=True)

# 피드백 가중치
FEEDBACK_SIGNALS = {
    "explicit_positive": 1.0,
    "flow_continue":     0.3,
    "implicit_positive": 0.2,
    "explicit_negative": -1.0,
    "correction":        -0.8,
    "strong_objection":  -0.6,
    "implicit_negative": -0.3,
}

REINFORCE_TH = 2.0    # 이 이상 → 강화 적용
WEAKEN_TH    = -2.0   # 이 이하 → 약화 + 재검토 제안
DECAY        = 0.9    # 오래된 피드백 감쇠

# 감지 패턴
_POS_KO = ["좋아", "잘했", "맞아", "훌륭", "완벽", "최고", "정확", "고마워", "감사"]
_POS_EN = ["good", "great", "correct", "perfect", "thanks", "exactly", "well done"]
_NEG_KO = ["싫어", "틀렸", "아니야", "잘못", "틀린", "별로", "나빠", "엉터리"]
_NEG_EN = ["wrong", "incorrect", "bad", "no", "that's not", "mistake"]
_COR_KO = ["그게 아니라", "수정해", "고쳐", "다르게", "다시 해줘", "처음부터"]
_OBJ_KO = ["완전히 틀렸", "말도 안돼", "이해 못했", "엉뚱한"]


class FeedbackEngine:
    """실시간 피드백 감지 + shadow 누적 + 반영 결정."""

    def __init__(self):
        # {direction_id: accumulated_score}
        self._shadow: Dict[str, float] = defaultdict(float)
        self._history: List[Dict] = []
        self._load_shadow()

    # ─── 피드백 감지 ────────────────────────────────────────────

    def detect(self, query: str, prev_answer: str = "",
               explicit: Optional[str] = None) -> str:
        """
        쿼리 분석 → 피드백 유형 반환.
        explicit: "positive" | "negative" (버튼 클릭 시)
        """
        # 버튼 직접 클릭
        if explicit == "positive":
            return "explicit_positive"
        if explicit == "negative":
            return "explicit_negative"

        q = query.lower().strip()

        # 강한 이의
        if any(k in q for k in _OBJ_KO):
            return "strong_objection"

        # 교정
        if any(k in q for k in _COR_KO):
            return "correction"

        # 명시 부정
        if any(k in q for k in _NEG_KO + _NEG_EN):
            return "explicit_negative"

        # 명시 긍정
        if any(k in q for k in _POS_KO + _POS_EN):
            return "explicit_positive"

        # 추가 질문 (관심)
        if prev_answer and len(query) > 5 and "?" in query:
            return "implicit_positive"

        return "flow_continue"

    # ─── 누적 + 임계값 판단 ────────────────────────────────────

    def accumulate(self, direction_id: str, signal: str,
                   query: str = "") -> Dict:
        """
        피드백 누적. 임계값 초과 시 action 결정.
        direction_id: 현재 응답 방향 식별자 (mode + topic hash)
        """
        delta     = FEEDBACK_SIGNALS.get(signal, 0.0)
        old_score = self._shadow[direction_id]
        new_score = (old_score + delta) * DECAY

        self._shadow[direction_id] = new_score

        now = datetime.now().isoformat()
        entry = {
            "direction_id": direction_id,
            "signal":       signal,
            "delta":        delta,
            "score":        round(new_score, 3),
            "query":        query[:80],
            "time":         now,
        }
        self._history.append(entry)
        self._append_shadow(entry)

        # 임계값 판단
        action = "none"
        if new_score >= REINFORCE_TH:
            action = "reinforce"
            print(f"[FEEDBACK] 강화: {direction_id[:30]} score={new_score:.2f}")
            self._apply_reinforce(direction_id, new_score)
            self._shadow[direction_id] = 0.0   # 리셋

        elif new_score <= WEAKEN_TH:
            action = "weaken"
            print(f"[FEEDBACK] 약화+재검토: {direction_id[:30]} score={new_score:.2f}")
            self._apply_weaken(direction_id, new_score)
            self._shadow[direction_id] = 0.0

        return {
            "signal":   signal,
            "score":    round(new_score, 3),
            "action":   action,
            "reinforce": action == "reinforce",
            "weaken":    action == "weaken",
        }

    # ─── 강화/약화 적용 ─────────────────────────────────────────

    def _apply_reinforce(self, direction_id: str, score: float):
        """강화 → preferences에 저장."""
        try:
            from core.memory import MemoryStore
            from core.memory import validate_memory
            store = MemoryStore()
            key   = f"feedback_reinforce:{direction_id[:30]}"
            store._save_preference(key, f"강화됨(score={score:.2f})")
            self._log_apply("reinforce", direction_id, score)
        except Exception as e:
            print(f"[FEEDBACK] 강화 저장 실패: {e}")

    def _apply_weaken(self, direction_id: str, score: float):
        """[4-C] 약화 → EvoAnalyzer 재검토 + 웹 검색 지식 보강 제안."""
        try:
            from tools.self.evo_analyzer import _make_proposal, save_proposal

            # 기본 재검토 proposal
            p = _make_proposal(
                prop_type   = "config_update",
                title       = f"[피드백-약화] 재검토 필요: {direction_id[:30]}",
                description = f"피드백 누적 score={score:.2f} → 응답 방향 재검토",
                content     = (
                    f"방향 ID: {direction_id}\n"
                    f"누적 점수: {score:.2f}\n"
                    f"→ 관련 wiki/persona 재검토 권장"
                ),
                metadata    = {
                    "direction_id": direction_id,
                    "score":        score,
                    "changes":      {"review_flag": direction_id}
                }
            )
            save_proposal(p)

            # [4-C] 웹 검색 지식 보강 제안 (별도 proposal)
            topic_key = direction_id[:20]  # direction_id에서 주제 추정
            p_web = _make_proposal(
                prop_type   = "knowledge_update",
                title       = f"[지식보강] 웹 검색으로 '{topic_key}' 지식 업그레이드",
                description = (
                    f"부정 피드백이 누적됐습니다. "
                    f"이 주제에 대한 내부 지식이 부족할 수 있습니다.\n"
                    f"웹 검색으로 최신 정보를 수집하여 장기 지식으로 저장하겠습니다."
                ),
                content     = (
                    f"자동 실행 내용:\n"
                    f"1. DuckDuckGo/Tavily로 '{topic_key}' 검색\n"
                    f"2. URL 본문 fetch → LLM 지식화\n"
                    f"3. wiki entity 저장 + vector 인덱싱\n"
                    f"4. 지식 레벨 +5점"
                ),
                metadata    = {
                    "direction_id": direction_id,
                    "score":        score,
                    "auto_action":  "web_learn",
                    "topic":        topic_key,
                }
            )
            save_proposal(p_web)
            print(f"[FEEDBACK] 지식보강 제안 생성: {topic_key}")
            self._log_apply("weaken+web_proposal", direction_id, score)
        except Exception as e:
            print(f"[FEEDBACK] 약화 제안 실패: {e}")

    # ─── 유틸 ───────────────────────────────────────────────────

    @staticmethod
    def make_direction_id(mode: str, query: str) -> str:
        """응답 방향 ID 생성."""
        import hashlib
        key = f"{mode}:{query[:40]}"
        return hashlib.md5(key.encode()).hexdigest()[:12]

    def get_stats(self) -> Dict:
        pos = sum(1 for h in self._history
                  if FEEDBACK_SIGNALS.get(h["signal"], 0) > 0)
        neg = sum(1 for h in self._history
                  if FEEDBACK_SIGNALS.get(h["signal"], 0) < 0)
        return {
            "total":    len(self._history),
            "positive": pos,
            "negative": neg,
            "tracked_directions": len(self._shadow),
        }

    def _load_shadow(self):
        try:
            if SHADOW_DB.exists():
                for line in SHADOW_DB.read_text(encoding="utf-8").splitlines():
                    d = json.loads(line)
                    did = d.get("direction_id","")
                    if did:
                        self._shadow[did] = d.get("score", 0.0)
        except Exception:
            pass

    def _append_shadow(self, entry: Dict):
        try:
            with open(SHADOW_DB, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _log_apply(self, action: str, did: str, score: float):
        try:
            with open(APPLY_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "action": action, "direction_id": did,
                    "score": score, "time": datetime.now().isoformat()
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass


# ─── 싱글턴 ──────────────────────────────────────────────────────

_engine: Optional[FeedbackEngine] = None

def get_engine() -> FeedbackEngine:
    global _engine
    if _engine is None:
        _engine = FeedbackEngine()
    return _engine

def detect_feedback(query: str, prev_answer: str = "",
                    explicit: Optional[str] = None) -> str:
    return get_engine().detect(query, prev_answer, explicit)

def accumulate_feedback(direction_id: str, signal: str,
                        query: str = "") -> Dict:
    return get_engine().accumulate(direction_id, signal, query)

def get_feedback_stats() -> Dict:
    return get_engine().get_stats()
