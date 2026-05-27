"""v0.4 Sprint 5 PR-T1.B — operator runner for the T1 expiration cascade.

Walks the wiki, flips ``mutation_type="expired"`` + ``status.active=False``
on every edge whose **all** active sources have reached
``valid_until``. **Does not delete** — CASCADE is a separate path
(Layer 3 ``cascade_remove``). Manual immunity (``edge.manual_immune``)
respected.

Modes
-----

    python scripts/run_expiration_cascade.py                # dry-run
    python scripts/run_expiration_cascade.py --apply        # write
    python scripts/run_expiration_cascade.py --root other_wiki

Idempotent — re-running after an apply is a no-op (every affected
edge already has ``status.active=False`` + the cascade's
"already-inactive" guard skips it).

Rollback
--------

The cascade is reversible per-edge: clear ``status.active`` back to
``True`` + reset ``mutation_type`` to ``"active"`` in the affected
entity file. There is no batch rollback flag — by design, expiration
is a forward-only operational hook (an edge "un-expiring" would
imply its source was wrong, which is a manual investigation, not a
script).

For a full rollback after ``--apply`` (e.g., the wrong wiki was
targeted), use ``git checkout HEAD -- wiki/`` to restore the
pre-cascade state. PR-T1.A migration writes a ``wiki.pre-v04-migration/``
snapshot; PR-T1.B intentionally does not snapshot again because
its mutation surface is small (two fields per edge) and a git diff
shows the operator exactly what changed.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Project root on sys.path so `core.*` import works.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from utils.console import ensure_utf8_console  # noqa: E402
    ensure_utf8_console()
except Exception:
    pass

from core.lifecycle.clock import now as clock_now  # noqa: E402
from core.lifecycle.expiration_cascade import expiration_cascade  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description="v0.4 Sprint 5 PR-T1.B — T1 expiration cascade.",
    )
    ap.add_argument(
        "--root",
        default="wiki",
        help="wiki root directory (default: wiki)",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Actually write the cascaded mutations to disk. Without "
            "this flag the script is dry-run — stats reported, "
            "nothing written."
        ),
    )
    ap.add_argument(
        "--time",
        default=None,
        help=(
            "ISO 8601 timestamp to use as current_time (test/replay "
            "use). Default: core.lifecycle.clock.now() (UTC). "
            "Example: --time 2026-12-31T23:59:59+00:00"
        ),
    )
    args = ap.parse_args()

    if args.time is not None:
        try:
            current_time = datetime.fromisoformat(
                args.time.replace("Z", "+00:00")
            )
        except ValueError as e:
            print(f"[EXPIRE] --time not parseable: {e}")
            return 2
    else:
        current_time = clock_now()

    root = Path(args.root)
    if not root.exists():
        print(f"[EXPIRE] wiki root not found: {root}")
        return 2

    mode_tag = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== expiration cascade ({mode_tag}) ===")
    print(f"  wiki root:    {root.resolve()}")
    print(f"  current_time: {current_time.isoformat()}")
    print()

    stats = expiration_cascade(
        root,
        current_time=current_time,
        dry_run=not args.apply,
    )

    print("=== Stats ===")
    for k, v in stats.items():
        print(f"  {k:<22s}: {v}")

    if stats.get("errors"):
        return 1
    if not args.apply and stats.get("files_mutated", 0) > 0:
        print()
        print(
            f"[EXPIRE] dry-run found {stats['files_mutated']} files "
            f"to mutate ({stats['edges_expired']} edges). "
            f"Re-run with --apply to write."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
