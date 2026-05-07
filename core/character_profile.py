"""
PROJECT JAMES — Character Profile (P7-EVO-D)

자메스의 성향 수치 관리.
상충 그룹 규칙: A~D 그룹 내 합 = 1.0 유지
E 그룹: 독립 성향
"""

from datetime import datetime
from typing import Dict

try:
    from config import BASE_DIR
except ImportError:
    BASE_DIR = "."

TRAITS = {
    "curiosity":     {"label":"Curiosity",    "label_ko":"탐구심",   "group":"A","default":0.5,"icon":"🔍"},
    "focus":         {"label":"Focus",         "label_ko":"집중력",   "group":"A","default":0.5,"icon":"🎯"},
    "caution":       {"label":"Caution",       "label_ko":"신중함",   "group":"B","default":0.7,"icon":"🛡️"},
    "boldness":      {"label":"Boldness",       "label_ko":"과감함",   "group":"B","default":0.3,"icon":"⚡"},
    "analytical":    {"label":"Analytical",    "label_ko":"분석력",   "group":"C","default":0.6,"icon":"📊"},
    "intuitive":     {"label":"Intuitive",     "label_ko":"직관력",   "group":"C","default":0.4,"icon":"💡"},
    "independent":   {"label":"Independent",   "label_ko":"독립성",   "group":"D","default":0.5,"icon":"🦅"},
    "collaborative": {"label":"Collaborative", "label_ko":"협력성",   "group":"D","default":0.5,"icon":"🤝"},
    "security":      {"label":"Security",      "label_ko":"보안의식", "group":"E","default":0.9,"icon":"🔐"},
    "creativity":    {"label":"Creativity",    "label_ko":"창의성",   "group":"E","default":0.5,"icon":"🎨"},
    "empathy":       {"label":"Empathy",       "label_ko":"공감능력", "group":"E","default":0.5,"icon":"💙"},
}

_OPPONENTS = {"curiosity":"focus","focus":"curiosity",
               "caution":"boldness","boldness":"caution",
               "analytical":"intuitive","intuitive":"analytical",
               "independent":"collaborative","collaborative":"independent"}


class CharacterProfile:
    def __init__(self):
        self._values: Dict[str, float] = {k: v["default"] for k, v in TRAITS.items()}
        self._load()

    def get(self) -> Dict:
        return {k: round(v, 3) for k, v in self._values.items()}

    def get_with_meta(self) -> list:
        return [{
            "id":      k,
            "label":   TRAITS[k]["label"],
            "icon":    TRAITS[k]["icon"],
            "group":   TRAITS[k]["group"],
            "value":   round(self._values[k], 3),
            "default": TRAITS[k]["default"],
        } for k in TRAITS]

    def set_trait(self, trait_id: str, value: float) -> Dict:
        """성향 설정. 상충 그룹 자동 조정."""
        if trait_id not in TRAITS:
            return {"error": f"알 수 없는 성향: {trait_id}"}
        value = max(0.0, min(1.0, round(value, 3)))
        self._values[trait_id] = value
        # 상충 그룹 자동 조정
        opp = _OPPONENTS.get(trait_id)
        if opp:
            self._values[opp] = round(1.0 - value, 3)
        self._save()
        return {"trait_id": trait_id, "value": value, "opponent": opp}

    def get_prompt_modifiers(self) -> str:
        """reasoning_engine 프롬프트에 주입할 성향 지시문."""
        p = self._values
        lines = []

        # 0.7 이상 → 강하게 반영
        if p.get("caution",     0.5) > 0.7:
            lines.append("확실한 정보만 포함하고 불확실한 부분은 명시하라.")
        if p.get("curiosity",   0.5) > 0.7:
            lines.append("관련된 흥미로운 주제도 함께 제시하라.")
        if p.get("analytical",  0.5) > 0.7:
            lines.append("논리적 근거와 데이터를 중심으로 분석하라.")
        if p.get("empathy",     0.5) > 0.7:
            lines.append("사용자의 감정과 맥락을 고려해서 답변하라.")
        if p.get("creativity",  0.5) > 0.7:
            lines.append("창의적이고 다양한 관점에서 접근하라.")
        if p.get("directness",  0.5) > 0.7:
            lines.append("결론을 먼저 말하고 간결하게 핵심만 전달하라.")
        if p.get("security",    0.5) > 0.7:
            lines.append("보안 위험성과 잠재적 취약점을 항상 함께 언급하라.")
        if p.get("conciseness", 0.5) > 0.7:
            lines.append("불필요한 설명을 제거하고 최대한 짧게 답하라.")

        # 0.3 이하 → 반대 방향 반영
        if p.get("caution",     0.5) < 0.3:
            lines.append("다양한 가능성을 열어두고 과감하게 제안하라.")
        if p.get("conciseness", 0.5) < 0.3:
            lines.append("충분한 배경 설명과 맥락을 포함하여 상세히 답하라.")

        return " ".join(lines)

    def _load(self):
        try:
            from core.memory import MemoryStore
            from core.memory.store import _connect
            with _connect() as conn:
                rows = conn.execute(
                    "SELECT key, value FROM preferences WHERE key LIKE 'trait:%'"
                ).fetchall()
                for r in rows:
                    tid = r["key"].replace("trait:", "")
                    if tid in TRAITS:
                        try: self._values[tid] = float(r["value"])
                        except Exception: pass
        except Exception:
            pass

    def _save(self):
        try:
            from core.memory.store import _connect
            now = datetime.now().isoformat()
            with _connect() as conn:
                for tid, val in self._values.items():
                    conn.execute(
                        "INSERT OR REPLACE INTO preferences "
                        "(key, value, raw, confidence, created_at, updated_at) "
                        "VALUES (?,?,?,?,?,?)",
                        (f"trait:{tid}", str(val), "", 1.0, now, now)
                    )
        except Exception as e:
            print(f"[PROFILE] 저장 실패: {e}")


_profile = None
def get_profile() -> CharacterProfile:
    global _profile
    if _profile is None:
        _profile = CharacterProfile()
    return _profile
