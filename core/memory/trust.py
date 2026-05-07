"""
PROJECT JAMES - Memory Trust Scoring (Phase 4.5)

브리핑 스펙:
  score = trust × consistency × recency
  threshold 미달 시 write 거부

공식:
  trust       = ROLE_TRUST[user_role]          (0.0 ~ 1.0)
  consistency = ontology_valid × no_conflict   (0.0 ~ 1.0)
  recency     = exp(-DECAY × age_days)         (0.0 ~ 1.0)
  SCORE       = trust × consistency × recency
  THRESHOLD   = 0.5  → 미달 시 write 거부

적용 위치:
  wiki_generator.create_entity_file() 진입 전
  server_llmwiki.py /upload/ 처리 시
"""

import math
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from core.ontology import (
    normalize_relation,
    RELATION_TYPES,
    is_sensitive_relation,
)
from core.security_layer import log_system_event

# ─── 상수 ────────────────────────────────────────────────────

TRUST_THRESHOLD = 0.5      # 이 이하 → write 거부
RECENCY_DECAY   = 0.01     # 하루당 감쇠율 (30일 후 ≈ 0.74)
SYSTEM_LOG_PATH = "james_system_log.jsonl"

ROLE_TRUST: Dict[str, float] = {
    "admin":    1.0,
    "manager":  0.8,
    "employee": 0.6,
    "external": 0.1,   # external의 write는 사실상 차단
}


class MemoryTrustScorer:
    """
    entity write 전 신뢰도 검증.

    compute_score() → 0.0 ~ 1.0
    verify_before_write() → (ok: bool, reason: str, score: float)
    """

    def __init__(self, wiki_dir: Optional[str] = None):
        self.wiki_dir = wiki_dir
        self._entity_index: Optional[Dict] = None   # 충돌 검사용 캐시

    # ─── 메인 API ─────────────────────────────────────────────

    def verify_before_write(
        self,
        entity:    Dict,
        user_role: str,
        source_date: Optional[str] = None,   # ISO 날짜 (없으면 오늘)
    ) -> Tuple[bool, str, float]:
        """
        write 허용 여부 판단.

        Returns:
            (ok, reason, score)
            ok=False → write 거부
        """
        score, breakdown = self.compute_score(entity, user_role, source_date)

        if score < TRUST_THRESHOLD:
            reason = (
                f"Memory Trust Score 미달 ({score:.3f} < {TRUST_THRESHOLD}) | "
                f"trust={breakdown['trust']:.2f} "
                f"consistency={breakdown['consistency']:.2f} "
                f"recency={breakdown['recency']:.2f}"
            )
            self._log_rejection(entity, user_role, score, reason)
            return False, reason, score

        return True, f"신뢰도 검증 통과 (score={score:.3f})", score

    def compute_score(
        self,
        entity:      Dict,
        user_role:   str,
        source_date: Optional[str] = None,
    ) -> Tuple[float, Dict]:
        """
        score = trust × consistency × recency

        Returns:
            (score, breakdown_dict)
        """
        trust       = self._compute_trust(user_role)
        consistency = self._compute_consistency(entity)
        recency     = self._compute_recency(source_date)

        score = round(trust * consistency * recency, 4)

        breakdown = {
            "trust":       round(trust, 4),
            "consistency": round(consistency, 4),
            "recency":     round(recency, 4),
            "score":       score,
            "threshold":   TRUST_THRESHOLD,
            "passed":      score >= TRUST_THRESHOLD,
        }

        return score, breakdown

    # ─── Trust: 역할 기반 ────────────────────────────────────

    @staticmethod
    def _compute_trust(user_role: str) -> float:
        """
        역할 기반 신뢰도.
        external은 0.1 → score 최대 0.1 → threshold 0.5 미달 → 자동 차단
        """
        return ROLE_TRUST.get(user_role, 0.1)

    # ─── Consistency: Ontology + 충돌 검사 ───────────────────

    def _compute_consistency(self, entity: Dict) -> float:
        """
        consistency = ontology_valid × no_conflict

        ontology_valid: relations 중 ONTOLOGY에 등록된 비율
        no_conflict:    기존 entity와 name/type 충돌 없으면 1.0, 충돌 시 0.0
        """
        ontology_valid = self._check_ontology(entity)
        no_conflict    = self._check_no_conflict(entity)
        return round(ontology_valid * no_conflict, 4)

    @staticmethod
    def _check_ontology(entity: Dict) -> float:
        """
        relations 중 ONTOLOGY에 등록된 relation_type 비율.
        relation 없으면 1.0 (신뢰 중립).
        """
        relations = entity.get("relations", [])
        if not relations:
            return 1.0

        valid = 0
        for rel in relations:
            raw  = rel.get("type") or rel.get("label") or "RELATED_TO"
            std  = normalize_relation(raw)
            if std in RELATION_TYPES:
                valid += 1

        return round(valid / len(relations), 4)

    def _check_no_conflict(self, entity: Dict) -> float:
        """
        기존 wiki entity와 name + entity_type 충돌 검사.
        충돌 없음 → 1.0 / 충돌 → 0.0
        충돌 = 동일 name + 동일 type의 entity_id가 이미 존재
        (동일 entity 업데이트는 허용 — entity_id 기준)
        """
        if not self.wiki_dir:
            return 1.0   # wiki_dir 없으면 검사 불가 → 통과

        name      = entity.get("name", "")
        etype     = entity.get("type", entity.get("entity_type", "concept"))
        entity_id = entity.get("entity_id", "")

        try:
            entity_base = Path(self.wiki_dir) / "entity"

            # prod + test + 레거시 모두 검사
            for sub in ["prod", "test", ""]:
                check_path = entity_base / sub / etype if sub else entity_base / etype
                if not check_path.exists():
                    continue
                for f in check_path.glob("*.md"):
                    content = f.read_text(encoding="utf-8")
                    # 동일 entity_id면 업데이트이므로 허용
                    if entity_id and f"entity_id: {entity_id}" in content:
                        return 1.0
                    # 동일 name + type 충돌
                    norm_name = name.strip().lower().replace(" ", "_")
                    if f"normalized_name: {norm_name}" in content:
                        print(f"[TRUST] 충돌 감지: {name} ({etype}) 이미 존재")
                        return 0.0
        except Exception as e:
            log_system_event("memory_trust.conflict_check", str(e), level="WARN")

        return 1.0

    # ─── Recency: 날짜 기반 감쇠 ────────────────────────────

    @staticmethod
    def _compute_recency(source_date: Optional[str] = None) -> float:
        """
        recency = exp(-DECAY × age_days)

        source_date 없으면 오늘 날짜 사용 → recency=1.0
        오래된 데이터일수록 낮아짐.

        예시:
          오늘:   1.000
          30일:   0.741
          60일:   0.549
          100일:  0.368
          365일:  0.026
        """
        if not source_date:
            return 1.0   # 오늘 생성 → 최신

        try:
            # ISO 날짜 파싱 (날짜만 또는 datetime 모두 허용)
            if "T" in source_date:
                dt = datetime.fromisoformat(source_date.split("T")[0])
            else:
                dt = datetime.strptime(source_date[:10], "%Y-%m-%d")

            age_days = (datetime.now() - dt).days
            age_days = max(0, age_days)   # 음수 방지

            recency  = math.exp(-RECENCY_DECAY * age_days)
            return round(recency, 4)
        except Exception:
            return 1.0   # 파싱 실패 → 중립값

    # ─── 로그 ─────────────────────────────────────────────────

    @staticmethod
    def _log_rejection(entity: Dict, user_role: str, score: float, reason: str):
        entry = {
            "time":      datetime.now().isoformat(),
            "level":     "WARN",
            "step":      "memory_trust.rejected",
            "entity":    entity.get("name", "?"),
            "role":      user_role,
            "score":     score,
            "threshold": TRUST_THRESHOLD,
            "reason":    reason[:200],
        }
        try:
            with open(SYSTEM_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass
        print(f"[TRUST] ⛔ write 거부: {entity.get('name','?')} score={score:.3f}")


# ─── 편의 함수 ───────────────────────────────────────────────

def verify_before_write(
    entity:      Dict,
    user_role:   str,
    wiki_dir:    Optional[str] = None,
    source_date: Optional[str] = None,
) -> Tuple[bool, str, float]:
    """
    단순 호출용 편의 함수.
    wiki_generator, server_llmwiki에서 직접 임포트하여 사용.
    """
    scorer = MemoryTrustScorer(wiki_dir=wiki_dir)
    return scorer.verify_before_write(entity, user_role, source_date)


# ─── 자가 테스트 ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Memory Trust Scoring 자가 테스트 ===\n")

    scorer = MemoryTrustScorer()

    test_cases = [
        # (entity, role, source_date, expect_pass)
        ({"name":"경제학","type":"concept","relations":[{"type":"IS_A","confidence":0.9}]},
         "admin", None, True),

        ({"name":"김철수","type":"person","relations":[{"type":"BELONGS_TO","confidence":0.9}]},
         "manager", None, True),

        ({"name":"테스트","type":"concept","relations":[{"type":"IS_A"}]},
         "external", None, False),   # external → trust=0.1 → score < 0.5

        ({"name":"오래된데이터","type":"concept","relations":[]},
         "admin", "2020-01-01", True),  # admin은 오래된 데이터도 trust가 높아 통과

        ({"name":"미등록relation","type":"concept",
          "relations":[{"type":"UNKNOWN_REL_XYZ","confidence":0.9}]},
         "employee", None, False),  # ontology 미등록 → consistency 낮아짐
    ]

    passed = 0
    for entity, role, date, expect in test_cases:
        score, breakdown = scorer.compute_score(entity, role, date)
        ok_actual = score >= TRUST_THRESHOLD
        match = ok_actual == expect
        passed += int(match)
        icon = "✅" if match else "❌"
        print(f"  {icon} [{role:8s}] {entity['name']:20s} "
              f"score={score:.3f} "
              f"trust={breakdown['trust']:.2f} "
              f"cons={breakdown['consistency']:.2f} "
              f"rec={breakdown['recency']:.2f} "
              f"→ {'PASS' if ok_actual else 'BLOCK'} (기대={'PASS' if expect else 'BLOCK'})")

    print(f"\n  결과: {passed}/{len(test_cases)} PASS")

    print("\n--- recency 감쇠 예시 ---")
    for days in [0, 30, 60, 100, 365]:
        from datetime import timedelta
        date_str = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        r = MemoryTrustScorer._compute_recency(date_str)
        print(f"  {days:4d}일 전: recency={r:.3f}")
