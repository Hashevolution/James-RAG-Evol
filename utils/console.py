"""Console encoding hardening for Windows scripts (Issue #2).

Several admin scripts (`tools/admin/wiki_reset.py`,
`tools/admin/seed_data.py`, `tools/admin/upload_simulator.py`,
`scripts/reset_for_production.py`) print Unicode box-drawing
characters (``═``, ``─``, ``│`` …) for visual section dividers. On a
default Windows console (cp949 in Korean Windows), these chars raise

    UnicodeEncodeError: 'cp949' codec can't encode character '═' …

before the script can do anything useful. The workaround used so far
has been to wrap each invocation in `PYTHONIOENCODING=utf-8`, which
forces operators to remember it every time.

This helper makes the encoding switch script-internal: each affected
script calls `ensure_utf8_console()` at the top, so a plain
`python tools/admin/wiki_reset.py --dry-run` works regardless of the
host shell's default encoding.

The reconfigure path (Python 3.7+) is preferred. If `reconfigure`
isn't available or the streams aren't TextIOWrappers (rare; some
embedded environments), it silently falls through — never raises.
"""
from __future__ import annotations

import sys


def ensure_utf8_console() -> None:
    """Reconfigure stdout/stderr to UTF-8 on Windows. No-op elsewhere
    or when reconfiguration isn't supported."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            # Some test runners replace stdout with a non-TextIOWrapper.
            # Box-drawing prints will still raise there, but we don't want
            # to make matters worse — leave whatever the runner installed.
            continue
