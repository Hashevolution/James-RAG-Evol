"""
PROJECT JAMES — Character Profile (P7-EVO-D + P1 unified UX 2026-05-10)

자메스의 성향 수치 관리.

[원본 — 2026-05]
- 11 traits, 4 opposing pair groups (A~D, sum=1.0 강제) + 1 independent group (E)
- 슬라이더 + 자유 텍스트 페르소나 두 인터페이스가 충돌 가능

[P1 — 2026-05-10 (Alternative A 통합 UX 1단계)]
- 11 → 16 traits (간결성 / 직설성 / 낙관성 / 위험감수 / 인내심 추가, Group F)
- CORRELATIONS — 짝(opposing) 외에도 trait 간 soft 상관관계
- set_trait 시 짝(즉시 flip, sum=1.0) + 상관 trait ripple(damped 비례 nudge) 동시 적용
- get_correlations() — 프론트가 시각화에 사용 (radar 위 edge 표시)
- 기존 11개 + _OPPONENTS dict 변경 없음 → 마이그레이션 부담 0

[P1 후속]
- P2: interactive radar (드래그 + ripple visualization)
- P3: Identity 탭 분리 + Live Preview + Settings 페르소나 제거
- P4: 기존 persona.style/custom 자유텍스트 마이그레이션
"""

from datetime import datetime
from typing import Dict, List

try:
    from config import BASE_DIR
except ImportError:
    BASE_DIR = "."

# ─── Trait registry ────────────────────────────────────────────────
# 16 traits — 11 (legacy) + 5 (P1 신규).
# Group: A~D 짝(서로 합 1.0 강제) / E,F 독립(상관관계로만 영향).
TRAITS: Dict[str, dict] = {
    # ─── A: cognitive curiosity vs focus ────────────────────────
    "curiosity":     {"label": "Curiosity",     "label_ko": "탐구심",   "group": "A", "default": 0.5, "icon": "🔍"},
    "focus":         {"label": "Focus",         "label_ko": "집중력",   "group": "A", "default": 0.5, "icon": "🎯"},
    # ─── B: caution vs boldness ─────────────────────────────────
    "caution":       {"label": "Caution",       "label_ko": "신중함",   "group": "B", "default": 0.7, "icon": "🛡️"},
    "boldness":      {"label": "Boldness",      "label_ko": "과감함",   "group": "B", "default": 0.3, "icon": "⚡"},
    # ─── C: analytical vs intuitive ─────────────────────────────
    "analytical":    {"label": "Analytical",    "label_ko": "분석력",   "group": "C", "default": 0.6, "icon": "📊"},
    "intuitive":     {"label": "Intuitive",     "label_ko": "직관력",   "group": "C", "default": 0.4, "icon": "💡"},
    # ─── D: independence vs collaboration ───────────────────────
    "independent":   {"label": "Independent",   "label_ko": "독립성",   "group": "D", "default": 0.5, "icon": "🦅"},
    "collaborative": {"label": "Collaborative", "label_ko": "협력성",   "group": "D", "default": 0.5, "icon": "🤝"},
    # ─── E: independent core values ─────────────────────────────
    "security":      {"label": "Security",      "label_ko": "보안의식", "group": "E", "default": 0.9, "icon": "🔐"},
    "creativity":    {"label": "Creativity",    "label_ko": "창의성",   "group": "E", "default": 0.5, "icon": "🎨"},
    "empathy":       {"label": "Empathy",       "label_ko": "공감능력", "group": "E", "default": 0.5, "icon": "💙"},
    # ─── F: P1 신규 (모두 독립, 상관관계만 작용) ─────────────────
    "conciseness":   {"label": "Conciseness",   "label_ko": "간결성",   "group": "F", "default": 0.5, "icon": "✂️"},
    "directness":    {"label": "Directness",    "label_ko": "직설성",   "group": "F", "default": 0.5, "icon": "🎯"},
    "optimism":      {"label": "Optimism",      "label_ko": "낙관성",   "group": "F", "default": 0.5, "icon": "☀️"},
    "risk_tolerance":{"label": "Risk Tolerance","label_ko": "위험감수", "group": "F", "default": 0.4, "icon": "🎲"},
    "patience":      {"label": "Patience",      "label_ko": "인내심",   "group": "F", "default": 0.6, "icon": "⏳"},
}

# 짝(opposing) — set_trait 시 즉시 flip, sum=1.0 invariant.
# Group A~D만 해당 — Group E/F는 독립.
_OPPONENTS = {
    "curiosity": "focus", "focus": "curiosity",
    "caution": "boldness", "boldness": "caution",
    "analytical": "intuitive", "intuitive": "analytical",
    "independent": "collaborative", "collaborative": "independent",
}

# ─── Correlations (P1 신규) ────────────────────────────────────────
# Sparse hand-curated graph — trait 간 soft 상관관계.
# 형식: (source, target, weight). weight ∈ [-1, 1].
#   양수: source 증가 → target 증가 (예: 탐구심 ↑ → 창의성 ↑)
#   음수: source 증가 → target 감소 (예: 신중함 ↑ → 위험감수 ↓)
#
# damping factor (0.3, set_trait 안 하드코딩) 적용 후 nudge:
#   target += (source_delta) × weight × damping
#
# 짝(opposing pair)은 이미 _OPPONENTS로 100% flip 처리되므로 여기에
# 중복 등재 X. 이 그래프는 "짝 외에 약한 영향" 만 표현.
#
# 사람이 직관적으로 동의할 만한 관계만 등재 (15 edges).
CORRELATIONS: List[tuple] = [
    # 인지(A,C) → 창의/직관 cluster
    ("curiosity",      "creativity",     +0.30),
    ("intuitive",      "creativity",     +0.20),
    ("focus",          "patience",       +0.30),
    ("analytical",     "directness",     +0.20),

    # 방어(B) ↔ 보안 / 위험감수
    ("caution",        "security",       +0.40),
    ("caution",        "risk_tolerance", -0.40),
    ("boldness",       "risk_tolerance", +0.50),
    ("boldness",       "directness",     +0.20),

    # 사회(D) ↔ 공감
    ("empathy",        "collaborative",  +0.30),
    ("collaborative",  "empathy",        +0.20),  # 양방향 (강도 다름)
    ("independent",    "directness",     +0.20),

    # 표현 스타일(F) 내부
    ("conciseness",    "directness",     +0.30),
    ("directness",     "empathy",        -0.20),  # 직설 ↑ → 공감 표현 약화

    # 정서 cluster
    ("creativity",     "optimism",       +0.20),
    ("patience",       "empathy",        +0.20),
]

# 효율적인 이웃 lookup용 인덱스 (set_trait이 매 호출마다 재계산하지
# 않도록 모듈 로드 시 1회만).
_CORR_INDEX: Dict[str, List[tuple]] = {}
for _src, _tgt, _w in CORRELATIONS:
    _CORR_INDEX.setdefault(_src, []).append((_tgt, _w))

# Ripple damping — cascade 폭주 방지. 0.3 = 짝(1.0) 대비 30% 영향.
_RIPPLE_DAMPING = 0.3


class CharacterProfile:
    def __init__(self):
        self._values: Dict[str, float] = {k: v["default"] for k, v in TRAITS.items()}
        self._load()

    # ─── 조회 ──────────────────────────────────────────────────────
    def get(self) -> Dict:
        return {k: round(v, 3) for k, v in self._values.items()}

    def get_with_meta(self) -> list:
        return [{
            "id":      k,
            "label":   TRAITS[k]["label"],
            "label_ko": TRAITS[k].get("label_ko", TRAITS[k]["label"]),
            "icon":    TRAITS[k]["icon"],
            "group":   TRAITS[k]["group"],
            "value":   round(self._values[k], 3),
            "default": TRAITS[k]["default"],
        } for k in TRAITS]

    @staticmethod
    def get_correlations() -> List[dict]:
        """Return correlations as dicts for frontend visualization.

        Frontend uses these to draw edges between trait vertices on
        the radar chart, color-coded by sign and thickness by weight.
        """
        return [{"from": s, "to": t, "weight": w} for (s, t, w) in CORRELATIONS]

    @staticmethod
    def get_damping() -> float:
        """Expose damping factor so frontend animation matches the
        backend's actual ripple magnitude."""
        return _RIPPLE_DAMPING

    # ─── 변경 ──────────────────────────────────────────────────────
    def set_trait(self, trait_id: str, value: float) -> Dict:
        """성향 설정. 짝(opposing) 즉시 flip + 상관 trait ripple 적용.

        Returns:
            {trait_id, value, opponent, ripples: [{trait, old, new, weight}, ...]}
            opponent: 짝이 있는 group A~D 경우 짝 trait의 새 값 (1.0 - value)
            ripples: 상관관계로 인해 함께 움직인 trait들의 변경 내역
        """
        if trait_id not in TRAITS:
            return {"error": f"알 수 없는 성향: {trait_id}"}

        old_value = self._values[trait_id]
        value = max(0.0, min(1.0, round(value, 3)))
        delta = value - old_value
        self._values[trait_id] = value

        result: Dict = {"trait_id": trait_id, "value": value,
                        "opponent": None, "ripples": []}

        # ─── 짝 자동 flip (Group A~D, sum=1.0 invariant) ────────────
        opp = _OPPONENTS.get(trait_id)
        if opp:
            self._values[opp] = round(1.0 - value, 3)
            result["opponent"] = opp

        # ─── 상관 trait ripple (Group 무관, damped 비례) ────────────
        # 짝 trait은 이미 위에서 처리 — 이중 적용 방지 위해 skip set.
        skip = {trait_id}
        if opp:
            skip.add(opp)

        for target, weight in _CORR_INDEX.get(trait_id, []):
            if target in skip:
                continue
            old = self._values[target]
            nudge = delta * weight * _RIPPLE_DAMPING
            new = max(0.0, min(1.0, round(old + nudge, 3)))
            if abs(new - old) > 0.001:   # 실제 변화 있을 때만 기록
                self._values[target] = new
                result["ripples"].append({
                    "trait":  target,
                    "old":    round(old, 3),
                    "new":    new,
                    "weight": weight,
                })

        self._save()
        return result

    # ─── LLM 프롬프트 주입 ─────────────────────────────────────────
    def get_prompt_modifiers(self) -> str:
        """reasoning_engine 프롬프트에 주입할 성향 지시문.

        규칙:
          - 0.7 이상 → 강하게 반영 (해당 trait 관련 directive 추가)
          - 0.3 이하 → 반대 방향 directive 추가 (있는 경우)
        """
        p = self._values
        lines: List[str] = []

        # ─── 0.7 이상 ─────────────────────────────────────────────
        if p.get("caution",        0.5) > 0.7:
            lines.append("확실한 정보만 포함하고 불확실한 부분은 명시하라.")
        if p.get("curiosity",      0.5) > 0.7:
            lines.append("관련된 흥미로운 주제도 함께 제시하라.")
        if p.get("analytical",     0.5) > 0.7:
            lines.append("논리적 근거와 데이터를 중심으로 분석하라.")
        if p.get("empathy",        0.5) > 0.7:
            lines.append("사용자의 감정과 맥락을 고려해서 답변하라.")
        if p.get("creativity",     0.5) > 0.7:
            lines.append("창의적이고 다양한 관점에서 접근하라.")
        if p.get("directness",     0.5) > 0.7:
            lines.append("결론을 먼저 말하고 간결하게 핵심만 전달하라.")
        if p.get("security",       0.5) > 0.7:
            lines.append("보안 위험성과 잠재적 취약점을 항상 함께 언급하라.")
        if p.get("conciseness",    0.5) > 0.7:
            lines.append("불필요한 설명을 제거하고 최대한 짧게 답하라.")
        # ─── P1 신규 trait directives ─────────────────────────────
        if p.get("optimism",       0.5) > 0.7:
            lines.append("긍정적 가능성과 기회를 강조해서 제시하라.")
        if p.get("risk_tolerance", 0.5) > 0.7:
            lines.append("리스크 있는 옵션도 검토 가치가 있다면 제안하라.")
        if p.get("patience",       0.5) > 0.7:
            lines.append("단계적이고 차분한 설명으로 답하라.")

        # ─── 0.3 이하 (반대 방향) ─────────────────────────────────
        if p.get("caution",        0.5) < 0.3:
            lines.append("다양한 가능성을 열어두고 과감하게 제안하라.")
        if p.get("conciseness",    0.5) < 0.3:
            lines.append("충분한 배경 설명과 맥락을 포함하여 상세히 답하라.")
        if p.get("optimism",       0.5) < 0.3:
            lines.append("리스크와 한계를 명확히 짚고 신중한 톤으로 답하라.")
        if p.get("risk_tolerance", 0.5) < 0.3:
            lines.append("안전한 옵션을 우선 제안하라.")
        if p.get("patience",       0.5) < 0.3:
            lines.append("핵심 결론을 빠르게 전달하라.")
        if p.get("directness",     0.5) < 0.3:
            lines.append("우회적이고 부드러운 표현을 사용하라.")

        return " ".join(lines)

    # ─── 영속화 (preferences DB의 trait:* 키) ──────────────────────
    def _load(self):
        try:
            from core.memory.store import _connect
            with _connect() as conn:
                rows = conn.execute(
                    "SELECT key, value FROM preferences WHERE key LIKE 'trait:%'"
                ).fetchall()
                for r in rows:
                    tid = r["key"].replace("trait:", "")
                    if tid in TRAITS:
                        try:
                            self._values[tid] = float(r["value"])
                        except Exception:
                            pass
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
