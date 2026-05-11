"""W8-D — lightweight job scheduler + result-directory retention.

A small ``threading.Timer``-based loop that polls ``jobs`` for rows
where ``schedule_cron`` is set and ``next_run_at <= now``. Re-fires
``execute_job`` for each, then computes the next ``next_run_at`` from
the cron spec and persists it.

No external dependencies — Rule 1 (local-first) and Rule 3 (mother
platform stays small). The supported cron spec is a small DSL rather
than the full crontab format because operators routinely fat-finger
the day-of-month vs day-of-week column ordering, and the use cases
for v0.2 (daily/weekly/hourly retention sweeps, periodic exports)
don't need the full grammar. croniter can be added later as an opt-in
if a real cron need surfaces.

Cron DSL
--------
  every:N             — repeat every N seconds (1 ≤ N ≤ 86400)
  hourly              — fire at the top of each hour
  daily:HH:MM         — fire at HH:MM local time every day
  weekly:DOW:HH:MM    — DOW ∈ mon/tue/wed/thu/fri/sat/sun

Public surface
--------------
  RESULT_RETENTION_DAYS                       — default purge cutoff
  compute_next_run(spec, now=None)            — DSL → unix epoch
  claim_due_scheduled_jobs(now=None)          — DB-side SELECT
  update_schedule(job_id, next_run_at)        — persist next firing
  purge_old_results(days=RESULT_RETENTION_DAYS, now=None)
                                              — sweep workspace/results/
  Scheduler                                   — background-thread loop
  default_scheduler                           — module singleton
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import threading
import time
from typing import Optional, List, Dict

# Importing the *module* (not the names) so attribute lookups are
# live — tests that monkey-patch ``workspace._RESULT_DIR`` or
# ``_DB_PATH`` need this module to follow them. ``_get_conn`` is
# the same: dereference each call so a patched module-level path is
# honored.
from core import workspace as _ws  # noqa: F401  (re-exposed via _ws.*)


def _get_conn():
    return _ws._get_conn()


def execute_job(job_id: str):
    return _ws.execute_job(job_id)


# Default retention for workspace/results/<job_id>/ artefacts. Kept
# generous so an admin can grab a job result a quarter after running
# it; operators wanting stricter cleanup pass a smaller value.
RESULT_RETENTION_DAYS = 90


# ───────────────────────────────────────────────────────────────
# DSL → unix epoch
# ───────────────────────────────────────────────────────────────

def compute_next_run(spec: str, now: Optional[int] = None) -> Optional[int]:
    """Translate a small DSL into the next firing time (unix epoch).

    Unknown / malformed spec → None. The caller leaves ``next_run_at``
    as-is so the row is effectively paused — an operator typo doesn't
    fire every poll.
    """
    now = now if now is not None else int(time.time())
    if not spec or not isinstance(spec, str):
        return None
    s = spec.strip().lower()

    if s == "hourly":
        d = _dt.datetime.fromtimestamp(now)
        nxt = d.replace(minute=0, second=0, microsecond=0) + _dt.timedelta(hours=1)
        return int(nxt.timestamp())

    if s.startswith("every:"):
        try:
            n = int(s.split(":", 1)[1])
        except (ValueError, IndexError):
            return None
        if n < 1 or n > 86400:
            return None
        return now + n

    if s.startswith("daily:"):
        parts = s.split(":")
        if len(parts) != 3:
            return None
        try:
            hh, mm = int(parts[1]), int(parts[2])
        except ValueError:
            return None
        if not (0 <= hh < 24 and 0 <= mm < 60):
            return None
        d = _dt.datetime.fromtimestamp(now)
        target = d.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= d:
            target += _dt.timedelta(days=1)
        return int(target.timestamp())

    if s.startswith("weekly:"):
        parts = s.split(":")
        if len(parts) != 4:
            return None
        dow_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3,
                   "fri": 4, "sat": 5, "sun": 6}
        if parts[1] not in dow_map:
            return None
        try:
            hh, mm = int(parts[2]), int(parts[3])
        except ValueError:
            return None
        if not (0 <= hh < 24 and 0 <= mm < 60):
            return None
        d = _dt.datetime.fromtimestamp(now)
        target = d.replace(hour=hh, minute=mm, second=0, microsecond=0)
        days_ahead = (dow_map[parts[1]] - d.weekday()) % 7
        if days_ahead == 0 and target <= d:
            days_ahead = 7
        target += _dt.timedelta(days=days_ahead)
        return int(target.timestamp())

    return None


# ───────────────────────────────────────────────────────────────
# DB helpers — operate on jobs table directly
# ───────────────────────────────────────────────────────────────

def claim_due_scheduled_jobs(now: Optional[int] = None) -> List[Dict]:
    """Return scheduled jobs whose ``next_run_at`` is at-or-past now.

    Returns the full row dict (with parsed input_refs/options) so the
    Scheduler doesn't need its own SQL.
    """
    now = now if now is not None else int(time.time())
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs "
            "WHERE schedule_cron IS NOT NULL "
            "  AND (next_run_at IS NULL OR next_run_at <= ?) "
            "ORDER BY (next_run_at IS NULL) DESC, next_run_at ASC",
            (now,),
        ).fetchall()
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


def update_schedule(job_id: str, next_run_at: Optional[int]) -> bool:
    """Persist the next firing time. ``None`` pauses the row."""
    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE jobs SET next_run_at = ? WHERE job_id = ?",
            (next_run_at, job_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ───────────────────────────────────────────────────────────────
# Retention sweep
# ───────────────────────────────────────────────────────────────

def purge_old_results(retention_days: int = RESULT_RETENTION_DAYS,
                      now: Optional[int] = None) -> Dict[str, int]:
    """Remove result directories whose owning job finished more than
    ``retention_days`` ago.

    Strategy:
      - ``jobs.finished_at`` is the authoritative cutoff (truthful even
        if the file system mtime drifted after a snapshot restore).
      - For directories whose name has no matching row (legacy results
        from before W8-A), fall back to directory mtime.
      - Pending/running jobs (row present, finished_at NULL) are never
        purged.

    Returns ``{"removed_dirs": N, "skipped": M, "errors": E}``.
    """
    now    = now if now is not None else int(time.time())
    cutoff = now - retention_days * 86400
    out    = {"removed_dirs": 0, "skipped": 0, "errors": 0}

    result_dir = _ws._RESULT_DIR
    if not os.path.isdir(result_dir):
        return out

    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT job_id, finished_at FROM jobs"
        ).fetchall()
    finally:
        conn.close()
    finished = {r["job_id"]: r["finished_at"] for r in rows}

    for name in os.listdir(result_dir):
        full = os.path.join(result_dir, name)
        if not os.path.isdir(full):
            continue
        ft = finished.get(name)
        if ft is None:
            if name in finished:
                # Row present but unfinished — skip (running/pending).
                out["skipped"] += 1
                continue
            try:
                ft = int(os.path.getmtime(full))
            except OSError:
                out["errors"] += 1
                continue
        if ft > cutoff:
            out["skipped"] += 1
            continue
        try:
            shutil.rmtree(full)
            out["removed_dirs"] += 1
        except Exception:
            out["errors"] += 1
    return out


# ───────────────────────────────────────────────────────────────
# Background scheduler
# ───────────────────────────────────────────────────────────────

class Scheduler:
    """Polling-loop scheduler.

    Default poll interval is 60 seconds — fine-grained enough for the
    DSL's smallest unit (every:1 still resolves to a 60s lower bound
    in practice) without thrashing SQLite on a quiet system.

    Lifecycle:
      ``start()`` — launches a daemon thread + immediately invokes
                    ``_retention_tick`` once (operators want stale
                    result dirs gone at boot, not 24h later).
      ``stop()``  — sets the event; the next loop iteration exits.

    The loop:
      every poll_interval_sec:
        1. claim_due_scheduled_jobs(now)
        2. for each row: execute_job(row.job_id)
                          → compute_next_run(row.schedule_cron, now)
                          → update_schedule(row.job_id, next)
        3. once a day: purge_old_results()
    """
    def __init__(self, poll_interval_sec: int = 60,
                 retention_days: int = RESULT_RETENTION_DAYS):
        self.poll_interval_sec = poll_interval_sec
        self.retention_days    = retention_days
        self._stop             = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_retention   = 0   # unix epoch of last sweep

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="james-scheduler", daemon=True,
        )
        self._thread.start()
        # Immediate retention sweep — see lifecycle comment above.
        try:
            self._retention_tick(int(time.time()), force=True)
        except Exception as e:
            print(f"[SCHED] initial retention sweep failed: {e}")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = int(time.time())
            try:
                self._scheduled_tick(now)
            except Exception as e:
                print(f"[SCHED] scheduled tick failed: {e}")
            try:
                self._retention_tick(now)
            except Exception as e:
                print(f"[SCHED] retention tick failed: {e}")
            # Use wait() instead of sleep() so stop() exits promptly.
            self._stop.wait(self.poll_interval_sec)

    def _scheduled_tick(self, now: int) -> None:
        for row in claim_due_scheduled_jobs(now):
            jid = row.get("job_id")
            if not jid:
                continue
            try:
                execute_job(jid)
            except Exception as e:
                print(f"[SCHED] execute_job({jid}) failed: {e}")
            spec = row.get("schedule_cron") or ""
            nxt  = compute_next_run(spec, now)
            update_schedule(jid, nxt)

    def _retention_tick(self, now: int, force: bool = False) -> None:
        # Sweep at most once per 24h unless force=True.
        if not force and now - self._last_retention < 86400:
            return
        result = purge_old_results(self.retention_days, now)
        self._last_retention = now
        if result["removed_dirs"]:
            print(f"[SCHED] result retention swept "
                  f"{result['removed_dirs']} dir(s) "
                  f"(retention={self.retention_days}d)")


# Module-level singleton. Server startup hook calls
# ``default_scheduler.start()``; tests construct their own Scheduler
# with shorter poll intervals.
default_scheduler = Scheduler()
