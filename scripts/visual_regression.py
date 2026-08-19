"""Visual-regression harness — render every JAMES page in a headless
browser, capture console errors + a screenshot, and (when a baseline
exists) pixel-diff against it.

Why this exists
---------------
The 2026-06-22 UI cycle shipped ~14 PRs (de-emoji, intro front door,
graph hub) that were verified only at the source level (node --check,
tag-balance, emoji counts) — never visually. This harness closes that
gap: it loads each page in real Chromium and flags (a) JS console errors
and (b) pixel drift vs an approved baseline. Run it before/after a UI
change to catch blank pages, broken layouts, and runtime errors that
source-level checks miss.

Heavy dependency, opt-in (matches the DiffusionGemma / cloud-backend
pattern). Activate once:

    pip install playwright pillow
    playwright install chromium

Then, with the server running (``python server_llmwiki.py``):

    # capture the approved baseline (first time / after an intended change)
    python scripts/visual_regression.py --update-baseline

    # check current render against the baseline
    python scripts/visual_regression.py

    # authed views (admin/graph/workspace) need a JWT — inject one:
    python scripts/visual_regression.py --token "<jwt>" --api-key "<key>"

Output: reports/visual/<name>.png (current) +
reports/visual/baseline/<name>.png (approved) + a per-page report
(console errors, diff %). Exit non-zero on any console error or a diff
above --threshold (default 1.0%).

Console errors and a diff over threshold are the gate. Screenshots are
committed under reports/visual/baseline/ as the reference; the current
captures are gitignored.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "reports" / "visual"
BASELINE_DIR = OUT_DIR / "baseline"

# (name, path) — path may carry a #hash to land on a hub tab. Authed
# pages render a login modal without --token; that is still a valid
# "did it render without error" smoke.
PAGES = [
    ("intro",          "/"),
    ("chat",           "/chat"),
    ("admin",          "/admin"),
    ("graph",          "/admin/graph"),
    ("graph-flow",     "/admin/graph#flow"),
    ("graph-rollback", "/admin/graph#rollback"),
    ("workspace",      "/workspace"),
]

# JS console messages that are benign in this app and must NOT fail the
# render smoke (network 401s on authed endpoints when unauthenticated,
# the pynvml deprecation noise, favicon, etc.).
CONSOLE_IGNORE = (
    "favicon", "401", "Failed to load resource",
    "ERR_", "net::", "the server responded with a status",
    # benign in report-only CSP mode (the directive is simply ignored,
    # not an error in the app) — emitted on every page by the browser.
    "upgrade-insecure-requests",
)


def _have_playwright() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


def _diff_ratio(a: Path, b: Path) -> float:
    """Fraction of differing pixels (0.0–1.0) via Pillow. Returns 1.0 if
    sizes differ or Pillow is unavailable (treated as a full mismatch)."""
    try:
        from PIL import Image, ImageChops
    except Exception:
        return 1.0
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if ia.size != ib.size:
        return 1.0
    diff = ImageChops.difference(ia, ib)
    bbox = diff.getbbox()
    if not bbox:
        return 0.0
    # count non-zero pixels
    hist = diff.convert("L").point(lambda p: 255 if p > 16 else 0).histogram()
    changed = hist[255] if len(hist) > 255 else 0
    total = ia.size[0] * ia.size[1]
    return (changed / total) if total else 1.0


def run(base_url: str, update_baseline: bool, threshold: float,
        token: str = "", api_key: str = "") -> int:
    from playwright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)

    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Emulate prefers-reduced-motion so scroll-reveal / entrance
        # animations settle instantly → deterministic screenshots (an
        # animated page must not make the diff timing-dependent).
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  reduced_motion="reduce")
        if token:
            # seed auth before any page script runs
            ctx.add_init_script(
                f"try{{localStorage.setItem('james_token',{token!r});"
                f"localStorage.setItem('james_api_key',{api_key!r});}}catch(e){{}}"
            )
        for name, path in PAGES:
            page = ctx.new_page()
            errors = []
            page.on("console", lambda m: (
                m.type == "error"
                and not any(s in m.text for s in CONSOLE_IGNORE)
                and errors.append(m.text)
            ))
            page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
            try:
                page.goto(base_url + path, wait_until="networkidle", timeout=20000)
            except Exception:
                page.wait_for_timeout(1500)  # networkidle may not settle (polling)
            page.wait_for_timeout(800)
            cur = OUT_DIR / f"{name}.png"
            page.screenshot(path=str(cur), full_page=True)
            page.close()

            note = ""
            if update_baseline:
                (BASELINE_DIR / f"{name}.png").write_bytes(cur.read_bytes())
                note = "baseline updated"
            else:
                base = BASELINE_DIR / f"{name}.png"
                if not base.exists():
                    note = "NO BASELINE (run --update-baseline)"
                else:
                    ratio = _diff_ratio(cur, base)
                    note = f"diff={ratio*100:.2f}%"
                    if ratio * 100 > threshold:
                        failures.append(f"{name}: diff {ratio*100:.2f}% > {threshold}%")
            if errors:
                failures.append(f"{name}: {len(errors)} console error(s): {errors[:2]}")
            print(f"  {name:<16} {path:<24} {note}"
                  + (f"  | {len(errors)} err" if errors else ""))
        browser.close()

    print()
    if failures:
        print(f"[visual] FAIL — {len(failures)} issue(s):")
        for f in failures:
            print("   " + f)
        return 1
    print("[visual] OK — no console errors, no diffs over threshold.")
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="JAMES visual-regression harness")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--update-baseline", action="store_true",
                    help="capture the current render as the approved baseline")
    ap.add_argument("--threshold", type=float, default=1.0,
                    help="max %% differing pixels before a page fails")
    ap.add_argument("--token", default="", help="JWT for authed views")
    ap.add_argument("--api-key", default="", help="api_key for authed views")
    args = ap.parse_args(argv)

    if not _have_playwright():
        print("[visual] playwright not installed. Activate the harness:\n"
              "    pip install playwright pillow\n"
              "    playwright install chromium")
        return 2
    print(f"[visual] base={args.base_url}  pages={len(PAGES)}  "
          f"{'(updating baseline)' if args.update_baseline else ''}")
    return run(args.base_url, args.update_baseline, args.threshold,
               args.token, args.api_key)


if __name__ == "__main__":
    raise SystemExit(main())
