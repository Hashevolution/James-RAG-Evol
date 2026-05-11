"""W7-A — data lifecycle backbone.

Tracks every uploaded file as a first-class ``artifact`` row and links
it to the wiki entities derived from it. Before this module, the
relationship "I uploaded this PDF — which entities came from it?" was
implicit (a UUID prefix in the filename). Now it is queryable.

Where this lives
----------------
- ``data_artifacts`` and ``wiki_links`` rows live in a new SQLite DB
  ``james_data.db`` (separate from ``james_users.db``). Auth data and
  user-generated data have different retention / backup profiles, so
  splitting them now avoids painful surgery later when one needs to
  rotate or restore independently.
- Path resolution: ``BASE_DIR / james_data.db``, with the same
  cwd-fallback as ``core/auth.py``.

Why DB-side own/all separation
------------------------------
``list_artifacts(username=...)`` filters at the SQL level, not after
fetching. An employee querying their own artifacts never sees another
user's rows in memory — there's no in-Python ACL bug surface.

API
---
- ``register_artifact(origin_path, origin_name, origin_size, uploaded_by)
  -> artifact_id`` — call from /upload/ on first successful save.
- ``update_status(artifact_id, status)`` — uploaded → extracted →
  indexed → (failed). Used by /upload/'s processing pipeline.
- ``link_entity(artifact_id, entity_id)`` — wiki_generator records
  which entity it derived from which artifact.
- ``get_artifact(artifact_id, requester_username=None) -> Optional[Dict]``
  — full row + linked entity_ids. If ``requester_username`` is given
  AND differs from ``uploaded_by``, returns None (own-only access).
- ``list_artifacts(username=None, status=None, q=None, limit, offset)``
  — username=None ⇒ admin view (all rows). username=str ⇒ own rows
  only. q substring on origin_name.
- ``count_artifacts(...)``: same filters, COUNT(*) only.
- ``backfill_from_uploads_dir(uploads_dir)`` — first-boot scan that
  inserts a row for every file already on disk with
  ``uploaded_by="legacy"`` and ``status="indexed"`` (the file is
  already in the corpus; the row just makes it queryable).
"""
from __future__ import annotations

import os
import sqlite3
import time
import uuid
from typing import Optional, List, Dict


try:
    from config import BASE_DIR
    _DB_PATH = os.path.join(BASE_DIR, "james_data.db")
except ImportError:
    _DB_PATH = "james_data.db"


ALLOWED_STATUSES = {"uploaded", "extracted", "indexed", "failed"}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    """Create tables + indexes if missing. Idempotent — called on import.

    Indexes match the dominant query shapes:
      - listing by uploader (employee's own files)
      - filtering by status (operator wants only 'failed')
      - newest-first sort by uploaded_at
    """
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS data_artifacts (
                artifact_id   TEXT PRIMARY KEY,
                origin_path   TEXT NOT NULL,
                origin_name   TEXT NOT NULL,
                origin_size   INTEGER,
                uploaded_at   INTEGER NOT NULL,
                uploaded_by   TEXT,
                status        TEXT NOT NULL DEFAULT 'uploaded'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wiki_links (
                artifact_id  TEXT NOT NULL,
                entity_id    TEXT NOT NULL,
                linked_at    INTEGER NOT NULL,
                PRIMARY KEY (artifact_id, entity_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_uploader "
                     "ON data_artifacts (uploaded_by, uploaded_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_status "
                     "ON data_artifacts (status, uploaded_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wiki_links_entity "
                     "ON wiki_links (entity_id)")
        conn.commit()
    finally:
        conn.close()


_init_db()


def register_artifact(origin_path: str, origin_name: str,
                      origin_size: Optional[int] = None,
                      uploaded_by: Optional[str] = None,
                      status: str = "uploaded") -> str:
    """Insert a new artifact row and return the generated id.

    ``origin_path`` is the absolute or relative path stored at /upload/
    time (e.g. ``uploads/<uuid>_<name>``). ``origin_name`` is the
    original filename without the UUID prefix. The status default
    matches the lifecycle entry point.
    """
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid status: {status!r}")
    artifact_id = uuid.uuid4().hex
    now = int(time.time())
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO data_artifacts "
            "(artifact_id, origin_path, origin_name, origin_size, "
            "uploaded_at, uploaded_by, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (artifact_id, origin_path, origin_name, origin_size,
             now, uploaded_by, status),
        )
        conn.commit()
        return artifact_id
    finally:
        conn.close()


def update_status(artifact_id: str, status: str) -> bool:
    """Move the artifact through the lifecycle. Returns False if the
    artifact id is unknown — caller can decide whether that's an error
    or a no-op for backfilled rows."""
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid status: {status!r}")
    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE data_artifacts SET status = ? WHERE artifact_id = ?",
            (status, artifact_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def link_entity(artifact_id: str, entity_id: str) -> bool:
    """Record that ``entity_id`` was derived from ``artifact_id``.

    Idempotent: re-linking the same pair is a no-op (PK conflict
    swallowed). Returns True if a new row was created.
    """
    now = int(time.time())
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO wiki_links "
            "(artifact_id, entity_id, linked_at) VALUES (?, ?, ?)",
            (artifact_id, entity_id, now),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_artifact(artifact_id: str,
                 requester_username: Optional[str] = None
                 ) -> Optional[Dict]:
    """Return one row + ``entities`` list of linked entity_ids.

    Ownership check: if ``requester_username`` is supplied, the call
    only returns the row when ``uploaded_by == requester_username``.
    Pass ``None`` for the admin path (see is_admin in the endpoint).
    """
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM data_artifacts WHERE artifact_id = ?",
            (artifact_id,),
        ).fetchone()
        if row is None:
            return None
        if requester_username is not None and row["uploaded_by"] != requester_username:
            return None
        entities = [r["entity_id"] for r in conn.execute(
            "SELECT entity_id FROM wiki_links WHERE artifact_id = ? "
            "ORDER BY linked_at ASC",
            (artifact_id,),
        ).fetchall()]
        out = dict(row)
        out["entities"] = entities
        return out
    finally:
        conn.close()


def list_artifacts(username: Optional[str] = None,
                   status: Optional[str] = None,
                   q: Optional[str] = None,
                   limit: int = 50, offset: int = 0) -> List[Dict]:
    """Filtered list, newest first.

    - ``username=None`` ⇒ admin view (every row).
    - ``username=str`` ⇒ that user's rows only (SQL filter, not
      post-filter — prevents leak through pagination math).
    - ``status`` ⇒ exact match (uploaded/extracted/indexed/failed).
    - ``q`` ⇒ case-insensitive substring on origin_name.

    Each row also carries ``entity_count`` (cheap COUNT join in SQL)
    so the UI can render "PDF → 12 entities" without a per-row fetch.
    """
    where: list = []
    params: list = []
    if username is not None:
        where.append("a.uploaded_by = ?")
        params.append(username)
    if status:
        if status not in ALLOWED_STATUSES:
            return []
        where.append("a.status = ?")
        params.append(status)
    if q:
        where.append("LOWER(a.origin_name) LIKE ?")
        params.append(f"%{q.lower()}%")
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    sql = (
        "SELECT a.*, "
        "  (SELECT COUNT(*) FROM wiki_links w WHERE w.artifact_id = a.artifact_id) "
        "    AS entity_count "
        "FROM data_artifacts a"
        + where_sql +
        " ORDER BY a.uploaded_at DESC LIMIT ? OFFSET ?"
    )
    params.extend([max(1, min(int(limit), 500)), max(0, int(offset))])

    conn = _get_conn()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def count_artifacts(username: Optional[str] = None,
                    status: Optional[str] = None,
                    q: Optional[str] = None) -> int:
    """Match the filter shape of ``list_artifacts``; SQL COUNT only."""
    where: list = []
    params: list = []
    if username is not None:
        where.append("uploaded_by = ?")
        params.append(username)
    if status:
        if status not in ALLOWED_STATUSES:
            return 0
        where.append("status = ?")
        params.append(status)
    if q:
        where.append("LOWER(origin_name) LIKE ?")
        params.append(f"%{q.lower()}%")
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    conn = _get_conn()
    try:
        return int(conn.execute(
            f"SELECT COUNT(*) AS c FROM data_artifacts{where_sql}",
            params,
        ).fetchone()["c"])
    finally:
        conn.close()


def backfill_from_uploads_dir(uploads_dir: str) -> int:
    """One-time scan of ``uploads/`` to register pre-W7-A files.

    Idempotent: every call inserts only files that don't already have a
    row matching their origin_path. ``uploaded_by`` is set to ``legacy``
    and ``status`` to ``indexed`` (the file is already in the corpus
    via prior /upload/ calls; the row only makes it queryable).

    Returns the number of new rows inserted. 0 on subsequent runs.

    The filename convention from /upload/ is ``<uuid>_<original-name>``
    (see server_llmwiki.upload). We split on the first ``_`` to
    recover origin_name; if no underscore is found, the full filename
    becomes origin_name and origin_path retains the leading bare token.
    """
    if not os.path.isdir(uploads_dir):
        return 0

    conn = _get_conn()
    try:
        existing = {r["origin_path"] for r in conn.execute(
            "SELECT origin_path FROM data_artifacts WHERE uploaded_by = 'legacy'"
        ).fetchall()}

        inserted = 0
        now = int(time.time())
        for fname in sorted(os.listdir(uploads_dir)):
            full = os.path.join(uploads_dir, fname)
            if not os.path.isfile(full):
                continue
            rel = os.path.join("uploads", fname).replace("\\", "/")
            if rel in existing:
                continue
            if "_" in fname:
                _uuid_part, _, origin_name = fname.partition("_")
            else:
                origin_name = fname
            try:
                size = os.path.getsize(full)
            except OSError:
                size = None
            conn.execute(
                "INSERT INTO data_artifacts "
                "(artifact_id, origin_path, origin_name, origin_size, "
                "uploaded_at, uploaded_by, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, rel, origin_name, size,
                 now, "legacy", "indexed"),
            )
            inserted += 1
        conn.commit()
        return inserted
    finally:
        conn.close()
