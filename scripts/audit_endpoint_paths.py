"""Server-split regression gate — endpoint URL byte-identical invariant.

Per docs/design/v0.4.x-server-split.md §2.1 + §6.1.

Compares the set of (method, path) tuples registered on the current FastAPI
app against a baseline captured from a base branch (default: main). If the
sets differ by even one entry, exit-code 1 and print +added / -removed.

This gate runs on every server-split PR (A → H) so the URL surface stays
byte-identical through the cycle. It does NOT care about handler internals
— only the routing table.

Usage
-----
  python scripts/audit_endpoint_paths.py                # diff vs origin/main
  python scripts/audit_endpoint_paths.py main           # diff vs main
  python scripts/audit_endpoint_paths.py <sha>          # diff vs commit
  python scripts/audit_endpoint_paths.py --baseline-file routes.json
  python scripts/audit_endpoint_paths.py --capture routes.json

Exit codes
----------
  0 — endpoint sets identical
  1 — diff present (printed)
  2 — wrapper error (git missing, import failed, etc.)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]

# FastAPI auto-registers these regardless of source. Excluded from the
# invariant comparison so refactors that don't touch app.openapi config
# don't show false-positive churn.
_FASTAPI_AUTO_PATHS = frozenset({
    "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json",
})


def _collect_current_endpoints() -> set[tuple[str, str]]:
    """Import server_llmwiki and read its routing table.

    Returns the set of (method, path) tuples for routes that surface a
    real HTTP method (skips Mount / WebSocket / etc).
    """
    # Make sure we import from the repo, not a stale installed package.
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import server_llmwiki  # type: ignore
    except Exception as exc:  # pragma: no cover — surfacing import errors
        print(f"FAIL: could not import server_llmwiki — {exc}", file=sys.stderr)
        sys.exit(2)

    pairs: set[tuple[str, str]] = set()
    for route in server_llmwiki.app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            # Mount (StaticFiles), Starlette WebSocketRoute, etc. — skip.
            continue
        if path in _FASTAPI_AUTO_PATHS:
            continue
        for m in methods:
            # `route.methods` is the explicit method set on the route
            # (e.g. {"GET"}). HEAD is handled by Starlette at request
            # time without a separate route entry, so don't synthesize
            # ("HEAD", path) here — keep it to what app.routes actually
            # reports, which is the same shape on both sides.
            pairs.add((m.upper(), path))
    return pairs


def _collect_baseline_from_git(ref: str) -> set[tuple[str, str]]:
    """Run this script under a worktree of `ref` and read its output.

    The cleanest way to compare two snapshots of the routing table is to
    actually IMPORT each version's server_llmwiki and read app.routes. We
    do that by:
      1. `git worktree add` a temp dir at the requested ref
      2. running this script there with --capture <tmp>.json
      3. parsing the captured json
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        wt_dir = Path(tmp) / "wt"
        capture_file = Path(tmp) / "routes.json"
        # Create worktree
        try:
            subprocess.run(
                ["git", "worktree", "add", "-f", "--detach", str(wt_dir), ref],
                cwd=REPO_ROOT, check=True, capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            print(f"FAIL: git worktree add {ref} — {exc.stderr.decode(errors='replace')}",
                  file=sys.stderr)
            sys.exit(2)
        try:
            # Run this very script from the worktree, --capture into shared file
            script = wt_dir / "scripts" / "audit_endpoint_paths.py"
            if not script.exists():
                # Baseline ref predates this script; fall back to AST scan.
                return _ast_scan_for_endpoints(wt_dir / "server_llmwiki.py")
            res = subprocess.run(
                [sys.executable, str(script), "--capture", str(capture_file)],
                cwd=wt_dir, check=False, capture_output=True,
            )
            if res.returncode != 0:
                print(f"FAIL: capture from {ref} returned {res.returncode}",
                      file=sys.stderr)
                print(res.stderr.decode(errors="replace"), file=sys.stderr)
                sys.exit(2)
            data = json.loads(capture_file.read_text(encoding="utf-8"))
            return {tuple(pair) for pair in data["endpoints"]}
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "-f", str(wt_dir)],
                cwd=REPO_ROOT, check=False, capture_output=True,
            )


def _ast_scan_for_endpoints(server_path: Path) -> set[tuple[str, str]]:
    """Fallback: parse @app.<method>("path", ...) decorators via AST.

    Used when the baseline ref predates this script (no capture available).
    Imperfect for routes registered via include_router after split, but
    pre-split server_llmwiki.py has every route inline as @app.* — so this
    gives a correct baseline for cycle-start comparisons.
    """
    import ast

    pairs: set[tuple[str, str]] = set()
    try:
        tree = ast.parse(server_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"FAIL: no server_llmwiki.py at {server_path}", file=sys.stderr)
        sys.exit(2)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            func = deco.func
            # Match @app.<method>(...) where method ∈ {get, post, ...}
            if (isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "app"
                and func.attr.lower() in {"get", "post", "put", "delete", "patch"}):
                if not deco.args:
                    continue
                first = deco.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    method = func.attr.upper()
                    path = first.value
                    if path in _FASTAPI_AUTO_PATHS:
                        continue
                    pairs.add((method, path))
    return pairs


def _format_diff(added: Iterable[tuple[str, str]],
                 removed: Iterable[tuple[str, str]]) -> str:
    out = []
    for method, path in sorted(added):
        out.append(f"  + {method:7s} {path}")
    for method, path in sorted(removed):
        out.append(f"  - {method:7s} {path}")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "ref", nargs="?", default="origin/main",
        help="git ref to compare against (default: origin/main)",
    )
    parser.add_argument(
        "--baseline-file", type=Path,
        help="read baseline from a previously captured JSON instead of git",
    )
    parser.add_argument(
        "--capture", type=Path,
        help="write current endpoint set to JSON and exit (no comparison)",
    )
    args = parser.parse_args()

    current = _collect_current_endpoints()

    if args.capture:
        payload = {
            "endpoints": sorted(list(p) for p in current),
            "count": len(current),
        }
        args.capture.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"captured {len(current)} endpoints → {args.capture}")
        return 0

    if args.baseline_file:
        data = json.loads(args.baseline_file.read_text(encoding="utf-8"))
        baseline = {tuple(p) for p in data["endpoints"]}
    else:
        baseline = _collect_baseline_from_git(args.ref)

    added = current - baseline
    removed = baseline - current

    if not added and not removed:
        print(f"OK: {len(current)} endpoints identical to {args.ref}")
        return 0

    print(f"FAIL: +{len(added)} -{len(removed)} (current={len(current)}, "
          f"baseline={len(baseline)})", file=sys.stderr)
    print(_format_diff(added, removed), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
