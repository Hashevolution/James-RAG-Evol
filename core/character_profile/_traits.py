"""Character profile — trait registry + correlation graph.

16-trait registry, opposing-pair flip map, sparse hand-curated
correlation edge list, and the per-source neighbour index used by
``set_trait`` ripple math. Split out of the monolithic
``core/character_profile.py`` in Stage C.3 (2026-05-24) so every
file in the package respects CLAUDE.md rule #5 (< 20 KB).

External callers depend on:

- ``TRAITS`` — tests + i18n convention checks
- ``CORRELATIONS`` — tests/test_character_w3b.py + traits-correlations test
- ``_CORR_INDEX`` — tests/test_character_traits_correlations.py
- ``_OPPONENTS`` — tests/test_character_traits_correlations.py
- ``_RIPPLE_DAMPING`` — tests/test_character_w3b.py

All four are re-exported from ``core.character_profile`` so existing
import paths keep working byte-identical.
"""
from __future__ import annotations

from typing import Dict, List

try:
    from config import BASE_DIR  # noqa: F401 — kept for backward compat
except ImportError:
    BASE_DIR = "."

# ─── Trait registry ────────────────────────────────────────────────
# 16 traits — 11 (legacy) + 5 (P1 신규).
# Group: A~D 짝(서로 합 1.0 강제) / E,F 독립(상관관계로만 영향).
TRAITS: Dict[str, dict] = {
    # ─── A: cognitive curiosity vs focus ────────────────────────
    "curiosity":     {"label": "Curiosity",     "label_ko": "탐구심",   "label_key": "char.trait.curiosity",     "group": "A", "default": 0.5, "icon": "🔍"},
    "focus":         {"label": "Focus",         "label_ko": "집중력",   "label_key": "char.trait.focus",         "group": "A", "default": 0.5, "icon": "🎯"},
    # ─── B: caution vs boldness ─────────────────────────────────
    "caution":       {"label": "Caution",       "label_ko": "신중함",   "label_key": "char.trait.caution",       "group": "B", "default": 0.7, "icon": "🛡️"},
    "boldness":      {"label": "Boldness",      "label_ko": "과감함",   "label_key": "char.trait.boldness",      "group": "B", "default": 0.3, "icon": "⚡"},
    # ─── C: analytical vs intuitive ─────────────────────────────
    "analytical":    {"label": "Analytical",    "label_ko": "분석력",   "label_key": "char.trait.analytical",    "group": "C", "default": 0.6, "icon": "📊"},
    "intuitive":     {"label": "Intuitive",     "label_ko": "직관력",   "label_key": "char.trait.intuitive",     "group": "C", "default": 0.4, "icon": "💡"},
    # ─── D: independence vs collaboration ───────────────────────
    "independent":   {"label": "Independent",   "label_ko": "독립성",   "label_key": "char.trait.independent",   "group": "D", "default": 0.5, "icon": "🦅"},
    "collaborative": {"label": "Collaborative", "label_ko": "협력성",   "label_key": "char.trait.collaborative", "group": "D", "default": 0.5, "icon": "🤝"},
    # ─── E: independent core values ─────────────────────────────
    "security":      {"label": "Security",      "label_ko": "보안의식", "label_key": "char.trait.security",      "group": "E", "default": 0.9, "icon": "🔐"},
    "creativity":    {"label": "Creativity",    "label_ko": "창의성",   "label_key": "char.trait.creativity",    "group": "E", "default": 0.5, "icon": "🎨"},
    "empathy":       {"label": "Empathy",       "label_ko": "공감능력", "label_key": "char.trait.empathy",       "group": "E", "default": 0.5, "icon": "💙"},
    # ─── F: P1 신규 (모두 독립, 상관관계만 작용) ─────────────────
    "conciseness":   {"label": "Conciseness",   "label_ko": "간결성",   "label_key": "char.trait.conciseness",   "group": "F", "default": 0.5, "icon": "✂️"},
    "directness":    {"label": "Directness",    "label_ko": "직설성",   "label_key": "char.trait.directness",    "group": "F", "default": 0.5, "icon": "🎯"},
    "optimism":      {"label": "Optimism",      "label_ko": "낙관성",   "label_key": "char.trait.optimism",      "group": "F", "default": 0.5, "icon": "☀️"},
    "risk_tolerance":{"label": "Risk Tolerance","label_ko": "위험감수", "label_key": "char.trait.risk_tolerance","group": "F", "default": 0.4, "icon": "🎲"},
    "patience":      {"label": "Patience",      "label_ko": "인내심",   "label_key": "char.trait.patience",      "group": "F", "default": 0.6, "icon": "⏳"},
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
# [W3b 2026-05-10, W1 진단 §1-C] 28 edges (이전 15) — 사용자 체감 영향력
# 강화. P1 미반영 5 trait (focus/intuitive/independent/collaborative/
# boldness) 가 모두 incoming edge 를 받도록 incoming 보강.
CORRELATIONS: List[tuple] = [
    # ── 원본 15 (P1) ─────────────────────────────────────────────
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

    # ── W3b 추가 13 — 미반영 5 trait 의 incoming 보강 ────────────
    # focus 의 incoming (이전엔 outgoing 만 있었음 — 슬라이더 변경
    # 시 다른 trait 변화에 따라 자동 조정되도록).
    ("analytical",     "focus",          +0.40),  # 분석 ↑ → 집중 ↑
    ("patience",       "focus",          +0.30),  # 인내 ↑ → 집중 ↑
    ("caution",        "focus",          +0.20),  # 신중 ↑ → 집중 ↑
    ("conciseness",    "focus",          +0.20),  # 간결 ↑ → 집중 ↑

    # intuitive 의 incoming
    ("creativity",     "intuitive",      +0.30),  # 창의 ↑ → 직관 ↑
    ("empathy",        "intuitive",      +0.20),  # 공감 ↑ → 직관 ↑

    # boldness 의 incoming (이전엔 outgoing 만)
    ("risk_tolerance", "boldness",       +0.40),  # 위험감수 ↑ → 과감 ↑
    ("creativity",     "boldness",       +0.20),  # 창의 ↑ → 과감 ↑
    ("optimism",       "boldness",       +0.20),  # 낙관 ↑ → 과감 ↑

    # collaborative 의 incoming (empathy 외 추가)
    ("patience",       "collaborative",  +0.30),  # 인내 ↑ → 협력 ↑

    # independent 의 incoming
    ("analytical",     "independent",    +0.30),  # 분석 ↑ → 독립 ↑

    # 추가 cluster 강화 — 표현 스타일 양방향
    ("directness",     "conciseness",    +0.20),  # 직설 ↑ → 간결 ↑
    ("security",       "caution",        +0.30),  # 보안의식 ↑ → 신중 ↑
]

# 효율적인 이웃 lookup용 인덱스 (set_trait이 매 호출마다 재계산하지
# 않도록 모듈 로드 시 1회만).
_CORR_INDEX: Dict[str, List[tuple]] = {}
for _src, _tgt, _w in CORRELATIONS:
    _CORR_INDEX.setdefault(_src, []).append((_tgt, _w))

# [W3b 2026-05-10] damping 0.3 → 0.6. W1 진단: 0.3 으로는 ripple 변화량이
# 0.05 미만이라 사용자 눈에 거의 안 보였음. 0.6 으로 올려도 cascade 폭주는
# set_trait 가 1-level (no recursion) 이므로 안전.
_RIPPLE_DAMPING = 0.6


__all__ = [
    "TRAITS",
    "_OPPONENTS",
    "CORRELATIONS",
    "_CORR_INDEX",
    "_RIPPLE_DAMPING",
]
