"""Standalone GPU detection diagnostic.

Run this on the same PC + same Python interpreter that hosts the
JAMES server. It tells you WHY hardware_inspector returns
"Unknown" — env vs. code vs. running-stale-server problem.

Usage:
  python scripts/diagnose_hardware.py

What it does:
  1. Print the Python interpreter + cwd + first lines of sys.path
     so you can verify it matches what `python server_llmwiki.py`
     uses.
  2. Probe each GPU fallback (pynvml, nvidia-smi, wmic) directly
     with full error messages — no silent except.
  3. Call hardware_inspector._get_gpu() with JAMES_HW_DEBUG=1 and
     print the debug trail.
  4. Hit the LIVE /hardware/ endpoint (requires server running) and
     compare the live response to what the inspector returns
     in-process. A mismatch means the server is running OLD code.

Exit codes:
  0 — GPU detected at module level (RTX-something + VRAM > 0)
  1 — GPU NOT detected at module level (real env problem)
  2 — Live endpoint differs from in-process result (stale server)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# UTF-8 console for the Korean prints below.
try:
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except Exception:
    pass


def _section(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _probe_pynvml() -> None:
    _section("1. pynvml probe")
    try:
        import pynvml
        ver = getattr(pynvml, "__version__", "(unknown)")
        print(f"  pynvml import: OK (version={ver})")
        try:
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            print(f"  GPU count: {count}")
            for i in range(count):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(h)
                if isinstance(name, bytes):
                    name = name.decode()
                mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                print(f"    [{i}] {name} - {mem.total / (1024**3):.1f} GB")
            pynvml.nvmlShutdown()
        except Exception as e:
            print(f"  nvml init/query failed: {type(e).__name__}: {e}")
    except ImportError as e:
        print(f"  pynvml NOT installed ({e})")
        print(f"  -> install with: pip install pynvml")
    except Exception as e:
        print(f"  pynvml failed unexpectedly: {type(e).__name__}: {e}")


def _probe_nvidia_smi() -> None:
    _section("2. nvidia-smi probe (subprocess)")
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            encoding="utf-8", errors="replace",
        )
        print(f"  exit code: {result.returncode}")
        print(f"  stdout: {result.stdout.strip()!r}")
        if result.stderr:
            print(f"  stderr: {result.stderr.strip()!r}")
    except FileNotFoundError:
        print("  nvidia-smi NOT in PATH")
        print("  PATH:", os.environ.get("PATH", "")[:300] + "...")
    except subprocess.TimeoutExpired:
        print("  nvidia-smi TIMED OUT (>5s)")
    except Exception as e:
        print(f"  nvidia-smi failed: {type(e).__name__}: {e}")


def _probe_wmic() -> None:
    _section("3. wmic probe (Windows fallback)")
    if sys.platform != "win32":
        print("  skipped — not Windows")
        return
    try:
        result = subprocess.run(
            ["wmic", "path", "win32_VideoController",
             "get", "name,AdapterRAM", "/format:csv"],
            capture_output=True, text=True, timeout=5,
            encoding="utf-8", errors="replace",
        )
        print(f"  exit code: {result.returncode}")
        print(f"  stdout (first 400 chars): {(result.stdout or '')[:400]!r}")
    except FileNotFoundError:
        print("  wmic NOT in PATH (Windows 11 24H2+ removes it)")
    except Exception as e:
        print(f"  wmic failed: {type(e).__name__}: {e}")


def _probe_inspector() -> dict:
    _section("4. hardware_inspector._get_gpu() in-process")
    os.environ["JAMES_HW_DEBUG"] = "1"
    from tools.system.hardware_inspector import _get_gpu
    result = _get_gpu()
    print()
    print(f"  RESULT:")
    print(f"    name:    {result.get('name')!r}")
    print(f"    vram_gb: {result.get('vram_gb')}")
    print(f"    found:   {result.get('found')}")
    print(f"  debug trail:")
    for line in result.get("debug", []):
        print(f"    - {line}")
    return result


def _probe_live_endpoint() -> dict | None:
    _section("5. Live /hardware/ endpoint (requires server running)")

    # Resolve api_key from .env or environment.
    api_key = os.environ.get("JAMES_API_KEY", "").strip()
    if not api_key:
        env_path = ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8-sig").splitlines():
                if line.startswith("JAMES_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if not api_key:
        print("  JAMES_API_KEY missing; cannot hit endpoint. Skipping.")
        return None

    try:
        import requests
    except ImportError:
        print("  requests not installed; cannot hit endpoint. Skipping.")
        return None

    try:
        r = requests.get(
            f"http://127.0.0.1:8000/hardware/",
            params={"api_key": api_key},
            timeout=5,
        )
        print(f"  HTTP {r.status_code}")
        if r.status_code != 200:
            print(f"  body: {r.text[:300]!r}")
            return None
        data = r.json()
        gpu = (data.get("specs") or {}).get("gpu") or {}
        print(f"  endpoint gpu.name:    {gpu.get('name')!r}")
        print(f"  endpoint gpu.vram_gb: {gpu.get('vram_gb')}")
        print(f"  endpoint gpu.found:   {gpu.get('found')}")
        print(f"  endpoint gpu.level:   {gpu.get('level')}")
        return gpu
    except requests.ConnectionError:
        print("  server NOT running at http://127.0.0.1:8000 — start it first.")
    except Exception as e:
        print(f"  endpoint call failed: {type(e).__name__}: {e}")
    return None


def main() -> int:
    _section("Environment")
    print(f"  python: {sys.executable}")
    print(f"  cwd:    {os.getcwd()}")
    print(f"  ROOT:   {ROOT}")
    print(f"  sys.path[0:3]: {sys.path[0:3]}")

    _probe_pynvml()
    _probe_nvidia_smi()
    _probe_wmic()
    in_proc = _probe_inspector()
    live    = _probe_live_endpoint()

    _section("Verdict")
    if not in_proc.get("found"):
        print("  ❌ GPU NOT detected at module level.")
        print("  ALL three fallbacks failed in this Python interpreter's env.")
        print("  Action: install pynvml (`pip install pynvml`) OR ensure")
        print("          nvidia-smi is reachable from this interpreter's PATH.")
        return 1

    print(f"  ✅ In-process: {in_proc['name']} {in_proc['vram_gb']}GB")
    if live is None:
        print("  (Live endpoint check skipped — see section 5)")
        return 0

    if live.get("name") == in_proc["name"] and live.get("found"):
        print(f"  ✅ Live endpoint matches: {live['name']} {live.get('vram_gb')}GB")
        return 0

    print(f"  ⚠️  Live endpoint disagrees:")
    print(f"      in-process: name={in_proc['name']!r} found={in_proc['found']}")
    print(f"      live:       name={live.get('name')!r} found={live.get('found')}")
    print()
    print("  This means the running server is using STALE code.")
    print("  Action: stop server (Ctrl+C) and run `python server_llmwiki.py`")
    print("          again. The reload=True flag should pick up changes,")
    print("          but a hard restart is the surest fix.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
