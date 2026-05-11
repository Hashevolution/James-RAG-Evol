"""W8-D — scheduler + retention.

Three layers:
  1. compute_next_run — DSL parsing.
  2. claim_due_scheduled_jobs / update_schedule — DB roundtrip.
  3. Scheduler loop tick / purge_old_results — integration.
  4. POST /jobs/schedule — feature gate + DSL validation.

Avoid sleeping on a real scheduler thread — drive ``_scheduled_tick``
directly so tests stay deterministic and fast.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault(
    "JAMES_JWT_SECRET",
    "test-secret-for-scheduler-32chars-min",
)
# Don't auto-start the singleton scheduler when server_llmwiki imports.
os.environ["JAMES_DISABLE_SCHEDULER"] = "1"

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


def _api_key() -> str:
    env_v = os.environ.get("JAMES_API_KEY")
    if env_v:
        return env_v.strip()
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("JAMES_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


class _SchedulerFixture(unittest.TestCase):
    """Point workspace + scheduler at an isolated tmp DB + results dir."""

    def setUp(self):
        from core import workspace as ws
        self._tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp_db.close()
        self._tmp_dir = tempfile.mkdtemp(prefix="sched_results_")
        self._saved_db  = ws._DB_PATH
        self._saved_dir = ws._RESULT_DIR
        ws._DB_PATH    = self._tmp_db.name
        ws._RESULT_DIR = self._tmp_dir
        ws._init_db()

    def tearDown(self):
        from core import workspace as ws
        ws._DB_PATH    = self._saved_db
        ws._RESULT_DIR = self._saved_dir
        Path(self._tmp_db.name).unlink(missing_ok=True)
        try:
            shutil.rmtree(self._tmp_dir)
        except Exception:
            pass


class ComputeNextRunTests(unittest.TestCase):
    """Pure DSL — no DB, no clock dependency beyond ``now``."""

    def test_unknown_spec_returns_none(self):
        from core.scheduler import compute_next_run
        for s in ("", None, "garbage", "yearly", "daily", "every:",
                  "every:99999999", "weekly:xxx:09:00"):
            self.assertIsNone(compute_next_run(s, now=1_000_000),
                              f"expected None for {s!r}")

    def test_every_seconds(self):
        from core.scheduler import compute_next_run
        self.assertEqual(compute_next_run("every:300", now=1_000_000),
                         1_000_300)

    def test_hourly_rounds_to_top_of_next_hour(self):
        from core.scheduler import compute_next_run
        import datetime
        # 09:23:45 → 10:00:00
        d = datetime.datetime(2026, 5, 11, 9, 23, 45)
        nxt = compute_next_run("hourly", now=int(d.timestamp()))
        ndt = datetime.datetime.fromtimestamp(nxt)
        self.assertEqual((ndt.hour, ndt.minute, ndt.second),
                         (10, 0, 0))

    def test_daily_picks_today_if_future(self):
        from core.scheduler import compute_next_run
        import datetime
        # 09:00 now, schedule daily:17:30 → today 17:30
        d = datetime.datetime(2026, 5, 11, 9, 0, 0)
        nxt = compute_next_run("daily:17:30", now=int(d.timestamp()))
        ndt = datetime.datetime.fromtimestamp(nxt)
        self.assertEqual((ndt.year, ndt.month, ndt.day, ndt.hour, ndt.minute),
                         (2026, 5, 11, 17, 30))

    def test_daily_picks_tomorrow_if_past(self):
        from core.scheduler import compute_next_run
        import datetime
        # 18:00 now, schedule daily:09:00 → next day 09:00
        d = datetime.datetime(2026, 5, 11, 18, 0, 0)
        nxt = compute_next_run("daily:09:00", now=int(d.timestamp()))
        ndt = datetime.datetime.fromtimestamp(nxt)
        self.assertEqual((ndt.year, ndt.month, ndt.day, ndt.hour, ndt.minute),
                         (2026, 5, 12, 9, 0))

    def test_weekly_jumps_to_named_weekday(self):
        from core.scheduler import compute_next_run
        import datetime
        # Monday 2026-05-11 12:00 → weekly:wed:09:00 should land
        # Wednesday 2026-05-13 09:00
        d = datetime.datetime(2026, 5, 11, 12, 0, 0)
        nxt = compute_next_run("weekly:wed:09:00", now=int(d.timestamp()))
        ndt = datetime.datetime.fromtimestamp(nxt)
        self.assertEqual((ndt.year, ndt.month, ndt.day, ndt.hour, ndt.minute),
                         (2026, 5, 13, 9, 0))

    def test_invalid_time_fields_rejected(self):
        from core.scheduler import compute_next_run
        self.assertIsNone(compute_next_run("daily:25:00", now=1_000_000))
        self.assertIsNone(compute_next_run("daily:12:60", now=1_000_000))
        self.assertIsNone(compute_next_run("weekly:mon:24:00", now=1_000_000))


class ClaimAndUpdateTests(_SchedulerFixture):
    def test_one_shot_jobs_never_claimed(self):
        from core.workspace import register_job
        from core.scheduler import claim_due_scheduled_jobs
        register_job("excel_build", [], owner="alice")
        self.assertEqual(claim_due_scheduled_jobs(now=9_999_999_999), [])

    def test_scheduled_with_past_next_run_is_claimed(self):
        from core.workspace import register_job
        from core.scheduler import claim_due_scheduled_jobs
        register_job("excel_build", [], owner="alice",
                     schedule_cron="every:60", next_run_at=1_000_000)
        rows = claim_due_scheduled_jobs(now=2_000_000)
        self.assertEqual(len(rows), 1)

    def test_scheduled_with_future_next_run_not_claimed(self):
        from core.workspace import register_job
        from core.scheduler import claim_due_scheduled_jobs
        register_job("excel_build", [], owner="alice",
                     schedule_cron="every:60", next_run_at=3_000_000)
        self.assertEqual(claim_due_scheduled_jobs(now=2_000_000), [])

    def test_null_next_run_is_claimed_eagerly(self):
        # First firing — scheduler hasn't computed next_run_at yet.
        from core.workspace import register_job
        from core.scheduler import claim_due_scheduled_jobs
        register_job("excel_build", [], owner="alice",
                     schedule_cron="every:60", next_run_at=None)
        rows = claim_due_scheduled_jobs(now=2_000_000)
        self.assertEqual(len(rows), 1)

    def test_update_schedule_persists_next_run(self):
        from core.workspace import register_job, get_job
        from core.scheduler import update_schedule
        jid = register_job("excel_build", [], owner="alice",
                           schedule_cron="every:60")
        self.assertTrue(update_schedule(jid, 2_500_000))
        self.assertEqual(get_job(jid)["next_run_at"], 2_500_000)


class _StubWiki:
    def __init__(self, entities):
        self._fm = entities
        self.entity_id_index = {k: k for k in entities}
    def _read_frontmatter(self, p):
        return self._fm.get(str(p))


class SchedulerLoopTickTests(_SchedulerFixture):
    def setUp(self):
        super().setUp()
        # Lightweight stub wiki so excel_build doesn't hit the live engine.
        import server_llmwiki as srv
        class _Eng: pass
        self._saved_engine = getattr(srv, "rag_engine", None)
        srv.rag_engine = _Eng()
        srv.rag_engine.wiki_generator = _StubWiki({})

    def tearDown(self):
        import server_llmwiki as srv
        if self._saved_engine is None:
            try: del srv.rag_engine
            except AttributeError: pass
        else:
            srv.rag_engine = self._saved_engine
        super().tearDown()

    def test_scheduled_tick_fires_and_reschedules(self):
        from core.workspace import register_job, get_job
        from core.scheduler import Scheduler
        jid = register_job("excel_build", [], owner="alice",
                           schedule_cron="every:60",
                           next_run_at=1_000_000)
        sched = Scheduler(poll_interval_sec=999_999)  # avoid thread loop
        sched._scheduled_tick(now=1_000_100)

        row = get_job(jid)
        # Status reaches done (handler completes).
        self.assertEqual(row["status"], "done")
        # next_run_at advanced; with now=1_000_100 + every:60 → 1_000_160.
        self.assertEqual(row["next_run_at"], 1_000_160)

    def test_scheduled_tick_pauses_row_on_invalid_spec(self):
        from core.workspace import register_job, get_job, _get_conn
        from core.scheduler import Scheduler
        jid = register_job("excel_build", [], owner="alice",
                           schedule_cron="every:60",
                           next_run_at=1_000_000)
        # Corrupt the cron on the row.
        conn = _get_conn()
        conn.execute("UPDATE jobs SET schedule_cron='garbage' "
                     "WHERE job_id = ?", (jid,))
        conn.commit()
        conn.close()
        sched = Scheduler(poll_interval_sec=999_999)
        sched._scheduled_tick(now=1_000_100)
        row = get_job(jid)
        # compute_next_run returned None → row is paused (next_run_at=NULL).
        self.assertIsNone(row["next_run_at"])


class RetentionTests(_SchedulerFixture):
    def _mkdir_in_results(self, name: str) -> str:
        from core import workspace as ws
        d = os.path.join(ws._RESULT_DIR, name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "out.txt"), "w") as f:
            f.write("x")
        return d

    def test_purge_keeps_recent_finished(self):
        from core.workspace import register_job, _set_status
        from core.scheduler import purge_old_results
        jid = register_job("excel_build", [], owner="alice")
        _set_status(jid, "done", output_path=None)
        self._mkdir_in_results(jid)
        # 1 hour ago → kept under 90d retention.
        from core.workspace import _get_conn
        conn = _get_conn()
        now = int(time.time())
        conn.execute("UPDATE jobs SET finished_at = ? WHERE job_id = ?",
                     (now - 3600, jid))
        conn.commit()
        conn.close()
        result = purge_old_results(retention_days=90, now=now)
        self.assertEqual(result["removed_dirs"], 0)

    def test_purge_removes_old_finished(self):
        from core.workspace import register_job, _set_status, _get_conn
        from core.scheduler import purge_old_results
        jid = register_job("excel_build", [], owner="alice")
        _set_status(jid, "done", output_path=None)
        self._mkdir_in_results(jid)
        now = int(time.time())
        old = now - 100 * 86400   # 100 days ago > 90d retention
        conn = _get_conn()
        conn.execute("UPDATE jobs SET finished_at = ? WHERE job_id = ?",
                     (old, jid))
        conn.commit()
        conn.close()
        result = purge_old_results(retention_days=90, now=now)
        self.assertEqual(result["removed_dirs"], 1)
        # Directory actually gone.
        from core import workspace as ws
        self.assertFalse(os.path.exists(os.path.join(ws._RESULT_DIR, jid)))

    def test_purge_skips_pending_jobs(self):
        from core.workspace import register_job
        from core.scheduler import purge_old_results
        # Pending job — finished_at is NULL, row exists.
        jid = register_job("excel_build", [], owner="alice")
        self._mkdir_in_results(jid)
        result = purge_old_results(retention_days=0,   # aggressive
                                   now=int(time.time()))
        self.assertEqual(result["removed_dirs"], 0)
        self.assertEqual(result["skipped"], 1)

    def test_purge_handles_legacy_dirs_via_mtime(self):
        from core.scheduler import purge_old_results
        legacy = self._mkdir_in_results("legacy-no-row")
        # Backdate mtime to 100 days ago.
        old = time.time() - 100 * 86400
        os.utime(legacy, (old, old))
        result = purge_old_results(retention_days=90, now=int(time.time()))
        self.assertEqual(result["removed_dirs"], 1)


class ScheduleEndpointTests(_SchedulerFixture):
    @classmethod
    def setUpClass(cls):
        cls._api_key = _api_key()

    def setUp(self):
        if not self._api_key:
            self.skipTest("JAMES_API_KEY missing")
        super().setUp()

    def _client(self):
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        return TestClient(srv.app)

    def _hdr(self, role: str):
        from core.auth import create_token
        return {"Authorization": f"Bearer {create_token('test-'+role, role)}"}

    def test_schedule_requires_workspace_schedule(self):
        # workspace.schedule defaults to admin-only. employee → 403.
        r = self._client().post(
            "/jobs/schedule",
            params={"api_key": self._api_key},
            json={"job_type": "excel_build", "input_refs": [],
                  "schedule_cron": "every:60"},
            headers=self._hdr("employee"),
        )
        self.assertEqual(r.status_code, 403)

    def test_schedule_admin_happy_path(self):
        r = self._client().post(
            "/jobs/schedule",
            params={"api_key": self._api_key},
            json={"job_type": "excel_build", "input_refs": [],
                  "schedule_cron": "daily:09:00"},
            headers=self._hdr("admin"),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["schedule_cron"], "daily:09:00")
        self.assertIsInstance(body["next_run_at"], int)

    def test_schedule_unknown_cron_returns_400(self):
        r = self._client().post(
            "/jobs/schedule",
            params={"api_key": self._api_key},
            json={"job_type": "excel_build", "input_refs": [],
                  "schedule_cron": "every-five-minutes"},
            headers=self._hdr("admin"),
        )
        self.assertEqual(r.status_code, 400)

    def test_schedule_unknown_job_type_returns_400(self):
        r = self._client().post(
            "/jobs/schedule",
            params={"api_key": self._api_key},
            json={"job_type": "fake", "input_refs": [],
                  "schedule_cron": "every:60"},
            headers=self._hdr("admin"),
        )
        self.assertEqual(r.status_code, 400)

    def test_schedule_requires_jwt(self):
        # api_key valid, no Bearer → role=employee (via system key path).
        # Even if workspace.schedule passed (it won't), the owner check
        # fires. Confirm 403 (feature gate) or 401 (no JWT) — both
        # indicate the endpoint is locked without auth.
        r = self._client().post(
            "/jobs/schedule",
            params={"api_key": self._api_key},
            json={"job_type": "excel_build", "input_refs": [],
                  "schedule_cron": "every:60"},
        )
        self.assertIn(r.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
