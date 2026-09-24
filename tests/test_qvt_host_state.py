"""Host-state capture for measurement runs.

On 2026-09-22 the QVT baseline ran ~2.4x slower than the same default
path on 2026-09-24 — same hardware, model and budgets. ``reason:synth``,
which no budget or code change touches, isolated the host as the cause.
*Why* the host was slow is unrecoverable: nothing recorded it.

``eval/qvt/host_state.py`` records it now. These tests pin its behaviour
without needing a GPU or a running Ollama — every probe is mocked — so
they run the same on CI as on the capture host. That matters twice over:
the previous CI failure in this area came from a test asserting a fact
about the workstation (an installed model) instead of the contract.

Run:
  python -m unittest tests.test_qvt_host_state
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eval.qvt import host_state as hs  # noqa: E402

_LOADED = "NVIDIA GeForce RTX 4070 SUPER, 596.36, 8187, 12282, 94, 79, 2745, 3120, 203.74"
_IDLE = "NVIDIA GeForce RTX 4070 SUPER, 596.36, 5591, 12282, 0, 37, 210, 3120, 6.85"


class ParseGpuLineTests(unittest.TestCase):
    def test_fields_are_typed(self):
        g = hs.parse_gpu_line(_LOADED)
        self.assertEqual(g["name"], "NVIDIA GeForce RTX 4070 SUPER")
        self.assertEqual(g["driver_version"], "596.36")
        self.assertEqual(g["utilization.gpu"], 94.0)
        self.assertEqual(g["clocks.sm"], 2745.0)
        self.assertEqual(g["power.draw"], 203.74)

    def test_not_available_becomes_none_without_losing_the_rest(self):
        """Laptop GPUs / some drivers report [N/A] for power or clocks."""
        g = hs.parse_gpu_line(
            "Some GPU, 1.0, 100, 8000, 50, 60, [N/A], [Not Supported], [N/A]")
        self.assertIsNone(g["clocks.sm"])
        self.assertIsNone(g["power.draw"])
        self.assertEqual(g["utilization.gpu"], 50.0)

    def test_why_sampling_not_snapshotting(self):
        """The same GPU reads 210 MHz idle and 2745 MHz under load. A
        single reading is dominated by when it was taken."""
        idle, loaded = hs.parse_gpu_line(_IDLE), hs.parse_gpu_line(_LOADED)
        self.assertGreater(loaded["clocks.sm"] / idle["clocks.sm"], 10)


class ProbeFailureTests(unittest.TestCase):
    """Fail soft and say which probe failed — never abort a capture."""

    def test_missing_nvidia_smi_reports_instead_of_raising(self):
        with mock.patch.object(hs.shutil, "which", return_value=None):
            self.assertEqual(hs.read_gpu(), {"error": "nvidia-smi not found"})

    def test_nvidia_smi_nonzero_exit_reports(self):
        fake = mock.Mock(returncode=9, stdout="", stderr="driver gone")
        with mock.patch.object(hs.shutil, "which", return_value="nvidia-smi"), \
             mock.patch.object(hs.subprocess, "run", return_value=fake):
            out = hs.read_gpu()
        self.assertIn("error", out)
        self.assertIn("exit 9", out["error"])

    def test_unreachable_ollama_reports(self):
        out = hs.read_ollama_ps("http://127.0.0.1:1", timeout_s=0.5)
        self.assertIn("error", out)

    def test_missing_psutil_reports(self):
        with mock.patch.dict(sys.modules, {"psutil": None}):
            out = hs.read_cpu_and_processes()
        self.assertEqual(out, {"error": "psutil not installed"})


class OllamaUnitsTests(unittest.TestCase):
    """GiB, with the unit in the key. 3.01 GiB and 3.23 GB are the same
    model; this week already had one unit confusion (disk vs loaded)."""

    def _fake_ps(self, models):
        import io
        import json
        body = io.BytesIO(json.dumps({"models": models}).encode())
        cm = mock.MagicMock()
        cm.__enter__.return_value = body
        cm.__exit__.return_value = False
        return cm

    def test_sizes_are_gib_and_gpu_fraction_is_explicit(self):
        gib = 1 << 30
        fake = self._fake_ps([{"name": "gemma4:e4b",
                               "size": int(3.01 * gib),
                               "size_vram": int(3.01 * gib)}])
        with mock.patch.object(hs.urllib.request, "urlopen", return_value=fake):
            out = hs.read_ollama_ps()
        m = out["models"][0]
        self.assertEqual(m["loaded_gib"], 3.01)
        self.assertEqual(m["vram_gib"], 3.01)
        self.assertEqual(m["gpu_fraction"], 1.0)
        self.assertNotIn("size_gb", m)

    def test_partial_offload_shows_as_a_fraction(self):
        gib = 1 << 30
        fake = self._fake_ps([{"name": "big", "size": 10 * gib,
                               "size_vram": 4 * gib}])
        with mock.patch.object(hs.urllib.request, "urlopen", return_value=fake):
            m = hs.read_ollama_ps()["models"][0]
        self.assertEqual(m["gpu_fraction"], 0.4)


class GpuSamplerTests(unittest.TestCase):
    def test_summary_reports_min_mean_max(self):
        readings = iter([hs.parse_gpu_line(_IDLE), hs.parse_gpu_line(_LOADED)]
                        + [hs.parse_gpu_line(_LOADED)] * 50)
        with mock.patch.object(hs, "read_gpu", side_effect=lambda: next(readings)):
            with hs.GpuSampler(interval_s=0.05) as g:
                time.sleep(0.2)
        s = g.summary()
        self.assertGreaterEqual(s["n_samples"], 2)
        self.assertEqual(s["clocks.sm"]["min"], 210.0)
        self.assertEqual(s["clocks.sm"]["max"], 2745.0)
        self.assertIn("mean", s["utilization.gpu"])
        self.assertIsNotNone(s["started_at"])
        self.assertIsNotNone(s["stopped_at"])

    def test_probe_errors_are_recorded_not_raised(self):
        with mock.patch.object(hs, "read_gpu",
                               return_value={"error": "nvidia-smi not found"}):
            with hs.GpuSampler(interval_s=0.05) as g:
                time.sleep(0.12)
        s = g.summary()
        self.assertEqual(s["n_samples"], 0)
        self.assertEqual(s["errors"], ["nvidia-smi not found"])

    def test_sampler_thread_stops(self):
        with mock.patch.object(hs, "read_gpu",
                               return_value=hs.parse_gpu_line(_IDLE)):
            with hs.GpuSampler(interval_s=0.05) as g:
                time.sleep(0.1)
        self.assertFalse(g._thread.is_alive())


class StaticSnapshotTests(unittest.TestCase):
    def test_snapshot_has_every_section_even_when_all_probes_fail(self):
        with mock.patch.object(hs, "read_gpu", return_value={"error": "x"}), \
             mock.patch.object(hs, "read_ollama_ps", return_value={"error": "y"}), \
             mock.patch.object(hs, "read_cpu_and_processes",
                               return_value={"error": "z"}):
            s = hs.static_snapshot()
        for key in ("captured_at", "platform", "python", "gpu", "ollama", "host"):
            self.assertIn(key, s)
        self.assertEqual(s["gpu"], {"error": "x"})


if __name__ == "__main__":
    unittest.main()
