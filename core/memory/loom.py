"""
PROJECT JAMES - Memory Loom-lite (Phase 5)

역할: 검증된 결과만 조건부 저장.

절대 제약:
  ❌ raw 입력 저장 금지
  ❌ 미검증 추론 저장 금지
  ✅ dedup 필수
  ✅ conflict detection 필수
  ✅ write rate 제한 필수 (MAX_WRITES_PER_SESSION=3)

5개 Gate:
  Gate 1: confidence >= 0.75
  Gate 2: ontology_valid == True
  Gate 3: session write 횟수 < MAX_WRITES_PER_SESSION
  Gate 4: dedup (최근 MEMORY_DEDUP_WINDOW 내 동일 triple 없음)
  Gate 5: conflict detection (동일 entity+relation + 다른 tail → 양쪽 거부)
"""

import json
import hashlib
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Tuple

SYSTEM_LOG_PATH          = "james_system_log.jsonl"
MAX_WRITES_PER_SESSION   = 3       # 세션당 최대 저장 횟수
MEMORY_CONFIDENCE_TH     = 0.75    # 저장 최소 confidence
MEMORY_DEDUP_WINDOW      = 100     # 최근 N개 내 중복 검사
CONFLICT_CONFIDENCE_DIFF = 0.3     # confidence 차이 이 이상이면 conflict


def _log(step: str, detail: str, level: str = "INFO"):
    entry = {"time": datetime.now().isoformat(), "level": level,
             "step": f"memory_loom.{step}", "detail": detail[:300]}
    try:
        with open(SYSTEM_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # Phase 2: mirror to SQLite (see core/audit_bridge.py).
    try:
        from core.audit_bridge import mirror_system_event
        mirror_system_event(entry)
    except Exception:
        pass


def _triple_key(result: Dict) -> str:
    """
    (entity_id + relation_type + tail_id) 기반 dedup/conflict key.
    없는 필드는 text hash로 대체.
    """
    entity_id   = result.get("entity_id",    "")
    relation    = result.get("relation_type","")
    tail_id     = result.get("tail_id",      "")
    text        = result.get("text",         "")[:100]

    if entity_id and relation and tail_id:
        return f"{entity_id}::{relation}::{tail_id}"

    # fallback: text hash
    return hashlib.md5(text.encode()).hexdigest()


def _conflict_base_key(result: Dict) -> str:
    """충돌 판단용 (entity_id + relation_type만, tail_id 제외)"""
    return f"{result.get('entity_id','')}::{result.get('relation_type','')}"


class MemoryLoom:
    """
    Phase 5 Memory Loom-lite.
    세션 단위로 사용. 서버 재시작 시 카운터 초기화.
    """

    def __init__(self):
        self._session_write_count: int          = 0
        self._dedup_buffer:   deque             = deque(maxlen=MEMORY_DEDUP_WINDOW)
        self._conflict_index: Dict[str, Dict]   = {}   # base_key → result
        self._write_log:      List[Dict]         = []

    # ─── 메인 API ─────────────────────────────────────────────

    def store(self, result: Dict) -> Tuple[bool, str]:
        """
        5개 Gate 순서대로 통과 시만 저장.

        Returns:
            (ok, reason)
            ok=True → 저장 완료
            ok=False → 거부 사유 포함
        """
        # Gate 1: confidence
        confidence = float(result.get("confidence", 0.0))
        if confidence < MEMORY_CONFIDENCE_TH:
            reason = (f"Gate1 confidence 미달: {confidence:.3f} < {MEMORY_CONFIDENCE_TH}")
            _log("gate1_fail", reason, "WARN")
            return False, reason

        # Gate 2: ontology_valid
        if not result.get("ontology_valid", False):
            reason = "Gate2 ontology 검증 미통과"
            _log("gate2_fail", reason, "WARN")
            return False, reason

        # Gate 3: write rate 제한
        if self._session_write_count >= MAX_WRITES_PER_SESSION:
            reason = (f"Gate3 session write 한도 초과: "
                      f"{self._session_write_count}/{MAX_WRITES_PER_SESSION}")
            _log("gate3_limit", reason, "WARN")
            print(f"[LOOM] ⛔ MEMORY_WRITE_LIMIT_REACHED ({self._session_write_count}회)")
            return False, reason

        # Gate 4: dedup
        triple_key = _triple_key(result)
        if triple_key in self._dedup_buffer:
            reason = f"Gate4 중복: triple_key={triple_key[:40]}"
            _log("gate4_dedup", reason)
            return False, reason

        # Gate 5: conflict detection
        base_key = _conflict_base_key(result)
        if base_key and base_key in self._conflict_index:
            existing = self._conflict_index[base_key]
            existing_tail = existing.get("tail_id","")
            new_tail      = result.get("tail_id","")

            # 동일 entity+relation + 다른 tail → conflict
            if existing_tail and new_tail and existing_tail != new_tail:
                reason = (f"Gate5 conflict: entity+relation 동일, tail 불일치 "
                          f"({existing_tail} vs {new_tail})")
                _log("gate5_conflict", reason, "WARN")
                print(f"[LOOM] ⚠️ MEMORY_CONFLICT_DETECTED: {reason}")
                return False, reason

            # 동일 사실 + confidence 차이 > 0.3 → conflict
            existing_conf = float(existing.get("confidence", 0.0))
            if abs(confidence - existing_conf) > CONFLICT_CONFIDENCE_DIFF:
                reason = (f"Gate5 confidence 충돌: "
                          f"|{confidence:.3f} - {existing_conf:.3f}| > {CONFLICT_CONFIDENCE_DIFF}")
                _log("gate5_conf_conflict", reason, "WARN")
                print(f"[LOOM] ⚠️ MEMORY_CONFLICT_DETECTED: {reason}")
                return False, reason

        # ── 전부 통과 → 저장 ──────────────────────────────────
        self._write(result, triple_key, base_key)
        self._session_write_count += 1

        reason = (f"저장 완료 (session={self._session_write_count}/{MAX_WRITES_PER_SESSION} "
                  f"conf={confidence:.3f})")
        _log("store_ok", reason)
        print(f"[LOOM] ✅ {reason}")
        return True, reason

    def _write(self, result: Dict, triple_key: str, base_key: str):
        """실제 저장 (메모리 + 인덱스)"""
        self._dedup_buffer.append(triple_key)
        if base_key:
            self._conflict_index[base_key] = result
        self._write_log.append({
            **result,
            "_stored_at": datetime.now().isoformat(),
            "_session_count": self._session_write_count + 1,
        })

    # ─── 상태 조회 ────────────────────────────────────────────

    def get_stats(self) -> Dict:
        return {
            "session_writes":      self._session_write_count,
            "max_writes":          MAX_WRITES_PER_SESSION,
            "remaining_writes":    MAX_WRITES_PER_SESSION - self._session_write_count,
            "dedup_buffer_size":   len(self._dedup_buffer),
            "conflict_index_size": len(self._conflict_index),
            "write_log_count":     len(self._write_log),
        }

    def get_write_log(self) -> List[Dict]:
        return list(self._write_log)

    def reset_session(self):
        """테스트용 세션 리셋 (운영에서는 서버 재시작으로 자동 초기화)"""
        self._session_write_count = 0
        _log("session_reset", "세션 카운터 리셋")


# ─── 글로벌 인스턴스 (서버 레벨 싱글톤) ─────────────────────

_loom_instance: Optional[MemoryLoom] = None

def get_loom() -> MemoryLoom:
    global _loom_instance
    if _loom_instance is None:
        _loom_instance = MemoryLoom()
    return _loom_instance


def store_result(result: Dict) -> Tuple[bool, str]:
    """편의 함수 — reasoning_engine.py에서 호출"""
    return get_loom().store(result)


# ─── 자가 테스트 ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Memory Loom-lite 자가 테스트 (5개 Gate) ===\n")

    loom = MemoryLoom()
    passed = 0

    def chk(name, ok, detail=""):
        global passed
        print(f"  {'✅' if ok else '❌'} {name}" + (f" → {detail}" if detail else ""))
        return ok

    # Gate 1: confidence 미달
    ok, r = loom.store({"confidence":0.5,"ontology_valid":True,
                         "entity_id":"e1","relation_type":"IS_A","tail_id":"t1"})
    chk("Gate1 confidence 미달", not ok, r[:60])

    # Gate 2: ontology_valid 미통과
    ok, r = loom.store({"confidence":0.8,"ontology_valid":False,
                         "entity_id":"e1","relation_type":"IS_A","tail_id":"t1"})
    chk("Gate2 ontology 미통과", not ok, r[:60])

    # 정상 저장 1
    ok, r = loom.store({"confidence":0.9,"ontology_valid":True,
                         "entity_id":"e1","relation_type":"IS_A","tail_id":"t1","text":"A"})
    chk("정상 저장 1", ok, r[:60])

    # 정상 저장 2
    ok, r = loom.store({"confidence":0.85,"ontology_valid":True,
                         "entity_id":"e2","relation_type":"STUDIES","tail_id":"t2","text":"B"})
    chk("정상 저장 2", ok, r[:60])

    # 정상 저장 3 (마지막)
    ok, r = loom.store({"confidence":0.8,"ontology_valid":True,
                         "entity_id":"e3","relation_type":"BELONGS_TO","tail_id":"t3","text":"C"})
    chk("정상 저장 3 (마지막)", ok, r[:60])

    # Gate 3: write rate 초과
    ok, r = loom.store({"confidence":0.9,"ontology_valid":True,
                         "entity_id":"e4","relation_type":"IS_A","tail_id":"t4","text":"D"})
    chk("Gate3 write rate 초과", not ok, r[:60])

    # Gate 4: dedup (e1+IS_A+t1 재시도)
    loom.reset_session()
    ok1, _ = loom.store({"confidence":0.9,"ontology_valid":True,
                           "entity_id":"e5","relation_type":"IS_A","tail_id":"t5","text":"E"})
    ok2, r = loom.store({"confidence":0.9,"ontology_valid":True,
                           "entity_id":"e5","relation_type":"IS_A","tail_id":"t5","text":"E"})
    chk("Gate4 dedup (동일 triple)", not ok2, r[:60])

    # Gate 5: conflict (동일 entity+relation, 다른 tail)
    ok3, r = loom.store({"confidence":0.9,"ontology_valid":True,
                           "entity_id":"e6","relation_type":"STUDIES","tail_id":"tail_A","text":"F"})
    ok4, r = loom.store({"confidence":0.9,"ontology_valid":True,
                           "entity_id":"e6","relation_type":"STUDIES","tail_id":"tail_B","text":"G"})
    chk("Gate5 conflict (다른 tail)", not ok4, r[:60])

    # Gate 5: confidence 충돌
    loom.reset_session()
    loom.store({"confidence":0.95,"ontology_valid":True,
                "entity_id":"e7","relation_type":"IS_A","tail_id":"t7","text":"H"})
    ok5, r = loom.store({"confidence":0.6,"ontology_valid":True,
                          "entity_id":"e7","relation_type":"IS_A","tail_id":"t7","text":"H2"})
    chk("Gate5 confidence 충돌 (diff>0.3)", not ok5, r[:60])

    print(f"\n  통계: {loom.get_stats()}")
    print("\n✅ Memory Loom 자가 테스트 완료")
