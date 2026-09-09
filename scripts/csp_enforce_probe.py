"""Load each served page under an ENFORCED CSP and count violations.

Run it before flipping ``JAMES_CSP_MODE`` to ``enforce``:

    pip install playwright && playwright install chromium
    python scripts/csp_enforce_probe.py

Exits non-zero on any style-src violation, and prints violations of the
other directives too (they do not fail the run -- they are the operator's
call, not this script's).

No server is started. Playwright fulfils every request from disk against
a synthetic origin, so `'self'` means something and the CSP header can be
attached -- the same measurement #1095 made with a dedicated enforce
server, without one running.

Limit, stated plainly: there is no backend here, so the admin views that
render from API data never draw. This proves the page shells and the JS
that runs on load are clean; the dynamic views are covered by the
computed-style pair comparisons and the source-level guard instead.
"""
import mimetypes
import pathlib
import sys

from playwright.sync_api import sync_playwright

REPO = pathlib.Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend"
ORIGIN = "http://james.local"
PAGES = ["index.html", "admin.html", "graph.html", "workspace.html", "intro.html"]

# Built from the app's own directive table rather than a copy of it, so
# the probe cannot drift into testing a policy the server never sends.
sys.path.insert(0, str(REPO))
from core.security.headers import CSP_DIRECTIVES_DEFAULT  # noqa: E402

CSP = "; ".join(f"{k} {v}" for k, v in CSP_DIRECTIVES_DEFAULT.items())


def handler(route, request):
    url = request.url
    if not url.startswith(ORIGIN):
        route.fulfill(status=204, body="")
        return
    rel = url[len(ORIGIN):].split("?")[0].lstrip("/")
    if rel == "":
        rel = "index.html"
    target = FRONTEND / rel
    if not target.is_file():
        # API calls and anything else: an empty JSON body, so page JS
        # takes its error path rather than hanging.
        route.fulfill(status=200, content_type="application/json", body="{}")
        return
    ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    headers = {"Content-Type": ctype}
    if target.suffix == ".html":
        headers["Content-Security-Policy"] = CSP
    route.fulfill(status=200, headers=headers, body=target.read_bytes())


total = 0
with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for name in PAGES:
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        violations = []
        page.expose_function("__cspViolation", lambda d: violations.append(d))
        page.add_init_script(
            "document.addEventListener('securitypolicyviolation', e => {"
            "  window.__cspViolation({directive: e.effectiveDirective,"
            "    blocked: e.blockedURI, sample: (e.sample||'').slice(0,80),"
            "    src: (e.sourceFile||'').split('/').pop(),"
            "    line: e.lineNumber});"
            "});")
        page.route("**/*", handler)
        page.goto(ORIGIN + "/" + name, wait_until="networkidle")
        page.wait_for_timeout(1200)
        style = [v for v in violations if v["directive"] == "style-src-attr"
                 or v["directive"] == "style-src-elem"
                 or v["directive"] == "style-src"]
        other = [v for v in violations if v not in style]
        total += len(style)
        print("=" * 62)
        print(f"{name}: style violations {len(style)}, other {len(other)}")
        for v in style[:10]:
            print("   STYLE", v)
        for v in other[:6]:
            print("   other", v)
        page.close()
    browser.close()

print("=" * 62)
print("TOTAL style-src violations under enforce:", total)
sys.exit(1 if total else 0)
