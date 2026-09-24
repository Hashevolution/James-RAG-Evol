"""Host conditions for a measurement run — recorded, not assumed.

Why this exists
---------------
On 2026-09-22 the QVT 5-axis baseline was captured at ~146 s per query.
On 2026-09-24, same hardware, same model, same budgets, the default path
ran at ~82 s. ``reason:synth`` — a stage with no timeout interaction that
no code change touched — went 33.8 s -> 14.2 s, which isolates the host:
the machine was ~2.4x slower on 09-22.

Why is unknown and **cannot now be recovered**. Nothing recorded GPU
utilisation, clocks, co-resident processes or which models Ollama had
loaded. A CPU-offload hypothesis was proposed afterwards and could only
be tested against *today's* state, not that day's.

The consequence is not academic: ``baseline_6deca66.json``'s
``latency_cost`` band is 3.40 s within a day while the day-to-day swing
is ~57 s, so any PR measured on another day shows a large latency
"change" that is purely the host. This module is the fix of the same
shape as the week's others (#1136 router evidence, #1142 model pin,
#1143 provenance): put the fact in the artifact.

Design
------
* **Sample, don't snapshot, the GPU.** A single ``nvidia-smi`` reading
  is dominated by *when* it is taken: at idle the SM clock on the
  capture host reads ~210 MHz, under load ~2745 MHz. ``GpuSampler``
  polls through the run and reports min / mean / max.
* **Fail soft, and say which probe failed.** A missing ``nvidia-smi`` or
  an unreachable Ollama must never abort a 45-minute capture; it records
  ``{"error": ...}`` for that probe so its absence is visible rather
  than silently empty.
* **No new dependency.** ``psutil`` is already in ``requirements.txt``;
  if it is unavailable the CPU/process probes report that and the rest
  still runs.
"""
from __future__ import annotations

import json
import platform
import shutil
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, List, Optional

# Order matters: parse_gpu_line zips these against nvidia-smi's CSV.
GPU_FIELDS = (
    "name",
    "driver_version",
    "memory.used",
    "memory.total",
    "utilization.gpu",
    "temperature.gpu",
    "clocks.sm",
    "clocks.max.sm",
    "power.draw",
)
_NUMERIC = {
    "memory.used", "memory.total", "utilization.gpu", "temperature.gpu",
    "clocks.sm", "clocks.max.sm", "power.draw",
}
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_gpu_line(line: str) -> Dict[str, Any]:
    """One ``--format=csv,noheader,nounits`` row -> typed dict.

    Numeric fields that nvidia-smi reports as ``[N/A]`` / ``[Not
    Supported]`` become ``None`` rather than raising — laptop GPUs and
    some drivers omit power or clocks, and that must not lose the rest.
    """
    parts = [p.strip() for p in line.split(",")]
    out: Dict[str, Any] = {}
    for key, raw in zip(GPU_FIELDS, parts):
        if key in _NUMERIC:
            try:
                out[key] = float(raw)
            except ValueError:
                out[key] = None
        else:
            out[key] = raw
    return out


def read_gpu(timeout_s: float = 5.0) -> Dict[str, Any]:
    """Current GPU state, or ``{"error": ...}``. First GPU only."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return {"error": "nvidia-smi not found"}
    try:
        proc = subprocess.run(
            [exe, "--query-gpu=" + ",".join(GPU_FIELDS),
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=timeout_s, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": "{}: {}".format(type(exc).__name__, exc)}
    if proc.returncode != 0 or not proc.stdout.strip():
        return {"error": "nvidia-smi exit {}: {}".format(
            proc.returncode, (proc.stderr or "").strip()[:160])}
    return parse_gpu_line(proc.stdout.strip().splitlines()[0])


def read_ollama_ps(base_url: str = DEFAULT_OLLAMA_URL,
                   timeout_s: float = 3.0) -> Dict[str, Any]:
    """Which models Ollama has resident, and how much of each is on GPU.

    ``size`` is the *loaded* footprint, not the on-disk size — the
    2026-09-24 CPU-offload hypothesis briefly confused the two
    (``gemma4:e4b`` is 8.9 GB on disk per ``ollama list``, 3.01 GiB loaded,
    100% on GPU).
    ``gpu_fraction`` is reported explicitly so nobody has to redo that.
    """
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/ps",
                                    timeout=timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # network, JSON, anything: record it
        return {"error": "{}: {}".format(type(exc).__name__, str(exc)[:120])}
    # GiB (2**30), not GB (10**9), and the unit is in the key. The
    # 2026-09-24 records say "3.01" for gemma4:e4b; that was GiB. Mixing
    # the two gives 3.23 vs 3.01 for the same model, and this week has
    # already had one unit confusion (disk size vs loaded size) too many.
    gib = float(1 << 30)
    models = []
    for m in payload.get("models") or []:
        size = m.get("size") or 0
        vram = m.get("size_vram") or 0
        models.append({
            "name": m.get("name"),
            "loaded_gib": round(size / gib, 2) if size else None,
            "vram_gib": round(vram / gib, 2) if vram else None,
            "gpu_fraction": round(vram / size, 3) if size else None,
        })
    return {"models": models}


def read_cpu_and_processes(top_n: int = 8) -> Dict[str, Any]:
    """System CPU load and the heaviest processes, via psutil."""
    try:
        import psutil  # noqa: WPS433 — optional at import time
    except ImportError:
        return {"error": "psutil not installed"}
    try:
        load = psutil.cpu_percent(interval=0.5)
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent",
                                      "memory_info"]):
            info = p.info
            mem = info.get("memory_info")
            procs.append({
                "pid": info.get("pid"),
                "name": info.get("name"),
                "rss_mb": round(mem.rss / 1e6) if mem else None,
            })
        procs.sort(key=lambda d: d.get("rss_mb") or 0, reverse=True)
        return {
            "cpu_percent": load,
            "cpu_count": psutil.cpu_count(),
            "memory_percent": psutil.virtual_memory().percent,
            "top_by_rss": procs[:top_n],
        }
    except Exception as exc:
        return {"error": "{}: {}".format(type(exc).__name__, str(exc)[:120])}


def static_snapshot(ollama_url: str = DEFAULT_OLLAMA_URL) -> Dict[str, Any]:
    """Point-in-time context: platform, GPU identity, resident models."""
    return {
        "captured_at": _now(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "gpu": read_gpu(),
        "ollama": read_ollama_ps(ollama_url),
        "host": read_cpu_and_processes(),
    }


class GpuSampler:
    """Poll the GPU through a run; summarise min / mean / max.

    Used as a context manager around the bench subprocess. A daemon
    thread, so a crashed run cannot leave it pinning the interpreter.
    """

    SUMMARY_FIELDS = ("utilization.gpu", "clocks.sm", "temperature.gpu",
                      "power.draw", "memory.used")

    def __init__(self, interval_s: float = 15.0) -> None:
        self.interval_s = interval_s
        self.samples: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.started_at: Optional[str] = None
        self.stopped_at: Optional[str] = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            reading = read_gpu()
            if "error" in reading:
                self.errors.append(reading["error"])
            else:
                reading["t"] = time.time()
                self.samples.append(reading)
            self._stop.wait(self.interval_s)

    def __enter__(self) -> "GpuSampler":
        self.started_at = _now()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_s + 5)
        self.stopped_at = _now()

    def summary(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "interval_s": self.interval_s,
            "n_samples": len(self.samples),
        }
        if self.errors:
            out["errors"] = sorted(set(self.errors))[:5]
        for field in self.SUMMARY_FIELDS:
            vals = [s[field] for s in self.samples
                    if isinstance(s.get(field), (int, float))]
            if vals:
                out[field] = {
                    "min": round(min(vals), 1),
                    "mean": round(mean(vals), 1),
                    "max": round(max(vals), 1),
                }
        return out
