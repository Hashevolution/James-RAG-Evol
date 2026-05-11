"""W8-A — workspace job execution backbone.

Three generic handlers (Excel build / document combine / entity export)
plus the registry + execution layer that runs them synchronously and
records every step in the new ``jobs`` table.

Why generic, why sync, why now
------------------------------
- **Generic** — Rule #1 (no domain features) means we ship the
  Excel/doc/export primitives that any domain pack can later compose
  into a vertical workflow. Job ids in this PR are the three nouns,
  not "legal-review" / "food-spec".
- **Sync execution** — these handlers complete in seconds against
  typical wiki corpora. Background workers + a real queue are W8-A2
  territory once the surface stabilizes. The /jobs/run endpoint blocks
  until the handler returns, so the UI gets a deterministic 200 with
  the output path or a 500 with the traceback.
- **Now, before W8-B** — the workspace UI in W7-B already renders the
  artifact rows; W8-A lights up the "trigger a job against artifacts"
  surface; W8-B adds the UI trigger form. Splitting that way keeps
  this PR pure-backend and reviewable on its own.

Schema (added to james_data.db)
-------------------------------
``jobs``:
  job_id        TEXT PRIMARY KEY  -- uuid hex
  job_type      TEXT NOT NULL     -- excel_build | doc_combine | entity_export
  status        TEXT NOT NULL     -- pending | running | done | failed
  input_refs    TEXT NOT NULL     -- JSON list (artifact_ids or entity_ids)
  output_path   TEXT              -- relative path under workspace/results/
  owner         TEXT              -- JWT subject at job creation
  created_at    INTEGER NOT NULL
  finished_at   INTEGER           -- NULL until status moves out of pending/running
  error         TEXT              -- traceback / message on failure
  options       TEXT              -- JSON dict, handler-specific

No ``schedule_cron`` column yet — W8-A2 adds the scheduler. Including
it now would make every row in this PR have a NULL we don't read.

Surface
-------
- ``register_job(job_type, input_refs, owner, options=None) -> job_id``
  Validates the job_type against the handler registry, inserts a
  pending row. Returns the job_id.
- ``execute_job(job_id) -> Dict`` — runs the handler synchronously,
  updates the row to done/failed, returns the final row dict.
- ``list_jobs(owner=None, status=None, limit, offset)`` — same
  own/all pattern as data_artifacts.
- ``get_job(job_id, requester_username=None)`` — None for cross-owner.

Handler contract
----------------
``JobHandler.run(input_refs: List[str], output_dir: str,
                  options: Optional[Dict]) -> str``
Returns the relative path (under workspace/results/<job_id>/) of the
produced file. The runner sets that as ``output_path`` in the row.

Adding a new handler is one entry in ``HANDLERS`` plus the run()
implementation — Rule #1 keeps the surface small until v1.0 plugin
packs land.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import traceback
import uuid
from typing import Optional, List, Dict, Callable


try:
    from config import BASE_DIR
    _DB_PATH    = os.path.join(BASE_DIR, "james_data.db")
    _RESULT_DIR = os.path.join(BASE_DIR, "workspace", "results")
except ImportError:
    _DB_PATH    = "james_data.db"
    _RESULT_DIR = os.path.join("workspace", "results")


ALLOWED_STATUSES = {"pending", "running", "done", "failed"}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    """Idempotent — create ``jobs`` table + indexes.

    W8-D (2026-05-11) added two optional columns:
      schedule_cron — NULL for one-shot jobs (W8-A behaviour). When
                      set, the scheduler re-executes the row whenever
                      next_run_at <= now.
      next_run_at   — unix epoch; updated by the scheduler after each
                      successful tick.

    Existing DBs picked up via ``ALTER TABLE ... ADD COLUMN`` guarded
    by a column-existence check; sqlite has no IF NOT EXISTS on
    column adds.
    """
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id        TEXT PRIMARY KEY,
                job_type      TEXT NOT NULL,
                status        TEXT NOT NULL,
                input_refs    TEXT NOT NULL,
                output_path   TEXT,
                owner         TEXT,
                created_at    INTEGER NOT NULL,
                finished_at   INTEGER,
                error         TEXT,
                options       TEXT,
                schedule_cron TEXT,
                next_run_at   INTEGER
            )
        """)
        # ALTER for pre-W8-D DBs.
        existing_cols = {r["name"] for r in conn.execute(
            "PRAGMA table_info(jobs)"
        ).fetchall()}
        if "schedule_cron" not in existing_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN schedule_cron TEXT")
        if "next_run_at" not in existing_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN next_run_at INTEGER")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_owner "
                     "ON jobs (owner, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status "
                     "ON jobs (status, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_next_run "
                     "ON jobs (next_run_at) "
                     "WHERE schedule_cron IS NOT NULL")
        conn.commit()
    finally:
        conn.close()


_init_db()


# ───────────────────────────────────────────────────────────────
# Handlers
# ───────────────────────────────────────────────────────────────

def _excel_build(input_refs: List[str], output_dir: str,
                 options: Optional[Dict] = None) -> str:
    """Render a list of entity_ids (or artifact metadata) as a .xlsx.

    Schema of the rendered sheet:
      | entity_id | name | type | sensitivity | summary |

    Rows are looked up via ``rag_engine.wiki_generator.entity_id_index``
    so the handler doesn't need its own wiki crawler. Missing ids are
    silently skipped (recorded in a trailing "missing" sheet so the
    operator can see them).

    options:
      - ``filename`` (str) — output filename without extension.
        Defaults to ``entities-<timestamp>``.
    """
    from openpyxl import Workbook
    options = options or {}

    wb = Workbook()
    ws = wb.active
    ws.title = "entities"
    ws.append(["entity_id", "name", "type", "sensitivity", "summary"])

    missing: list = []
    # Look up the live engine through the FastAPI app's module so we
    # don't double-construct one. Any attribute miss here (e.g. tests
    # without a real engine wired up) falls through to "missing all"
    # rather than crashing the handler.
    import server_llmwiki as srv
    wiki = getattr(getattr(srv, "rag_engine", None), "wiki_generator", None)
    index = getattr(wiki, "entity_id_index", {}) or {}

    from pathlib import Path
    for eid in input_refs:
        path = index.get(eid) if index else None
        if not path or not wiki:
            missing.append(eid)
            continue
        try:
            fm = wiki._read_frontmatter(Path(path))
        except Exception:
            missing.append(eid)
            continue
        if not fm:
            missing.append(eid)
            continue
        ws.append([
            eid,
            fm.get("name", ""),
            fm.get("entity_type", fm.get("type", "")),
            fm.get("sensitivity", "internal"),
            (fm.get("summary", "") or "")[:240],
        ])

    if missing:
        ws2 = wb.create_sheet("missing")
        ws2.append(["entity_id"])
        for eid in missing:
            ws2.append([eid])

    fname = (options.get("filename") or f"entities-{int(time.time())}") + ".xlsx"
    full = os.path.join(output_dir, fname)
    wb.save(full)
    return fname


def _doc_combine(input_refs: List[str], output_dir: str,
                 options: Optional[Dict] = None) -> str:
    """Concatenate the markdown bodies of selected entities into one
    .md file. Each entity becomes an H1 section."""
    options = options or {}
    parts: list = []
    import server_llmwiki as srv
    wiki = getattr(getattr(srv, "rag_engine", None), "wiki_generator", None)
    index = getattr(wiki, "entity_id_index", {}) or {}

    from pathlib import Path
    for eid in input_refs:
        path = index.get(eid) if index else None
        if not path:
            parts.append(f"# {eid}\n\n_(missing)_\n")
            continue
        try:
            text = Path(path).read_text(encoding="utf-8")
        except Exception as e:
            parts.append(f"# {eid}\n\n_(read error: {e})_\n")
            continue
        parts.append(text.rstrip() + "\n\n---\n")

    fname = (options.get("filename") or f"combined-{int(time.time())}") + ".md"
    full = os.path.join(output_dir, fname)
    with open(full, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return fname


def _entity_export(input_refs: List[str], output_dir: str,
                   options: Optional[Dict] = None) -> str:
    """Export entities of selected categories (or all) as a single
    JSON file. ``input_refs`` here holds category names; empty list
    means "all categories"."""
    options = options or {}

    import server_llmwiki as srv
    wiki = getattr(getattr(srv, "rag_engine", None), "wiki_generator", None)
    index = getattr(wiki, "entity_id_index", {}) or {}

    cats = {c.strip().lower() for c in input_refs if c.strip()}
    out: list = []
    if wiki:
        from pathlib import Path
        for eid, path in index.items():
            try:
                fm = wiki._read_frontmatter(Path(path))
            except Exception:
                continue
            if not fm:
                continue
            etype = (fm.get("entity_type") or fm.get("type") or "").lower()
            if cats and etype not in cats:
                continue
            out.append({
                "entity_id":   eid,
                "name":        fm.get("name", ""),
                "entity_type": etype,
                "sensitivity": fm.get("sensitivity", "internal"),
                "frontmatter": fm,
            })

    fname = (options.get("filename") or f"export-{int(time.time())}") + ".json"
    full = os.path.join(output_dir, fname)
    with open(full, "w", encoding="utf-8") as f:
        json.dump({"count": len(out), "categories_filter": sorted(cats),
                   "items": out}, f, ensure_ascii=False, indent=2)
    return fname


HANDLERS: Dict[str, Callable[..., str]] = {
    "excel_build":   _excel_build,
    "doc_combine":   _doc_combine,
    "entity_export": _entity_export,
}


# ───────────────────────────────────────────────────────────────
# Public job-management API
# ───────────────────────────────────────────────────────────────

def register_job(job_type: str, input_refs: List[str],
                 owner: Optional[str] = None,
                 options: Optional[Dict] = None,
                 schedule_cron: Optional[str] = None,
                 next_run_at: Optional[int] = None) -> str:
    """Insert a pending row. Caller then calls ``execute_job(id)``.

    For one-shot jobs (W8-A), leave ``schedule_cron`` and
    ``next_run_at`` as None. For scheduled jobs (W8-D), pass the
    cron-style spec + the computed next-run timestamp; the scheduler
    re-fires the row whenever next_run_at <= now.
    """
    if job_type not in HANDLERS:
        raise ValueError(f"unknown job_type: {job_type!r}")
    if not isinstance(input_refs, list):
        raise ValueError("input_refs must be a list of strings")
    job_id = uuid.uuid4().hex
    now = int(time.time())
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO jobs "
            "(job_id, job_type, status, input_refs, owner, created_at, "
            "options, schedule_cron, next_run_at) "
            "VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?)",
            (job_id, job_type, json.dumps(input_refs),
             owner, now,
             json.dumps(options) if options else None,
             schedule_cron, next_run_at),
        )
        conn.commit()
        return job_id
    finally:
        conn.close()


def _set_status(job_id: str, status: str,
                output_path: Optional[str] = None,
                error: Optional[str] = None) -> None:
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid status: {status!r}")
    finished = int(time.time()) if status in ("done", "failed") else None
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE jobs SET status = ?, output_path = ?, "
            "finished_at = ?, error = ? "
            "WHERE job_id = ?",
            (status, output_path, finished, error, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def execute_job(job_id: str) -> Dict:
    """Synchronously run the handler. Returns the final row dict.

    Sequence:
      1. Re-read the row to pull job_type / input_refs / options.
      2. Move status → 'running' (so a parallel poller can see the
         transition even on sync calls — useful for tests).
      3. Ensure workspace/results/<job_id>/ exists.
      4. Call the handler; on success → 'done' + output_path,
         on failure → 'failed' + traceback string in ``error``.
    """
    row = get_job(job_id)
    if row is None:
        raise ValueError(f"unknown job_id: {job_id!r}")
    handler = HANDLERS.get(row["job_type"])
    if handler is None:
        _set_status(job_id, "failed",
                    error=f"unknown handler: {row['job_type']}")
        return get_job(job_id)
    # get_job already parsed input_refs/options for us. Tolerate the
    # raw-string case in case a future caller stops going through it.
    raw_refs = row["input_refs"]
    if isinstance(raw_refs, list):
        input_refs = raw_refs
    else:
        try:
            input_refs = json.loads(raw_refs or "[]")
        except Exception:
            input_refs = []
    raw_opts = row.get("options")
    if isinstance(raw_opts, dict):
        options = raw_opts
    elif raw_opts:
        try:
            options = json.loads(raw_opts)
        except Exception:
            options = None
    else:
        options = None

    _set_status(job_id, "running")
    out_dir = os.path.join(_RESULT_DIR, job_id)
    os.makedirs(out_dir, exist_ok=True)
    try:
        fname = handler(input_refs, out_dir, options)
        rel = os.path.join("workspace", "results", job_id, fname).replace("\\", "/")
        _set_status(job_id, "done", output_path=rel)
    except Exception as e:
        tb = traceback.format_exc()
        _set_status(job_id, "failed", error=tb[-4000:])  # cap traceback length
        # don't re-raise — the row + tests are the contract.
    return get_job(job_id)


def get_job(job_id: str,
            requester_username: Optional[str] = None) -> Optional[Dict]:
    """Return the row (with parsed input_refs/options). Owner-scoped
    when ``requester_username`` is supplied."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        if requester_username is not None and row["owner"] != requester_username:
            return None
        out = dict(row)
        try:
            out["input_refs"] = json.loads(out.get("input_refs") or "[]")
        except Exception:
            out["input_refs"] = []
        if out.get("options"):
            try:
                out["options"] = json.loads(out["options"])
            except Exception:
                out["options"] = None
        return out
    finally:
        conn.close()


def list_jobs(owner: Optional[str] = None,
              status: Optional[str] = None,
              limit: int = 50, offset: int = 0) -> List[Dict]:
    """Newest-first list with owner / status filters at the SQL layer."""
    where: list = []
    params: list = []
    if owner is not None:
        where.append("owner = ?")
        params.append(owner)
    if status:
        if status not in ALLOWED_STATUSES:
            return []
        where.append("status = ?")
        params.append(status)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    sql = (
        "SELECT * FROM jobs"
        + where_sql +
        " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    )
    params.extend([max(1, min(int(limit), 500)), max(0, int(offset))])
    conn = _get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    out: list = []
    for r in rows:
        d = dict(r)
        try:
            d["input_refs"] = json.loads(d.get("input_refs") or "[]")
        except Exception:
            d["input_refs"] = []
        if d.get("options"):
            try:
                d["options"] = json.loads(d["options"])
            except Exception:
                d["options"] = None
        out.append(d)
    return out


def count_jobs(owner: Optional[str] = None,
               status: Optional[str] = None) -> int:
    where: list = []
    params: list = []
    if owner is not None:
        where.append("owner = ?")
        params.append(owner)
    if status:
        if status not in ALLOWED_STATUSES:
            return 0
        where.append("status = ?")
        params.append(status)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    conn = _get_conn()
    try:
        return int(conn.execute(
            f"SELECT COUNT(*) AS c FROM jobs{where_sql}",
            params,
        ).fetchone()["c"])
    finally:
        conn.close()


# Schedule + retention helpers live in core/scheduler.py — kept
# separate to honor the 20 KB module-size gate (workspace.py reaches
# that ceiling with the three handlers alone). The sibling module
# imports _get_conn / _RESULT_DIR / execute_job from here; the
# dependency stays unidirectional (scheduler → workspace, never back).
