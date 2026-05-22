"""
PROJECT JAMES — Knowledge Tracker (P7-EVO-E / P2-11 개선)

분야별 지식 성장 추적 + 레벨 시스템.
[P2-11] wiki 실제 파일 수 + vector 인덱스 수 + 피드백 점수 통합.
"""

import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List

try:
    from config import BASE_DIR, WIKI_DIR, CHROMA_DIR
except ImportError:
    BASE_DIR  = "."
    WIKI_DIR  = "wiki"
    CHROMA_DIR= "chroma_db"

# `label_key` follows the i18n contract used elsewhere in the admin
# UI (LLM_TASK_TYPES, PROTECTED_CANDIDATES, feature_registry.Feature):
# frontend binds `data-i18n` to this key and falls back to `label`
# (EN) on miss. `label_ko` is kept as the historic Korean fallback
# but is no longer the UI's primary KO source — the i18n table is.
DOMAINS = {
    "security":  {"label":"Security",   "label_ko":"보안/정보보호","label_key":"growth.domain.security","icon":"🔐","color":"#f06292"},
    "coding":    {"label":"Coding",     "label_ko":"코딩/개발",    "label_key":"growth.domain.coding",  "icon":"💻","color":"#7c6af7"},
    "business":  {"label":"Business",   "label_ko":"비즈니스",     "label_key":"growth.domain.business","icon":"📊","color":"#4fc3f7"},
    "science":   {"label":"Science/AI", "label_ko":"과학/기술",    "label_key":"growth.domain.science", "icon":"🔬","color":"#4caf7d"},
    "general":   {"label":"General",    "label_ko":"일반 상식",    "label_key":"growth.domain.general", "icon":"🌍","color":"#ffb74d"},
    "personal":  {"label":"Personal",   "label_ko":"개인 맞춤",    "label_key":"growth.domain.personal","icon":"👤","color":"#ce93d8"},
}

CAPABILITIES = [
    {"id":"retrieval",    "label":"Knowledge Retrieval",
     "label_key":"growth.capability.retrieval",
     "desc":"Finds accurate information from documents and resources",
     "desc_key":"growth.capability.retrieval_desc",
     "icon":"📚","base":80},
    {"id":"graph",        "label":"Relation Reasoning",
     "label_key":"growth.capability.graph",
     "desc":"Analyzes connections between people, events, and concepts",
     "desc_key":"growth.capability.graph_desc",
     "icon":"🕸️","base":70},
    {"id":"security",     "label":"Security Judgment",
     "label_key":"growth.capability.security",
     "desc":"Automatically detects sensitive data and dangerous requests",
     "desc_key":"growth.capability.security_desc",
     "icon":"🔐","base":100},
    {"id":"conversation", "label":"Conversation Understanding",
     "label_key":"growth.capability.conversation",
     "desc":"Distinguishes casual chat from professional questions",
     "desc_key":"growth.capability.conversation_desc",
     "icon":"💬","base":80},
    {"id":"accuracy",     "label":"Answer Accuracy",
     "label_key":"growth.capability.accuracy",
     "desc":"Reduces misinformation and provides evidence-based answers",
     "desc_key":"growth.capability.accuracy_desc",
     "icon":"🎯","base":70},
    {"id":"multimodal",   "label":"Image/Video Analysis",
     "label_key":"growth.capability.multimodal",
     "desc":"Recognizes dates, places, and people in photos and videos",
     "desc_key":"growth.capability.multimodal_desc",
     "icon":"🖼️","base":40},
    {"id":"evolution",    "label":"Self-Evolution",
     "label_key":"growth.capability.evolution",
     "desc":"Generates better answers over time through self-improvement",
     "desc_key":"growth.capability.evolution_desc",
     "icon":"🧬","base":50},
    {"id":"agent",        "label":"Agent Capability",
     "label_key":"growth.capability.agent",
     "desc":"Plans and executes complex tasks autonomously",
     "desc_key":"growth.capability.agent_desc",
     "icon":"🤖","base":20},
]

_DOMAIN_KEYWORDS = {
    "security":  ["보안","공격","취약","인증","암호","해킹","침해","security"],
    "coding":    ["코드","함수","파이썬","버그","개발","알고리즘","python","class"],
    "business":  ["비즈니스","경제","시장","전략","매출","투자","기업"],
    "science":   ["과학","기술","물리","화학","AI","머신러닝","데이터"],
    "general":   ["역사","문화","사회","뉴스","일반","상식"],
    "personal":  ["나","저","제","개인","맞춤","취향","선호"],
}

# wiki entity_type → domain 매핑 (실측용)
_ENTITY_DOMAIN_MAP = {
    "person":   "personal",
    "org":      "business",
    "concept":  "science",
    "document": "general",
}

def classify_domain(query: str) -> str:
    q = query.lower()
    scores = {d: sum(1 for kw in kws if kw in q)
              for d, kws in _DOMAIN_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def _measure_wiki_counts() -> Dict[str, int]:
    """[P2-11] 실제 wiki 파일 수를 도메인별로 카운트."""
    counts = {d: 0 for d in DOMAINS}
    wiki = Path(WIKI_DIR)
    if not wiki.exists():
        return counts
    for md_file in wiki.rglob("*.md"):
        content = ""
        try:
            content = md_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # entity_type frontmatter로 도메인 매핑
        et_m = re.search(r'entity_type:\s*(\w+)', content)
        if et_m:
            et = et_m.group(1).lower()
            domain = _ENTITY_DOMAIN_MAP.get(et, "general")
            counts[domain] = counts.get(domain, 0) + 1
        else:
            # 키워드 기반 분류
            domain = classify_domain(content[:500])
            counts[domain] = counts.get(domain, 0) + 1
    return counts


def _measure_vector_counts() -> int:
    """[P2-11] vector store의 총 문서 수 확인."""
    try:
        try:
            from core.vector_store import VectorStore
        except ModuleNotFoundError:
            from vector_store import VectorStore
        vs = VectorStore()
        return vs.count()
    except Exception:
        return 0


class KnowledgeTracker:
    def __init__(self):
        self._scores: Dict[str, float] = {d: 0.0 for d in DOMAINS}
        self._load()

    def update(self, query: str, signal: str = "positive"):
        """쿼리 + 피드백으로 도메인 점수 업데이트."""
        domain = classify_domain(query)
        delta  = 1.0 if signal == "positive" else (-0.5 if signal == "negative" else 0.2)
        self._scores[domain] = max(0, self._scores[domain] + delta)
        self._save()

    def get_domain_levels(self) -> List[Dict]:
        """
        [P2-11] 실측 기반 레벨 계산.
        점수 = 피드백 누적(70%) + wiki 파일 수(20%) + 대화 수(10%)

        [#2-B 변경 2026-05-08] 사용자 피드백: "지식 레벨이 10에서 멈춤
        — 무한대로 늘리고 싶다". 게임식 레벨 캡(10) 제거 → 누적 점수에
        선형 비례. 매 5점당 +1 레벨. 시각적 표시는 도넛 차트로 전환했
        으니 (#2-C) 큰 숫자도 깨지지 않음.

        pct는 그대로 0-100 — 도넛 차트의 채움 비율로 사용. 5점 미만의
        새 도메인엔 5%로 가시성 확보.

        도넛 차트(#2-C)에 사용할 `level_max_in_tier`도 함께 반환 — 같은
        티어(10점 단위) 내에서 다음 레벨까지의 진행도. UI는 이걸로
        "Lv.13 (다음까지 60%)" 같은 표시 가능.
        """
        wiki_counts   = _measure_wiki_counts()
        vector_total  = _measure_vector_counts()

        result = []
        for d in DOMAINS:
            feedback_score = self._scores[d]

            # wiki 기여 (파일 1개당 +3점)
            wiki_boost = wiki_counts.get(d, 0) * 3.0

            # vector 기여 (전체 문서 수 비례 — 도메인 추정 불가 시 균등 배분)
            vector_boost = (vector_total / len(DOMAINS)) * 0.5

            total_score = feedback_score * 0.7 + wiki_boost * 0.2 + vector_boost * 0.1

            # [#2-B] uncapped: max(1, ...) 만 유지하고 min(10, ...) 제거.
            # 5점당 +1 레벨이라 100점이면 21레벨 → 1000점이면 201레벨.
            level = max(1, int(total_score / 5) + 1)
            pct   = max(5,  min(100, int(total_score * 2) + wiki_counts.get(d, 0) * 5))

            # [#2-C 도넛 차트용] 같은 5점 티어 내 다음 레벨까지 진행도.
            # 예: total_score=12 → tier_progress = 12 - 10 = 2점 → 40%.
            tier_floor    = (level - 1) * 5
            tier_progress = total_score - tier_floor
            tier_pct      = max(0, min(100, int(tier_progress / 5 * 100)))

            result.append({
                "domain":       d,
                "label":        DOMAINS[d]["label"],
                "label_key":    DOMAINS[d]["label_key"],   # i18n binding
                "icon":         DOMAINS[d]["icon"],
                "color":        DOMAINS[d]["color"],
                "score":        round(total_score, 1),
                "level":        level,
                "pct":          pct,
                "tier_pct":     tier_pct,    # [#2-C] 도넛 채움 %
                "wiki_count":   wiki_counts.get(d, 0),   # [P2-11] 실측 추가
                "vector_count": vector_total,              # [P2-11] 실측 추가
            })
        return result

    def get_capabilities(self) -> List[Dict]:
        """Phase 1~7 기준 능력치 반환."""
        ev_score = sum(self._scores.values())
        vector_total = _measure_vector_counts()
        # vector 문서가 많을수록 retrieval 능력 상승
        retrieval_boost = min(15, int(vector_total / 10))
        boosts = {
            "evolution": min(30, ev_score),
            "general":   min(10, ev_score * 0.5),
            "retrieval": retrieval_boost,
        }
        return [{
            **c,
            "pct": min(100, c["base"] + int(boosts.get(c["id"], 0))),
        } for c in CAPABILITIES]

    def get_recent_gains(self, limit: int = 3) -> List[str]:
        top = sorted(self._scores.items(), key=lambda x: x[1], reverse=True)[:limit]
        return [f"{DOMAINS[d]['icon']} {DOMAINS[d]['label']} (+{s:.0f})"
                for d, s in top if s > 0]

    def _load(self):
        try:
            from core.memory.store import _connect
            with _connect() as conn:
                rows = conn.execute(
                    "SELECT key, value FROM preferences WHERE key LIKE 'domain:%'"
                ).fetchall()
                for r in rows:
                    d = r["key"].replace("domain:", "")
                    if d in DOMAINS:
                        try: self._scores[d] = float(r["value"])
                        except Exception: pass
        except Exception:
            pass

    def _save(self):
        try:
            from core.memory.store import _connect
            now = datetime.now().isoformat()
            with _connect() as conn:
                for d, v in self._scores.items():
                    conn.execute(
                        "INSERT OR REPLACE INTO preferences "
                        "(key, value, raw, confidence, created_at, updated_at) "
                        "VALUES (?,?,?,?,?,?)",
                        (f"domain:{d}", str(v), "", 1.0, now, now)
                    )
        except Exception:
            pass


_tracker = None
def get_tracker() -> KnowledgeTracker:
    global _tracker
    if _tracker is None:
        _tracker = KnowledgeTracker()
    return _tracker
