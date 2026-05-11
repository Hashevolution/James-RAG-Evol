"""W4-Q1 — per-role feature capability registry.

Before this module, every endpoint-level role check was hardcoded
(`_require_admin` calls scattered across server_llmwiki.py, plus
ad-hoc role comparisons inside handlers). Changing "manager can also
upload" required a code edit + deploy.

This module turns those hardcoded checks into a **catalog of named
features** plus a small **override table**. Admins flip checkboxes in
the UI; the runtime consults the same catalog through
``PolicyEngine.can_use_feature(role, feature_id)``.

Surface
-------
- ``FEATURES`` — immutable catalog (~15 entries). Adding a feature is
  a code change on purpose: the operator UI exposes only what code
  knows about, so a typo can't silently authorize anything.
- ``get_override(feature_id, role) -> Optional[bool]`` — None = no
  override, fall through to the feature's default_allowed set.
- ``set_override(feature_id, role, allowed)`` — UPSERT one row.
- ``clear_override(feature_id, role)`` — remove one row; the
  feature falls back to its default.
- ``clear_all_overrides_for(feature_id)`` — reset one feature
  (used by the UI's "기본값 복원" action).
- ``list_effective(roles)`` — catalog + current effective matrix
  for the admin UI.

Persistence
-----------
``feature_overrides`` table lives in the same SQLite DB as the users
table (``james_users.db``). One row per (feature_id, role) that
differs from the default. Empty table ⇒ the entire system runs on
defaults, which is the pre-Q1 baseline.

Wiring
------
Q1 (this PR) sets up storage + ``can_use_feature`` only. Q2 wires
``_require_feature("upload.file", role)`` into the existing
endpoints, and Q3 ships the admin matrix UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, FrozenSet, List

from core.auth import _get_conn, ALLOWED_ROLES


@dataclass(frozen=True)
class Feature:
    """One atomic capability the system knows how to gate.

    Attributes:
      id: canonical dotted id, e.g. "upload.file". Used in the
          ``feature_overrides`` table and the ``applied_rule`` field
          of every PolicyEngine decision for this feature.
      description: short Korean label shown in the admin UI.
      default_allowed: roles that have this feature out of the box.
          A role NOT in this set is denied unless an admin adds an
          override row. Stored as frozenset to prevent accidental
          mutation.
    """
    id:               str
    description:      str
    default_allowed:  FrozenSet[str]


def _f(fid: str, desc: str, allowed_roles: str) -> Feature:
    """Compact constructor — `allowed_roles` is a comma-separated
    list ('admin,manager,employee') so the catalog stays readable."""
    roles = frozenset(r.strip() for r in allowed_roles.split(",") if r.strip())
    # Defensive check at module load: every default role must exist in
    # ALLOWED_ROLES. A typo here would silently produce a feature
    # nobody can ever use.
    unknown = roles - set(ALLOWED_ROLES)
    if unknown:
        raise RuntimeError(
            f"feature_registry: feature {fid!r} has unknown role(s) "
            f"in default_allowed: {sorted(unknown)}"
        )
    return Feature(id=fid, description=desc, default_allowed=roles)


# Canonical feature catalog. Order matters only for the admin UI
# (the grid renders top-to-bottom in this order).
FEATURES: Dict[str, Feature] = {
    # ── query / retrieval ───────────────────────────────────────
    "query.basic": _f(
        "query.basic",
        "자메스 질의 (/query/)",
        "admin,manager,employee,external",
    ),
    "query.web_search": _f(
        "query.web_search",
        "웹 검색 fallback",
        "admin,manager",
    ),
    # ── upload / ingestion ──────────────────────────────────────
    "upload.file": _f(
        "upload.file",
        "파일 업로드 (PDF/문서/이미지)",
        "admin,manager",
    ),
    "upload.video": _f(
        "upload.video",
        "영상 업로드 (현재 거부, video-asr 대비 슬롯)",
        "admin",
    ),
    # ── graph ──────────────────────────────────────────────────
    "graph.view": _f(
        "graph.view",
        "그래프 페이지 진입",
        "admin,manager,employee",
    ),
    "graph.explore_neighbor": _f(
        "graph.explore_neighbor",
        "노드 클릭 이웃 탐색",
        "admin,manager",
    ),
    # ── self-service auth ──────────────────────────────────────
    "password.change_self": _f(
        "password.change_self",
        "본인 비밀번호 변경",
        "admin,manager,employee,external",
    ),
    "api_keys.issue_self": _f(
        "api_keys.issue_self",
        "본인 API 키 발급/조회/회수",
        "admin,manager,employee",
    ),
    # ── admin surfaces ─────────────────────────────────────────
    "admin.users": _f(
        "admin.users",
        "사용자 관리 (승인/거부/비활성화)",
        "admin",
    ),
    "admin.audit_log": _f(
        "admin.audit_log",
        "감사 로그 조회",
        "admin",
    ),
    "admin.evolution": _f(
        "admin.evolution",
        "self-evolution 제어 (제안/승인/롤백)",
        "admin",
    ),
    "admin.policy_matrix": _f(
        "admin.policy_matrix",
        "권한 매트릭스 관리 (이 화면 자체)",
        "admin",
    ),
    # Added in W4-Q2-b — features that cover the remaining admin
    # endpoints. All admin-only by default; admins can grant subsets
    # to manager (e.g. "manager can read metrics but not change LLM
    # selection") via the matrix UI in W4-Q3.
    "admin.settings": _f(
        "admin.settings",
        "시스템 설정 (LLM 모델 / persona / 웹 검색 / model selection)",
        "admin",
    ),
    "admin.data": _f(
        "admin.data",
        "데이터 인스펙션 (entity / memory / files / 업로드 이력)",
        "admin",
    ),
    "admin.metrics": _f(
        "admin.metrics",
        "메트릭·대시보드·trace 조회",
        "admin",
    ),
    "admin.character": _f(
        "admin.character",
        "성향(character) 조회·설정",
        "admin",
    ),
    "admin.knowledge": _f(
        "admin.knowledge",
        "능력 성장(knowledge) 조회·학습",
        "admin",
    ),
    "admin.tools": _f(
        "admin.tools",
        "관리자 도구 (화면 캡처 분석 등)",
        "admin",
    ),
    # ── workspace (W8 후속, 카탈로그 슬롯만 미리 등록) ─────────
    "workspace.run_jobs": _f(
        "workspace.run_jobs",
        "(W8) 워크스페이스 job 실행",
        "admin,manager",
    ),
    "workspace.schedule": _f(
        "workspace.schedule",
        "(W8) 워크스페이스 job 예약 (cron)",
        "admin",
    ),
}


# ───────────────────────────────────────────────────────────────
# Storage helpers — ``feature_overrides`` table
# ───────────────────────────────────────────────────────────────

def _init_feature_overrides_table() -> None:
    """Create the override table if missing. Idempotent — called on
    module import so a fresh deployment has the schema before the
    first admin write."""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feature_overrides (
                feature_id  TEXT NOT NULL,
                role        TEXT NOT NULL,
                allowed     INTEGER NOT NULL,
                updated_at  INTEGER NOT NULL,
                updated_by  TEXT,
                PRIMARY KEY (feature_id, role)
            )
        """)
        conn.commit()
    finally:
        conn.close()


_init_feature_overrides_table()


def get_override(feature_id: str, role: str) -> Optional[bool]:
    """Return ``True``/``False`` if an override exists for this pair,
    else ``None`` (caller falls back to default).

    A missing ``feature_overrides`` table is treated as "no overrides".
    The table is created on module import for the live DB, but tests
    that monkey-patch ``_DB_PATH`` to a fresh file would otherwise
    crash with OperationalError; we'd rather fall through to defaults
    in that case than fail-closed on a runtime exception.
    """
    import sqlite3 as _sqlite3
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT allowed FROM feature_overrides "
            "WHERE feature_id = ? AND role = ?",
            (feature_id, role),
        ).fetchone()
        if row is None:
            return None
        return bool(row["allowed"])
    except _sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def set_override(feature_id: str, role: str, allowed: bool,
                 updated_by: Optional[str] = None) -> bool:
    """Upsert one override. Returns False if the feature_id is
    unknown or the role is not in ``ALLOWED_ROLES`` — admins should
    not be able to author rows that no runtime check will ever
    consult.
    """
    if feature_id not in FEATURES:
        return False
    if role not in ALLOWED_ROLES:
        return False
    import time as _time
    now = int(_time.time())
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO feature_overrides "
            "(feature_id, role, allowed, updated_at, updated_by) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(feature_id, role) DO UPDATE SET "
            "allowed = excluded.allowed, "
            "updated_at = excluded.updated_at, "
            "updated_by = excluded.updated_by",
            (feature_id, role, 1 if allowed else 0, now, updated_by),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def clear_override(feature_id: str, role: str) -> bool:
    """Remove a single override row. Returns True if a row was
    deleted (the feature×role pair will now fall through to the
    default)."""
    conn = _get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM feature_overrides "
            "WHERE feature_id = ? AND role = ?",
            (feature_id, role),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def clear_all_overrides_for(feature_id: str) -> int:
    """Reset one entire feature — all role overrides for it gone.
    Returns the number of rows deleted. Used by the admin UI's
    "기본값 복원" action."""
    conn = _get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM feature_overrides WHERE feature_id = ?",
            (feature_id,),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def list_effective(roles: Optional[List[str]] = None) -> List[Dict]:
    """Return the catalog with the *currently effective* allowed set
    for each feature × role. Shape per row:

      {
        "id": "upload.file",
        "description": "파일 업로드 (PDF/문서/이미지)",
        "default_allowed": ["admin", "manager"],
        "effective": {
          "admin":    {"allowed": True,  "source": "default"},
          "manager":  {"allowed": True,  "source": "default"},
          "employee": {"allowed": False, "source": "default"},
          "external": {"allowed": True,  "source": "override"},  # if any
        },
      }

    Used by the admin matrix UI — single round-trip captures both the
    catalog (so the UI can render rows in code order) and the live
    state (so checkboxes reflect any overrides).
    """
    roles = roles or list(ALLOWED_ROLES)

    # One scan of feature_overrides; building a {(fid,role): allowed}
    # dict keeps the per-feature lookup O(1). Missing table → empty
    # overrides (defaults apply across the board).
    import sqlite3 as _sqlite3
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT feature_id, role, allowed FROM feature_overrides"
        ).fetchall()
    except _sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    overrides = {(r["feature_id"], r["role"]): bool(r["allowed"]) for r in rows}

    out: List[Dict] = []
    for fid, feat in FEATURES.items():
        effective = {}
        for role in roles:
            ov = overrides.get((fid, role))
            if ov is None:
                effective[role] = {
                    "allowed": role in feat.default_allowed,
                    "source":  "default",
                }
            else:
                effective[role] = {"allowed": ov, "source": "override"}
        out.append({
            "id":               fid,
            "description":      feat.description,
            "default_allowed":  sorted(feat.default_allowed),
            "effective":        effective,
        })
    return out
