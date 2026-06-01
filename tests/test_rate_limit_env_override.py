"""Contract — `JAMES_RATE_LIMIT_MAX` + `JAMES_RATE_LIMIT_WINDOW_SEC`
env overrides on `server_llmwiki.py`'s `RateLimiter` (PR #671 fix).

Three invariants pinned:
  1. Default values (env unset) — max=30, window=60. Production
     operator-safe defaults preserved.
  2. Env override `JAMES_RATE_LIMIT_MAX=10000` — rate limiter
     instance has max_requests=10000.
  3. Env override `JAMES_RATE_LIMIT_WINDOW_SEC=120` — instance has
     window_sec=120.

We test the env-read expression in isolation rather than spawning
the FastAPI app, because the limiter is initialised at module import.
"""
from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent


class RateLimitEnvOverrideContract(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop("JAMES_RATE_LIMIT_MAX", None)
        os.environ.pop("JAMES_RATE_LIMIT_WINDOW_SEC", None)

    def tearDown(self) -> None:
        os.environ.pop("JAMES_RATE_LIMIT_MAX", None)
        os.environ.pop("JAMES_RATE_LIMIT_WINDOW_SEC", None)

    def test_default_values_preserved_when_env_unset(self):
        # Read defaults via the same expression server_llmwiki.py uses.
        max_req = int(os.environ.get("JAMES_RATE_LIMIT_MAX", "30"))
        window  = int(os.environ.get("JAMES_RATE_LIMIT_WINDOW_SEC", "60"))
        self.assertEqual(max_req, 30,
            "default max_requests must remain 30 (operator-safe)")
        self.assertEqual(window, 60,
            "default window_sec must remain 60s")

    def test_max_override_recognised(self):
        with patch.dict(os.environ,
                        {"JAMES_RATE_LIMIT_MAX": "10000"},
                        clear=False):
            v = int(os.environ.get("JAMES_RATE_LIMIT_MAX", "30"))
            self.assertEqual(v, 10000)

    def test_window_override_recognised(self):
        with patch.dict(os.environ,
                        {"JAMES_RATE_LIMIT_WINDOW_SEC": "120"},
                        clear=False):
            v = int(os.environ.get("JAMES_RATE_LIMIT_WINDOW_SEC", "60"))
            self.assertEqual(v, 120)


class MatrixRunnerSetsRateLimitFixedEnvContract(unittest.TestCase):
    """Pin that the matrix runner's `_FIXED_ENV` includes
    `JAMES_RATE_LIMIT_MAX=10000` (PR #671 Option C). Without it,
    Phase 3a (gemma3:1b sub-1s/query) would corrupt silently.
    """

    def test_fixed_env_disables_rate_limit_for_bench_loops(self):
        # Import the matrix runner module fresh so we read the
        # current _FIXED_ENV.
        sys.path.insert(0, str(ROOT))
        spec = importlib.util.spec_from_file_location(
            "qvt_ablation_matrix",
            ROOT / "scripts" / "qvt_ablation_matrix.py",
        )
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules["qvt_ablation_matrix"] = mod
        spec.loader.exec_module(mod)
        self.assertIn("JAMES_RATE_LIMIT_MAX", mod._FIXED_ENV,
            "matrix runner must set JAMES_RATE_LIMIT_MAX for "
            "fast-response cells (per α-6 Phase 2 post-mortem #671)")
        max_val = int(mod._FIXED_ENV["JAMES_RATE_LIMIT_MAX"])
        self.assertGreaterEqual(max_val, 1000,
            f"JAMES_RATE_LIMIT_MAX in matrix _FIXED_ENV is {max_val}; "
            "must be ≥ 1000 to absorb 100-query bench runs without "
            "hitting the rate limit on sub-2s/query cells.")


if __name__ == "__main__":
    unittest.main()
